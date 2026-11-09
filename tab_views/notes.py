import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from pymongo.errors import PyMongoError
from typesafe_sdk import TypeSafeError

from .message_injection import get_message_injection_checker
from .data_models import PrivateNote
from .principal import Principal
from .user_data import delete_user_note, load_user_notes, save_user_note

LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
DRAFTS_KEY = "note_drafts"
EDITING_KEY = "note_editing"


def _local_datetime(note: PrivateNote) -> datetime:
    try:
        created = datetime.fromisoformat(note.created_at)
    except (KeyError, TypeError, ValueError):
        return datetime.fromtimestamp(0, LOCAL_TZ)
    return created.astimezone(LOCAL_TZ)


def _text_key(note_id: str) -> str:
    return f"note_text_{note_id}"


def _stop_editing(note_id: str) -> None:
    if note_id in st.session_state[DRAFTS_KEY]:
        st.session_state[DRAFTS_KEY].remove(note_id)
    st.session_state[EDITING_KEY].discard(note_id)
    st.session_state.pop(_text_key(note_id), None)


def _save(principal: Principal, note_id: str) -> bool:
    text = st.session_state.get(_text_key(note_id), "")
    try:
        is_injection = get_message_injection_checker().check(text)
    except (KeyError, TypeSafeError) as error:
        st.error(f"Could not check note safety: {error}")
        return False
    if is_injection:
        st.toast("No, no, no...!")
        return False
    try:
        save_user_note(principal, note_id, text)
    except (PermissionError, PyMongoError, ValueError, FileNotFoundError) as error:
        st.error(f"Could not save note: {error}")
        return False
    return True


def _delete(principal: Principal, note_id: str, is_draft: bool) -> bool:
    if not is_draft:
        try:
            delete_user_note(principal, note_id)
        except (PermissionError, PyMongoError, ValueError, FileNotFoundError) as error:
            st.error(f"Could not delete note: {error}")
            return False
    return True


def _render_note(principal: Principal, note: PrivateNote, is_draft: bool) -> None:
    note_id = note.id
    editing = is_draft or note_id in st.session_state[EDITING_KEY]
    changed = False

    text = st.session_state.get(_text_key(note_id), note.text)
    first_line = text.split("\n", 1)[0].strip() or "Untitled note"
    date = datetime.now(LOCAL_TZ) if is_draft else _local_datetime(note)
    header = f"{date.strftime('%d %B %Y')} — {first_line}"

    with st.expander(header, expanded=editing):
        text_column, buttons_column = st.columns([4, 1])
        with buttons_column, st.container(horizontal=True, horizontal_alignment="right"):
            if editing:
                if st.button("Save", key=f"save_{note_id}"):
                    if _save(principal, note_id):
                        _stop_editing(note_id)
                        changed = True
                if st.button("Cancel", key=f"cancel_{note_id}"):
                    _stop_editing(note_id)
                    changed = True
            elif st.button(
                "", icon=":material/edit:", key=f"edit_{note_id}", help="Edit"
            ):
                st.session_state[EDITING_KEY].add(note_id)
                changed = True

            if st.button(
                "", icon=":material/delete:", key=f"trash_{note_id}", help="Trash"
            ):
                if _delete(principal, note_id, is_draft):
                    _stop_editing(note_id)
                    changed = True

        if changed:
            st.rerun()

        with text_column:
            if editing:
                if _text_key(note_id) not in st.session_state:
                    st.session_state[_text_key(note_id)] = note.text
                st.text_area(
                    "Note",
                    key=_text_key(note_id),
                    height=200,
                    label_visibility="collapsed",
                )
            else:
                st.markdown(note.text)


def render_notes_tab(principal: Principal):
    st.session_state.setdefault(DRAFTS_KEY, [])
    st.session_state.setdefault(EDITING_KEY, set())

    if st.button("+ New note"):
        st.session_state[DRAFTS_KEY].insert(0, uuid.uuid4().hex)

    try:
        notes = load_user_notes(principal)
    except FileNotFoundError:
        st.error(f"User data not found for {principal.username}.")
        return
    except (PermissionError, PyMongoError, ValueError) as error:
        st.error(f"Could not load notes: {error}")
        return

    for note_id in list(st.session_state[DRAFTS_KEY]):
        _render_note(
            principal,
            PrivateNote(id=note_id, text="", created_at=datetime.now(LOCAL_TZ).isoformat()),
            is_draft=True,
        )

    notes.sort(key=_local_datetime, reverse=True)
    current_day = None
    for note in notes:
        day = _local_datetime(note).date()
        if day != current_day:
            current_day = day
            st.subheader(day.strftime("%A %d %B %Y"))
        _render_note(principal, note, is_draft=False)
