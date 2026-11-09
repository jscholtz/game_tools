from datetime import datetime, timezone

from .database import (
    get_database,
    load_chat_messages,
    load_dm_unread_counts,
    load_private_notes,
    mark_dm_messages_read,
    save_chat_message,
    save_private_notes,
)
from .data_models import ChatMessage, PrivateNote
from .principal import Principal


def _conversation(principal: Principal, player_name: str) -> tuple[str, str]:
    if principal.role == "player":
        principal.require_player()
        if principal.username != player_name:
            raise PermissionError("Players can only access their own conversation.")
    else:
        principal.require_dm()
        if get_database()["logins"].find_one({"username": player_name, "role": "player"}) is None:
            raise PermissionError("Conversation does not belong to a player.")
    return player_name, "dm"


def get_conversation(principal: Principal, player_name: str) -> list[ChatMessage]:
    player, dm = _conversation(principal, player_name)
    return load_chat_messages(player, dm)


def get_unread_counts(principal: Principal, player_names: list[str]) -> dict[str, int]:
    principal.require_dm()
    return load_dm_unread_counts(player_names)


def mark_messages_read(principal: Principal, player_name: str) -> None:
    principal.require_dm()
    _conversation(principal, player_name)
    mark_dm_messages_read(player_name)


def send_message(principal: Principal, player_name: str, text: str) -> None:
    _conversation(principal, player_name)
    sender, recipient = (player_name, "dm") if principal.role == "player" else ("dm", player_name)
    fields: dict[str, str | bool] = {
        "sender": sender,
        "recipient": recipient,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": text,
    }
    if recipient == "dm":
        fields["dm_read"] = False
    message = ChatMessage.model_validate(fields)
    save_chat_message(message)


def load_user_notes(principal: Principal) -> list[PrivateNote]:
    principal.require_player()
    return load_private_notes(principal.username)


def save_user_note(principal: Principal, note_id: str, text: str) -> None:
    principal.require_player()
    notes = load_private_notes(principal.username)
    for note in notes:
        if note.id == note_id:
            note.text = text
            break
    else:
        notes.append(
            PrivateNote(
                id=note_id,
                text=text,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        )
    save_private_notes(principal.username, notes)


def delete_user_note(principal: Principal, note_id: str) -> None:
    principal.require_player()
    notes = [note for note in load_private_notes(principal.username) if note.id != note_id]
    save_private_notes(principal.username, notes)
