import base64
import binascii
import io
import json
import os
import secrets
import shlex
import signal
import sys
import tempfile
import threading
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, decode_token, get_jwt, get_jwt_identity, jwt_required,
)
from flask_jwt_extended.exceptions import JWTDecodeError
from flask_socketio import SocketIO, emit
from jwt.exceptions import PyJWTError
from pydantic import ValidationError
from PIL import Image, UnidentifiedImageError
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app_support import bestiary
from app_support.mongo_timing import MongoTimingListener, configure_mongo_logging
from app_support.models import (
    MAX_IMAGE_BYTES, MAX_NOTE_LENGTH, MIN_PASSWORD_LENGTH, BoardImage, BoardNote, BoardNoteRequest, BoardNoteUpdate,
    CharacterData, ChatReadRequest, InitiativeState, LocalCreature, LocalCreatureInput, LocalCreatureUpdate,
    LoginRequest, MessageRequest, NoteRequest, NoteUpdate, PrivateMessage,
    Snapshot, SocketAuth,
)
from tab_views.statblock_renderer import render_creature

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
HISTORY_FILE = DATA_DIR / "history.json"
REVOCATIONS_FILE = DATA_DIR / "revoked.json"
SNAPSHOT_FILE = DATA_DIR / "mongo-snapshot.json"
KEY_FILE = DATA_DIR / "jwt.key"
state_lock = threading.RLock()
connections = {}
MONGODB_DATABASE = os.environ.get("EXPERIMENT_MONGODB_DATABASE", "game_helper_dev").strip()
MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
configure_mongo_logging()
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not configured.")
if not MONGODB_DATABASE:
    raise RuntimeError("EXPERIMENT_MONGODB_DATABASE must not be empty.")
mongo_client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=10_000,
    connectTimeoutMS=10_000,
    event_listeners=[MongoTimingListener()],
)
database = mongo_client[MONGODB_DATABASE]
SESSION_METADATA_ID = "__experiment_session_metadata__"


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
        for entry in database.logins.find({"password_hash": {"$exists": True}})
    }


def user_exists(username):
    return database.logins.find_one({"_id": username}, {"_id": 1}) is not None


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

    metadata = database.logins.find_one({"_id": SESSION_METADATA_ID})
    if metadata is not None:
        return

    collections = (
        database.boards, database.characters, database.chats, database.custom_bestiary,
        database.initiative, database.logins, database.private_notes,
    )
    if any(collection.estimated_document_count() for collection in collections):
        raise RuntimeError(
            f"{MONGODB_DATABASE} contains experiment data but no migration marker; refusing to overwrite it."
        )

    documents = {
        "chats": [
            {"_id": index, "message": message.model_dump()}
            for index, message in enumerate(snapshot.history)
        ],
        "logins": [
            {
                "_id": username,
                **account.model_dump(),
                "chat_read": snapshot.chat_read.get(username, -1),
            }
            for username, account in snapshot.users.items()
        ],
        "private_notes": [
            {"_id": username, "entries": {key: note.model_dump() for key, note in notes.items()}}
            for username, notes in snapshot.notes.items()
        ],
        "boards": [
            {"_id": note_id, **note.model_dump(exclude_none=True)}
            for note_id, note in snapshot.board.items()
        ],
        "characters": [
            {"_id": username, **character.model_dump(exclude_none=True)}
            for username, character in snapshot.characters.items()
        ],
        "initiative": [{"_id": "state", **snapshot.initiative.model_dump()}],
        "custom_bestiary": [
            {"_id": creature_id, **creature.model_dump()}
            for creature_id, creature in snapshot.custom_creatures.items()
        ],
    }
    documents["logins"].append({
        "_id": SESSION_METADATA_ID,
        "revoked": snapshot.revoked,
    })
    with mongo_client.start_session() as session:
        with session.start_transaction():
            for name, entries in documents.items():
                if entries:
                    database[name].insert_many(entries, session=session)
    save_database()


