import streamlit as st
from pymongo.errors import PyMongoError

from tab_views.auth_service import load_users, login_user
from tab_views.bestiary import render_bestiary_tab
from tab_views.character import render_character_tab, render_dm_character_tab
from tab_views.custom_bestiary import render_custom_bestiary_tab
from tab_views.initiative import render_dm_initiative_tab, render_player_initiative_tab
from tab_views.messages import render_dm_messages_tab, render_player_messages_tab
from tab_views.notes import render_notes_tab
from tab_views.principal import Principal
from tab_views.public_board import render_dm_public_tab, render_player_public_tab


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
            try:
                users = load_users()
            except (KeyError, PyMongoError, ValueError) as error:
                st.error(f"Could not connect to MongoDB or load login records: {error}")
                return

            user = login_user(username, password, users)
            if user is not None:
                st.session_state.logged_in_user = username
                st.session_state.logged_in_role = user.role
                st.session_state.logged_in_player_names = [
                    name for name, details in users.items() if details.role == "player"
                ]
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

        return

    username = st.session_state.logged_in_user
    role = st.session_state.get("logged_in_role")
    if role not in ("dm", "player"):
        st.error("This account has an unsupported role.")
        return
    player_names = st.session_state.get("logged_in_player_names", [])
    principal = Principal(username=username, role=role)

    if role == "dm":
        st.subheader("Dungeon Master")
    else:
        st.title("D&D Campaign Portal")
        st.subheader(f"Welcome, {username}")
        st.caption(f"Campaign role: {role}")

    tab_names = ["Character"]
    if role == "player":
        tab_names.append("Notes")
    tab_names.extend(["Public Board", "Messages with DM", "Initiative Tracker"])
    if role == "dm":
        tab_names.extend(["Bestiary", "Custom Bestiary Editor"])
    tabs = iter(st.tabs(tab_names, key="main_tabs", on_change="rerun"))

    with next(tabs):
        if role == "dm":
            render_dm_character_tab(principal, player_names)
        else:
            render_character_tab(principal)

    if role == "player":
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
                principal, player_names
            )
        else:
            render_player_messages_tab(principal)

    with next(tabs):
        if principal.role == "dm":
            render_dm_initiative_tab(principal)
        else:
            render_player_initiative_tab(principal)

    if role == "dm":
        bestiary_tab = next(tabs)
        if bestiary_tab.open:
            with bestiary_tab:
                render_bestiary_tab(principal)
        custom_bestiary_tab = next(tabs)
        if custom_bestiary_tab.open:
            with custom_bestiary_tab:
                render_custom_bestiary_tab(principal)

    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()


if __name__ == "__main__":
    main()
