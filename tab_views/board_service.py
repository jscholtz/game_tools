from .database import (
    PublicNote,
    create_public_notes,
    load_public_image,
    load_public_notes,
    save_public_image,
    save_public_notes,
)
from .principal import Principal


def get_dm_board(principal: Principal) -> tuple[list[PublicNote], str] | None:
    principal.require_dm()
    return load_public_notes()


def get_player_board(principal: Principal) -> list[PublicNote]:
    if principal.role != "player":
        raise PermissionError("Only players can access the player board.")
    board = load_public_notes()
    if board is None:
        return []
    return [note for note in board[0] if note["visible"]]


def get_board_image(principal: Principal, reference: str) -> tuple[str, bytes]:
    if principal.role == "player":
        if not any(reference in note["images"] for note in get_player_board(principal)):
            raise PermissionError("Image is not visible to players.")
    else:
        principal.require_dm()
    return load_public_image(reference)


def create_board(principal: Principal) -> bool:
    principal.require_dm()
    return create_public_notes([])


def add_board_image(principal: Principal, name: str, content: bytes) -> str:
    principal.require_dm()
    return save_public_image(name, content)


def save_board(principal: Principal, notes: list[PublicNote], revision: str) -> bool:
    principal.require_dm()
    return save_public_notes(notes, revision)
