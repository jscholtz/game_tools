from typing import Any
from uuid import uuid4

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from pydantic import TypeAdapter, ValidationError

from .config import get_required_env
from .data_models import (
    BestiaryDisplay, BestiaryEntry, CharacterData, ChatMessage, CustomCreature, LoginRecord,
    PrivateNote, PublicBoard, PublicNote, StandardCreature,
)

DATABASE_NAME = "game_helper"

BESTIARY_INDEX_FIELDS = {
    "_id": 0,
    "slug": 1,
    "name": 1,
    "type": 1,
    "size": 1,
    "challenge_rating": 1,
    "cr": 1,
    "document__title": 1,
    "hit_points": 1,
}
BESTIARY_DISPLAY_FIELDS = {"_id": 0, "inline": 1, "sizes": 1}

_private_notes_adapter = TypeAdapter(list[PrivateNote])


def _validate_private_notes(data: Any) -> list[PrivateNote]:
    try:
        return _private_notes_adapter.validate_python(data, strict=True)
    except ValidationError as error:
        raise ValueError("Invalid private notes data; expected a list of note objects.") from error


@st.cache_resource
def get_mongodb_client() -> MongoClient:
    uri = get_required_env("MONGODB_URI")
    client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    client.admin.command("ping")
    return client


def get_database():
    return get_mongodb_client()[DATABASE_NAME]


@st.cache_data(show_spinner=False)
def load_bestiary_index() -> list[BestiaryEntry]:
    return [
        BestiaryEntry.model_validate(document)
        for document in get_mongodb_client()["creatures"]["basic_list"].find({}, BESTIARY_INDEX_FIELDS)
    ]


@st.cache_data(show_spinner=False)
def load_bestiary_display(slug: str) -> BestiaryDisplay:
    display = get_mongodb_client()["creatures"]["display"].find_one(
        {"slug": slug}, BESTIARY_DISPLAY_FIELDS
    )
    if display is None:
        raise FileNotFoundError(f"Creature stat block not found: {slug}")
    return BestiaryDisplay.model_validate(display)


@st.cache_data(show_spinner=False, max_entries=1024)
def load_standard_creature(slug: str) -> StandardCreature:
    document = get_mongodb_client()["creatures"]["basic_list"].find_one(
        {"slug": slug}, {"_id": 0}
    )
    if document is None:
        raise FileNotFoundError(f"Creature not found: {slug}")
    return StandardCreature.model_validate(document)


def load_custom_creatures() -> list[CustomCreature]:
    return [
        CustomCreature.model_validate(document)
        for document in get_database()["custom_bestiary"].find({}, {"_id": 0})
    ]


def load_custom_creature(slug: str) -> CustomCreature:
    document = get_database()["custom_bestiary"].find_one({"_id": slug}, {"_id": 0})
    if document is None:
        raise FileNotFoundError(f"Custom creature not found: {slug}")
    return CustomCreature.model_validate(document)


def create_custom_creature(creature: CustomCreature) -> None:
    get_database()["custom_bestiary"].insert_one(
        {"_id": creature.slug, **creature.model_dump()}
    )


def update_custom_creature(creature: CustomCreature, previous_revision: str) -> None:
    result = get_database()["custom_bestiary"].update_one(
        {"_id": creature.slug, "revision": previous_revision},
        {"$set": creature.model_dump()},
    )
    if result.matched_count == 0:
        raise ValueError("Creature changed or was removed. Copy your draft and reopen it before saving.")


def get_users() -> dict[str, LoginRecord]:
    users = {}
    for document in get_database()["logins"].find(
        {}, {"_id": 0, "username": 1, "password_hash": 1, "role": 1}
    ):
        user = LoginRecord.model_validate(document)
        users[user.username] = user
    return users


def load_private_data(username: str) -> CharacterData:
    document = get_database()["private_data"].find_one({"_id": username})
    if document is None:
        raise FileNotFoundError(f"No private data found for {username}.")
    document.pop("_id", None)
    return CharacterData.model_validate(document)


