from html import escape
import streamlit as st
from bson.errors import InvalidDocument
from pymongo.errors import PyMongoError

from .config import load_character_card_players
from .character_service import (
    CARD_STATS,
    CLASS_FIELDS,
    PLAYER_TEXT_FIELDS,
    CharacterEdit,
    CharacterInputError,
    get_character,
    get_dm_character_cards,
    get_dm_unread_counts,
    resolve_character_players,
    update_character,
    valid_website_url,
)
from .principal import Principal


def _stat_value(data: dict, field: str):
    return data.get(field)


def _render_portrait(data: dict) -> None:
    portrait = data.get("portrait")
    if portrait is not None:
        if isinstance(portrait, bytes) and portrait:
            st.image(portrait, width="stretch")
        else:
            st.error("Character picture must be non-empty binary data.")


def _render_character_details(data: dict) -> None:
    parts = []
    if data.get("race"):
        parts.append(escape(str(data["race"])))

    class_parts = []
    for entry in data.get("classes", []):
        labels = []
        for label, name_field, url_field in (
            ("Class", "class_name", "class_url"),
            ("Subclass", "subclass_name", "subclass_url"),
        ):
            name, url = entry[name_field], entry[url_field]
            if url and not valid_website_url(url):
                st.error(f"{label} website URL is invalid.")
                url = ""
            if name or url:
                text = escape(name or f"{label} reference")
                if url:
                    text = (
                        f'<a href="{escape(url, quote=True)}" '
                        f'target="_blank" rel="noopener noreferrer">{text}</a>'
                    )
                labels.append(text)
        if entry["levels"]:
            labels.append(f"Level {escape(entry['levels'])}")
        if labels:
            class_parts.append(", ".join(labels))
    if class_parts:
        parts.append(" / ".join(class_parts))
    if parts:
        st.html(f"<strong>{' '.join(parts)}</strong>")


