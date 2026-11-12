import argparse
import getpass

from werkzeug.security import generate_password_hash

from app import USERS_FILE, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description="Create or update a local chat user.")
    parser.add_argument("username", help="Username for the experiment")
    args = parser.parse_args()
    username = args.username.strip()
    if not username or len(username) > 100:
        parser.error("Username must contain 1-100 characters.")
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12 or len(password) > 1024:
        parser.error("Password must contain 12-1024 characters.")
    if password != confirmation:
        parser.error("Passwords do not match.")
    users = read_json(USERS_FILE, {})
    if not isinstance(users, dict) or not all(
        isinstance(name, str) and isinstance(value, str) for name, value in users.items()
    ):
        parser.error("Credential file is invalid.")
    users[username] = generate_password_hash(password, method="scrypt")
    write_json(USERS_FILE, users)
    print(f"Saved user {username}.")


if __name__ == "__main__":
    main()
