import json
import os
from typing import Any

import redis
import streamlit as st

from .config import get_required_env
from .database import get_database

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


def _validate_tracker(tracker: Any) -> dict[str, Any]:
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
            or not isinstance(combatant.get("visible"), bool)
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


def load_tracker() -> dict[str, Any]:
    encoded_tracker = _load_tracker_state().get("current")
    if encoded_tracker is None:
        return {"combatants": [], "current_turn_id": None}
    return _validate_tracker(json.loads(encoded_tracker))


def load_tracker_default() -> dict[str, Any] | None:
    encoded_default = _load_tracker_state().get("default")
    if encoded_default is None:
        return None
    return _validate_tracker(json.loads(encoded_default))


def save_tracker(tracker: dict[str, Any]) -> None:
    get_redis_client().hset(
        TRACKER_KEY,
        mapping={
            "_initialized": "1",
            "current": json.dumps(tracker),
        },
    )


def save_tracker_snapshot(tracker: dict[str, Any]) -> None:
    get_database()["initiative"].update_one(
        {"_id": "tracker"},
        {"$set": {"current": tracker}},
        upsert=True,
    )
