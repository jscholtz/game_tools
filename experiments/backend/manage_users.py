import argparse
import getpass

from werkzeug.security import generate_password_hash

from app import database, load_database, save_database
from models import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


def main():
    parser = argparse.ArgumentParser(description="Create or update a local chat user.")
    parser.add_argument("username", help="Username for the experiment")
    parser.add_argument("--role", choices=("dm", "player"), help="Role for a new or existing user")
    args = parser.parse_args()
    username = args.username.strip()
    if not username or len(username) > 100:
        parser.error("Username must contain 1-100 characters.")
    if username == "dm" and args.role == "player":
        parser.error("The dm account must have the dm role.")
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        parser.error(
            f"Password must contain {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters."
        )
    if password != confirmation:
        parser.error("Passwords do not match.")
    load_database()
    existing = database.users.find_one({"_id": username})
    role = args.role or (existing["role"] if existing else ("dm" if username == "dm" else "player"))
    database.users.update_one(
        {"_id": username},
        {"$set": {"password_hash": generate_password_hash(password, method="scrypt"), "role": role}},
        upsert=True,
    )
    save_database()
    print(f"Saved user {username}.")


if __name__ == "__main__":
    main()
