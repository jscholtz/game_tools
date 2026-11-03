import hashlib
import json
import mimetypes
import os
import tomllib
from pathlib import Path
from typing import Any

from pymongo import MongoClient

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PUBLIC_DATA_DIR = ROOT / "public_data"
SECRETS_FILE = ROOT / ".streamlit" / "secrets.toml"
DATABASE_NAME = "game_helper"


def get_mongodb_uri() -> str:
    uri = os.environ.get("MONGODB_URI")
    if uri:
        return uri

    with SECRETS_FILE.open("rb") as secrets_file:
        secrets = tomllib.load(secrets_file)
    try:
        return secrets["tokens"]["mongodb"]["mongo_db_login"]
    except KeyError as error:
        raise RuntimeError(
            "Set MONGODB_URI or tokens.mongodb.mongo_db_login in .streamlit/secrets.toml."
        ) from error


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def upsert_documents(collection, documents: list[dict[str, Any]]) -> None:
    for document in documents:
        collection.replace_one({"_id": document["_id"]}, document, upsert=True)


def upload() -> None:
    uri = get_mongodb_uri()
    users = tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8"))["users"]
    logins = [
        {
            "_id": username,
            "username": username,
            "password_hash": details["password_hash"],
            "role": details["role"],
        }
        for username, details in users.items()
    ]

    private_data = []
    chat_messages = {}
    initiative_state = {}
    publication_settings = None
    for path in sorted(DATA_DIR.glob("*.json")):
        username = path.stem
        data = load_json(path)
        messages = data.get("messages", [])
        if not isinstance(messages, list) or not all(
            isinstance(message, dict) for message in messages
        ):
            raise ValueError(f"'messages' in {path.name} must be a list of objects.")

        for message in messages:
            serialized = json.dumps(message, sort_keys=True, ensure_ascii=False)
            message_id = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            chat_messages[message_id] = {"_id": message_id, **message}

        private_fields = {
            key: value
            for key, value in data.items()
            if key not in {
                "messages",
                "initiative_tracker",
                "initiate_tracker_default",
                "public_sections",
            }
        }
        private_data.append({"_id": username, "username": username, **private_fields})

        if "initiative_tracker" in data or "initiate_tracker_default" in data:
            initiative_state = {
                "current": data.get("initiative_tracker"),
                "default": data.get("initiate_tracker_default"),
            }
        if "public_sections" in data:
            publication_settings = data["public_sections"]

    public_documents = []
    for path in sorted(PUBLIC_DATA_DIR.iterdir()):
        if not path.is_file():
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content: str | bytes
        content = path.read_text(encoding="utf-8") if path.suffix == ".md" else path.read_bytes()
        public_documents.append(
            {
                "_id": path.name,
                "filename": path.name,
                "content_type": content_type,
                "content": content,
            }
        )

    if initiative_state:
        initiative_state["_id"] = "tracker"
        initiative_documents = [initiative_state]
    else:
        initiative_documents = []
    if publication_settings is not None:
        public_documents.append(
            {
                "_id": "publication_settings",
                "name": "publication_settings",
                "sections": publication_settings,
            }
        )

    with MongoClient(uri, serverSelectionTimeoutMS=10_000) as client:
        client.admin.command("ping")
        database = client[DATABASE_NAME]
        upsert_documents(database["chats"], list(chat_messages.values()))
        upsert_documents(database["initiative"], initiative_documents)
                
        upsert_documents(database["personal_data"], private_data)
        upsert_documents(database["public_data"], public_documents)
        upsert_documents(database["logins"], logins)
        

    print(
        "Uploaded "
        f"{len(logins)} logins, {len(private_data)} private records, "
        f"{len(chat_messages)} messages, {len(initiative_documents)} initiative records, "
        f"and {len(public_documents)} public-data records to {DATABASE_NAME}."
    )


if __name__ == "__main__":
    upload()
