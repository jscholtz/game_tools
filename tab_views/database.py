import os
from typing import Any

import streamlit as st
from pymongo import MongoClient

DATABASE_NAME = "game_helper"


@st.cache_resource
def get_mongodb_client() -> MongoClient:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        uri = st.secrets["tokens"]["mongodb"]["mongo_db_login"]
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


def save_publication_settings(settings: dict[str, bool]) -> None:
    get_database()["public_data"].replace_one(
        {"_id": "publication_settings"},
        {"_id": "publication_settings", "name": "publication_settings", "sections": settings},
        upsert=True,
    )


def load_tracker() -> dict[str, Any]:
    document = get_database()["initiative"].find_one({"_id": "tracker"})
    if document is None:
        return {"combatants": [], "current_turn_id": None}
    tracker = document.get("current")
    if tracker is None:
        return {"combatants": [], "current_turn_id": None}
    if not isinstance(tracker, dict):
        raise ValueError("Initiative tracker must be an object.")
    combatants = tracker.get("combatants")
    if not isinstance(combatants, list):
        raise ValueError("Initiative tracker must contain a combatants list.")
    for combatant in combatants:
        if (
            not isinstance(combatant, dict)
            or not isinstance(combatant.get("id"), str)
            or not isinstance(combatant.get("name"), str)
            or not isinstance(combatant.get("initiative"), int)
            or not isinstance(combatant.get("dead"), bool)
        ):
            raise ValueError("Initiative tracker contains an invalid combatant.")
        current_hp = combatant.setdefault("current_hp", 10)
        if not isinstance(current_hp, int):
            raise ValueError("Combatant hit points are invalid.")
        max_hp = combatant.setdefault("max_hp", max(current_hp, 1))
        if (
            not isinstance(max_hp, int)
            or current_hp < 0
            or max_hp < 1
            or current_hp > max_hp
        ):
            raise ValueError("Combatant hit points are invalid.")
    return tracker


def load_tracker_default() -> dict[str, Any] | None:
    document = get_database()["initiative"].find_one({"_id": "tracker"})
    if document is None:
        return None
    default = document.get("default")
    return default if isinstance(default, dict) else None


def save_tracker(tracker: dict[str, Any]) -> None:
    collection = get_database()["initiative"]
    collection.update_one(
        {"_id": "tracker"},
        {"$set": {"current": tracker}},
        upsert=True,
    )


def load_chat_messages(username: str, is_dm: bool, conversation_partner: str) -> list[dict[str, Any]]:
    collection = get_database()["chats"]
    query = (
        {}
        if is_dm
        else {
            "$or": [
                {"sender": username, "recipient": conversation_partner},
                {"sender": conversation_partner, "recipient": username},
            ]
        }
    )
    messages = list(collection.find(query, {"_id": 0}))
    messages.sort(key=lambda message: message.get("timestamp", ""))
    return messages


def save_chat_message(message: dict[str, str]) -> None:
    get_database()["chats"].insert_one(message)
