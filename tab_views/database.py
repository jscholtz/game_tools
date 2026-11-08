import base64
import binascii
from typing import Any, TypedDict
from uuid import uuid4

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from .config import get_required_env

DATABASE_NAME = "game_helper"


class PublicNote(TypedDict):
    header: str
    date: str
    text: str
    visible: bool
    images: list[str]


@st.cache_resource
def get_mongodb_client() -> MongoClient:
    uri = get_required_env("MONGODB_URI")
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    client.admin.command("ping")
    return client


def get_database():
    return get_mongodb_client()[DATABASE_NAME]


def get_users() -> dict[str, dict[str, Any]]:
    return {
        document["username"]: document
        for document in get_database()["logins"].find(
            {}, {"username": 1, "password_hash": 1, "role": 1}
        )
    }


def load_private_data(username: str) -> dict[str, Any]:
    document = get_database()["private_data"].find_one({"_id": username})
    if document is None:
        raise FileNotFoundError(f"No private data found for {username}.")
    document.pop("_id", None)
    return document


def save_private_data(username: str, data: dict[str, Any]) -> None:
    fields = {key: value for key, value in data.items() if key != "_id"}
    result = get_database()["private_data"].update_one(
        {"_id": username},
        {"$set": fields},
    )
    if result.matched_count == 0:
        raise FileNotFoundError(f"No private data found for {username}.")


def load_character_cards(player_names: list[str]) -> dict[str, dict[str, Any]]:
    fields = {
        "character": 1,
        "level": 1,
        "race": 1,
        "class": 1,
        "subclass": 1,
        "passive_perception": 1,
        "passive_insight": 1,
        "insight": 1,
        "armor_class": 1,
        "max_hp": 1,
        "class_url": 1,
        "subclass_url": 1,
        "portrait": 1,
    }
    return {
        document["_id"]: document
        for document in get_database()["private_data"].find(
            {"_id": {"$in": player_names}}, fields
        )
    }


def save_character_card(
    username: str, fields: dict[str, Any], removed_fields: list[str]
) -> None:
    update: dict[str, Any] = {"$set": fields}
    if removed_fields:
        update["$unset"] = {field: "" for field in removed_fields}
    result = get_database()["private_data"].update_one({"_id": username}, update)
    if result.matched_count == 0:
        raise FileNotFoundError(f"User data not found for {username}.")


def load_public_file(filename: str) -> str | bytes:
    document = get_database()["public_data"].find_one({"_id": filename})
    if document is None:
        raise FileNotFoundError(f"No public data found for {filename}.")
    content = document.get("content")
    if not isinstance(content, (str, bytes)):
        raise ValueError(f"Public data content for {filename} must be text or bytes.")
    return content


def load_publication_settings() -> dict[str, bool]:
    document = get_database()["public_data"].find_one({"_id": "publication_settings"})
    if document is None:
        return {}
    settings = document.get("sections")
    if not isinstance(settings, dict) or not all(
        isinstance(key, str) and isinstance(value, bool)
        for key, value in settings.items()
    ):
        raise ValueError("DM publication settings must map section names to true/false.")
    return settings


def load_public_board() -> tuple[str, dict[str, bool] | None, dict[str, bool]]:
    document = get_database()["public_data"].find_one({"_id": "public.md"})
    if document is None:
        raise FileNotFoundError("No public data found for public.md.")
    content = document.get("content")
    if not isinstance(content, str):
        raise ValueError("Public board content must be text.")
    settings = document.get("sections")
    if "sections" in document and (
        not isinstance(settings, dict)
        or not all(isinstance(key, str) and isinstance(value, bool) for key, value in settings.items())
    ):
        raise ValueError("Public board settings must map section names to true/false.")
    return content, settings, settings if settings is not None else load_publication_settings()


def load_public_notes() -> tuple[list[PublicNote], str] | None:
    document = get_database()["public_data"].find_one({"_id": "public_notes"})
    if document is None:
        return None
    notes = document.get("notes")
    revision = document.get("revision")
    if not isinstance(notes, list) or not isinstance(revision, str):
        raise ValueError("Public notes must contain a list and a revision.")
    for note in notes:
        if (
            not isinstance(note, dict)
            or set(note) != {"header", "date", "text", "visible", "images"}
            or not all(isinstance(note[field], str) for field in ("header", "date", "text"))
            or not isinstance(note["visible"], bool)
            or not isinstance(note["images"], list)
            or not all(isinstance(image, str) for image in note["images"])
        ):
            raise ValueError("Invalid public note data.")
        for image in note["images"]:
            if image.startswith("image:") and len(image) > len("image:"):
                continue
            try:
                base64.b64decode(image, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("Invalid public note image encoding.") from error
    return notes, revision


def save_public_image(name: str, content: bytes) -> str:
    if not name or not content:
        raise ValueError("Image name and content must not be empty.")
    image_id = uuid4().hex
    get_database()["public_data"].insert_one(
        {"_id": f"public_image:{image_id}", "name": name, "content": content}
    )
    return f"image:{image_id}"


def load_public_image(reference: str) -> tuple[str, bytes]:
    if not reference.startswith("image:") or len(reference) == len("image:"):
        raise ValueError("Invalid image reference.")
    image_id = reference[len("image:"):]
    image = get_database()["public_data"].find_one({"_id": f"public_image:{image_id}"})
    if image is None:
        image = get_database()["public_images"].find_one({"_id": image_id})
    if image is None:
        raise FileNotFoundError(f"Image {reference} not found.")
    name = image.get("name")
    content = image.get("content")
    if not isinstance(name, str) or not name or not isinstance(content, bytes) or not content:
        raise ValueError(f"Invalid stored image {reference}.")
    return name, content


def create_public_notes(notes: list[PublicNote]) -> bool:
    try:
        get_database()["public_data"].insert_one(
            {"_id": "public_notes", "notes": notes, "revision": uuid4().hex}
        )
    except DuplicateKeyError:
        return False
    return True


def save_public_notes(notes: list[PublicNote], revision: str) -> bool:
    result = get_database()["public_data"].update_one(
        {"_id": "public_notes", "revision": revision},
        {"$set": {"notes": notes, "revision": uuid4().hex}},
    )
    return result.matched_count == 1


def load_chat_messages(username: str, conversation_partner: str) -> list[dict[str, Any]]:
    collection = get_database()["chats"]
    query = {
        "$or": [
            {"sender": username, "recipient": conversation_partner},
            {"sender": conversation_partner, "recipient": username},
        ]
    }
    messages = list(collection.find(query, {"_id": 0}))
    messages.sort(key=lambda message: message.get("timestamp", ""))
    return messages


def load_dm_unread_counts(player_names: list[str]) -> dict[str, int]:
    if not player_names:
        return {}
    rows = get_database()["chats"].aggregate(
        [
            {
                "$match": {
                    "recipient": "dm",
                    "sender": {"$in": player_names},
                    "dm_read": {"$ne": True},
                }
            },
            {"$group": {"_id": "$sender", "count": {"$sum": 1}}},
        ]
    )
    return {row["_id"]: row["count"] for row in rows}


def mark_dm_messages_read(player_name: str) -> None:
    get_database()["chats"].update_many(
        {
            "sender": player_name,
            "recipient": "dm",
            "dm_read": {"$ne": True},
        },
        {"$set": {"dm_read": True}},
    )


def save_chat_message(message: dict[str, Any]) -> None:
    get_database()["chats"].insert_one(message)