def save_database():
    messages = [
        message["message"]
        for message in database.chats.find().sort("_id", 1)
    ]
    metadata = database.logins.find_one({"_id": SESSION_METADATA_ID}) or {}
    revocations = metadata.get("revoked", {})
    notes = {entry["_id"]: entry["entries"] for entry in database.private_notes.find()}
    board = {
        entry["_id"]: {key: value for key, value in entry.items() if key != "_id"}
        for entry in database.boards.find()
    }
    characters = {
        entry["_id"]: {key: value for key, value in entry.items() if key != "_id"}
        for entry in database.characters.find()
    }
    initiative = database.initiative.find_one({"_id": "state"}, {"_id": 0}) or InitiativeState().model_dump()
    chat_read = {
        entry["_id"]: entry.get("chat_read", -1)
        for entry in database.logins.find({"password_hash": {"$exists": True}})
    }
    custom_creatures = {
        entry["_id"]: {key: value for key, value in entry.items() if key != "_id"}
        for entry in database.custom_bestiary.find()
    }
    snapshot = Snapshot.model_validate(
        {"history": messages, "revoked": revocations, "users": users(), "notes": notes,
         "board": board, "characters": characters, "initiative": initiative, "chat_read": chat_read,
         "custom_creatures": custom_creatures}
    )
    write_json(SNAPSHOT_FILE, snapshot.model_dump(exclude_none=True))


def chat_data(username):
    account = database.logins.find_one({"_id": username})
    if account is None:
        raise ValueError("Account no longer exists.")
    if account["role"] == "dm":
        if username != "dm":
            raise ValueError("Private chat is available only to the dm account.")
        players = sorted(user["_id"] for user in database.logins.find({"role": "player"}))
    else:
        players = [username]
    cursor = account.get("chat_read", -1)
    conversations = {}
    for player in players:
        query = {"$or": [
            {"message.sender": player, "message.recipient": "dm"},
            {"message.sender": "dm", "message.recipient": player},
        ]}
        recent = list(database.chats.find(query).sort("_id", -1).limit(20))
        unread = database.chats.find({
            "$and": [query, {"_id": {"$gt": cursor}, "message.recipient": username}]
        })
        entries = {item["_id"]: item for item in recent}
        entries.update({item["_id"]: item for item in unread})
        conversations[player] = [
            {"id": item["_id"], **item["message"]}
            for item in sorted(entries.values(), key=lambda item: item["_id"])
        ]
    return conversations


def unread_count(username):
    account = database.logins.find_one({"_id": username}, {"chat_read": 1})
    return database.chats.count_documents({
        "_id": {"$gt": account.get("chat_read", -1) if account else -1},
        "message.recipient": username,
    })


def notify_unread(username):
    count = unread_count(username)
    for sid, connection in connections.items():
        if (connection["user"] == username and connection["exp"] > time.time()
                and not is_revoked(connection["jti"]) and user_exists(username)):
            socketio.emit("chat_unread", {"count": count}, to=sid)


def is_revoked(jti):
    return database.logins.find_one(
        {"_id": SESSION_METADATA_ID, f"revoked.{jti}": {"$exists": True}}, {"_id": 1}
    ) is not None


def initiative_player_view(state):
    visible = [actor for actor in state.tracker.combatants if actor.visible]
    return {
        "revision": state.revision,
        "tracker": {
            "combatants": [
                {"id": actor.id, "name": actor.name, "initiative": actor.initiative, "dead": actor.dead}
                for actor in visible
            ],
            "current_turn_id": state.tracker.current_turn_id
            if any(actor.id == state.tracker.current_turn_id for actor in visible) else None,
        },
    }


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
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
        account = database.logins.find_one({"_id": username})
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
        account = database.logins.find_one({"_id": username})
        if account is None:
            return jsonify(status="error", message="Account no longer exists."), 401
    return jsonify(status="valid", username=username, role=account["role"])


