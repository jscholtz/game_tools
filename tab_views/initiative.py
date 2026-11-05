from copy import deepcopy
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import streamlit as st
from pymongo.errors import PyMongoError

from .database import load_tracker, load_tracker_default, save_tracker

TRACKER_SESSION_KEY = "initiative_tracker"
TRACKER_SAVE_FUTURES_KEY = "initiative_save_futures"
TRACKER_SAVE_ERROR_KEY = "initiative_save_error"
TRACKER_SAVE_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="initiative-save"
)


def get_session_tracker() -> dict[str, Any]:
    if TRACKER_SESSION_KEY not in st.session_state:
        st.session_state[TRACKER_SESSION_KEY] = load_tracker()
    return deepcopy(st.session_state[TRACKER_SESSION_KEY])


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
        except (PyMongoError, ValueError) as error:
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
        except (PyMongoError, ValueError) as error:
            st.error(f"Could not reset initiative tracker: {error}")
        else:
            st.rerun(scope="app")
    if cancel_column.button("Cancel"):
        st.rerun(scope="app")


@st.dialog("Change initiative")
def edit_initiative(combatant_id: str) -> None:
    try:
        tracker = get_session_tracker()
    except (PyMongoError, ValueError) as error:
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
        except (PyMongoError, ValueError) as error:
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
    except (PyMongoError, ValueError, StopIteration) as error:
        st.error(f"Could not update hit points: {error}")
    else:
        st.rerun(scope="fragment")


@st.fragment(run_every=1)
def render_initiative_tab() -> None:
    show_tracker_save_status()
    st.markdown(
        """
        <style>
        .st-key-initiative-add button {
            background-color: #238636;
            border-color: #238636;
            color: white;
        }
        [class*="st-key-initiative-next-turn-"] button {
            background-color: #163f70;
            border-color: #3b82f6;
            color: white;
        }
        [class*="st-key-current-combatant-"] {
            background-color: #163f70;
            border: 2px solid #3b82f6;
            border-radius: 0.75rem;
            padding: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    try:
        tracker = get_session_tracker()
    except (PyMongoError, ValueError) as error:
        st.error(f"Could not load initiative tracker: {error}")
        return

    combatants = tracker["combatants"]
    current_turn_id = tracker["current_turn_id"]

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
            new_combatant = {
                "id": uuid4().hex,
                "name": name,
                "initiative": int(initiative),
                "dead": False,
                "current_hp": int(hit_points),
                "max_hp": int(hit_points),
            }
            combatants.append(new_combatant)
            try:
                persist_tracker(tracker)
            except (PyMongoError, ValueError) as error:
                st.error(f"Could not save initiative tracker: {error}")
            else:
                st.rerun(scope="fragment")

    if not combatants:
        st.caption("No combatants yet.")

    next_turn_column, reorder_column, reset_column = st.columns(3)
    living_combatants = [actor for actor in combatants if not actor["dead"]]
    with next_turn_column.container(key="initiative-next-turn"):
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
            except (PyMongoError, RuntimeError, ValueError) as error:
                st.error(f"Could not advance initiative: {error}")
            else:
                st.rerun(scope="fragment")

    with reorder_column.container(key="initiative-reorder"):
        reorder = st.button("Reorder by initiative", disabled=not combatants)

    if reset_column.button("Reset to default"):
        confirm_reset_tracker()

    if reorder:
        combatants.sort(key=lambda actor: actor["initiative"], reverse=True)
        try:
            persist_tracker(tracker)
        except (PyMongoError, ValueError) as error:
            st.error(f"Could not reorder initiative: {error}")
        else:
            st.rerun(scope="fragment")

    for actor in combatants:
        hp_key = f"current_hp_{actor['id']}"
        if st.session_state.get(hp_key, actor["current_hp"]) > actor["max_hp"]:
            st.session_state[hp_key] = actor["max_hp"]
        st.session_state.setdefault(hp_key, actor["current_hp"])
        is_current = actor["id"] == current_turn_id and not actor["dead"]
        container_key = (
            f"current-combatant-{actor['id']}"
            if is_current
            else f"combatant-{actor['id']}"
        )
        with st.container(border=True, key=container_key):
            (
                name_column,
                initiative_column,
                hp_value_column,
                hp_save_column,
                initiative_edit_column,
                dead_column,
                delete_column,
            ) = st.columns(
                [4, 1.2, 1, 0.5, 0.5, 0.5, 0.5]
            )
            name_column.markdown(
                f"**{actor['name']}** (max hitpoints: {actor['max_hp']})"
                + (" — DEAD" if actor["dead"] else "")
            )
            initiative_column.markdown(f"**Initiative:** {actor['initiative']}")
            hp_value_column.number_input(
                "HP",
                min_value=0,
                max_value=actor["max_hp"],
                step=1,
                key=hp_key,
                label_visibility="collapsed",
            )
            if hp_save_column.button(
                "❤️", help="Save hit points", key=f"hp_save_{actor['id']}"
            ):
                save_combatant_hp(actor["id"], st.session_state[hp_key])

            if initiative_edit_column.button("🎲", help="Change initiative", key=f"change_{actor['id']}"):
                edit_initiative(actor["id"])

            if dead_column.button(
                "💀",
                help="Revive" if actor["dead"] else "Make dead",
                key=f"dead_{actor['id']}",
            ):
                actor["dead"] = not actor["dead"]
                if actor["dead"] and current_turn_id == actor["id"]:
                    tracker["current_turn_id"] = None
                try:
                    persist_tracker(tracker)
                except (PyMongoError, ValueError) as error:
                    st.error(f"Could not update combatant status: {error}")
                else:
                    st.rerun(scope="fragment")

            with delete_column.container(key=f"initiative-delete-{actor['id']}"):
                if st.button("❌", help="Delete", key=f"delete_{actor['id']}"):
                    combatants.remove(actor)
                    if current_turn_id == actor["id"]:
                        tracker["current_turn_id"] = None
                    try:
                        persist_tracker(tracker)
                    except (PyMongoError, ValueError) as error:
                        st.error(f"Could not delete combatant: {error}")
                    else:
                        st.rerun(scope="fragment")
