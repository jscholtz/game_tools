import hashlib
import streamlit as st

from tab_views.character import render_character_tab
from tab_views.messages import render_messages_tab
from tab_views.public_board import render_public_tab

USERS = st.secrets["users"]


def login_user(username: str, password: str):
    user = USERS.get(username)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user is not None and user["password_hash"] == password_hash:
        return user
    return None


def main():
    st.set_page_config(page_title="D&D Campaign Portal", page_icon="🐉", layout="centered")

    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

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
    user_details = USERS[username]

    st.title("D&D Campaign Portal")
    st.subheader(f"Welcome, {username}")
    st.caption(f"Campaign role: {user_details['role']}")

    character_tab, public_tab, messages_tab = st.tabs(["Character", "Public Board", "Messages with DM"])
    with character_tab:
        render_character_tab(username)

    with public_tab:
        render_public_tab()

    with messages_tab:
        render_messages_tab(
            username,
            user_details["role"] == "dm",
            USERS,
        )

    if st.sidebar.button("Log out"):
        st.session_state.logged_in_user = None
        st.rerun()


if __name__ == "__main__":
    main()
