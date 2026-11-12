import json
import os
import secrets
import shlex
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, decode_token, get_jwt, get_jwt_identity, jwt_required,
)
from flask_jwt_extended.exceptions import JWTDecodeError
from flask_socketio import SocketIO, emit
from jwt.exceptions import PyJWTError
from werkzeug.security import check_password_hash

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
HISTORY_FILE = DATA_DIR / "history.json"
REVOCATIONS_FILE = DATA_DIR / "revoked.json"
KEY_FILE = DATA_DIR / "jwt.key"
MAX_MESSAGE_LENGTH = 1000
state_lock = threading.RLock()
connections = {}


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
    result = read_json(USERS_FILE, None)
    if result is None and not USERS_FILE.exists():
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(DATA_DIR.parent / 'manage_users.py'))} player1"
        raise FileNotFoundError(
            f"Credential file not found: {USERS_FILE}\n"
            f"Create an account first (choose a password of at least 12 characters):\n  {command}"
        )
    if not isinstance(result, dict) or not all(
        isinstance(name, str) and isinstance(password_hash, str)
        for name, password_hash in result.items()
    ):
        raise ValueError(f"Missing or invalid credential file: {USERS_FILE}")
    return result


def history():
    result = read_json(HISTORY_FILE, [])
    if not isinstance(result, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("user"), str)
        and isinstance(item.get("text"), str)
        for item in result
    ):
        raise ValueError(f"Invalid chat history file: {HISTORY_FILE}")
    return result


def revoked():
    result = read_json(REVOCATIONS_FILE, {})
    if not isinstance(result, dict) or not all(
        isinstance(jti, str) and isinstance(exp, int) for jti, exp in result.items()
    ):
        raise ValueError(f"Invalid token revocation file: {REVOCATIONS_FILE}")
    return result


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
        return payload["jti"] in revoked() or payload["sub"] not in users()


@app.post("/api/login")
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(status="error", message="Expected a JSON object."), 400
    username, password = data.get("username"), data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(status="error", message="Enter a username and password."), 400
    if len(username) > 100 or len(password) > 1024:
        return jsonify(status="error", message="Invalid username or password."), 401
    username = username.strip()
    with state_lock:
        password_hash = users().get(username)
    if not password_hash or not check_password_hash(password_hash, password):
        return jsonify(status="error", message="Invalid username or password."), 401
    return jsonify(status="success", username=username, token=create_access_token(identity=username))


@app.get("/api/verify")
@jwt_required()
def verify():
    with state_lock:
        messages = history()[-20:]
    return jsonify(status="valid", username=get_jwt_identity(), history=messages)


@app.post("/api/logout")
@jwt_required()
def logout():
    payload = get_jwt()
    with state_lock:
        entries = {jti: exp for jti, exp in revoked().items() if exp > time.time()}
        entries[payload["jti"]] = payload["exp"]
        write_json(REVOCATIONS_FILE, entries)
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
    if not isinstance(auth, dict) or not isinstance(auth.get("token"), str):
        return False
    try:
        payload = decode_token(auth["token"])
    except (PyJWTError, JWTDecodeError, ValueError, TypeError):
        return False
    if payload.get("type") != "access":
        return False
    with state_lock:
        if payload["jti"] in revoked() or payload["sub"] not in users():
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
                or identity["jti"] in revoked() or identity["user"] not in users()):
            return {"status": "error", "message": "Session expired. Log in again."}
        emit("chat_history", history()[-20:], to=request.sid)
    return {"status": "success"}


@socketio.on("send_message")
def handle_message(data):
    if not isinstance(data, dict):
        return {"status": "error", "message": "Expected a message object."}
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return {"status": "error", "message": "Message must not be empty."}
    text = text.strip()
    if len(text) > MAX_MESSAGE_LENGTH:
        return {"status": "error", "message": "Message is too long."}
    with state_lock:
        identity = connections.get(request.sid)
        if not identity or identity["exp"] <= time.time() or identity["jti"] in revoked():
            return {"status": "error", "message": "Session expired. Log in again."}
        if identity["user"] not in users():
            return {"status": "error", "message": "Account no longer exists."}
        message = {"user": identity["user"], "text": text}
        write_json(HISTORY_FILE, history() + [message])
        revoked_tokens = revoked()
        current_users = users()
        for sid, recipient in connections.items():
            if (recipient["exp"] > time.time() and recipient["jti"] not in revoked_tokens
                    and recipient["user"] in current_users):
                emit("receive_message", message, to=sid)
    return {"status": "success"}


if __name__ == "__main__":
    try:
        users()
    except FileNotFoundError as error:
        raise SystemExit(str(error)) from error
    history()
    revoked()
    socketio.run(
        app, host="127.0.0.1", port=5000, debug=False,
        allow_unsafe_werkzeug=True,
    )
