import hashlib

import streamlit as st
from pymongo.errors import PyMongoError

from tab_views.bestiary import render_bestiary_tab
from tab_views.character import render_character_tab, render_dm_character_tab
from tab_views.database import get_users
from tab_views.initiative import render_initiative_tab
from tab_views.messages import render_messages_tab
from tab_views.notes import render_notes_tab
from tab_views.public_board import render_public_tab

def login_user(username: str, password: str, users: dict):
    user = users.get(username)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user is not None and user["password_hash"] == password_hash:
        return user
    return None


def main():
    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

    page_layout = (
        "wide"
        if st.session_state.get("logged_in_role") == "dm"
        or st.session_state.get("main_tabs") == "Notes"
        else "centered"
    )
    st.set_page_config(
        page_title="D&D Campaign Portal",
        page_icon="🐉",
        layout=page_layout,
    )

    try:
        users = get_users()
    except (KeyError, PyMongoError) as error:
        st.error(f"Could not connect to MongoDB or load login records: {error}")
        return

    if st.session_state.logged_in_user is None:
        st.title("D&D Campaign Portal")
        st.subheader("Adventurers' Log In")

        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            user = login_user(username, password, users)
            if user is not None:
                st.session_state.logged_in_user = username
                st.session_state.logged_in_role = user["role"]
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

        return

    username = st.session_state.logged_in_user
    user_details = users.get(username)
    if user_details is None:
        st.session_state.logged_in_user = None
        st.session_state.logged_in_role = None
        st.error("This account no longer exists. Please log in again.")
        return
    if st.session_state.get("logged_in_role") != user_details["role"]:
        st.session_state.logged_in_role = user_details["role"]
        st.rerun()

    if user_details["role"] == "dm":
        st.subheader("Dungeon Master")
    else:
        st.title("D&D Campaign Portal")
        st.subheader(f"Welcome, {username}")
        st.caption(f"Campaign role: {user_details['role']}")

    tab_names = ["Character"]
    if user_details["role"] == "player":
        tab_names.append("Notes")
    tab_names.extend(["Public Board", "Messages with DM", "Initiative Tracker"])
    if user_details["role"] == "dm":
        tab_names.append("Bestiary")
    tabs = iter(st.tabs(tab_names, key="main_tabs", on_change="rerun"))

    with next(tabs):
        if user_details["role"] == "dm":
            render_dm_character_tab(
                [name for name, details in users.items() if details["role"] == "player"]
            )
        else:
            render_character_tab(username)

    if user_details["role"] == "player":
        with next(tabs):
            render_notes_tab(username)

    with next(tabs):
        render_public_tab(is_dm=user_details["role"] == "dm")

    with next(tabs):
        render_messages_tab(
            username,
            user_details["role"] == "dm",
            users,
        )

    with next(tabs):
        render_initiative_tab(is_dm=user_details["role"] == "dm")

    if user_details["role"] == "dm":
        bestiary_tab = next(tabs)
        if bestiary_tab.open:
            with bestiary_tab:
                render_bestiary_tab()

    if st.sidebar.button("Log out"):
        st.session_state.logged_in_user = None
        st.session_state.logged_in_role = None
        st.rerun()


if __name__ == "__main__":
    main()
