from copy import deepcopy
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import streamlit as st
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from .initiative_store import (
    load_tracker,
    load_tracker_default,
    save_tracker,
    save_tracker_snapshot,
)

TRACKER_SESSION_KEY = "initiative_tracker"
TRACKER_SAVE_FUTURES_KEY = "initiative_save_futures"
TRACKER_SAVE_ERROR_KEY = "initiative_save_error"
TRACKER_SNAPSHOT_TIME_KEY = "initiative_snapshot_time"
TRACKER_SAVE_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="initiative-save"
)


def make_combatant(name: str, initiative: int, hit_points: int) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "name": name,
        "initiative": initiative,
        "dead": False,
        "current_hp": hit_points,
        "max_hp": hit_points,
    }


def get_session_tracker() -> dict[str, Any]:
    tracker = load_tracker()
    st.session_state[TRACKER_SESSION_KEY] = deepcopy(tracker)
    return deepcopy(tracker)


def persist_tracker(tracker: dict[str, Any]) -> None:
    future = TRACKER_SAVE_EXECUTOR.submit(save_tracker, deepcopy(tracker))
    future.result()
    st.session_state[TRACKER_SESSION_KEY] = deepcopy(tracker)


def persist_tracker_async(tracker: dict[str, Any]) -> None:
    future: Future[None] = TRACKER_SAVE_EXECUTOR.submit(
        save_tracker, deepcopy(tracker)
    )
    st.session_state[TRACKER_SESSION_KEY] = deepcopy(tracker)
    st.session_state.setdefault(TRACKER_SAVE_FUTURES_KEY, []).append(future)


def show_tracker_save_status() -> None:
    futures: list[Future[None]] = st.session_state.setdefault(
        TRACKER_SAVE_FUTURES_KEY, []
    )
    while futures and futures[0].done():
        future = futures.pop(0)
        try:
            future.result()
        except (KeyError, PyMongoError, RedisError, ValueError) as error:
            st.session_state[TRACKER_SAVE_ERROR_KEY] = str(error)
        else:
            st.session_state.pop(TRACKER_SAVE_ERROR_KEY, None)

    save_error = st.session_state.get(TRACKER_SAVE_ERROR_KEY)
    if save_error:
        st.error(f"Could not save initiative tracker: {save_error}")


@st.dialog("Reset initiative tracker?")
def confirm_reset_tracker() -> None:
    st.warning("This will replace the current tracker with its saved default state.")
    confirm_column, cancel_column = st.columns(2)
    if confirm_column.button("Reset tracker", type="primary"):
        try:
            default_tracker = load_tracker_default()
            if not isinstance(default_tracker, dict):
                raise ValueError("No valid default initiative tracker is configured.")
            persist_tracker(deepcopy(default_tracker))
        except (KeyError, PyMongoError, RedisError, ValueError) as error:
            st.error(f"Could not reset initiative tracker: {error}")
        else:
            st.rerun(scope="app")
    if cancel_column.button("Cancel"):
        st.rerun(scope="app")


