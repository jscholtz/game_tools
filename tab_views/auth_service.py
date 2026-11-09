import hashlib

from .data_models import LoginRecord
from .database import get_users


def load_users() -> dict[str, LoginRecord]:
    return get_users()


def login_user(username: str, password: str, users: dict[str, LoginRecord]) -> LoginRecord | None:
    user = users.get(username)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user is not None and user.password_hash == password_hash:
        return user
    return None
