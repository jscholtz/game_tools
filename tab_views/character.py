from html import escape
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

import streamlit as st
from bson.errors import InvalidDocument
from PIL import Image, UnidentifiedImageError
from pymongo.errors import PyMongoError

from .config import load_character_card_players
from .database import (
    load_character_cards,
    load_dm_unread_counts,
    load_private_data,
    save_character_card,
)

CARD_STATS = (
    ("passive_perception", "Passive perception"),
    ("passive_insight", "Passive insight"),
    ("armor_class", "Armor class"),
    ("max_hp", "Maximum HP"),
)
CLASS_FIELDS = (
    ("class_name", "Class"),
    ("class_url", "Class URL"),
    ("subclass_name", "Subclass"),
    ("subclass_url", "Subclass URL"),
    ("levels", "Levels"),
)
PLAYER_TEXT_FIELDS = (
    ("character_description", "Character description"),
    ("background", "Character background"),
    ("story", "Character story"),
)


def _stat_value(data: dict, field: str):
    return data.get(field)


def _valid_website_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _render_portrait(data: dict) -> None:
    portrait = data.get("portrait")
    if portrait is not None:
        if isinstance(portrait, bytes) and portrait:
            st.image(portrait, width="stretch")
        else:
            st.error("Character picture must be non-empty binary data.")


def _character_classes(data: dict) -> list[dict[str, str]]:
    classes = data.get("classes", [])
    if not isinstance(classes, list):
        raise ValueError("Character classes must be a list.")
    expected = {field for field, _ in CLASS_FIELDS}
    if any(
        not isinstance(entry, dict)
        or set(entry) != expected
        or any(not isinstance(entry[field], str) for field, _ in CLASS_FIELDS)
        for entry in classes
    ):
        raise ValueError("Each character class must contain the five text fields.")
    return classes