@app.route("/api/notes", methods=["GET", "POST"])
@app.route("/api/notes/<note_id>", methods=["PUT"])
@jwt_required()
def notes(note_id=None):
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if account["role"] != "player":
            return jsonify(status="error", message="Notes are available only to players."), 403
        existing = database.private_notes.find_one({"_id": username})
        entries = existing["entries"].copy() if existing else {}
        if request.method == "GET":
            response = jsonify(notes=[{"id": key, **note} for key, note in entries.items()])
            response.headers["Cache-Control"] = "no-store"
            return response
        try:
            model = NoteUpdate if note_id is not None else NoteRequest
            note = model.model_validate(request.get_json(silent=True))
        except ValidationError:
            return jsonify(
                status="error",
                message=f"Provide a header and note text of at most {MAX_NOTE_LENGTH} characters.",
            ), 400
        previous = entries.get(note_id) if note_id is not None else None
        if note_id is not None:
            if previous is None:
                return jsonify(status="error", message="Note not found."), 404
            if not isinstance(note, NoteUpdate) or note.revision != previous["revision"]:
                return jsonify(status="error", message="Note changed elsewhere. Reload before editing."), 409
        else:
            note_id = secrets.token_hex(16)
        entries[note_id] = {
            "header": note.header, "content": note.content,
            "revision": previous["revision"] + 1 if previous else 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        database.private_notes.replace_one(
            {"_id": username}, {"_id": username, "entries": entries}, upsert=True
        )
    return jsonify(status="success", id=note_id, **entries[note_id])


class ImageStorageError(Exception):
    pass


def image_storage_config():
    base_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    token = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_TOKEN", "").strip()
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    )
    bucket = os.environ.get("SUPABASE_IMAGE_BUCKET", "images").strip()
    if not base_url or not token or not bucket:
        raise ImageStorageError(
            "Image storage is not configured. Set SUPABASE_URL and a Supabase API key."
        )
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ImageStorageError("SUPABASE_URL must be an HTTPS URL without credentials.")
    if bucket != bucket.strip("/") or "/" in bucket or "\\" in bucket:
        raise ImageStorageError("SUPABASE_IMAGE_BUCKET must be a bucket name without slashes.")
    return base_url, token, bucket


def decode_board_image(image):
    formats = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}
    if image.data is None:
        return None
    try:
        data = base64.b64decode(image.data, validate=True)
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Image must be at most 2 MiB.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as decoded:
                if formats.get(decoded.format) != image.media_type:
                    raise ValueError("Unsupported or mismatched image format.")
                decoded.verify()
        return data
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError("Invalid or oversized image.") from error


def image_public_prefix():
    base_url, _token, bucket = image_storage_config()
    return f"{base_url}/storage/v1/object/public/{quote(bucket)}/"


def upload_image(image, namespace):
    data = decode_board_image(image)
    if data is None:
        public_prefix = image_public_prefix()
        if not image.url.startswith(public_prefix):
            raise ValueError("Image URL does not belong to the configured public bucket.")
        return image, None
    base_url, token, bucket = image_storage_config()
    extension = {
        "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp",
    }[image.media_type]
    path = f"experiments/{namespace}/{secrets.token_hex(16)}.{extension}"
    endpoint = f"{base_url}/storage/v1/object/{quote(bucket)}/{quote(path, safe='/')}"
    storage_request = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": token,
            "Content-Type": image.media_type,
            "x-upsert": "false",
        },
    )
    try:
        with urlopen(storage_request, timeout=30):
            pass
    except (HTTPError, URLError, TimeoutError) as error:
        raise ImageStorageError("Could not store image in Supabase.") from error
    url = f"{base_url}/storage/v1/object/public/{quote(bucket)}/{quote(path, safe='/')}"
    return BoardImage(name=image.name, media_type=image.media_type, url=url), path


def store_images(images, namespace):
    stored = []
    uploaded_paths = []
    try:
        for image in images:
            result, path = upload_image(image, namespace)
            stored.append(result)
            if path is not None:
                uploaded_paths.append(path)
    except (ValueError, ImageStorageError):
        if uploaded_paths:
            try:
                delete_stored_images(uploaded_paths)
            except ImageStorageError:
                app.logger.exception("Could not roll back partial image upload.")
        raise
    return stored, uploaded_paths


def configured_image_path(url):
    try:
        prefix = image_public_prefix()
    except ImageStorageError:
        return None
    if not url.startswith(prefix):
        return None
    path = unquote(url[len(prefix):])
    if not path or path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/")):
        return None
    return path


