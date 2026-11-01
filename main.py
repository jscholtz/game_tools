import json
import streamlit as st
import hashlib
from datetime import datetime, timezone
from pathlib import Path

USERS = st.secrets["users"]
DATA_DIR = Path(__file__).parent / "data"


def login_user(username: str, password: str):
    user = USERS.get(username)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user is not None and user["password_hash"] == password_hash:
        return user
    return None


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


@st.fragment(run_every=5)
def show_chat(username: str, conversation_partner: str, is_dm: bool):
    try:
        _, user_data = read_user_data(username)
    except FileNotFoundError:
        st.error(f"User data file not found for {username}.")
        return
    except json.JSONDecodeError as error:
        st.error(f"Invalid JSON for {username}: {error}")
        return
    except (OSError, ValueError) as error:
        st.error(f"Could not load messages: {error}")
        return

    messages = user_data["messages"]
    if not is_dm:
        messages = [
            message for message in messages
            if {message["sender"], message["recipient"]} == {username, conversation_partner}
        ]
    prompt = st.chat_input("Write a message")
    if prompt and prompt.strip():
        try:
            send_message(username, conversation_partner, prompt.strip())
        except FileNotFoundError:
            st.error(f"User data file not found for {conversation_partner}.")
        except json.JSONDecodeError as error:
            st.error(f"Invalid JSON while sending message: {error}")
        except (OSError, ValueError) as error:
            st.error(f"Could not send message: {error}")
        else:
            st.rerun()

    if not messages:
        st.caption("No messages yet.")
    for message in reversed(messages):
        with st.chat_message(message["sender"]):
            details = f"{message['sender']} · {message['timestamp']}"
            if is_dm:
                details += f" · To: {message['recipient']}"
            st.caption(details)
            st.write(message["text"])


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

    private_tab, public_tab, messages_tab = st.tabs(["Private", "Public", "Messages"])
    with private_tab:
        user_data_file = DATA_DIR / f"{username}.json"
        try:
            with user_data_file.open(encoding="utf-8") as file:
                user_data = json.load(file)
        except FileNotFoundError:
            st.error(f"User data file not found: {user_data_file.name}")
        except json.JSONDecodeError as error:
            st.error(f"Invalid JSON in {user_data_file.name}: {error}")
        except OSError as error:
            st.error(f"Could not read {user_data_file.name}: {error}")
        else:
            if "character" in user_data:
                st.title(user_data["character"])
                st.subheader(f"Level {user_data['level']} {user_data['race']} {user_data['class']}")
                st.caption(user_data["gender"])

                stat_columns = st.columns(2)
                stat_columns[0].metric("Passive Perception", user_data["passive_perception"])
                stat_columns[1].metric("Insight", f"{user_data['insight']:+}")
            elif "text" in user_data:
                st.write(user_data["text"])

    with public_tab:
        public_page_file = Path(__file__).parent / "public.html"
        try:
            public_page = public_page_file.read_text(encoding="utf-8")
        except OSError as error:
            st.error(f"Could not read {public_page_file.name}: {error}")
        else:
            st.html(public_page)

    with messages_tab:
        st.caption("Chat refreshes automatically every 5 seconds.")
        if user_details["role"] == "dm":
            player_names = [
                name for name, details in USERS.items()
                if details["role"] == "player"
            ]
            conversation_partner = st.selectbox("Player", player_names)
        else:
            conversation_partner = "jakub"
        show_chat(
            username,
            conversation_partner,
            is_dm=user_details["role"] == "dm",
        )

    if st.sidebar.button("Log out"):
        st.session_state.logged_in_user = None
        st.rerun()


if __name__ == "__main__":
    main()
