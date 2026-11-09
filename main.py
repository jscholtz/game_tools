import hashlib

import streamlit as st
from pymongo.errors import PyMongoError

from tab_views.bestiary import render_bestiary_tab
from tab_views.character import render_character_tab, render_dm_character_tab
from tab_views.database import get_users
from tab_views.initiative import render_dm_initiative_tab, render_player_initiative_tab
from tab_views.messages import render_dm_messages_tab, render_player_messages_tab
from tab_views.notes import render_notes_tab
from tab_views.principal import Principal
from tab_views.public_board import render_dm_public_tab, render_player_public_tab


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
        notice = st.session_state.pop("login_notice", None)
        if notice:
            st.warning(notice)

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
        st.session_state.clear()
        st.session_state.login_notice = "This account no longer exists. Please log in again."
        st.rerun()
    if st.session_state.get("logged_in_role") != user_details["role"]:
        st.session_state.clear()
        st.session_state.login_notice = "Your account role changed. Please log in again."
        st.rerun()

    if user_details["role"] not in ("dm", "player"):
        st.error("This account has an unsupported role.")
        return
    principal = Principal(username=username, role=user_details["role"])

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
                principal,
                [name for name, details in users.items() if details["role"] == "player"]
            )
        else:
            render_character_tab(principal)

    if user_details["role"] == "player":
        with next(tabs):
            render_notes_tab(principal)

    with next(tabs):
        if principal.role == "dm":
            render_dm_public_tab(principal)
        else:
            render_player_public_tab(principal)

    with next(tabs):
        if principal.role == "dm":
            render_dm_messages_tab(
                principal, [name for name, details in users.items() if details["role"] == "player"]
            )
        else:
            render_player_messages_tab(principal)

    with next(tabs):
        if principal.role == "dm":
            render_dm_initiative_tab(principal)
        else:
            render_player_initiative_tab(principal)

    if user_details["role"] == "dm":
        bestiary_tab = next(tabs)
        if bestiary_tab.open:
            with bestiary_tab:
                render_bestiary_tab(principal)

    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()


if __name__ == "__main__":
    main()
