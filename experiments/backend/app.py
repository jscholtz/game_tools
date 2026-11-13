import json
import os
import secrets
import shlex
import signal
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

import mongomock
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, decode_token, get_jwt, get_jwt_identity, jwt_required,
)
from flask_jwt_extended.exceptions import JWTDecodeError
from flask_socketio import SocketIO, emit
from jwt.exceptions import PyJWTError
from pydantic import ValidationError
from werkzeug.security import check_password_hash

from models import (
    MAX_NOTE_LENGTH, MIN_PASSWORD_LENGTH, LoginRequest, MessageRequest, NoteRequest,
    PrivateMessage, Snapshot, SocketAuth,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
HISTORY_FILE = DATA_DIR / "history.json"
REVOCATIONS_FILE = DATA_DIR / "revoked.json"
SNAPSHOT_FILE = DATA_DIR / "mongo-snapshot.json"
KEY_FILE = DATA_DIR / "jwt.key"
state_lock = threading.RLock()
connections = {}
database = mongomock.MongoClient()["split_chat"]


def read_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path, value):
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=DATA_DIR, delete=False
        ) as file:
            temp_path = Path(file.name)
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def signing_key():
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        descriptor = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if not key:
            raise ValueError(f"JWT signing key is empty: {KEY_FILE}")
        return key
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        key = secrets.token_urlsafe(64)
        file.write(key)
    return key


def users():
    return {
        entry["_id"]: {"password_hash": entry["password_hash"], "role": entry["role"]}
        for entry in database.users.find()
    }


def user_exists(username):
    return database.users.find_one({"_id": username}, {"_id": 1}) is not None


def load_database():
    if SNAPSHOT_FILE.exists():
        raw_snapshot = read_json(SNAPSHOT_FILE, None)
        if isinstance(raw_snapshot, dict) and "users" not in raw_snapshot:
            raw_snapshot["users"] = read_json(USERS_FILE, {})
    else:
        raw_snapshot = {
            "history": read_json(HISTORY_FILE, []),
            "revoked": read_json(REVOCATIONS_FILE, {}),
            "users": read_json(USERS_FILE, {}),
        }
    try:
        snapshot = Snapshot.model_validate(raw_snapshot)
    except ValidationError:
        raise ValueError(f"Invalid database snapshot or legacy data: {SNAPSHOT_FILE}") from None

    for index, message in enumerate(snapshot.history):
        database.messages.insert_one({"_id": index, "message": message.model_dump()})
    for jti, exp in snapshot.revoked.items():
        database.revocations.insert_one({"_id": jti, "exp": exp})
    for username, account in snapshot.users.items():
        database.users.insert_one({"_id": username, **account.model_dump()})
    for username, content in snapshot.notes.items():
        database.notes.insert_one({"_id": username, "content": content})
    save_database()


def save_database():
    messages = [
        message["message"]
        for message in database.messages.find().sort("_id", 1)
    ]
    revocations = {entry["_id"]: entry["exp"] for entry in database.revocations.find()}
    notes = {entry["_id"]: entry["content"] for entry in database.notes.find()}
    snapshot = Snapshot.model_validate(
        {"history": messages, "revoked": revocations, "users": users(), "notes": notes}
    )
    write_json(SNAPSHOT_FILE, snapshot.model_dump())


def chat_data(username):
    account = database.users.find_one({"_id": username})
    if account is None:
        raise ValueError("Account no longer exists.")
    if account["role"] == "dm":
        if username != "dm":
            raise ValueError("Private chat is available only to the dm account.")
        players = sorted(user["_id"] for user in database.users.find({"role": "player"}))
    else:
        players = [username]
    conversations = {}
    for player in players:
        query = {"$or": [
            {"message.sender": player, "message.recipient": "dm"},
            {"message.sender": "dm", "message.recipient": player},
        ]}
        conversations[player] = [
            item["message"]
            for item in reversed(list(database.messages.find(query).sort("_id", -1).limit(20)))
        ]
    return conversations


def is_revoked(jti):
    return database.revocations.find_one({"_id": jti}) is not None


app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = signing_key()
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=8)
jwt = JWTManager(app)
allowed_origins = ["http://127.0.0.1:8000", "http://localhost:8000"]
frontend_origin = os.environ.get("FRONTEND_ORIGIN")
if frontend_origin:
    allowed_origins.append(frontend_origin.rstrip("/"))

CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
socketio = SocketIO(
    app, async_mode="threading", cors_allowed_origins=allowed_origins,
    max_http_buffer_size=8192,
)


@jwt.token_in_blocklist_loader
def token_revoked(_header, payload):
    with state_lock:
        return is_revoked(payload["jti"]) or not user_exists(payload["sub"])


