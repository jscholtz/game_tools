from dataclasses import dataclass
from uuid import uuid4

from .database import (
    create_custom_creature, load_bestiary_display, load_bestiary_index,
    load_custom_creature, load_custom_creatures, update_custom_creature,
)
from .data_models import BestiaryDisplay, BestiaryEntry, CustomCreature
from .initiative_service import add_bestiary_combatant
from .principal import Principal
from .statblock_renderer import render_creature


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
    return load_bestiary_index() + [
        creature.as_bestiary_entry() for creature in load_custom_creatures()
    ]


def get_bestiary_display(principal: Principal, slug: str) -> BestiaryDisplay:
    principal.require_dm()
    if slug.startswith("custom:"):
        return render_creature(load_custom_creature(slug))
    return load_bestiary_display(slug)


def get_custom_creatures(principal: Principal) -> list[CustomCreature]:
    principal.require_dm()
    return sorted(load_custom_creatures(), key=lambda creature: (creature.name.casefold(), creature.slug))


def save_custom_creature(
    principal: Principal, values: dict[str, str | int | float], original: CustomCreature | None
) -> CustomCreature:
    principal.require_dm()
    creature = CustomCreature.model_validate({
        **values,
        "slug": original.slug if original else f"custom:{uuid4().hex}",
        "revision": uuid4().hex,
    })
    if original is None:
        create_custom_creature(creature)
    else:
        update_custom_creature(creature, original.revision)
    return creature


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
