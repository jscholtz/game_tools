import hashlib
import streamlit as st

from tab_views.character import render_character_tab
from tab_views.initiative import render_initiative_tab
from tab_views.messages import render_messages_tab
from tab_views.notes import render_notes_tab
from tab_views.public_board import render_public_tab

USERS = st.secrets["users"]


def login_user(username: str, password: str):
    user = USERS.get(username)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user is not None and user["password_hash"] == password_hash:
        return user
    return None


def main():
    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

    active_user = st.session_state.logged_in_user
    page_layout = "wide" if USERS.get(active_user, {}).get("role") == "dm" else "centered"
    st.set_page_config(
        page_title="D&D Campaign Portal",
        page_icon="🐉",
        layout=page_layout,
    )

    if st.session_state.logged_in_user is None:
        st.title("D&D Campaign Portal")
        st.subheader("Adventurers' Log In")

        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            user = login_user(username, password)
            if user is not None:
                st.session_state.logged_in_user = username
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

        return

    username = st.session_state.logged_in_user
    if username == "jakub":
        username = "dm"
        st.session_state.logged_in_user = username
    user_details = USERS[username]

    st.title("D&D Campaign Portal")
    st.subheader(f"Welcome, {username}")
    st.caption(f"Campaign role: {user_details['role']}")

    tab_names = ["Character"]
    if user_details["role"] == "player":
        tab_names.append("Notes")
    tab_names.extend(["Public Board", "Messages with DM"])
    if user_details["role"] == "dm":
        tab_names.append("Initiative Tracker")
    tabs = iter(st.tabs(tab_names))

    with next(tabs):
        render_character_tab(username)

    if user_details["role"] == "player":
        with next(tabs):
            render_notes_tab(username)

    with next(tabs):
        render_public_tab()

    with next(tabs):
        render_messages_tab(
            username,
            user_details["role"] == "dm",
            USERS,
        )

    if user_details["role"] == "dm":
        with next(tabs):
            render_initiative_tab()

    if st.sidebar.button("Log out"):
        st.session_state.logged_in_user = None
        st.rerun()


if __name__ == "__main__":
    main()