def _render_character_details(data: dict) -> None:
    parts = []
    if data.get("race"):
        parts.append(escape(str(data["race"])))

    try:
        classes = _character_classes(data)
    except ValueError as error:
        st.error(f"Could not display character classes: {error}")
        return
    class_parts = []
    for entry in classes:
        labels = []
        for label, name_field, url_field in (
            ("Class", "class_name", "class_url"),
            ("Subclass", "subclass_name", "subclass_url"),
        ):
            name, url = entry[name_field], entry[url_field]
            if url and not _valid_website_url(url):
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
def _edit_character_card(username: str, *, is_dm: bool) -> None:
    role = st.session_state.get("logged_in_role")
    if (is_dm and role != "dm") or (
        not is_dm and (role != "player" or st.session_state.get("logged_in_user") != username)
    ):
        st.error("You can only edit your own character.")
        return
    edit_key = "editing_character_card" if is_dm else "editing_player_character"
    try:
        data = load_private_data(username)
    except (FileNotFoundError, PyMongoError) as error:
        st.error(f"Could not load character data: {error}")
        if st.button("Back to characters"):
            st.session_state.pop(edit_key, None)
            st.rerun()
        return

    character_name = data.get("character", "")
    if not isinstance(character_name, str) or (
        not is_dm
        and any(not isinstance(data.get(field, ""), str) for field, _ in PLAYER_TEXT_FIELDS)
    ):
        st.error("Character name and character text fields must be text.")
        if st.button("Back to characters"):
            st.session_state.pop(edit_key, None)
            st.rerun()
        return

    initiative_bonus = data.get("initiative_bonus", 0)
    if not is_dm and (
        not isinstance(initiative_bonus, int) or isinstance(initiative_bonus, bool)
    ):
        st.error("Initiative bonus must be a whole number.")
        if st.button("Back to characters"):
            st.session_state.pop(edit_key, None)
            st.rerun()
        return

    try:
        classes = _character_classes(data)
    except ValueError as error:
        st.error(f"Could not edit character classes: {error}")
        if st.button("Back to characters"):
            st.session_state.pop(edit_key, None)
            st.rerun()
        return

    st.subheader(f"Edit character: {username}")
    st.caption("Leave a stat blank if it is unknown.")
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
    if not character.strip():
        st.error("Enter a character name.")
        return
    fields: dict[str, Any] = {"character": character.strip()}
    removed = []
    for field, label in CARD_STATS:
        value = stats[field].strip()
        if not value:
            removed.append(field)
            continue
        if not value.isascii() or not value.isdecimal():
            st.error(f"{label} must be a non-negative whole number.")
            return
        number = int(value)
        if number > 2**31 - 1:
            st.error(f"{label} is too large.")
            return
        fields[field] = number
    if not is_dm:
        bonus = initiative_input.strip()
        digits = bonus.removeprefix("+").removeprefix("-")
        if (
            not digits
            or not digits.isascii()
            or not digits.isdecimal()
            or bonus not in (digits, f"+{digits}", f"-{digits}")
        ):
            st.error("Initiative bonus must be a whole number.")
            return
        if len(digits.lstrip("0")) > 10:
            st.error("Initiative bonus is too large.")
            return
        number = int(digits.lstrip("0") or "0")
        if bonus.startswith("-"):
            number = -number
        if not -(2**31) <= number <= 2**31 - 1:
            st.error("Initiative bonus is too large.")
            return
        fields["initiative_bonus"] = number
    updated_classes = []
    for row in zip(*(edited_classes[field] for field, _ in CLASS_FIELDS), strict=True):
        if any(value is not None and not isinstance(value, str) for value in row):
            st.error("Class fields must contain text.")
            return
        entry = {
            field: value.strip() if value is not None else ""
            for (field, _), value in zip(CLASS_FIELDS, row, strict=True)
        }
        if not any(entry.values()):
            continue
        if not entry["class_name"]:
            st.error("Each class must have a name.")
            return
        for field, label in (("class_url", "Class"), ("subclass_url", "Subclass")):
            if entry[field] and not _valid_website_url(entry[field]):
                st.error(f"{label} website must be a valid HTTP or HTTPS URL.")
                return
        levels = entry["levels"]
        if levels and (
            not levels.isascii()
            or not levels.isdecimal()
            or not levels.strip("0")
        ):
            st.error("Class levels must be a positive whole number or blank.")
            return
        updated_classes.append(entry)
    fields["classes"] = updated_classes
    if not is_dm:
        fields.update(player_text)
    if portrait is not None:
        picture = portrait.getvalue()
        if not picture:
            st.error("The uploaded picture is empty.")
            return
        try:
            with Image.open(BytesIO(picture)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            st.error("The uploaded picture is invalid or too large.")
            return
        fields["portrait"] = picture
    elif remove_portrait:
        removed.append("portrait")
    try:
        save_character_card(username, fields, removed)
    except (FileNotFoundError, PyMongoError, InvalidDocument) as error:
        st.error(f"Could not save character data: {error}")
    else:
        st.session_state.pop(edit_key, None)
        st.toast("Character saved.")
        st.rerun()


@st.fragment(run_every=5)
def _render_dm_characters(player_names: list[str]) -> None:
    try:
        characters = load_character_cards(player_names)
        unread = load_dm_unread_counts(player_names)
    except PyMongoError as error:
        st.error(f"Could not load characters or unread messages: {error}")
        return
    if not player_names:
        st.info("No configured player accounts to display.")
        return
    columns = st.columns(2)
    for index, username in enumerate(player_names):
        data = characters.get(username)
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


def render_dm_character_tab(player_names: list[str]) -> None:
    if "character_card_players" not in st.session_state:
        try:
            st.session_state["character_card_players"] = load_character_card_players()
        except (OSError, ValueError) as error:
            st.error(f"Could not load character card configuration: {error}")
            return

    player_lookup: dict[str, list[str]] = {}
    for player in player_names:
        player_lookup.setdefault(player.casefold(), []).append(player)
    selected_players = []
    for configured in st.session_state["character_card_players"]:
        matches = player_lookup.get(configured.casefold(), [])
        if len(matches) != 1:
            st.warning(
                f"Character card player {configured!r} matches {len(matches)} player accounts."
            )
        else:
            selected_players.append(matches[0])

    username = st.session_state.get("editing_character_card")
    if username in selected_players:
        _edit_character_card(username, is_dm=True)
    else:
        _render_dm_characters(selected_players)


def render_character_tab(username: str):
    if st.session_state.get("editing_player_character") == username:
        _edit_character_card(username, is_dm=False)
        return

    try:
        user_data = load_private_data(username)
    except FileNotFoundError:
        st.error(f"User data not found for {username}.")
    except PyMongoError as error:
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
