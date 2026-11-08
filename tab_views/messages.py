from datetime import datetime
from html import escape
from typing import Any, Callable

import streamlit as st
from pymongo.errors import PyMongoError
from typesafe_sdk import TypeSafeError

from .database import (
    load_chat_messages,
    load_dm_unread_counts,
    mark_dm_messages_read,
)
from .message_injection import get_message_injection_checker
from .user_data import send_message


def format_timestamp(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return timestamp


def format_dm_timestamp(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%d %b · %H:%M")
    except ValueError:
        return timestamp


def _render_chat_messages(
    messages: list[dict[str, Any]],
    *,
    timestamp_formatter: Callable[[str], str] = format_timestamp,
    max_height: int | None = None,
) -> None:
    if not messages:
        st.caption("No messages yet.")
        return

    rows = []
    for message in reversed(messages):
        sender = escape(message["sender"])
        timestamp = escape(timestamp_formatter(message["timestamp"]))
        text = escape(message["text"])
        rows.append(
            '<div style="padding: 0.25rem 0; overflow-wrap: anywhere;">'
            '<div style="font-size: 0.8rem; opacity: 0.7;">'
            f"<strong>{sender}</strong> · {timestamp}</div>"
            f'<div style="white-space: pre-wrap;">{text}</div>'
            "</div>"
        )
    style = f' style="max-height: {max_height}px; overflow-y: auto;"' if max_height else ""
    st.html(f"<div{style}>" + "".join(rows) + "</div>")


@st.fragment(run_every=5)
def _show_player_chat(username: str):
    try:
        messages = load_chat_messages(username, "dm")
    except PyMongoError as error:
        st.error(f"Could not load messages: {error}")
        return

    prompt = st.chat_input("Write a message")
    if prompt and prompt.strip():
        if _message_is_allowed(prompt):
            try:
                send_message(username, "dm", prompt.strip())
            except PyMongoError as error:
                st.error(f"Could not send message: {error}")
            else:
                st.rerun()

    _render_chat_messages(messages)


def _message_is_allowed(message: str) -> bool:
    try:
        is_injection = get_message_injection_checker().check(message.strip())
    except (KeyError, TypeSafeError) as error:
        st.error(f"Could not check message safety: {error}")
        return False
    if is_injection:
        st.toast("No, no, no...!")
        return False
    return True


def _render_dm_conversation(player_name: str, unread_count: int) -> None:
    expander_key = f"dm_conversation_{player_name}"
    if st.session_state.get(expander_key, False) and unread_count:
        try:
            mark_dm_messages_read(player_name)
        except PyMongoError as error:
            st.error(f"Could not mark {player_name}'s messages as read: {error}")
        else:
            unread_count = 0

    unread_label = f"{unread_count} unread" if unread_count else "no unread"
    with st.expander(
        f"**{player_name}** · {unread_label}",
        key=expander_key,
        on_change="rerun",
    ):
        try:
            messages = load_chat_messages("dm", player_name)
        except PyMongoError as error:
            st.error(f"Could not load messages: {error}")
            return

        with st.form(f"dm_message_form_{player_name}", clear_on_submit=True, border=False):
            input_column, send_column = st.columns([4, 1], vertical_alignment="center")
            with input_column:
                prompt = st.text_input(
                    "Message",
                    placeholder="Write a message",
                    label_visibility="collapsed",
                )
            with send_column:
                submitted = st.form_submit_button("Send")
        if submitted and prompt.strip():
            if _message_is_allowed(prompt):
                try:
                    send_message("dm", player_name, prompt.strip())
                except PyMongoError as error:
                    st.error(f"Could not send message: {error}")
                else:
                    st.rerun()

        _render_chat_messages(messages, timestamp_formatter=format_dm_timestamp, max_height=320)


@st.fragment(run_every=5)
def _show_dm_conversations(player_names: list[str]) -> None:
    try:
        unread_counts = load_dm_unread_counts(player_names)
    except PyMongoError as error:
        st.error(f"Could not load unread message counts: {error}")
        return

    columns = st.columns(3)
    for index, player_name in enumerate(player_names):
        with columns[index % 3]:
            _render_dm_conversation(
                player_name,
                unread_counts.get(player_name, 0),
            )


def render_messages_tab(username: str, is_dm: bool, users: dict):
    if is_dm:
        player_names = [
            name for name, details in users.items()
            if details["role"] == "player"
        ]
        if not player_names:
            st.caption("No player accounts are registered.")
            return
        st.caption("Unread counts refresh every 5 seconds. Opening a conversation marks its messages as read.")
        _show_dm_conversations(player_names)
    else:
        st.caption("Chat refreshes automatically every 5 seconds.")
        _show_player_chat(username)
