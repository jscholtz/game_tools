import json

import streamlit as st
from typesafe_sdk import TypeSafeError

from .message_injection import get_message_injection_checker
from .user_data import DATA_DIR, save_user_notes


def render_notes_tab(username: str):
    user_data_file = DATA_DIR / f"{username}.json"
    try:
        with user_data_file.open(encoding="utf-8") as file:
            user_data = json.load(file)
    except FileNotFoundError:
        st.error(f"User data file not found: {user_data_file.name}")
        return
    except json.JSONDecodeError as error:
        st.error(f"Invalid JSON in {user_data_file.name}: {error}")
        return
    except OSError as error:
        st.error(f"Could not read {user_data_file.name}: {error}")
        return

    notes = user_data.get("notes", "")
    if not isinstance(notes, str):
        st.error(f"'notes' in {user_data_file.name} must be a string.")
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
            except (OSError, ValueError) as error:
                st.error(f"Could not save notes: {error}")
            else:
                st.success("Notes saved.")
