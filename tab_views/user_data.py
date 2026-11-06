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


def save_user_notes(username: str, notes: str) -> None:
    user_data = load_private_data(username)
    user_data["notes"] = notes
    save_private_data(username, user_data)
