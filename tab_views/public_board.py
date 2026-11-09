from uuid import uuid4

import streamlit as st
from bson.errors import InvalidDocument
from pymongo.errors import PyMongoError

from .board_service import (
    BoardEdit,
    BoardInputError,
    create_board,
    get_board_image,
    get_dm_board,
    get_player_board,
    new_board_note,
    save_board_edit,
)
from .data_models import PublicNote
from .principal import Principal


def start_editor(principal: Principal, notes: list[PublicNote], revision: str, index: int | None) -> None:
    principal.require_dm()
    note = (
        new_board_note(principal)
        if index is None
        else notes[index]
    )
    st.session_state["public_note_editor"] = {
        "owner": st.session_state["logged_in_user"],
        "notes": notes,
        "revision": revision,
        "index": index,
        "note": note,
        "key": uuid4().hex,
    }
    st.rerun()


def render_editor(principal: Principal) -> None:
    principal.require_dm()
    editor = st.session_state["public_note_editor"]
    note = editor["note"]
    key = editor["key"]
    st.subheader("New public note" if editor["index"] is None else "Edit public note")
    st.caption("Images appear after the note text. New notes are hidden by default.")
    with st.form(f"public_note_form_{key}"):
        header = st.text_input("Header", value=note.header)
        date = st.text_input("Date", value=note.date, help="Free text, for example 2026-11-08.")
        text = st.text_area("Markdown", value=note.text, height=350)
        visible = st.checkbox("Visible to players", value=note.visible)
        removed = []
        for index, image in enumerate(note.images):
            try:
                name, content = get_board_image(principal, image)
            except (FileNotFoundError, PermissionError, PyMongoError, ValueError) as error:
                st.error(f"Could not load image {index + 1}: {error}")
                name = f"Image {index + 1}"
            else:
                st.image(content, caption=name, width=200)
            removed.append(st.checkbox(f"Remove {name}", key=f"remove_{key}_{index}"))
        uploads = st.file_uploader(
            "Add images", type=["png", "jpg", "jpeg", "gif", "webp"],
            accept_multiple_files=True,
        )
        delete = (
            st.checkbox("Delete this note")
            if editor["index"] is not None
            else False
        )
        save = st.form_submit_button("Save", type="primary")
        cancel = st.form_submit_button("Cancel")

    if cancel:
        del st.session_state["public_note_editor"]
        st.rerun()
    if not save:
        return
    try:
        saved = save_board_edit(
            principal,
            editor["notes"],
            editor["revision"],
            editor["index"],
            BoardEdit(
                header=header,
                date=date,
                text=text,
                visible=visible,
                removed_images=removed,
                uploads=[(upload.name, upload.getvalue()) for upload in uploads] if not delete else [],
                delete=delete,
            ),
        )
    except BoardInputError as error:
        st.error(str(error))
    except (PermissionError, PyMongoError, InvalidDocument, ValueError) as error:
        st.error(f"Could not save public note: {error}")
    else:
        if saved:
            del st.session_state["public_note_editor"]
            st.toast("Public note saved.")
            st.rerun()
        else:
            st.error("Public notes changed while editing. Copy your draft, cancel, and try again.")


@st.fragment(run_every=10)
def render_dm_public_view(principal: Principal) -> None:
    try:
        board = get_dm_board(principal)
    except (PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load public notes: {error}")
        return
    if board is None:
        st.info("No public notes yet.")
        if st.button("Create public notes"):
            try:
                created = create_board(principal)
            except (PermissionError, PyMongoError, ValueError) as error:
                st.error(f"Could not create public notes: {error}")
            else:
                if not created:
                    st.warning("Public notes were created in another session.")
                st.rerun()
        return
    notes, revision = board
    if st.button("+ New public note"):
        start_editor(principal, notes, revision, None)
    if not notes:
        st.info("No public notes yet.")
    for index, note in enumerate(notes):
        label = f"{note.date} — {note.header}" if note.date else note.header
        with st.expander(label):
            if not note.visible:
                st.caption("Hidden from players")
            if st.button("Edit", key=f"edit_public_note_{index}", icon=":material/edit:"):
                start_editor(principal, notes, revision, index)
            st.markdown(note.text)
            for image_index, image in enumerate(note.images):
                try:
                    name, content = get_board_image(principal, image)
                except (FileNotFoundError, PermissionError, PyMongoError, ValueError) as error:
                    st.error(f"Could not load image {image_index + 1}: {error}")
                else:
                    st.image(content, caption=name, width=600)


@st.fragment
def render_public_editor(principal: Principal) -> None:
    render_editor(principal)


def render_dm_public_tab(principal: Principal) -> None:
    editor = st.session_state.get("public_note_editor")
    if editor is not None and editor["owner"] == principal.username:
        render_public_editor(principal)
    else:
        render_dm_public_view(principal)


@st.fragment(run_every=10)
def render_player_public_tab(principal: Principal) -> None:
    try:
        notes = get_player_board(principal)
    except (PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load public notes: {error}")
        return
    if not notes:
        st.info("No public notes yet.")
    for note in notes:
        label = f"{note.date} — {note.header}" if note.date else note.header
        with st.expander(label):
            st.markdown(note.text)
            for image_index, image in enumerate(note.images):
                try:
                    name, content = get_board_image(principal, image)
                except (FileNotFoundError, PermissionError, PyMongoError, ValueError) as error:
                    st.error(f"Could not load image {image_index + 1}: {error}")
                else:
                    st.image(content, caption=name, width=600)