@st.dialog("Change initiative")
def edit_initiative(combatant_id: str) -> None:
    try:
        tracker = get_session_tracker()
    except (KeyError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not load initiative tracker: {error}")
        return

    actor = next(
        (item for item in tracker["combatants"] if item["id"] == combatant_id),
        None,
    )
    if actor is None:
        st.error("Combatant no longer exists.")
        return

    with st.form(f"edit_initiative_{combatant_id}"):
        initiative = st.number_input(
            "Initiative", value=actor["initiative"], step=1
        )
        save = st.form_submit_button("Save")

    if save:
        actor["initiative"] = int(initiative)
        try:
            persist_tracker(tracker)
        except (KeyError, PyMongoError, RedisError, ValueError) as error:
            st.error(f"Could not update initiative: {error}")
        else:
            st.rerun(scope="app")


def save_combatant_hp(combatant_id: str, current_hp: int) -> None:
    try:
        tracker = get_session_tracker()
        actor = next(
            item for item in tracker["combatants"] if item["id"] == combatant_id
        )
        actor["current_hp"] = min(current_hp, actor["max_hp"])
        persist_tracker(tracker)
    except (KeyError, PyMongoError, RedisError, ValueError, StopIteration) as error:
        st.error(f"Could not update hit points: {error}")
    else:
        st.rerun(scope="fragment")


@st.fragment(run_every=1)
def render_initiative_tab(is_dm: bool = True) -> None:
    if is_dm:
        show_tracker_save_status()
        snapshot_time = st.session_state.get(TRACKER_SNAPSHOT_TIME_KEY)
        if snapshot_time:
            st.caption(f"MongoDB snapshot saved at {snapshot_time} UTC")
    st.markdown(
        """
        <style>
        [class*="st-key-current-combatant-"] {
            background-color: #f1e6c9;
            border: 2px solid #7a3428;
            border-radius: 0.75rem;
            padding: 1rem;
            color: #292722;
        }
        [class*="st-key-current-combatant-"] [data-testid="stMarkdownContainer"],
        [class*="st-key-current-combatant-"] [data-testid="stMarkdownContainer"] * {
            color: #292722;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    try:
        tracker = get_session_tracker()
    except (KeyError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not load initiative tracker: {error}")
        return

    combatants = tracker["combatants"]
    current_turn_id = tracker["current_turn_id"]

    if is_dm:
        with st.form("add_combatant", clear_on_submit=True):
            name_column, initiative_column, hp_column, add_column = st.columns([5, 2, 2, 1])
            name = name_column.text_input("Character or monster")
            initiative = initiative_column.number_input(
                "Initiative", value=0, step=1, key="new_combatant_initiative"
            )
            hit_points = hp_column.number_input(
                "Hit points", min_value=1, value=10, step=1
            )
            add_combatant = add_column.form_submit_button(
                "+", help="Add character or monster", key="initiative-add"
            )

        if add_combatant:
            name = name.strip()
            if not name:
                st.error("Enter a character or monster name.")
            else:
                new_combatant = make_combatant(name, int(initiative), int(hit_points))
                combatants.append(new_combatant)
                try:
                    persist_tracker(tracker)
                except (KeyError, PyMongoError, RedisError, ValueError) as error:
                    st.error(f"Could not save initiative tracker: {error}")
                else:
                    st.rerun(scope="fragment")

    if not combatants:
        st.caption("No combatants yet.")

    if is_dm:
        living_combatants = [actor for actor in combatants if not actor["dead"]]
        with st.container(horizontal=True):
            with st.container(key="initiative-next-turn", width="content"):
                if st.button("Next turn", disabled=not living_combatants, type="primary"):
                    current_index = next(
                        (
                            index for index, actor in enumerate(living_combatants)
                            if actor["id"] == current_turn_id
                        ),
                        -1,
                    )
                    next_actor = living_combatants[(current_index + 1) % len(living_combatants)]
                    tracker["current_turn_id"] = next_actor["id"]
                    try:
                        persist_tracker_async(tracker)
                    except (KeyError, PyMongoError, RedisError, RuntimeError, ValueError) as error:
                        st.error(f"Could not advance initiative: {error}")
                    else:
                        st.rerun(scope="fragment")

            with st.container(key="initiative-reorder", width="content"):
                reorder = st.button("Reorder by initiative", disabled=not combatants)

            if st.button("Reset to default"):
                confirm_reset_tracker()

            if st.button("Save snapshot", help="Save current tracker state to MongoDB"):
                try:
                    persist_tracker(tracker)
                    save_tracker_snapshot(tracker)
                except (KeyError, PyMongoError, RedisError, ValueError) as error:
                    st.error(f"Could not save tracker snapshot to MongoDB: {error}")
                else:
                    st.session_state[TRACKER_SNAPSHOT_TIME_KEY] = datetime.now(
                        timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S")

        if reorder:
            combatants.sort(key=lambda actor: actor["initiative"], reverse=True)
            try:
                persist_tracker(tracker)
            except (KeyError, PyMongoError, RedisError, ValueError) as error:
                st.error(f"Could not reorder initiative: {error}")
            else:
                st.rerun(scope="fragment")

    for actor in combatants:
        is_current = actor["id"] == current_turn_id and not actor["dead"]
        container_key = (
            f"current-combatant-{actor['id']}"
            if is_current
            else f"combatant-{actor['id']}"
        )
        with st.container(border=True, key=container_key):
            if is_dm:
                (
                    name_column,
                    initiative_column,
                    hp_value_column,
                    buttons_column,
                ) = st.columns([4, 1.2, 1, 2])
                name_column.markdown(
                    f"**{actor['name']}** (max hitpoints: {actor['max_hp']})"
                    + (" — DEAD" if actor["dead"] else "")
                )
                initiative_column.markdown(f"**Initiative:** {actor['initiative']}")
                hp_key = f"current_hp_{actor['id']}"
                if st.session_state.get(hp_key, actor["current_hp"]) > actor["max_hp"]:
                    st.session_state[hp_key] = actor["max_hp"]
                st.session_state.setdefault(hp_key, actor["current_hp"])
                hp_value_column.number_input(
                    "HP",
                    min_value=0,
                    max_value=actor["max_hp"],
                    step=1,
                    key=hp_key,
                    label_visibility="collapsed",
                )
                with buttons_column.container(horizontal=True, gap="small"):
                    if st.button(
                        "❤️", help="Save hit points", key=f"hp_save_{actor['id']}"
                    ):
                        save_combatant_hp(actor["id"], st.session_state[hp_key])

                    if st.button("🎲", help="Change initiative", key=f"change_{actor['id']}"):
                        edit_initiative(actor["id"])

                    if st.button(
                        "💀",
                        help="Revive" if actor["dead"] else "Make dead",
                        key=f"dead_{actor['id']}",
                    ):
                        actor["dead"] = not actor["dead"]
                        if actor["dead"] and current_turn_id == actor["id"]:
                            tracker["current_turn_id"] = None
                        try:
                            persist_tracker(tracker)
                        except (KeyError, PyMongoError, RedisError, ValueError) as error:
                            st.error(f"Could not update combatant status: {error}")
                        else:
                            st.rerun(scope="fragment")

                    with st.container(key=f"initiative-delete-{actor['id']}", width="content"):
                        if st.button("❌", help="Delete", key=f"delete_{actor['id']}"):
                            combatants.remove(actor)
                            if current_turn_id == actor["id"]:
                                tracker["current_turn_id"] = None
                            try:
                                persist_tracker(tracker)
                            except (KeyError, PyMongoError, RedisError, ValueError) as error:
                                st.error(f"Could not delete combatant: {error}")
                            else:
                                st.rerun(scope="fragment")
            else:
                name_column, initiative_column = st.columns([4, 1.2])
                name_column.markdown(
                    f"**{actor['name']}**" + (" — DEAD" if actor["dead"] else "")
                )
                initiative_column.markdown(f"**Initiative:** {actor['initiative']}")
                if actor["dead"]:
                    st.caption("Combatant is defeated.")
