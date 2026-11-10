import streamlit as st
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from .bestiary_service import (
    BestiaryFilters, add_creature, bestiary_options, creature_hit_points,
    filter_bestiary, get_bestiary_display, get_bestiary_index,
)
from .principal import Principal
from .stat_blocks import render_stat_block


def render_bestiary_tab(principal: Principal) -> None:
    if principal.role != "dm":
        st.error("Only the DM can access the bestiary.")
        return

    st.header("Bestiary")
    try:
        creatures = get_bestiary_index(principal)
    except (KeyError, PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load bestiary: {error}")
        return

    if not creatures:
        st.info("The bestiary is empty.")
        return

    options = bestiary_options(creatures)
    filters, results_column = st.columns([1, 2])
    with filters:
        name = st.text_input("Search by name")
        selected_type = st.selectbox("Type", ["All", *options.types])
        selected_rating = st.selectbox("Challenge rating", ["All", *options.ratings])
        selected_size = st.selectbox("Size", ["All", *options.sizes])
        selected_source = st.selectbox("Source", ["All", *options.sources])

    matches = filter_bestiary(
        creatures, BestiaryFilters(name, selected_type, selected_rating, selected_size, selected_source)
    )
    with results_column:
        st.caption(f"{len(matches)} creatures found.")
        if not matches:
            return
        labels = {
            entry.slug: (
                f"{entry.name} · CR {entry.challenge_rating} · "
                f"{entry.type} · {entry.size} · {entry.document__title}"
            )
            for entry in matches
        }
        selected = st.selectbox(
            "Creature",
            list(labels),
            index=None,
            placeholder="Choose a creature",
            format_func=labels.__getitem__,
        )
        if selected is None:
            return

        creature = next(entry for entry in matches if entry.slug == selected)
        if selected.startswith("custom:"):
            st.caption("Edit this creature in the Custom Bestiary Editor tab.")
        try:
            hit_points = creature_hit_points(creature)
        except ValueError as error:
            st.error(str(error))
        else:
            with st.form(f"bestiary_add_{selected}"):
                combatant_name = st.text_input("Name in initiative", value=creature.name)
                initiative = st.number_input("Initiative", value=0, step=1)
                st.caption(f"Starting hit points: {hit_points}")
                submitted = st.form_submit_button("Add to initiative")
            if submitted:
                try:
                    add_creature(principal, creature, combatant_name, int(initiative))
                except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                    st.error(f"Could not add creature to initiative: {error}")
                else:
                    st.success(f"{combatant_name.strip()} added to initiative.")

        try:
            display = get_bestiary_display(principal, selected)
        except (FileNotFoundError, KeyError, PermissionError, PyMongoError, ValueError) as error:
            st.error(f"Could not load creature: {error}")
            return
        render_stat_block(display)