def delete_stored_images(paths):
    if not paths:
        return
    base_url, token, bucket = image_storage_config()
    endpoint = f"{base_url}/storage/v1/object/{quote(bucket)}"
    storage_request = Request(
        endpoint,
        data=json.dumps({"prefixes": paths}).encode(),
        method="DELETE",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(storage_request, timeout=30):
            pass
    except (HTTPError, URLError, TimeoutError) as error:
        raise ImageStorageError("Could not remove image from Supabase.") from error


def obsolete_image_paths(previous, current):
    current_urls = {image.url for image in current if image.url}
    paths = []
    for image in previous:
        if image.url and image.url not in current_urls:
            path = configured_image_path(image.url)
            if path is not None:
                paths.append(path)
    return paths


@app.route("/api/character", methods=["GET", "PUT"])
@jwt_required()
def character():
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if account["role"] != "player":
            return jsonify(status="error", message="Only players can access their character."), 403
        existing = database.characters.find_one({"_id": username})
        if request.method == "GET":
            data = {key: value for key, value in existing.items() if key != "_id"} if existing else CharacterData().model_dump()
            response = jsonify(character=data)
            response.headers["Cache-Control"] = "no-store"
            return response
        try:
            character_data = CharacterData.model_validate(request.get_json(silent=True))
            if not character_data.name.strip():
                raise ValueError("Enter a character name.")
            if character_data.portrait:
                if character_data.portrait.media_type == "image/gif":
                    raise ValueError("Portrait must be PNG, JPEG or WebP.")
        except ValidationError:
            return jsonify(status="error", message="Invalid character data. Check fields and class URLs."), 400
        except ValueError as error:
            return jsonify(status="error", message=str(error)), 400
        if character_data.revision != (existing["revision"] if existing else 0):
            return jsonify(status="error", message="Character changed elsewhere. Reload before editing."), 409
        uploaded_paths = []
        if character_data.portrait:
            try:
                portraits, uploaded_paths = store_images([character_data.portrait], f"portraits/{username}")
                character_data.portrait = portraits[0]
            except ValueError as error:
                return jsonify(status="error", message=str(error)), 400
            except ImageStorageError as error:
                return jsonify(status="error", message=str(error)), 503
        previous_portrait = (
            BoardImage.model_validate(existing["portrait"])
            if existing and existing.get("portrait") else None
        )
        character_data.revision += 1
        try:
            database.characters.replace_one(
                {"_id": username},
                {"_id": username, **character_data.model_dump(exclude_none=True)},
                upsert=True,
            )
        except PyMongoError:
            if uploaded_paths:
                try:
                    delete_stored_images(uploaded_paths)
                except ImageStorageError:
                    app.logger.exception("Could not roll back character portrait upload.")
            raise
        obsolete = obsolete_image_paths(
            [previous_portrait] if previous_portrait else [],
            [character_data.portrait] if character_data.portrait else [],
        )
        if obsolete:
            try:
                delete_stored_images(obsolete)
            except ImageStorageError:
                app.logger.exception("Could not remove obsolete character portrait.")
    return jsonify(status="success", character=character_data.model_dump(exclude_none=True))


@app.get("/api/characters")
@jwt_required()
def player_characters():
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if username != "dm" or account["role"] != "dm":
            return jsonify(status="error", message="Only the dm can view player characters."), 403
        players = sorted(user["_id"] for user in database.logins.find({"role": "player"}, {"_id": 1}))
        entries = []
        for player in players:
            data = database.characters.find_one({"_id": player}, {"_id": 0})
            entries.append({"username": player, "character": data})
        response = jsonify(characters=entries)
        response.headers["Cache-Control"] = "no-store"
        return response


@app.get("/api/bestiary")
@app.get("/api/bestiary/creature")
@jwt_required()
def bestiary_read():
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if username != "dm" or account["role"] != "dm":
            return jsonify(status="error", message="Only the dm can view the bestiary."), 403
    slug = request.args.get("slug") if request.path.endswith("/creature") else None
    if request.path.endswith("/creature") and (
        not slug or len(slug) > 512 or "\x00" in slug
    ):
        return jsonify(status="error", message="Invalid creature identifier."), 400
    try:
        if slug is None:
            result = {"creatures": [entry.model_dump() for entry in bestiary.load_index()]}
        else:
            loaded = bestiary.load_creature(slug)
            if loaded is None:
                result = None
            else:
                creature, initiative_bonus = loaded
                result = {
                    "display": render_creature(creature).model_dump(),
                    "creature": creature.model_dump(include=set(LocalCreatureInput.model_fields) - {"initiative_bonus"}),
                    "stored_initiative_bonus": initiative_bonus,
                    "initiative_bonus": initiative_bonus if initiative_bonus is not None
                    else (creature.dexterity - 10) // 2,
                    "initiative_bonus_source": "initiative" if initiative_bonus is not None else "dexterity",
                }
    except bestiary.BestiaryConfigurationError as error:
        return jsonify(status="error", message=str(error)), 503
    except bestiary.BestiaryLimitError:
        app.logger.error("Bestiary index exceeds the supported entry limit.")
        return jsonify(status="error", message="Bestiary exceeds the 10,000-entry limit."), 503
    except PyMongoError as error:
        app.logger.error("Bestiary read failed (%s).", type(error).__name__)
        return jsonify(status="error", message="Could not connect to the bestiary database. Check server configuration and logs."), 503
    except (ValidationError, ValueError) as error:
        app.logger.error("Invalid bestiary data (%s).", type(error).__name__)
        return jsonify(status="error", message="Invalid bestiary data or configuration. Check server logs."), 500
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if payload["exp"] <= time.time() or is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if username != "dm" or account["role"] != "dm":
            return jsonify(status="error", message="Only the dm can view the bestiary."), 403
    if result is None:
        return jsonify(status="error", message="Creature not found."), 404
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/custom-creatures", methods=["GET", "POST"])
@app.route("/api/custom-creatures/<creature_id>", methods=["GET", "PUT"])
@jwt_required()
def custom_creatures(creature_id=None):
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        if username != "dm" or account["role"] != "dm":
            return jsonify(status="error", message="Only the dm can manage custom creatures."), 403
        existing = database.custom_bestiary.find_one({"_id": creature_id}) if creature_id else None
        if creature_id and existing is None:
            return jsonify(status="error", message="Custom creature not found."), 404
        if request.method == "GET":
            if creature_id:
                creature = LocalCreature.model_validate({key: value for key, value in existing.items() if key != "_id"})
                result = {"id": creature_id, "creature": creature.model_dump(),
                          "display": render_creature(creature).model_dump()}
            else:
                result = {"creatures": sorted(
                    ({"id": entry["_id"], "name": entry["name"], "type": entry["type"],
                      "challenge_rating": entry["challenge_rating"]}
                     for entry in database.custom_bestiary.find()),
                    key=lambda entry: (entry["name"].casefold(), entry["id"]),
                )}
            response = jsonify(result)
            response.headers["Cache-Control"] = "no-store"
            return response
        try:
            incoming = (LocalCreatureUpdate if creature_id else LocalCreatureInput).model_validate(
                request.get_json(silent=True)
            )
        except ValidationError as error:
            issues = error.errors(include_url=False, include_input=False, include_context=False)
            details = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
                for issue in issues[:5]
            )
            return jsonify(status="error", message=f"Invalid creature data: {details}"), 400
        if existing and incoming.revision != existing["revision"]:
            return jsonify(status="error", message="Creature changed elsewhere. Copy your edits and reload."), 409
        if not creature_id:
            creature_id = f"local:{secrets.token_hex(16)}"
        values = incoming.model_dump(exclude={"revision"})
        creature = LocalCreature(**values, revision=existing["revision"] + 1 if existing else 1)
        display = render_creature(creature).model_dump()
        database.custom_bestiary.replace_one(
            {"_id": creature_id}, {"_id": creature_id, **creature.model_dump()}, upsert=True
        )
        response = jsonify(status="success", id=creature_id, creature=creature.model_dump(), display=display)
        response.headers["Cache-Control"] = "no-store"
        return response


