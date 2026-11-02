import json
from datetime import datetime

import streamlit as st
from typesafe_sdk import TypeSafeError

from .message_injection import get_message_injection_checker
from .user_data import read_user_data, send_message


def format_timestamp(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp


@st.fragment(run_every=5)
def _show_chat(username: str, conversation_partner: str, is_dm: bool):
    try:
        _, user_data = read_user_data(username)
    except FileNotFoundError:
        st.error(f"User data file not found for {username}.")
        return
    except json.JSONDecodeError as error:
        st.error(f"Invalid JSON for {username}: {error}")
        return
    except (OSError, ValueError) as error:
        st.error(f"Could not load messages: {error}")
        return

    messages = user_data["messages"]
    if not is_dm:
        messages = [
            message for message in messages
            if {message["sender"], message["recipient"]} == {username, conversation_partner}
        ]

    prompt = st.chat_input("Write a message")
    if prompt and prompt.strip():
        try:
            checker = get_message_injection_checker()
            is_injection = checker.check(prompt.strip())
        except (KeyError, TypeSafeError) as error:
            st.error(f"Could not check message safety: {error}")
        else:
            if is_injection:
                st.toast("No, no, no...")
            else:
                try:
                    send_message(username, conversation_partner, prompt.strip())
                except FileNotFoundError:
                    st.error(f"User data file not found for {conversation_partner}.")
                except json.JSONDecodeError as error:
                    st.error(f"Invalid JSON while sending message: {error}")
                except (OSError, ValueError) as error:
                    st.error(f"Could not send message: {error}")
                else:
                    st.rerun()

    if not messages:
        st.caption("No messages yet.")
    for message in reversed(messages):
        with st.chat_message(message["sender"]):
            details = f"{message['sender']} · {format_timestamp(message['timestamp'])}"
            if is_dm:
                details += f" · To: {message['recipient']}"
            st.text(details)
            st.text(message["text"])


def render_messages_tab(username: str, is_dm: bool, users: dict):
    st.caption("Chat refreshes automatically every 5 seconds.")
    if is_dm:
        player_names = [
            name for name, details in users.items()
            if details["role"] == "player"
        ]
        conversation_partner = st.selectbox("Player", player_names)
    else:
        conversation_partner = "jakub"

    _show_chat(username, conversation_partner, is_dm)
