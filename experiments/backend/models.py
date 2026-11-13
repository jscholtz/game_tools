from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_LENGTH = 1000
MAX_NOTE_LENGTH = 100_000
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


class BoardNoteRequest(NoteRequest):
    visible: bool


class BoardNote(BoardNoteRequest):
    revision: int = Field(ge=1)
    updated_at: str | None = None

    header: str = Field(default="Untitled", min_length=1, max_length=200)


class BoardNoteUpdate(BoardNoteRequest):
    revision: int = Field(ge=1)


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