@app.route("/api/initiative", methods=["GET", "PUT"])
@jwt_required()
def initiative():
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        is_dm = username == "dm" and account["role"] == "dm"
        if not is_dm and account["role"] != "player":
            return jsonify(status="error", message="Initiative is unavailable for this account."), 403
        existing = database.initiative.find_one({"_id": "state"})
        state = InitiativeState.model_validate(
            {key: value for key, value in existing.items() if key != "_id"} if existing else {}
        )
        if request.method == "GET":
            data = state.model_dump() if is_dm else initiative_player_view(state)
            response = jsonify(initiative=data)
            response.headers["Cache-Control"] = "no-store"
            return response
        if not is_dm:
            return jsonify(status="error", message="Only the dm can edit initiative."), 403
        try:
            incoming = InitiativeState.model_validate(request.get_json(silent=True))
        except ValidationError:
            return jsonify(status="error", message="Invalid initiative data. Check names, numbers and hit points."), 400
        if incoming.revision != state.revision:
            return jsonify(status="error", message="Initiative changed elsewhere. Reload before saving."), 409
        previous_revision = incoming.revision
        incoming.revision += 1
        result = database.initiative.replace_one(
            {"_id": "state", "revision": previous_revision},
            {"_id": "state", **incoming.model_dump()},
            upsert=False,
        )
        if result.matched_count == 0:
            return jsonify(status="error", message="Initiative changed elsewhere. Reload before saving."), 409
        with state_lock:
            active_connections = [
                (sid, connection["role"])
                for sid, connection in connections.items()
                if connection["exp"] > time.time()
            ]
        dm_data = incoming.model_dump()
        player_data = initiative_player_view(incoming)
        for sid, role in active_connections:
            socketio.emit(
                "initiative_changed",
                {"initiative": dm_data if role == "dm" else player_data},
                to=sid,
            )
        return jsonify(status="success", initiative=incoming.model_dump())


