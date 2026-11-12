import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import redis
import streamlit as st
from pymongo import ReturnDocument

from .config import get_required_env
from .database import get_database
from .initiative_models import InitiativeTracker, SavedEncounter

TRACKER_KEY = "game_helper:initiative:tracker"
INITIATIVE_COLLECTION = "initiative"
ENCOUNTER_TYPE = "encounter"
SAVED_ORDER_ID = "encounter-metadata:saved-order"


@st.cache_resource
def get_redis_client() -> redis.Redis:
    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "machine-hand-mice-91302.db.redis.io"),
        port=int(os.environ.get("REDIS_PORT", "18224")),
        username=get_required_env("REDIS_USERNAME"),
        password=get_required_env("REDIS_PASSWORD"),
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )
    client.ping()
    return client


def _load_tracker_state() -> dict[str, str]:
    client = get_redis_client()
    state = client.hgetall(TRACKER_KEY)
    if state.get("_initialized") == "1":
        return state

    with client.lock(f"{TRACKER_KEY}:migration-lock", timeout=30, blocking_timeout=15):
        state = client.hgetall(TRACKER_KEY)
        if state.get("_initialized") == "1":
            return state

        values = {"_initialized": "1"}
        if "current" not in state:
            document = get_database()[INITIATIVE_COLLECTION].find_one(
                {"type": ENCOUNTER_TYPE, "saved_order": {"$type": "number"}},
                sort=[("saved_order", -1)],
            )
            if document is not None:
                encounter = _encounter_from_document(document)
                values["current"] = json.dumps(_validated_document(encounter.tracker))
        client.hset(TRACKER_KEY, mapping=values)
        return client.hgetall(TRACKER_KEY)


def load_tracker() -> InitiativeTracker:
    encoded_tracker = _load_tracker_state().get("current")
    if encoded_tracker is None:
        return InitiativeTracker(combatants=[], current_turn_id=None)
    return InitiativeTracker.model_validate_json(encoded_tracker)


def _validated_document(tracker: InitiativeTracker) -> dict[str, Any]:
    document = tracker.model_dump(exclude_unset=True)
    return InitiativeTracker.model_validate(document).model_dump(exclude_unset=True)


def save_tracker(tracker: InitiativeTracker) -> None:
    client = get_redis_client()
    with client.lock(f"{TRACKER_KEY}:migration-lock", timeout=30, blocking_timeout=15):
        client.hset(
            TRACKER_KEY,
            mapping={
                "_initialized": "1",
                "current": json.dumps(_validated_document(tracker)),
            },
        )


def _encounter_from_document(document: dict[str, Any]) -> SavedEncounter:
    values = {key: value for key, value in document.items() if key not in ("_id", "type")}
    return SavedEncounter.model_validate({"id": document["_id"], **values})


def _next_saved_order() -> int:
    document = get_database()[INITIATIVE_COLLECTION].find_one_and_update(
        {"_id": SAVED_ORDER_ID},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return document["value"]


def list_encounters() -> list[SavedEncounter]:
    return [
        _encounter_from_document(document)
        for document in get_database()[INITIATIVE_COLLECTION].find({"type": ENCOUNTER_TYPE}).sort(
            [("created_at", -1), ("_id", 1)]
        )
    ]


def load_encounter(encounter_id: str) -> SavedEncounter:
    document = get_database()[INITIATIVE_COLLECTION].find_one(
        {"_id": encounter_id, "type": ENCOUNTER_TYPE}
    )
    if document is None:
        raise ValueError("Saved encounter no longer exists.")
    return _encounter_from_document(document)


def create_encounter(name: str, tracker: InitiativeTracker) -> SavedEncounter:
    validated_tracker = _validated_document(tracker)
    client = get_redis_client()
    with client.lock(f"{TRACKER_KEY}:encounter-save-lock", timeout=30, blocking_timeout=15):
        document = {
            "_id": f"encounter:{uuid4().hex}",
            "type": ENCOUNTER_TYPE,
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "saved_order": _next_saved_order(),
            "tracker": validated_tracker,
        }
        get_database()[INITIATIVE_COLLECTION].insert_one(document)
    return _encounter_from_document(document)


def rename_encounter(encounter_id: str, name: str) -> None:
    result = get_database()[INITIATIVE_COLLECTION].update_one(
        {"_id": encounter_id, "type": ENCOUNTER_TYPE}, {"$set": {"name": name}}
    )
    if result.matched_count == 0:
        raise ValueError("Saved encounter no longer exists.")


def overwrite_encounter(encounter_id: str, tracker: InitiativeTracker) -> None:
    document = _validated_document(tracker)
    client = get_redis_client()
    with client.lock(f"{TRACKER_KEY}:encounter-save-lock", timeout=30, blocking_timeout=15):
        order = _next_saved_order()
        result = get_database()[INITIATIVE_COLLECTION].update_one(
            {"_id": encounter_id, "type": ENCOUNTER_TYPE},
            {"$set": {"tracker": document, "saved_order": order}},
        )
    if result.matched_count == 0:
        raise ValueError("Saved encounter no longer exists.")


def delete_encounter(encounter_id: str) -> None:
    result = get_database()[INITIATIVE_COLLECTION].delete_one(
        {"_id": encounter_id, "type": ENCOUNTER_TYPE}
    )
    if result.deleted_count == 0:
        raise ValueError("Saved encounter no longer exists.")
