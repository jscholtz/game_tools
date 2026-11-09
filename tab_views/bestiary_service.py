from typing import Any

from .database import load_bestiary_display, load_bestiary_index
from .principal import Principal


def get_bestiary_index(principal: Principal) -> list[dict[str, Any]]:
    principal.require_dm()
    return load_bestiary_index()


def get_bestiary_display(principal: Principal, slug: str) -> dict[str, Any]:
    principal.require_dm()
    return load_bestiary_display(slug)
