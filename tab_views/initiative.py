from copy import deepcopy
from concurrent.futures import Future
from typing import Literal

import streamlit as st
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from .bestiary_service import get_bestiary_display
from .initiative_models import InitiativeTracker
from .initiative_service import (
    add_combatant as add_combatant_to_tracker,
    advance_turn,
    create_dm_encounter,
    delete_dm_encounter,
    get_dm_tracker,
    get_player_tracker,
    list_dm_encounters,
    load_dm_encounter,
    overwrite_dm_encounter,
    queue_dm_tracker_save,
    remove_combatant,
    rename_dm_encounter,
    reorder_combatants,
    save_dm_tracker,
    set_combatant_hp,
    set_combatant_initiative,
    set_combatant_visibility,
    toggle_combatant_death,
)
from .principal import Principal
from .stat_blocks import render_stat_block_tab_link

TRACKER_SESSION_KEY = "initiative_tracker"
TRACKER_SAVE_FUTURES_KEY = "initiative_save_futures"
TRACKER_SAVE_ERROR_KEY = "initiative_save_error"
TRACKER_WIDGET_GENERATION_KEY = "initiative_widget_generation"
ENCOUNTERS_KEY = "initiative_encounters"
ENCOUNTER_NOTICE_KEY = "initiative_encounter_notice"


def get_session_tracker(principal: Principal) -> InitiativeTracker:
    tracker = get_dm_tracker(principal)
    st.session_state[TRACKER_SESSION_KEY] = deepcopy(tracker)
    return deepcopy(tracker)


def persist_tracker(principal: Principal, tracker: InitiativeTracker) -> None:
    save_dm_tracker(principal, tracker)
    st.session_state[TRACKER_SESSION_KEY] = deepcopy(tracker)
    st.session_state.pop(TRACKER_SAVE_ERROR_KEY, None)


def persist_tracker_async(principal: Principal, tracker: InitiativeTracker) -> None:
    future = queue_dm_tracker_save(principal, tracker)
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
        except (KeyError, PermissionError, PyMongoError, RedisError, RuntimeError, ValueError) as error:
            st.session_state[TRACKER_SAVE_ERROR_KEY] = str(error)
        else:
            st.session_state.pop(TRACKER_SAVE_ERROR_KEY, None)

    save_error = st.session_state.get(TRACKER_SAVE_ERROR_KEY)
    if save_error:
        st.error(f"Could not save initiative tracker: {save_error}")


def wait_for_tracker_saves() -> None:
    futures: list[Future[None]] = st.session_state.setdefault(TRACKER_SAVE_FUTURES_KEY, [])
    while futures:
        future = futures.pop(0)
        try:
            future.result()
        except (KeyError, PermissionError, PyMongoError, RedisError, RuntimeError, ValueError) as error:
            st.session_state[TRACKER_SAVE_ERROR_KEY] = str(error)
        else:
            st.session_state.pop(TRACKER_SAVE_ERROR_KEY, None)
    error = st.session_state.get(TRACKER_SAVE_ERROR_KEY)
    if error:
        raise ValueError(f"An earlier tracker save failed: {error}")


@st.dialog("Confirm encounter action")
def confirm_encounter_action(
    principal: Principal, encounter_id: str, name: str, action: Literal["load", "overwrite", "delete"]
) -> None:
    messages = {
        "load": f"Replace the live tracker with '{name}'? Players will see the loaded tracker.",
        "overwrite": f"Replace saved encounter '{name}' with the current live tracker?",
        "delete": f"Delete saved encounter '{name}'? This cannot be undone.",
    }
    labels = {"load": "Load encounter", "overwrite": "Overwrite encounter", "delete": "Delete encounter"}
    st.warning(messages[action])
    confirm_column, cancel_column = st.columns(2)
    if confirm_column.button(labels[action], type="primary"):
        try:
            if action == "load":
                wait_for_tracker_saves()
                tracker = load_dm_encounter(principal, encounter_id)
                st.session_state[TRACKER_SESSION_KEY] = deepcopy(tracker)
                st.session_state[TRACKER_WIDGET_GENERATION_KEY] = (
                    st.session_state.get(TRACKER_WIDGET_GENERATION_KEY, 0) + 1
                )
            elif action == "overwrite":
                wait_for_tracker_saves()
                overwrite_dm_encounter(principal, encounter_id)
            else:
                delete_dm_encounter(principal, encounter_id)
        except (KeyError, PermissionError, PyMongoError, RedisError, RuntimeError, ValueError) as error:
            st.error(f"Could not {action} encounter: {error}")
        else:
            st.session_state.pop(ENCOUNTERS_KEY, None)
            st.session_state[ENCOUNTER_NOTICE_KEY] = f"Encounter {action} complete."
            st.rerun(scope="app")
    if cancel_column.button("Cancel"):
        st.rerun(scope="app")


