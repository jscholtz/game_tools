import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def read_user_data(username: str) -> tuple[Path, dict]:
    user_data_file = DATA_DIR / f"{username}.json"
    with user_data_file.open(encoding="utf-8") as file:
        user_data = json.load(file)

    if not isinstance(user_data, dict):
        raise ValueError(f"{user_data_file.name} must contain a JSON object.")

    messages = user_data.setdefault("messages", [])
    if not isinstance(messages, list) or not all(
        isinstance(message, dict)
        and all(
            isinstance(message.get(key), str)
            for key in ("sender", "timestamp", "text", "recipient")
        )
        for message in messages
    ):
        raise ValueError(f"'messages' in {user_data_file.name} must be a list of message objects.")
    return user_data_file, user_data


def send_message(sender: str, recipient: str, text: str):
    sender_file, sender_data = read_user_data(sender)
    recipient_file, recipient_data = read_user_data(recipient)

    message = {
        "sender": sender,
        "recipient": recipient,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": text,
    }
    sender_data["messages"].append(message)
    recipient_data["messages"].append(message)

    sender_file.write_text(json.dumps(sender_data, indent=2) + "\n", encoding="utf-8")
    recipient_file.write_text(json.dumps(recipient_data, indent=2) + "\n", encoding="utf-8")


def save_user_notes(username: str, notes: str) -> None:
    user_data_file, user_data = read_user_data(username)
    user_data["notes"] = notes
    user_data_file.write_text(
        json.dumps(user_data, indent=2) + "\n",
        encoding="utf-8",
    )