@app.post("/api/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="Expected a JSON object."), 400
    try:
        login_request = LoginRequest.model_validate(data)
    except ValidationError as error:
        errors = error.errors(include_input=False)
        if any(item["type"] in ("missing", "string_type") for item in errors):
            return jsonify(status="error", message="Enter a username and password."), 400
        return jsonify(status="error", message="Invalid username or password."), 401
    username = login_request.username.strip()
    with state_lock:
        account = database.users.find_one({"_id": username})
        password_hash = account["password_hash"] if account else None
    if not password_hash or not check_password_hash(password_hash, login_request.password):
        return jsonify(status="error", message="Invalid username or password."), 401
    return jsonify(
        status="success", username=username, role=account["role"],
        token=create_access_token(identity=username),
    )


@app.get("/api/verify")
@jwt_required()
def verify():
    with state_lock:
        username = get_jwt_identity()
        account = database.users.find_one({"_id": username})
        if account is None:
            return jsonify(status="error", message="Account no longer exists."), 401
    return jsonify(status="valid", username=username, role=account["role"])


@app.route("/api/notes", methods=["GET", "PUT"])
@jwt_required()
def notes():
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.users.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if account["role"] != "player":
            return jsonify(status="error", message="Notes are available only to players."), 403
        existing = database.notes.find_one({"_id": username})
        if request.method == "GET":
            return jsonify(content=existing["content"] if existing else "")
        try:
            note = NoteRequest.model_validate(request.get_json(silent=True))
        except ValidationError:
            return jsonify(
                status="error",
                message=f"Provide note text of at most {MAX_NOTE_LENGTH} characters.",
            ), 400
        database.notes.update_one(
            {"_id": username}, {"$set": {"content": note.content}}, upsert=True
        )
        try:
            save_database()
        except (OSError, ValueError, TypeError):
            if existing is None:
                database.notes.delete_one({"_id": username})
            else:
                database.notes.replace_one({"_id": username}, existing)
            raise
    return jsonify(status="success")


@app.post("/api/logout")
@jwt_required()
def logout():
    payload = get_jwt()
    with state_lock:
        existing = database.revocations.find_one({"_id": payload["jti"]})
        if existing is None:
            database.revocations.insert_one({"_id": payload["jti"], "exp": payload["exp"]})
        try:
            save_database()
        except (OSError, ValueError, TypeError):
            if existing is None:
                database.revocations.delete_one({"_id": payload["jti"]})
            raise
        sockets = [sid for sid, info in connections.items() if info["jti"] == payload["jti"]]
    for sid in sockets:
        socketio.server.disconnect(sid, namespace="/")
    return jsonify(status="success")


def disconnect_at_expiry(sid, expires):
    socketio.sleep(max(0, expires - time.time()))
    with state_lock:
        active = sid in connections
    if active:
        socketio.server.disconnect(sid, namespace="/")


@socketio.on("connect")
def connect(auth):
    try:
        socket_auth = SocketAuth.model_validate(auth)
        payload = decode_token(socket_auth.token)
    except (ValidationError, PyJWTError, JWTDecodeError, ValueError, TypeError):
        return False
    if payload.get("type") != "access":
        return False
    with state_lock:
        if is_revoked(payload["jti"]) or not user_exists(payload["sub"]):
            return False
        connections[request.sid] = {
            "user": payload["sub"], "jti": payload["jti"], "exp": payload["exp"],
        }
    socketio.start_background_task(disconnect_at_expiry, request.sid, payload["exp"])


@socketio.on("disconnect")
def disconnect(_reason=None):
    with state_lock:
        connections.pop(request.sid, None)


@socketio.on("get_history")
def get_history():
    with state_lock:
        identity = connections.get(request.sid)
        if (not identity or identity["exp"] <= time.time()
                or is_revoked(identity["jti"]) or not user_exists(identity["user"])):
            return {"status": "error", "message": "Session expired. Log in again."}
        try:
            conversations = chat_data(identity["user"])
        except ValueError as error:
            return {"status": "error", "message": str(error)}
        emit("chat_history", conversations, to=request.sid)
    return {"status": "success"}


@socketio.on("send_message")
def handle_message(data):
    try:
        message_request = MessageRequest.model_validate(data)
    except ValidationError as error:
        errors = error.errors(include_input=False)
        if any(item["loc"] == ("recipient",) for item in errors):
            return {"status": "error", "message": "Invalid recipient."}
        error_types = {item["type"] for item in errors}
        if "model_type" in error_types:
            return {"status": "error", "message": "Expected a message object."}
        if error_types & {"missing", "string_type", "string_too_short"}:
            return {"status": "error", "message": "Message must not be empty."}
        return {"status": "error", "message": "Message is too long."}
    with state_lock:
        identity = connections.get(request.sid)
        if not identity or identity["exp"] <= time.time() or is_revoked(identity["jti"]):
            return {"status": "error", "message": "Session expired. Log in again."}
        account = database.users.find_one({"_id": identity["user"]})
        if not account:
            return {"status": "error", "message": "Account no longer exists."}
        if account["role"] == "player":
            if message_request.recipient not in (None, "dm"):
                return {"status": "error", "message": "Players can only message the DM."}
            target = "dm"
            if database.users.find_one({"_id": target, "role": "dm"}) is None:
                return {"status": "error", "message": "DM account is unavailable."}
        else:
            if identity["user"] != "dm":
                return {"status": "error", "message": "Private chat is available only to the dm account."}
            target = message_request.recipient
            if not target or database.users.find_one({"_id": target, "role": "player"}) is None:
                return {"status": "error", "message": "Select a valid player."}
        message = PrivateMessage(
            sender=identity["user"], recipient=target, text=message_request.text
        ).model_dump()
        latest = database.messages.find_one(sort=[("_id", -1)])
        message_id = latest["_id"] + 1 if latest else 0
        database.messages.insert_one({"_id": message_id, "message": message})
        try:
            save_database()
        except (OSError, ValueError, TypeError):
            database.messages.delete_one({"_id": message_id})
            raise
        for sid, recipient in connections.items():
            if (recipient["exp"] > time.time() and not is_revoked(recipient["jti"])
                    and recipient["user"] in (message["sender"], message["recipient"])
                    and user_exists(recipient["user"])):
                emit("receive_message", message, to=sid)
    return {"status": "success"}


if __name__ == "__main__":
    load_database()
    if not users():
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(DATA_DIR.parent / 'manage_users.py'))} player1"
        raise SystemExit(
            f"No accounts found. Create an account first "
            f"(password: at least {MIN_PASSWORD_LENGTH} characters):\n  {command}"
        )

    def handle_sigterm(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        socketio.run(
            app, host="127.0.0.1", port=5000, debug=False,
            allow_unsafe_werkzeug=True,
        )
    finally:
        with state_lock:
            save_database()
