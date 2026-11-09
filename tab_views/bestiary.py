import streamlit as st
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from .bestiary_service import get_bestiary_display, get_bestiary_index
from .initiative_service import add_bestiary_combatant
from .principal import Principal
from .stat_blocks import render_stat_block


def render_bestiary_tab(principal: Principal) -> None:
    if principal.role != "dm":
        st.error("Only the DM can access the bestiary.")
        return

    st.header("Bestiary")
    try:
        creatures = get_bestiary_index(principal)
    except (KeyError, PermissionError, PyMongoError) as error:
        st.error(f"Could not load bestiary: {error}")
        return

    if not creatures:
        st.info("The bestiary is empty.")
        return

    creature_types = sorted({entry["type"] for entry in creatures})
    sizes = sorted({entry["size"] for entry in creatures})
    sources = sorted({entry["document__title"] for entry in creatures})
    rating_values = {entry["challenge_rating"]: entry["cr"] for entry in creatures}
    ratings = sorted(rating_values, key=rating_values.__getitem__)
    filters, results_column = st.columns([1, 2])
    with filters:
        name = st.text_input("Search by name").strip().casefold()
        selected_type = st.selectbox("Type", ["All", *creature_types])
        selected_rating = st.selectbox("Challenge rating", ["All", *ratings])
        selected_size = st.selectbox("Size", ["All", *sizes])
        selected_source = st.selectbox("Source", ["All", *sources])

    matches = sorted(
        (
            entry for entry in creatures
            if name in entry["name"].casefold()
            and (selected_type == "All" or entry["type"] == selected_type)
            and (selected_rating == "All" or entry["challenge_rating"] == selected_rating)
            and (selected_size == "All" or entry["size"] == selected_size)
            and (selected_source == "All" or entry["document__title"] == selected_source)
        ),
        key=lambda entry: (entry["name"].casefold(), entry["document__title"], entry["slug"]),
    )
    with results_column:
        st.caption(f"{len(matches)} creatures found.")
        if not matches:
            return
        labels = {
            entry["slug"]: (
                f"{entry['name']} · CR {entry['challenge_rating']} · "
                f"{entry['type']} · {entry['size']} · {entry['document__title']}"
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

        creature = next(entry for entry in matches if entry["slug"] == selected)
        hit_points = creature.get("hit_points")
        if not isinstance(hit_points, int) or isinstance(hit_points, bool) or hit_points < 1:
            st.error("Creature hit points must be a positive whole number.")
        else:
            with st.form(f"bestiary_add_{selected}"):
                combatant_name = st.text_input("Name in initiative", value=creature["name"])
                initiative = st.number_input("Initiative", value=0, step=1)
                st.caption(f"Starting hit points: {hit_points}")
                add_creature = st.form_submit_button("Add to initiative")
            if add_creature:
                combatant_name = combatant_name.strip()
                if not combatant_name:
                    st.error("Enter a name for the combatant.")
                else:
                    try:
                        add_bestiary_combatant(
                            principal, combatant_name, int(initiative), hit_points, selected
                        )
                    except (KeyError, PermissionError, PyMongoError, RedisError, ValueError) as error:
                        st.error(f"Could not add creature to initiative: {error}")
                    else:
                        st.success(f"{combatant_name} added to initiative.")

        try:
            display = get_bestiary_display(principal, selected)
        except (FileNotFoundError, KeyError, PermissionError, PyMongoError) as error:
            st.error(f"Could not load creature: {error}")
            return
        render_stat_block(display)
