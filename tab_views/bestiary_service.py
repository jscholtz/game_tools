from dataclasses import dataclass

from .database import load_bestiary_display, load_bestiary_index
from .data_models import BestiaryDisplay, BestiaryEntry
from .initiative_service import add_bestiary_combatant
from .principal import Principal


@dataclass(frozen=True)
class BestiaryFilters:
    name: str
    type: str
    rating: str
    size: str
    source: str


@dataclass(frozen=True)
class BestiaryOptions:
    types: list[str]
    ratings: list[str]
    sizes: list[str]
    sources: list[str]


def get_bestiary_index(principal: Principal) -> list[BestiaryEntry]:
    principal.require_dm()
    return load_bestiary_index()


def get_bestiary_display(principal: Principal, slug: str) -> BestiaryDisplay:
    principal.require_dm()
    return load_bestiary_display(slug)


def bestiary_options(creatures: list[BestiaryEntry]) -> BestiaryOptions:
    ratings = {entry.challenge_rating: entry.cr for entry in creatures}
    return BestiaryOptions(
        types=sorted({entry.type for entry in creatures}),
        ratings=sorted(ratings, key=ratings.__getitem__),
        sizes=sorted({entry.size for entry in creatures}),
        sources=sorted({entry.document__title for entry in creatures}),
    )


def filter_bestiary(creatures: list[BestiaryEntry], filters: BestiaryFilters) -> list[BestiaryEntry]:
    name = filters.name.strip().casefold()
    return sorted(
        (
            entry for entry in creatures
            if name in entry.name.casefold()
            and (filters.type == "All" or entry.type == filters.type)
            and (filters.rating == "All" or entry.challenge_rating == filters.rating)
            and (filters.size == "All" or entry.size == filters.size)
            and (filters.source == "All" or entry.document__title == filters.source)
        ),
        key=lambda entry: (entry.name.casefold(), entry.document__title, entry.slug),
    )


def creature_hit_points(creature: BestiaryEntry) -> int:
    hit_points = creature.hit_points
    if hit_points is None or hit_points < 1:
        raise ValueError("Creature hit points must be a positive whole number.")
    return hit_points


def add_creature(principal: Principal, creature: BestiaryEntry, name: str, initiative: int) -> None:
    principal.require_dm()
    name = name.strip()
    if not name:
        raise ValueError("Enter a name for the combatant.")
    add_bestiary_combatant(principal, name, initiative, creature_hit_points(creature), creature.slug)