def load_private_notes(username: str) -> list[PrivateNote]:
    document = get_database()["private_data"].find_one({"_id": username}, {"notes": 1})
    if document is None:
        raise FileNotFoundError(f"No private data found for {username}.")
    return _validate_private_notes(document.get("notes", []))


def save_private_notes(username: str, notes: list[PrivateNote]) -> None:
    validated = _validate_private_notes([note.model_dump(exclude_unset=True) for note in notes])
    result = get_database()["private_data"].update_one(
        {"_id": username},
        {"$set": {"notes": [note.model_dump(exclude_unset=True) for note in validated]}},
    )
    if result.matched_count == 0:
        raise FileNotFoundError(f"No private data found for {username}.")


def load_character_cards(player_names: list[str]) -> dict[str, CharacterData]:
    fields = {
        "character": 1,
        "race": 1,
        "passive_perception": 1,
        "passive_insight": 1,
        "armor_class": 1,
        "max_hp": 1,
        "classes": 1,
        "portrait": 1,
    }
    return {
        document["_id"]: CharacterData.model_validate(
            {key: value for key, value in document.items() if key != "_id"}
        )
        for document in get_database()["private_data"].find(
            {"_id": {"$in": player_names}}, fields
        )
    }


def save_character_card(
    username: str, fields: dict[str, Any], removed_fields: list[str]
) -> None:
    validated = CharacterData.model_validate(fields)
    update: dict[str, Any] = {"$set": validated.model_dump(exclude_unset=True)}
    if removed_fields:
        update["$unset"] = {field: "" for field in removed_fields}
    result = get_database()["private_data"].update_one({"_id": username}, update)
    if result.matched_count == 0:
        raise FileNotFoundError(f"User data not found for {username}.")


def load_public_notes() -> tuple[list[PublicNote], str] | None:
    document = get_database()["public_data"].find_one({"_id": "public_notes"})
    if document is None:
        return None
    board = PublicBoard.model_validate(document)
    return board.notes, board.revision


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
        raise FileNotFoundError(f"Image {reference} not found.")
    name = image.get("name")
    content = image.get("content")
    if not isinstance(name, str) or not name or not isinstance(content, bytes) or not content:
        raise ValueError(f"Invalid stored image {reference}.")
    return name, content


def create_public_notes(notes: list[PublicNote]) -> bool:
    board = PublicBoard.model_validate(
        {"notes": [note.model_dump() for note in notes], "revision": uuid4().hex}
    )
    try:
        get_database()["public_data"].insert_one(
            {"_id": "public_notes", **board.model_dump()}
        )
    except DuplicateKeyError:
        return False
    return True


def save_public_notes(notes: list[PublicNote], revision: str) -> bool:
    board = PublicBoard.model_validate(
        {"notes": [note.model_dump() for note in notes], "revision": uuid4().hex}
    )
    result = get_database()["public_data"].update_one(
        {"_id": "public_notes", "revision": revision},
        {"$set": board.model_dump()},
    )
    return result.matched_count == 1


def load_chat_messages(username: str, conversation_partner: str) -> list[ChatMessage]:
    collection = get_database()["chats"]
    query = {
        "$or": [
            {"sender": username, "recipient": conversation_partner},
            {"sender": conversation_partner, "recipient": username},
        ]
    }
    messages = [ChatMessage.model_validate(message) for message in collection.find(query, {"_id": 0})]
    messages.sort(key=lambda message: message.timestamp)
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
                    "dm_read": False,
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
            "dm_read": False,
        },
        {"$set": {"dm_read": True}},
    )


def save_chat_message(message: ChatMessage) -> None:
    validated = ChatMessage.model_validate(message.model_dump(exclude_unset=True))
    get_database()["chats"].insert_one(validated.model_dump(exclude_unset=True))
