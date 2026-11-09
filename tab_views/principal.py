from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Principal:
    username: str
    role: Literal["dm", "player"]

    def require_dm(self) -> None:
        if self.role != "dm":
            raise PermissionError("Only the DM can perform this action.")

    def require_player(self) -> None:
        if self.role != "player":
            raise PermissionError("Only players can perform this action.")