@st.fragment
def _edit_character_card(principal: Principal, username: str) -> None:
    is_dm = principal.role == "dm"
    edit_key = "editing_character_card" if is_dm else "editing_player_character"
    try:
        data = get_character(principal, username).model_dump(exclude_unset=True)
    except (FileNotFoundError, PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load character data: {error}")
        if st.button("Back to characters"):
            st.session_state.pop(edit_key, None)
            st.rerun()
        return

    character_name = data.get("character", "")
    initiative_bonus = data.get("initiative_bonus", 0)
    classes = data.get("classes", [])

    st.subheader(f"Edit character: {username}")
    st.caption("Leave a stat blank if it is unknown.")
    initiative_input = None
    with st.form(f"character_card_{username}"):
        character = st.text_input("Character name", value=character_name)
        stats = {
            field: st.text_input(
                label,
                value=str(value) if (value := _stat_value(data, field)) is not None else "",
            )
            for field, label in CARD_STATS
        }
        if not is_dm:
            initiative_input = st.text_input("Initiative bonus", value=f"{initiative_bonus:+}")
        st.write("Classes")
        class_columns = {
            field: [entry[field] for entry in classes] or [""]
            for field, _ in CLASS_FIELDS
        }
        edited_classes = st.data_editor(
            class_columns,
            column_config={
                field: st.column_config.TextColumn(label) for field, label in CLASS_FIELDS
            },
            num_rows="dynamic",
            hide_index=True,
            key=f"character_classes_{username}",
        )
        player_text = {}
        if not is_dm:
            player_text = {
                field: st.text_area(label, value=data.get(field, ""))
                for field, label in PLAYER_TEXT_FIELDS
            }
        portrait = st.file_uploader(
            "Character picture", type=["png", "jpg", "jpeg", "webp"]
        )
        remove_portrait = st.checkbox("Remove current picture") if data.get("portrait") else False
        save = st.form_submit_button("Save", type="primary")
        cancel = st.form_submit_button("Cancel")

    if cancel:
        st.session_state.pop(edit_key, None)
        st.rerun()
    if not save:
        return
    try:
        update_character(
            principal,
            username,
            CharacterEdit(
                character=character,
                stats=stats,
                classes=edited_classes,
                initiative_bonus=initiative_input,
                player_text=player_text,
                portrait=portrait.getvalue() if portrait is not None else None,
                remove_portrait=remove_portrait,
            ),
        )
    except CharacterInputError as error:
        st.error(str(error))
    except (FileNotFoundError, PermissionError, PyMongoError, InvalidDocument, ValueError) as error:
        st.error(f"Could not save character data: {error}")
    else:
        st.session_state.pop(edit_key, None)
        st.toast("Character saved.")
        st.rerun()


@st.fragment(run_every=5)
def _render_dm_characters(principal: Principal, player_names: list[str]) -> None:
    try:
        characters = get_dm_character_cards(principal, player_names)
        unread = get_dm_unread_counts(principal, player_names)
    except (PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load characters or unread messages: {error}")
        return
    if not player_names:
        st.info("No configured player accounts to display.")
        return
    columns = st.columns(2)
    for index, username in enumerate(player_names):
        character = characters.get(username)
        data = character.model_dump(exclude_unset=True) if character is not None else None
        with columns[index % len(columns)], st.container(border=True):
            name = data.get("character") if data else None
            count = unread.get(username, 0)
            display_name = name if isinstance(name, str) and name else "Character name not set"
            st.subheader(f"{display_name} 🔔" if count else display_name)
            st.caption(f"{username} · {count} unread" if count else username)
            if data is None:
                st.error("Character data not found.")
                continue
            _render_character_details(data)
            _render_portrait(data)
            for start in range(0, len(CARD_STATS), 2):
                stats = st.columns(2)
                for column, (field, label) in zip(stats, CARD_STATS[start : start + 2]):
                    value = _stat_value(data, field)
                    column.write(f"{label}: {value if value is not None else 'Not set'}")
            if st.button("Edit", key=f"edit_character_card_{username}", icon=":material/edit:"):
                st.session_state["editing_character_card"] = username
                st.rerun()


def render_dm_character_tab(principal: Principal, player_names: list[str]) -> None:
    if "character_card_players" not in st.session_state:
        try:
            st.session_state["character_card_players"] = load_character_card_players()
        except (OSError, ValueError) as error:
            st.error(f"Could not load character card configuration: {error}")
            return

    selected_players, unmatched = resolve_character_players(
        st.session_state["character_card_players"], player_names
    )
    for configured, count in unmatched:
        st.warning(f"Character card player {configured!r} matches {count} player accounts.")

    username = st.session_state.get("editing_character_card")
    if username in selected_players:
        _edit_character_card(principal, username)
    else:
        _render_dm_characters(principal, selected_players)


def render_character_tab(principal: Principal):
    username = principal.username
    if st.session_state.get("editing_player_character") == username:
        _edit_character_card(principal, username)
        return

    try:
        user_data = get_character(principal, username).model_dump(exclude_unset=True)
    except FileNotFoundError:
        st.error(f"User data not found for {username}.")
    except (PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load character data: {error}")
    else:
        if st.button("Edit character", icon=":material/edit:"):
            st.session_state["editing_player_character"] = username
            st.rerun()
        if "character" in user_data:
            with st.container(border=True):
                st.subheader("Character Data")
                st.title(user_data["character"])
                _render_portrait(user_data)
                _render_character_details(user_data)
                if "gender" in user_data:
                    st.caption(user_data["gender"])

                stats = []
                for field, label in CARD_STATS:
                    value = _stat_value(user_data, field)
                    stats.append((label, value if value is not None else "Not set"))
                initiative_bonus = user_data.get("initiative_bonus", 0)
                if isinstance(initiative_bonus, int) and not isinstance(initiative_bonus, bool):
                    stats.append(("Initiative bonus", f"{initiative_bonus:+}"))
                else:
                    st.error("Initiative bonus must be a whole number.")
                for start in range(0, len(stats), 2):
                    row = stats[start : start + 2]
                    stat_columns = st.columns(len(row))
                    for column, (label, value) in zip(stat_columns, row):
                        column.metric(label, value)
                for field, label in PLAYER_TEXT_FIELDS:
                    text = user_data.get(field)
                    if text:
                        if isinstance(text, str):
                            st.subheader(label)
                            if field == "character_description":
                                st.markdown(text)
                            else:
                                st.text(text)
                        else:
                            st.error(f"{label} must be text.")
        elif "character_description" in user_data:
            with st.container(border=True):
                st.subheader("Character Data")
                description = user_data["character_description"]
                if isinstance(description, str):
                    st.markdown(description)
                else:
                    st.error("Character description must be text.")
