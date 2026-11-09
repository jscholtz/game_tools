from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st
from bson.errors import InvalidDocument
from pymongo.errors import PyMongoError

from .database import (
    PublicNote,
    create_public_notes,
    load_public_image,
    load_public_notes,
    save_public_image,
    save_public_notes,
)


def start_editor(notes: list[PublicNote], revision: str, index: int | None) -> None:
    note: PublicNote = (
        {
            "header": "",
            "date": datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat(),
            "text": "",
            "visible": False,
            "images": [],
        }
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


def render_editor() -> None:
    editor = st.session_state["public_note_editor"]
    note = editor["note"]
    key = editor["key"]
    st.subheader("New public note" if editor["index"] is None else "Edit public note")
    st.caption("Images appear after the note text. New notes are hidden by default.")
    with st.form(f"public_note_form_{key}"):
        header = st.text_input("Header", value=note["header"])
        date = st.text_input("Date", value=note["date"], help="Free text, for example 2026-11-08.")
        text = st.text_area("Markdown", value=note["text"], height=350)
        visible = st.checkbox("Visible to players", value=note["visible"])
        removed = []
        for index, image in enumerate(note["images"]):
            try:
                name, content = load_public_image(image)
            except (FileNotFoundError, PyMongoError, ValueError) as error:
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
    if not delete and not header.strip():
        st.error("Enter a header for the note.")
        return
    notes = list(editor["notes"])
    index = editor["index"]
    if delete:
        del notes[index]
    else:
        updated: PublicNote = {
            "header": header.strip(),
            "date": date.strip(),
            "text": text,
            "visible": visible,
            "images": [
                image for image, remove in zip(note["images"], removed) if not remove
            ],
        }
        if index is None:
            notes.append(updated)
        else:
            notes[index] = updated
    try:
        if not delete:
            updated["images"].extend(
                save_public_image(upload.name, upload.getvalue()) for upload in uploads
            )
        saved = save_public_notes(notes, editor["revision"])
    except (PyMongoError, InvalidDocument, ValueError) as error:
        st.error(f"Could not save public note: {error}")
    else:
        if saved:
            del st.session_state["public_note_editor"]
            st.toast("Public note saved.")
            st.rerun()
        else:
            st.error("Public notes changed while editing. Copy your draft, cancel, and try again.")


@st.fragment(run_every=10)
def render_public_view(is_dm: bool) -> None:
    try:
        board = load_public_notes()
    except (PyMongoError, ValueError) as error:
        st.error(f"Could not load public notes: {error}")
        return
    if board is None:
        st.info("No public notes yet.")
        if is_dm and st.button("Create public notes"):
            try:
                created = create_public_notes([])
            except PyMongoError as error:
                st.error(f"Could not create public notes: {error}")
            else:
                if not created:
                    st.warning("Public notes were created in another session.")
                st.rerun()
        return
    notes, revision = board
    if is_dm and st.button("+ New public note"):
        start_editor(notes, revision, None)
    if not any(is_dm or note["visible"] for note in notes):
        st.info("No public notes yet.")
    for index, note in enumerate(notes):
        if not is_dm and not note["visible"]:
            continue
        label = f"{note['date']} — {note['header']}" if note["date"] else note["header"]
        with st.expander(label):
            if is_dm:
                if not note["visible"]:
                    st.caption("Hidden from players")
                if st.button("Edit", key=f"edit_public_note_{index}", icon=":material/edit:"):
                    start_editor(notes, revision, index)
            st.markdown(note["text"])
            for image_index, image in enumerate(note["images"]):
                try:
                    name, content = load_public_image(image)
                except (FileNotFoundError, PyMongoError, ValueError) as error:
                    st.error(f"Could not load image {image_index + 1}: {error}")
                else:
                    st.image(content, caption=name, width=600)


@st.fragment
def render_public_editor() -> None:
    render_editor()


def render_public_tab(is_dm: bool = False) -> None:
    editor = st.session_state.get("public_note_editor")
    if is_dm and editor is not None and editor["owner"] == st.session_state.get("logged_in_user"):
        render_public_editor()
    else:
        render_public_view(is_dm)
