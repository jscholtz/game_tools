from datetime import datetime
from html import escape
from typing import Any, Callable

import streamlit as st
from pymongo.errors import PyMongoError
from typesafe_sdk import TypeSafeError

from .message_injection import get_message_injection_checker
from .principal import Principal
from .user_data import get_conversation, get_unread_counts, mark_messages_read, send_message


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
def _show_player_chat(principal: Principal):
    try:
        messages = get_conversation(principal, principal.username)
    except (PermissionError, PyMongoError) as error:
        st.error(f"Could not load messages: {error}")
        return

    prompt = st.chat_input("Write a message")
    if prompt and prompt.strip():
        if _message_is_allowed(prompt):
            try:
                send_message(principal, principal.username, prompt.strip())
            except (PermissionError, PyMongoError) as error:
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


def _render_dm_conversation(principal: Principal, player_name: str, unread_count: int) -> None:
    expander_key = f"dm_conversation_{player_name}"
    if st.session_state.get(expander_key, False) and unread_count:
        try:
            mark_messages_read(principal, player_name)
        except (PermissionError, PyMongoError) as error:
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
            messages = get_conversation(principal, player_name)
        except (PermissionError, PyMongoError) as error:
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
                    send_message(principal, player_name, prompt.strip())
                except (PermissionError, PyMongoError) as error:
                    st.error(f"Could not send message: {error}")
                else:
                    st.rerun()

        _render_chat_messages(messages, timestamp_formatter=format_dm_timestamp, max_height=320)


@st.fragment(run_every=5)
def _show_dm_conversations(principal: Principal, player_names: list[str]) -> None:
    try:
        unread_counts = get_unread_counts(principal, player_names)
    except (PermissionError, PyMongoError) as error:
        st.error(f"Could not load unread message counts: {error}")
        return

    columns = st.columns(3)
    for index, player_name in enumerate(player_names):
        with columns[index % 3]:
            _render_dm_conversation(
                principal,
                player_name,
                unread_counts.get(player_name, 0),
            )


def render_dm_messages_tab(principal: Principal, player_names: list[str]) -> None:
    if not player_names:
        st.caption("No player accounts are registered.")
        return
    st.caption("Unread counts refresh every 5 seconds. Opening a conversation marks its messages as read.")
    _show_dm_conversations(principal, player_names)


def render_player_messages_tab(principal: Principal) -> None:
    st.caption("Chat refreshes automatically every 5 seconds.")
    _show_player_chat(principal)