@st.dialog("Rename encounter")
def rename_encounter_dialog(principal: Principal, encounter_id: str, name: str) -> None:
    with st.form("rename_encounter"):
        new_name = st.text_input("Encounter name", value=name, max_chars=200)
        submitted = st.form_submit_button("Rename")
    if submitted:
        try:
            rename_dm_encounter(principal, encounter_id, new_name)
        except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
            st.error(f"Could not rename encounter: {error}")
        else:
            st.session_state.pop(ENCOUNTERS_KEY, None)
            st.session_state[ENCOUNTER_NOTICE_KEY] = "Encounter renamed."
            st.rerun(scope="app")


def render_encounter_controls(principal: Principal) -> None:
    with st.expander("Saved encounters"):
        notice = st.session_state.pop(ENCOUNTER_NOTICE_KEY, None)
        if notice:
            st.success(notice)
        st.caption(
            "Encounters save the live tracker. Changes to the tracker do not update a saved encounter "
            "until you overwrite it. Unsaved HP edits are not included."
        )
        with st.form("save_new_encounter", clear_on_submit=True):
            name = st.text_input("New encounter name", max_chars=200)
            save_new = st.form_submit_button("Save new encounter")
        if save_new:
            try:
                wait_for_tracker_saves()
                create_dm_encounter(principal, name)
            except (KeyError, PermissionError, PyMongoError, RedisError, RuntimeError, ValueError) as error:
                st.error(f"Could not save encounter: {error}")
            else:
                st.session_state.pop(ENCOUNTERS_KEY, None)
                st.session_state[ENCOUNTER_NOTICE_KEY] = "Encounter saved."
                st.rerun(scope="app")

        if st.button("Refresh encounters"):
            st.session_state.pop(ENCOUNTERS_KEY, None)
        try:
            if ENCOUNTERS_KEY not in st.session_state:
                st.session_state[ENCOUNTERS_KEY] = list_dm_encounters(principal)
            encounters = st.session_state[ENCOUNTERS_KEY]
        except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
            st.error(f"Could not load saved encounters: {error}")
            return
        if not encounters:
            st.caption("No saved encounters.")
            return
        by_id = {encounter.id: encounter for encounter in encounters}
        selected_id = st.selectbox(
            "Saved encounter",
            options=list(by_id),
            format_func=lambda encounter_id: (
                f"{by_id[encounter_id].name} — "
                f"{by_id[encounter_id].created_at[:19].replace('T', ' ')} UTC "
                f"[{encounter_id}]"
            ),
            key="initiative_selected_encounter",
        )
        encounter = by_id[selected_id]
        with st.container(horizontal=True):
            if st.button("Load"):
                confirm_encounter_action(principal, encounter.id, encounter.name, "load")
            if st.button("Overwrite"):
                confirm_encounter_action(principal, encounter.id, encounter.name, "overwrite")
            if st.button("Rename"):
                rename_encounter_dialog(principal, encounter.id, encounter.name)
            if st.button("Delete"):
                confirm_encounter_action(principal, encounter.id, encounter.name, "delete")


@st.dialog("Change initiative")
def edit_initiative(principal: Principal, combatant_id: str) -> None:
    try:
        tracker = get_session_tracker(principal)
    except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not load initiative tracker: {error}")
        return

    actor = next(
        (item for item in tracker.combatants if item.id == combatant_id),
        None,
    )
    if actor is None:
        st.error("Combatant no longer exists.")
        return

    with st.form(f"edit_initiative_{combatant_id}"):
        initiative = st.number_input(
            "Initiative", value=actor.initiative, step=1
        )
        save = st.form_submit_button("Save")

    if save:
        try:
            set_combatant_initiative(principal, tracker, combatant_id, int(initiative))
            persist_tracker(principal, tracker)
        except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
            st.error(f"Could not update initiative: {error}")
        else:
            st.rerun(scope="app")


def save_combatant_hp(principal: Principal, combatant_id: str, current_hp: int) -> None:
    try:
        tracker = get_session_tracker(principal)
        set_combatant_hp(principal, tracker, combatant_id, current_hp)
        persist_tracker(principal, tracker)
    except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not update hit points: {error}")
    else:
        st.rerun(scope="fragment")


def save_combatant_visibility(principal: Principal, combatant_id: str, checkbox_key: str) -> None:
    try:
        tracker = get_session_tracker(principal)
        set_combatant_visibility(principal, tracker, combatant_id, st.session_state[checkbox_key])
        persist_tracker(principal, tracker)
    except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not update combatant visibility: {error}")


def _render_tracker_style() -> None:
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


@st.fragment(run_every=1)
def render_player_initiative_tab(principal: Principal) -> None:
    _render_tracker_style()
    try:
        tracker = get_player_tracker(principal)
    except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not load initiative tracker: {error}")
        return

    if not tracker.combatants:
        st.caption("No combatants yet.")
    for actor in tracker.combatants:
        is_current = actor.id == tracker.current_turn_id and not actor.dead
        container_key = (
            f"current-combatant-{actor.id}" if is_current else f"combatant-{actor.id}"
        )
        with st.container(border=True, key=container_key):
            name_column, initiative_column = st.columns([4, 1.2])
            name_column.markdown(
                f"**{actor.name}**" + (" — DEAD" if actor.dead else "")
            )
            initiative_column.markdown(f"**Initiative:** {actor.initiative}")
            if actor.dead:
                st.caption("Combatant is defeated.")


