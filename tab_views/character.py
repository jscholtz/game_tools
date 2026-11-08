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
CARD_LINKS = (
    ("class_url", "Class"),
    ("subclass_url", "Subclass"),
)
PLAYER_TEXT_FIELDS = (
    ("background", "Character background"),
    ("story", "Character story"),
)


def _stat_value(data: dict, field: str):
    value = data.get(field)
    if field == "passive_insight" and value is None:
        insight = data.get("insight")
        if isinstance(insight, int) and not isinstance(insight, bool):
            return 10 + insight
    return value


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


def _render_character_details(data: dict) -> None:
    parts = []
    if data.get("level") is not None:
        parts.append(escape(f"Level {data['level']}"))
    if data.get("race"):
        parts.append(escape(str(data["race"])))

    raw_class = data.get("class", "")
    raw_subclass = data.get("subclass", "")
    if not isinstance(raw_class, str) or not isinstance(raw_subclass, str):
        st.error("Class and subclass must be text.")
        return
    class_name, separator, legacy_subclass = raw_class.partition(",")
    class_name = class_name.strip()
    subclass_name = raw_subclass.strip() or (legacy_subclass.strip() if separator else "")

    class_parts = []
    for label, name, url_field in (
        ("Class", class_name, "class_url"),
        ("Subclass", subclass_name, "subclass_url"),
    ):
        url = data.get(url_field)
        if url and (not isinstance(url, str) or not _valid_website_url(url)):
            st.error(f"{label} website URL is invalid.")
            url = None
        if name or url:
            text = escape(name or f"{label} reference")
            if url:
                text = (
                    f'<a href="{escape(url, quote=True)}" '
                    f'target="_blank" rel="noopener noreferrer">{text}</a>'
                )
            class_parts.append(text)
    if class_parts:
        parts.append(", ".join(class_parts))
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
    text_fields = CARD_LINKS if is_dm else CARD_LINKS + PLAYER_TEXT_FIELDS
    if not isinstance(character_name, str) or any(
        not isinstance(data.get(field, ""), str) for field, _ in text_fields
    ):
        st.error("Character name, website URLs, background, and story must be text.")
        if st.button("Back to characters"):
            st.session_state.pop(edit_key, None)
            st.rerun()
        return

    st.subheader(f"Edit character: {username}")
    st.caption("Leave a stat blank if it is unknown. Passive insight defaults to 10 + Insight modifier.")
    with st.form(f"character_card_{username}"):
        character = st.text_input("Character name", value=character_name)
        stats = {
            field: st.text_input(
                label,
                value=str(value) if (value := _stat_value(data, field)) is not None else "",
            )
            for field, label in CARD_STATS
        }
        urls = {
            field: st.text_input(f"{label} website URL", value=data.get(field, ""))
            for field, label in CARD_LINKS
        }
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
    for field, label in CARD_LINKS:
        url = urls[field].strip()
        if url and not _valid_website_url(url):
            st.error(f"{label} website must be a valid HTTP or HTTPS URL.")
            return
        if url:
            fields[field] = url
        else:
            removed.append(field)
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
                if "insight" in user_data:
                    stats.append(("Insight", f"{user_data['insight']:+}"))
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
                            st.text(text)
                        else:
                            st.error(f"{label} must be text.")
        elif "text" in user_data:
            with st.container(border=True):
                st.subheader("Character Data")
                st.write(user_data["text"])
