from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .database import (
    create_public_notes,
    load_public_image,
    load_public_notes,
    save_public_image,
    save_public_notes,
)
from .data_models import PublicNote
from .principal import Principal


class BoardInputError(ValueError):
    pass


@dataclass(frozen=True)
class BoardEdit:
    header: str
    date: str
    text: str
    visible: bool
    removed_images: list[bool]
    uploads: list[tuple[str, bytes]]
    delete: bool


def new_board_note(principal: Principal) -> PublicNote:
    principal.require_dm()
    return PublicNote(
        header="",
        date=datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat(),
        text="",
        visible=False,
        images=[],
    )


def get_dm_board(principal: Principal) -> tuple[list[PublicNote], str] | None:
    principal.require_dm()
    return load_public_notes()


def get_player_board(principal: Principal) -> list[PublicNote]:
    if principal.role != "player":
        raise PermissionError("Only players can access the player board.")
    board = load_public_notes()
    if board is None:
        return []
    return [note for note in board[0] if note.visible]


def get_board_image(principal: Principal, reference: str) -> tuple[str, bytes]:
    if principal.role == "player":
        if not any(reference in note.images for note in get_player_board(principal)):
            raise PermissionError("Image is not visible to players.")
    else:
        principal.require_dm()
    return load_public_image(reference)


def create_board(principal: Principal) -> bool:
    principal.require_dm()
    return create_public_notes([])


def save_board_edit(
    principal: Principal,
    notes: list[PublicNote],
    revision: str,
    index: int | None,
    edit: BoardEdit,
) -> bool:
    principal.require_dm()
    if index is not None and (index < 0 or index >= len(notes)):
        raise BoardInputError("Public note no longer exists.")
    if edit.delete:
        if index is None:
            raise BoardInputError("Cannot delete a new note.")
        updated_notes = list(notes)
        del updated_notes[index]
    else:
        if not edit.header.strip():
            raise BoardInputError("Enter a header for the note.")
        images = notes[index].images if index is not None else []
        if len(images) != len(edit.removed_images):
            raise BoardInputError("Image selections do not match the note.")
        updated = PublicNote(
            header=edit.header.strip(),
            date=edit.date.strip(),
            text=edit.text,
            visible=edit.visible,
            images=[image for image, remove in zip(images, edit.removed_images, strict=True) if not remove],
        )
        updated.images.extend(save_public_image(name, content) for name, content in edit.uploads)
        updated_notes = list(notes)
        if index is None:
            updated_notes.append(updated)
        else:
            updated_notes[index] = updated
    return save_public_notes(updated_notes, revision)
