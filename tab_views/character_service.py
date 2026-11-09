from typing import Any

from .database import (
    get_database,
    load_character_cards,
    load_dm_unread_counts,
    load_private_data,
    save_character_card,
)
from .principal import Principal

_SHARED_EDIT_FIELDS = {
    "character", "passive_perception", "passive_insight", "armor_class",
    "max_hp", "classes", "portrait",
}
_PLAYER_EDIT_FIELDS = _SHARED_EDIT_FIELDS | {
    "initiative_bonus", "character_description", "background", "story",
}


def _authorize_character(principal: Principal, username: str) -> None:
    if principal.role == "player":
        if principal.username != username:
            raise PermissionError("Players can only access their own character.")
    else:
        principal.require_dm()
        if get_database()["logins"].find_one({"username": username, "role": "player"}) is None:
            raise PermissionError("The DM can only edit player characters.")


def get_character(principal: Principal, username: str) -> dict[str, Any]:
    _authorize_character(principal, username)
    if principal.role == "player":
        return load_private_data(username)
    data = load_character_cards([username]).get(username)
    if data is None:
        raise FileNotFoundError(f"User data not found for {username}.")
    return data


def get_dm_character_cards(principal: Principal, player_names: list[str]) -> dict[str, dict[str, Any]]:
    principal.require_dm()
    return load_character_cards(player_names)


def get_dm_unread_counts(principal: Principal, player_names: list[str]) -> dict[str, int]:
    principal.require_dm()
    return load_dm_unread_counts(player_names)


def update_character(
    principal: Principal, username: str, fields: dict[str, Any], removed_fields: list[str]
) -> None:
    _authorize_character(principal, username)
    allowed = _SHARED_EDIT_FIELDS if principal.role == "dm" else _PLAYER_EDIT_FIELDS
    if not set(fields).issubset(allowed) or not set(removed_fields).issubset(allowed):
        raise PermissionError("Character update contains fields this account cannot edit.")
    save_character_card(username, fields, removed_fields)
