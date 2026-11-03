import streamlit as st
from pymongo.errors import PyMongoError
from typesafe_sdk import TypeSafeError

from .database import load_private_data
from .message_injection import get_message_injection_checker
from .user_data import save_user_notes


def render_notes_tab(username: str):
    try:
        user_data = load_private_data(username)
    except FileNotFoundError:
        st.error(f"User data not found for {username}.")
        return
    except PyMongoError as error:
        st.error(f"Could not load notes: {error}")
        return

    notes = user_data.get("notes", "")
    if not isinstance(notes, str):
        st.error("Notes data must be a string.")
        return

    with st.form("player_notes"):
        save_notes = st.form_submit_button("Save notes")
        edited_notes = st.text_area("Your notes", value=notes, height=700)

    if save_notes:
        try:
            is_injection = get_message_injection_checker().check(edited_notes)
        except (KeyError, TypeSafeError) as error:
            st.error(f"Could not check notes safety: {error}")
        else:
            if is_injection:
                st.toast("No, no, no...!")
                return

            try:
                save_user_notes(username, edited_notes)
            except (PyMongoError, ValueError) as error:
                st.error(f"Could not save notes: {error}")
            else:
                st.success("Notes saved.")
