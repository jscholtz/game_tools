import json
import os
from typing import Any

import redis
import streamlit as st

from .config import get_required_env
from .database import get_database
from .initiative_models import InitiativeTracker

TRACKER_KEY = "game_helper:initiative:tracker"


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

        document = get_database()["initiative"].find_one({"_id": "tracker"})
        values = {"_initialized": "1"}
        if document is not None:
            for field in ("current", "default"):
                value = document.get(field)
                if field not in state and isinstance(value, dict):
                    values[field] = json.dumps(value)
        client.hset(TRACKER_KEY, mapping=values)
        return client.hgetall(TRACKER_KEY)


def load_tracker() -> InitiativeTracker:
    encoded_tracker = _load_tracker_state().get("current")
    if encoded_tracker is None:
        return InitiativeTracker(combatants=[], current_turn_id=None)
    return InitiativeTracker.model_validate_json(encoded_tracker)


def load_tracker_default() -> InitiativeTracker | None:
    encoded_default = _load_tracker_state().get("default")
    if encoded_default is None:
        return None
    return InitiativeTracker.model_validate_json(encoded_default)


def _validated_document(tracker: InitiativeTracker) -> dict[str, Any]:
    document = tracker.model_dump(exclude_unset=True)
    return InitiativeTracker.model_validate(document).model_dump(exclude_unset=True)


def save_tracker(tracker: InitiativeTracker) -> None:
    get_redis_client().hset(
        TRACKER_KEY,
        mapping={
            "_initialized": "1",
            "current": json.dumps(_validated_document(tracker)),
        },
    )


def save_tracker_snapshot(tracker: InitiativeTracker) -> None:
    get_database()["initiative"].update_one(
        {"_id": "tracker"},
        {"$set": {"current": _validated_document(tracker)}},
        upsert=True,
    )
