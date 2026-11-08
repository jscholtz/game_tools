import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise KeyError(f"Missing required environment variable: {name}")
    return value


def load_character_card_players() -> list[str]:
    path = PROJECT_ROOT / "character_cards.toml"
    with path.open("rb") as config_file:
        config = tomllib.load(config_file)
    players = config.get("players")
    if not isinstance(players, list) or not all(
        isinstance(name, str) and name.strip() and name == name.strip()
        for name in players
    ):
        raise ValueError("players must be a list of non-empty player login names.")
    if len({name.casefold() for name in players}) != len(players):
        raise ValueError("players must not contain duplicate login names.")
    return players
