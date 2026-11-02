import json
from uuid import uuid4

import streamlit as st

from .user_data import read_user_data


@st.dialog("Change initiative")
def edit_initiative(combatant_id: str) -> None:
    try:
        tracker = load_tracker()
    except (OSError, json.JSONDecodeError, ValueError) as error:
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
            save_tracker(tracker)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            st.error(f"Could not update initiative: {error}")
        else:
            st.rerun()


def load_tracker() -> dict:
    _, dm_data = read_user_data("dm")
    tracker = dm_data.get(
        "initiative_tracker",
        {"combatants": [], "current_turn_id": None},
    )

    if not isinstance(tracker, dict) or not isinstance(tracker.get("combatants"), list):
        raise ValueError("Initiative tracker data must contain a combatants list.")

    for combatant in tracker["combatants"]:
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
            not isinstance(current_hp, int)
            or not isinstance(max_hp, int)
            or current_hp < 0
            or max_hp < 1
            or current_hp > max_hp
        ):
            raise ValueError("Combatant hit points are invalid.")

    return {
        "combatants": tracker["combatants"],
        "current_turn_id": tracker.get("current_turn_id"),
    }


def save_tracker(tracker: dict) -> None:
    dm_file, dm_data = read_user_data("dm")
    dm_data["initiative_tracker"] = tracker
    dm_file.write_text(json.dumps(dm_data, indent=2) + "\n", encoding="utf-8")


def save_combatant_hp(combatant_id: str, current_hp: int) -> None:
    try:
        tracker = load_tracker()
        actor = next(
            item for item in tracker["combatants"] if item["id"] == combatant_id
        )
        actor["current_hp"] = min(current_hp, actor["max_hp"])
        save_tracker(tracker)
    except (OSError, json.JSONDecodeError, ValueError, StopIteration) as error:
        st.error(f"Could not update hit points: {error}")
    else:
        st.rerun()


def render_initiative_tab() -> None:
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
        tracker = load_tracker()
    except (OSError, json.JSONDecodeError, ValueError) as error:
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
                save_tracker(tracker)
            except (OSError, json.JSONDecodeError, ValueError) as error:
                st.error(f"Could not save initiative tracker: {error}")
            else:
                st.rerun()

    if not combatants:
        st.caption("No combatants yet.")
        return

    next_turn_column, reorder_column = st.columns(2)
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
                save_tracker(tracker)
            except (OSError, json.JSONDecodeError, ValueError) as error:
                st.error(f"Could not advance initiative: {error}")
            else:
                st.rerun()

    with reorder_column.container(key="initiative-reorder"):
        reorder = st.button("Reorder by initiative")

    if reorder:
        combatants.sort(key=lambda actor: actor["initiative"], reverse=True)
        try:
            save_tracker(tracker)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            st.error(f"Could not reorder initiative: {error}")
        else:
            st.rerun()

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
                    save_tracker(tracker)
                except (OSError, json.JSONDecodeError, ValueError) as error:
                    st.error(f"Could not update combatant status: {error}")
                else:
                    st.rerun()

            with delete_column.container(key=f"initiative-delete-{actor['id']}"):
                if st.button("❌", help="Delete", key=f"delete_{actor['id']}"):
                    combatants.remove(actor)
                    if current_turn_id == actor["id"]:
                        tracker["current_turn_id"] = None
                    try:
                        save_tracker(tracker)
                    except (OSError, json.JSONDecodeError, ValueError) as error:
                        st.error(f"Could not delete combatant: {error}")
                    else:
                        st.rerun()