@app.route("/api/board", methods=["GET", "POST"])
@app.route("/api/board/<note_id>", methods=["PUT"])
@jwt_required()
def board(note_id=None):
    username = get_jwt_identity()
    payload = get_jwt()
    with state_lock:
        account = database.logins.find_one({"_id": username})
        if is_revoked(payload["jti"]) or account is None:
            return jsonify(status="error", message="Session expired. Log in again."), 401
        is_dm = username == "dm" and account["role"] == "dm"
        if not is_dm and account["role"] != "player":
            return jsonify(status="error", message="Board is unavailable for this account."), 403
        if request.method == "GET":
            query = {} if is_dm else {"visible": True}
            entries = [
                {"id": entry["_id"], "header": entry["header"], "content": entry["content"],
                 "visible": entry["visible"], "revision": entry["revision"], "updated_at": entry["updated_at"],
                 "images": entry["images"]}
                for entry in database.boards.find(query)
            ]
            response = jsonify(notes=entries)
            response.headers["Cache-Control"] = "no-store"
            return response
        if not is_dm:
            return jsonify(status="error", message="Only the dm can edit the board."), 403
        try:
            model = BoardNoteUpdate if note_id is not None else BoardNoteRequest
            incoming = model.model_validate(request.get_json(silent=True))
        except ValidationError:
            return jsonify(status="error", message="Invalid board note."), 400
        existing = database.boards.find_one({"_id": note_id}) if note_id is not None else None
        if note_id is not None:
            if existing is None:
                return jsonify(status="error", message="Board note not found."), 404
            if not isinstance(incoming, BoardNoteUpdate) or incoming.revision != existing["revision"]:
                return jsonify(status="error", message="Note changed elsewhere. Reload before editing."), 409
        else:
            note_id = secrets.token_hex(16)
        images = incoming.images
        if images is None:
            images = [BoardImage.model_validate(image) for image in existing["images"]] if existing else []
        try:
            images, uploaded_paths = store_images(images, f"board/{note_id}")
        except ValueError as error:
            return jsonify(status="error", message=str(error)), 400
        except ImageStorageError as error:
            return jsonify(status="error", message=str(error)), 503
        previous_images = (
            [BoardImage.model_validate(image) for image in existing["images"]] if existing else []
        )
        note = BoardNote(
            header=incoming.header, content=incoming.content, visible=incoming.visible,
            revision=existing["revision"] + 1 if existing else 1,
            updated_at=datetime.now(timezone.utc).isoformat(),
            images=images,
        )
        try:
            database.boards.replace_one(
                {"_id": note_id},
                {"_id": note_id, **note.model_dump(exclude_none=True)},
                upsert=True,
            )
        except PyMongoError:
            if uploaded_paths:
                try:
                    delete_stored_images(uploaded_paths)
                except ImageStorageError:
                    app.logger.exception("Could not roll back board image upload.")
            raise
        obsolete = obsolete_image_paths(previous_images, images)
        if obsolete:
            try:
                delete_stored_images(obsolete)
            except ImageStorageError:
                app.logger.exception("Could not remove obsolete board images.")
        for sid, connection in connections.items():
            if connection["exp"] > time.time() and not is_revoked(connection["jti"]):
                socketio.emit("board_changed", to=sid)
    return jsonify(status="success", id=note_id, **note.model_dump(exclude_none=True))


