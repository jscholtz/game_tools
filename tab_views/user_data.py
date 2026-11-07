from datetime import datetime, timezone

from .database import load_private_data, save_chat_message, save_private_data


def send_message(sender: str, recipient: str, text: str) -> None:
    message = {
        "sender": sender,
        "recipient": recipient,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": text,
    }
    if recipient == "dm":
        message["dm_read"] = False
    save_chat_message(message)


def _notes_from(user_data: dict) -> list[dict]:
    notes = user_data.get("notes")
    if not isinstance(notes, list):
        return []
    return [note for note in notes if isinstance(note, dict) and "id" in note]


def load_user_notes(username: str) -> list[dict]:
    return _notes_from(load_private_data(username))


def save_user_note(username: str, note_id: str, text: str) -> None:
    user_data = load_private_data(username)
    notes = _notes_from(user_data)
    for note in notes:
        if note["id"] == note_id:
            note["text"] = text
            break
    else:
        notes.append(
            {
                "id": note_id,
                "text": text,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
    user_data["notes"] = notes
    save_private_data(username, user_data)


def delete_user_note(username: str, note_id: str) -> None:
    user_data = load_private_data(username)
    user_data["notes"] = [
        note for note in _notes_from(user_data) if note["id"] != note_id
    ]
    save_private_data(username, user_data)
