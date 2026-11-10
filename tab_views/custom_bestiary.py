from typing import TypeVar

import streamlit as st
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from .bestiary_service import add_creature, get_custom_creatures, save_custom_creature
from .data_models import CustomCreature
from .principal import Principal

_FieldValue = TypeVar("_FieldValue", str, int)


def render_custom_bestiary_tab(principal: Principal) -> None:
    if principal.role != "dm":
        st.error("Only the DM can edit custom creatures.")
        return

    st.header("Custom bestiary editor")
    try:
        creatures = get_custom_creatures(principal)
    except (KeyError, PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load custom creatures: {error}")
        return

    pending = st.session_state.pop("custom_editor_pending_selection", None)
    if pending is not None:
        st.session_state["custom_editor_selection"] = pending
    notice = st.session_state.pop("custom_editor_notice", None)
    if notice:
        st.success(notice)

    by_slug = {creature.slug: creature for creature in creatures}
    selected = st.selectbox(
        "Create or edit a creature",
        ["", *by_slug],
        format_func=lambda slug: (
            f"{by_slug[slug].name} ({slug.removeprefix('custom:')[:8]})"
            if slug else "New creature"
        ),
        key="custom_editor_selection",
    )
    if st.session_state.get("custom_editor_loaded_slug") != selected:
        st.session_state["custom_editor_loaded_slug"] = selected
        st.session_state["custom_editor_original"] = by_slug.get(selected)
    original: CustomCreature | None = st.session_state.get("custom_editor_original")
    if selected and original is None:
        st.error("Creature no longer exists. Select another creature.")
        return

    def initial(field: str, default: _FieldValue) -> _FieldValue:
        if original is None:
            return default
        value = getattr(original, field)
        if not isinstance(value, type(default)):
            raise ValueError(f"Invalid value for custom creature field {field}.")
        return value

    suffix = selected or "new"
    with st.form(f"custom_creature_{suffix}"):
        name = st.text_input("Name", value=initial("name", ""), key=f"custom_name_{suffix}")
        left, right = st.columns(2)
        with left:
            creature_type = st.text_input("Type", value=initial("type", ""), key=f"custom_type_{suffix}")
            size = st.text_input("Size", value=initial("size", ""), key=f"custom_size_{suffix}")
            alignment = st.text_input("Alignment", value=initial("alignment", ""), key=f"custom_alignment_{suffix}")
            rating = st.text_input(
                "Challenge rating", value=initial("challenge_rating", "0"),
                help="Enter a number or fraction, such as 1/2.", key=f"custom_cr_{suffix}",
            )
        with right:
            armor_class = st.text_input("Armor class", value=initial("armor_class", ""), key=f"custom_ac_{suffix}")
            hit_points = st.number_input(
                "Hit points", min_value=1, value=initial("hit_points", 1),
                step=1, key=f"custom_hp_{suffix}",
            )
            hit_dice = st.text_input("Hit dice", value=initial("hit_dice", ""), key=f"custom_dice_{suffix}")
            speed = st.text_input("Speed", value=initial("speed", ""), key=f"custom_speed_{suffix}")

        st.subheader("Ability scores")
        columns = st.columns(3)
        abilities = {}
        for index, field in enumerate(("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")):
            with columns[index % 3]:
                abilities[field] = st.number_input(
                    field.capitalize(), min_value=1, value=initial(field, 10),
                    step=1, key=f"custom_{field}_{suffix}",
                )

        st.subheader("Additional statistics")
        additional_fields = (
            ("saving_throws", "Saving throws"), ("skills", "Skills"),
            ("damage_vulnerabilities", "Damage vulnerabilities"),
            ("damage_resistances", "Damage resistances"),
            ("damage_immunities", "Damage immunities"),
            ("condition_immunities", "Condition immunities"),
            ("senses", "Senses"), ("languages", "Languages"),
        )
        additional = {
            field: st.text_input(label, value=initial(field, ""), key=f"custom_{field}_{suffix}")
            for field, label in additional_fields
        }

        st.subheader("Abilities and actions")
        st.caption("Enter any number of named abilities or actions in each section.")
        section_fields = (
            ("traits", "Traits and special abilities"), ("actions", "Actions"),
            ("bonus_actions", "Bonus actions"), ("reactions", "Reactions"),
            ("legendary_actions", "Legendary actions"), ("lair_actions", "Lair actions"),
            ("notes", "Other details"),
        )
        sections = {
            field: st.text_area(label, value=initial(field, ""), key=f"custom_{field}_{suffix}")
            for field, label in section_fields
        }
        submitted = st.form_submit_button("Save creature")

    if submitted:
        values = {
            "name": name, "type": creature_type, "size": size, "alignment": alignment,
            "challenge_rating": rating, "armor_class": armor_class, "hit_points": int(hit_points),
            "hit_dice": hit_dice, "speed": speed, **abilities, **additional, **sections,
        }
        try:
            saved = save_custom_creature(principal, values, original)
        except (KeyError, PermissionError, PyMongoError, ValueError) as error:
            st.error(f"Could not save creature: {error}")
        else:
            st.session_state["custom_editor_original"] = saved
            st.session_state["custom_editor_loaded_slug"] = saved.slug
            st.session_state["custom_editor_pending_selection"] = saved.slug
            st.session_state["custom_editor_notice"] = f"{saved.name} saved."
            st.rerun()

    if original is not None:
        with st.form(f"custom_add_{original.slug}"):
            combatant_name = st.text_input("Name in initiative", value=original.name)
            initiative = st.number_input("Initiative", value=0, step=1)
            st.caption(f"Starting hit points: {original.hit_points}")
            add_submitted = st.form_submit_button("Add saved creature to initiative")
        if add_submitted:
            try:
                add_creature(principal, original.as_bestiary_entry(), combatant_name, int(initiative))
            except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                st.error(f"Could not add creature to initiative: {error}")
            else:
                st.success(f"{combatant_name.strip()} added to initiative.")