@app.post("/api/logout")
@jwt_required()
def logout():
    payload = get_jwt()
    with state_lock:
        was_revoked = is_revoked(payload["jti"])
        if not was_revoked:
            database.logins.update_one(
                {"_id": SESSION_METADATA_ID},
                {"$set": {f"revoked.{payload['jti']}": payload["exp"]}},
                upsert=True,
            )
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
        account = database.logins.find_one({"_id": payload["sub"]}, {"role": 1})
        if account is None:
            return False
        connections[request.sid] = {
            "user": payload["sub"], "role": account["role"],
            "jti": payload["jti"], "exp": payload["exp"],
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
        emit("chat_unread", {"count": unread_count(identity["user"])}, to=request.sid)
    return {"status": "success"}


@socketio.on("mark_chat_read")
def mark_chat_read(data):
    try:
        incoming = ChatReadRequest.model_validate(data)
    except ValidationError:
        return {"status": "error", "message": "Invalid chat read position."}
    with state_lock:
        identity = connections.get(request.sid)
        if (not identity or identity["exp"] <= time.time()
                or is_revoked(identity["jti"]) or not user_exists(identity["user"])):
            return {"status": "error", "message": "Session expired. Log in again."}
        username = identity["user"]
        if database.chats.find_one({"_id": incoming.message_id, "message.recipient": username}) is None:
            return {"status": "error", "message": "Message not found."}
        account = database.logins.find_one({"_id": username}, {"chat_read": 1})
        previous_cursor = account.get("chat_read", -1) if account else -1
        if incoming.message_id > previous_cursor:
            database.logins.update_one(
                {"_id": username},
                {"$set": {"chat_read": incoming.message_id}},
            )
        notify_unread(username)
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
        account = database.logins.find_one({"_id": identity["user"]})
        if not account:
            return {"status": "error", "message": "Account no longer exists."}
        if account["role"] == "player":
            if message_request.recipient not in (None, "dm"):
                return {"status": "error", "message": "Players can only message the DM."}
            target = "dm"
            if database.logins.find_one({"_id": target, "role": "dm"}) is None:
                return {"status": "error", "message": "DM account is unavailable."}
        else:
            if identity["user"] != "dm":
                return {"status": "error", "message": "Private chat is available only to the dm account."}
            target = message_request.recipient
            if not target or database.logins.find_one({"_id": target, "role": "player"}) is None:
                return {"status": "error", "message": "Select a valid player."}
        message = PrivateMessage(
            sender=identity["user"], recipient=target, text=message_request.text
        ).model_dump()
        latest = database.chats.find_one(sort=[("_id", -1)])
        message_id = latest["_id"] + 1 if latest else 0
        database.chats.insert_one({"_id": message_id, "message": message})
        for sid, recipient in connections.items():
            if (recipient["exp"] > time.time() and not is_revoked(recipient["jti"])
                    and recipient["user"] in (message["sender"], message["recipient"])
                    and user_exists(recipient["user"])):
                emit("receive_message", {"id": message_id, **message}, to=sid)
        notify_unread(target)
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
