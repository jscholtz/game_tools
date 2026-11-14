from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_MESSAGE_LENGTH = 1000
MAX_NOTE_LENGTH = 100_000
MAX_BOARD_IMAGES = 5
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024


class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    username: str = Field(max_length=100)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH, repr=False)


class SocketAuth(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    token: str = Field(repr=False)


class MessageRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    text: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    recipient: str | None = None

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChatReadRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    message_id: int = Field(ge=0)


class NoteRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    header: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_NOTE_LENGTH)

    @field_validator("header", "content")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Note header and content must not be blank.")
        return value


class PersonalNote(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    header: str
    content: str
    revision: int = Field(ge=1)
    updated_at: str | None = None


class NoteUpdate(NoteRequest):
    revision: int = Field(ge=1)


class BoardImage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    media_type: Literal["image/png", "image/jpeg", "image/gif", "image/webp"]
    data: str = Field(min_length=1, max_length=4 * ((MAX_IMAGE_BYTES + 2) // 3), repr=False)


class BoardNoteRequest(NoteRequest):
    visible: bool
    images: list[BoardImage] | None = Field(default=None, max_length=MAX_BOARD_IMAGES)


class BoardNote(BoardNoteRequest):
    revision: int = Field(ge=1)
    updated_at: str | None = None
    images: list[BoardImage] = Field(default_factory=list, max_length=MAX_BOARD_IMAGES)

    header: str = Field(default="Untitled", min_length=1, max_length=200)


class BoardNoteUpdate(BoardNoteRequest):
    revision: int = Field(ge=1)


class CharacterClass(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    class_name: str = Field(min_length=1, max_length=200)
    class_url: str = Field(default="", max_length=2048)
    subclass_name: str = Field(default="", max_length=200)
    subclass_url: str = Field(default="", max_length=2048)
    levels: int | None = Field(default=None, ge=1, le=100)

    @field_validator("class_name")
    @classmethod
    def class_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Class name must not be blank.")
        return value

    @field_validator("class_url", "subclass_url")
    @classmethod
    def valid_url(cls, value):
        if value:
            try:
                url = urlsplit(value)
                if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
                    raise ValueError("Invalid website URL.")
            except ValueError as error:
                raise ValueError("Invalid website URL.") from error
        return value


class CharacterData(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    name: str = Field(default="", max_length=200)
    race: str = Field(default="", max_length=200)
    gender: str = Field(default="", max_length=200)
    classes: list[CharacterClass] = Field(default_factory=list, max_length=20)
    portrait: BoardImage | None = None
    passive_perception: int | None = Field(default=None, ge=0, le=10000)
    passive_insight: int | None = Field(default=None, ge=0, le=10000)
    armor_class: int | None = Field(default=None, ge=0, le=10000)
    max_hp: int | None = Field(default=None, ge=0, le=1000000)
    initiative_bonus: int | None = Field(default=None, ge=-10000, le=10000)
    strength: int | None = Field(default=None, ge=0, le=1000)
    dexterity: int | None = Field(default=None, ge=0, le=1000)
    constitution: int | None = Field(default=None, ge=0, le=1000)
    intelligence: int | None = Field(default=None, ge=0, le=1000)
    wisdom: int | None = Field(default=None, ge=0, le=1000)
    charisma: int | None = Field(default=None, ge=0, le=1000)
    speed_walk: int | None = Field(default=None, ge=0, le=10000)
    speed_fly: int | None = Field(default=None, ge=0, le=10000)
    speed_swim: int | None = Field(default=None, ge=0, le=10000)
    speed_climb: int | None = Field(default=None, ge=0, le=10000)
    speed_burrow: int | None = Field(default=None, ge=0, le=10000)
    character_description: str = Field(default="", max_length=MAX_NOTE_LENGTH)
    background: str = Field(default="", max_length=MAX_NOTE_LENGTH)
    story: str = Field(default="", max_length=MAX_NOTE_LENGTH)
    revision: int = Field(default=0, ge=0)


class InitiativeCombatant(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    initiative: int = Field(ge=-10000, le=10000)
    current_hp: int = Field(ge=0, le=1000000)
    max_hp: int = Field(ge=1, le=1000000)
    visible: bool = True
    dead: bool = False

    @model_validator(mode="after")
    def validate_combatant(self) -> Self:
        if not self.name.strip():
            raise ValueError("Combatant name must not be blank.")
        if self.current_hp > self.max_hp:
            raise ValueError("Current hit points cannot exceed maximum hit points.")
        return self


class InitiativeTracker(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    combatants: list[InitiativeCombatant] = Field(default_factory=list, max_length=100)
    current_turn_id: str | None = None

    @model_validator(mode="after")
    def validate_turn(self) -> Self:
        ids = {actor.id for actor in self.combatants}
        if len(ids) != len(self.combatants):
            raise ValueError("Combatant IDs must be unique.")
        if self.current_turn_id is not None and not any(
            actor.id == self.current_turn_id and not actor.dead for actor in self.combatants
        ):
            raise ValueError("Current turn must be a living combatant.")
        return self


class SavedInitiativeEncounter(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    tracker: InitiativeTracker

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Encounter name must not be blank.")
        return value


class InitiativeState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    tracker: InitiativeTracker = Field(default_factory=InitiativeTracker)
    encounters: list[SavedInitiativeEncounter] = Field(default_factory=list, max_length=100)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def unique_encounters(self) -> Self:
        if len({encounter.id for encounter in self.encounters}) != len(self.encounters):
            raise ValueError("Encounter IDs must be unique.")
        return self


class StoredMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    user: str
    text: str


class PrivateMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    sender: str
    recipient: str
    text: str


class UserRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    password_hash: str = Field(repr=False)
    role: Literal["dm", "player"]


class Snapshot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    history: list[PrivateMessage | StoredMessage]
    revoked: dict[str, int]
    users: dict[str, UserRecord] = Field(default_factory=dict, repr=False)
    notes: dict[str, dict[str, PersonalNote]] = Field(default_factory=dict, repr=False)
    board: dict[str, BoardNote] = Field(default_factory=dict, repr=False)
    characters: dict[str, CharacterData] = Field(default_factory=dict, repr=False)
    initiative: InitiativeState = Field(default_factory=InitiativeState, repr=False)
    chat_read: dict[str, int] = Field(default_factory=dict, repr=False)

    @model_validator(mode="before")
    @classmethod
    def migrate_chat_read(cls, value):
        if isinstance(value, dict) and "chat_read" not in value:
            value = dict(value)
            history = value.get("history")
            users = value.get("users")
            if isinstance(history, list) and isinstance(users, dict):
                value["chat_read"] = {username: len(history) - 1 for username in users}
        return value

    @field_validator("chat_read")
    @classmethod
    def valid_chat_read(cls, value):
        if any(cursor < -1 for cursor in value.values()):
            raise ValueError("Invalid chat read position.")
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def migrate_legacy_notes(cls, value):
        if not isinstance(value, dict):
            return value
        return {
            username: {"legacy": {
                "header": "Personal notes", "content": notes, "revision": 1,
                "updated_at": None,
            }} if isinstance(notes, str) else notes
            for username, notes in value.items()
        }

    @field_validator("users", mode="before")
    @classmethod
    def migrate_legacy_users(cls, value):
        if not isinstance(value, dict):
            return value
        return {
            username: {
                "password_hash": record,
                "role": "dm" if username == "dm" else "player",
            } if isinstance(record, str) else record
            for username, record in value.items()
        }

    @field_validator("users")
    @classmethod
    def validate_dm_role(cls, value):
        if "dm" in value and value["dm"].role != "dm":
            raise ValueError("The dm account must have the dm role.")
        return value
