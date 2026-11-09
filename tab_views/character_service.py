from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from .database import (
    get_database,
    load_character_cards,
    load_dm_unread_counts,
    load_private_data,
    save_character_card,
)
from .data_models import CharacterData
from .principal import Principal

_SHARED_EDIT_FIELDS = {
    "character", "passive_perception", "passive_insight", "armor_class",
    "max_hp", "classes", "portrait",
}
_PLAYER_EDIT_FIELDS = _SHARED_EDIT_FIELDS | {
    "initiative_bonus", "character_description", "background", "story",
}
CARD_STATS = (
    ("passive_perception", "Passive perception"),
    ("passive_insight", "Passive insight"),
    ("armor_class", "Armor class"),
    ("max_hp", "Maximum HP"),
)
CLASS_FIELDS = (
    ("class_name", "Class"),
    ("class_url", "Class URL"),
    ("subclass_name", "Subclass"),
    ("subclass_url", "Subclass URL"),
    ("levels", "Levels"),
)
PLAYER_TEXT_FIELDS = (
    ("character_description", "Character description"),
    ("background", "Character background"),
    ("story", "Character story"),
)


class CharacterInputError(ValueError):
    pass


@dataclass
class CharacterEdit:
    character: str
    stats: dict[str, str]
    classes: dict[str, list[str | None]]
    initiative_bonus: str | None
    player_text: dict[str, str]
    portrait: bytes | None
    remove_portrait: bool


def valid_website_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _character_update(edit: CharacterEdit) -> tuple[dict[str, Any], list[str]]:
    if not edit.character.strip():
        raise CharacterInputError("Enter a character name.")
    if not set(edit.player_text).issubset({field for field, _ in PLAYER_TEXT_FIELDS}):
        raise CharacterInputError("Invalid character text fields.")
    fields: dict[str, Any] = {"character": edit.character.strip()}
    removed = []
    for field, label in CARD_STATS:
        value = edit.stats[field].strip()
        if not value:
            removed.append(field)
            continue
        if not value.isascii() or not value.isdecimal():
            raise CharacterInputError(f"{label} must be a non-negative whole number.")
        digits = value.lstrip("0") or "0"
        if len(digits) > 10 or int(digits) > 2**31 - 1:
            raise CharacterInputError(f"{label} is too large.")
        fields[field] = int(digits)
    if edit.initiative_bonus is not None:
        bonus = edit.initiative_bonus.strip()
        digits = bonus.removeprefix("+").removeprefix("-")
        if (
            not digits
            or not digits.isascii()
            or not digits.isdecimal()
            or bonus not in (digits, f"+{digits}", f"-{digits}")
        ):
            raise CharacterInputError("Initiative bonus must be a whole number.")
        if len(digits.lstrip("0")) > 10:
            raise CharacterInputError("Initiative bonus is too large.")
        number = int(digits.lstrip("0") or "0")
        if bonus.startswith("-"):
            number = -number
        if not -(2**31) <= number <= 2**31 - 1:
            raise CharacterInputError("Initiative bonus is too large.")
        fields["initiative_bonus"] = number
    updated_classes = []
    for row in zip(*(edit.classes[field] for field, _ in CLASS_FIELDS), strict=True):
        if any(value is not None and not isinstance(value, str) for value in row):
            raise CharacterInputError("Class fields must contain text.")
        entry = {
            field: value.strip() if value is not None else ""
            for (field, _), value in zip(CLASS_FIELDS, row, strict=True)
        }
        if not any(entry.values()):
            continue
        if not entry["class_name"]:
            raise CharacterInputError("Each class must have a name.")
        for field, label in (("class_url", "Class"), ("subclass_url", "Subclass")):
            if entry[field] and not valid_website_url(entry[field]):
                raise CharacterInputError(f"{label} website must be a valid HTTP or HTTPS URL.")
        levels = entry["levels"]
        if levels and (not levels.isascii() or not levels.isdecimal() or not levels.strip("0")):
            raise CharacterInputError("Class levels must be a positive whole number or blank.")
        updated_classes.append(entry)
    fields["classes"] = updated_classes
    fields.update(edit.player_text)
    if edit.portrait is not None:
        if not edit.portrait:
            raise CharacterInputError("The uploaded picture is empty.")
        try:
            with Image.open(BytesIO(edit.portrait)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise CharacterInputError("The uploaded picture is invalid or too large.") from error
        fields["portrait"] = edit.portrait
    elif edit.remove_portrait:
        removed.append("portrait")
    return fields, removed


def _authorize_character(principal: Principal, username: str) -> None:
    if principal.role == "player":
        if principal.username != username:
            raise PermissionError("Players can only access their own character.")
    else:
        principal.require_dm()
        if get_database()["logins"].find_one({"username": username, "role": "player"}) is None:
            raise PermissionError("The DM can only edit player characters.")


def get_character(principal: Principal, username: str) -> CharacterData:
    _authorize_character(principal, username)
    if principal.role == "player":
        return load_private_data(username)
    data = load_character_cards([username]).get(username)
    if data is None:
        raise FileNotFoundError(f"User data not found for {username}.")
    return data


def get_dm_character_cards(principal: Principal, player_names: list[str]) -> dict[str, CharacterData]:
    principal.require_dm()
    return load_character_cards(player_names)


def resolve_character_players(
    configured_players: list[str], player_names: list[str]
) -> tuple[list[str], list[tuple[str, int]]]:
    lookup: dict[str, list[str]] = {}
    for player in player_names:
        lookup.setdefault(player.casefold(), []).append(player)
    selected = []
    unmatched = []
    for configured in configured_players:
        matches = lookup.get(configured.casefold(), [])
        if len(matches) == 1:
            selected.append(matches[0])
        else:
            unmatched.append((configured, len(matches)))
    return selected, unmatched


def get_dm_unread_counts(principal: Principal, player_names: list[str]) -> dict[str, int]:
    principal.require_dm()
    return load_dm_unread_counts(player_names)


def update_character(principal: Principal, username: str, edit: CharacterEdit) -> None:
    _authorize_character(principal, username)
    fields, removed_fields = _character_update(edit)
    allowed = _SHARED_EDIT_FIELDS if principal.role == "dm" else _PLAYER_EDIT_FIELDS
    if not set(fields).issubset(allowed) or not set(removed_fields).issubset(allowed):
        raise PermissionError("Character update contains fields this account cannot edit.")
    save_character_card(username, fields, removed_fields)
