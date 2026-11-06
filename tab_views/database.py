from typing import Any

import streamlit as st
from pymongo import MongoClient

from .config import get_required_env

DATABASE_NAME = "game_helper"


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