@st.fragment(run_every=1)
def render_dm_initiative_tab(principal: Principal) -> None:
    show_tracker_save_status()
    _render_tracker_style()
    try:
        tracker = get_session_tracker(principal)
    except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
        st.error(f"Could not load initiative tracker: {error}")
        return

    combatants = tracker.combatants
    current_turn_id = tracker.current_turn_id

    if principal.role == "dm":
        render_encounter_controls(principal)
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
            try:
                add_combatant_to_tracker(principal, tracker, name, int(initiative), int(hit_points))
                persist_tracker(principal, tracker)
            except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                st.error(f"Could not save initiative tracker: {error}")
            else:
                st.rerun(scope="fragment")

    displayed_combatants = combatants
    if not displayed_combatants:
        st.caption("No combatants yet.")

    if principal.role == "dm":
        living_combatants = [actor for actor in combatants if not actor.dead]
        with st.container(horizontal=True):
            with st.container(key="initiative-next-turn", width="content"):
                if st.button("Next turn", disabled=not living_combatants, type="primary"):
                    try:
                        advance_turn(principal, tracker)
                        persist_tracker_async(principal, tracker)
                    except (KeyError, PermissionError, PyMongoError, RedisError, RuntimeError, ValueError) as error:
                        st.error(f"Could not advance initiative: {error}")
                    else:
                        st.rerun(scope="fragment")

            with st.container(key="initiative-reorder", width="content"):
                reorder = st.button("Reorder by initiative", disabled=not combatants)

        if reorder:
            try:
                reorder_combatants(principal, tracker)
                persist_tracker(principal, tracker)
            except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                st.error(f"Could not reorder initiative: {error}")
            else:
                st.rerun(scope="fragment")

    for actor in displayed_combatants:
        is_current = actor.id == current_turn_id and not actor.dead
        container_key = (
            f"current-combatant-{actor.id}"
            if is_current
            else f"combatant-{actor.id}"
        )
        with st.container(border=True, key=container_key):
            if principal.role == "dm":
                (
                    name_column,
                    initiative_column,
                    hp_value_column,
                    buttons_column,
                ) = st.columns([4, 1.2, 1, 2])
                with name_column:
                    with st.container(horizontal=True, gap="small", vertical_alignment="top"):
                        st.markdown(
                            f"**{actor.name}** (max hitpoints: {actor.max_hp})"
                            + (" — DEAD" if actor.dead else ""),
                            width="content",
                        )
                        slug = actor.creature_slug
                        if slug is not None:
                            if not isinstance(slug, str) or not slug:
                                st.error("Creature identifier is invalid.")
                            else:
                                try:
                                    display = get_bestiary_display(principal, slug)
                                except (FileNotFoundError, KeyError, PermissionError, PyMongoError, ValueError) as error:
                                    st.error(f"Could not load creature stat block: {error}")
                                else:
                                    render_stat_block_tab_link(display, actor.name)
                    generation = st.session_state.get(TRACKER_WIDGET_GENERATION_KEY, 0)
                    visibility_key = f"visible_{generation}_{actor.id}"
                    st.session_state[visibility_key] = actor.visible
                    st.checkbox(
                        "Visible",
                        key=visibility_key,
                        on_change=save_combatant_visibility,
                        args=(principal, actor.id, visibility_key),
                        help="Show this combatant to players.",
                    )
                initiative_column.markdown(f"**Initiative:** {actor.initiative}")
                hp_key = f"current_hp_{generation}_{actor.id}"
                if st.session_state.get(hp_key, actor.current_hp) > actor.max_hp:
                    st.session_state[hp_key] = actor.max_hp
                st.session_state.setdefault(hp_key, actor.current_hp)
                hp_value_column.number_input(
                    "HP",
                    min_value=0,
                    max_value=actor.max_hp,
                    step=1,
                    key=hp_key,
                    label_visibility="collapsed",
                )
                with buttons_column.container(horizontal=True, gap="small"):
                    if st.button(
                        "❤️", help="Save hit points", key=f"hp_save_{actor.id}"
                    ):
                        save_combatant_hp(principal, actor.id, st.session_state[hp_key])

                    if st.button("🎲", help="Change initiative", key=f"change_{actor.id}"):
                        edit_initiative(principal, actor.id)

                    if st.button(
                        "💀",
                        help="Revive" if actor.dead else "Make dead",
                        key=f"dead_{actor.id}",
                    ):
                        try:
                            toggle_combatant_death(principal, tracker, actor.id)
                            persist_tracker(principal, tracker)
                        except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                            st.error(f"Could not update combatant status: {error}")
                        else:
                            st.rerun(scope="fragment")

                    with st.container(key=f"initiative-delete-{actor.id}", width="content"):
                        if st.button("❌", help="Delete", key=f"delete_{actor.id}"):
                            try:
                                remove_combatant(principal, tracker, actor.id)
                                persist_tracker(principal, tracker)
                            except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                                st.error(f"Could not delete combatant: {error}")
                            else:
                                st.rerun(scope="fragment")
