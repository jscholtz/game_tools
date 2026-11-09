from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .initiative_models import Combatant, InitiativeTracker
from .initiative_store import (
    load_tracker,
    load_tracker_default,
    save_tracker,
    save_tracker_snapshot,
)
from .principal import Principal

_SAVE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="initiative-save")


class PlayerCombatant(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    initiative: int
    dead: bool


class PlayerTracker(BaseModel):
    model_config = ConfigDict(frozen=True)

    combatants: tuple[PlayerCombatant, ...]
    current_turn_id: str | None


def get_player_tracker(principal: Principal) -> PlayerTracker:
    if principal.role != "player":
        raise PermissionError("Only players can access the player tracker.")
    tracker = load_tracker()
    combatants = tuple(
        PlayerCombatant(
            id=actor.id,
            name=actor.name,
            initiative=actor.initiative,
            dead=actor.dead,
        )
        for actor in tracker.combatants
        if actor.visible
    )
    visible_ids = {actor.id for actor in combatants}
    return PlayerTracker(
        combatants=combatants,
        current_turn_id=tracker.current_turn_id if tracker.current_turn_id in visible_ids else None,
    )


def get_dm_tracker(principal: Principal) -> InitiativeTracker:
    principal.require_dm()
    return load_tracker()


def get_dm_tracker_default(principal: Principal) -> InitiativeTracker | None:
    principal.require_dm()
    return load_tracker_default()


def save_dm_tracker(principal: Principal, tracker: InitiativeTracker) -> None:
    principal.require_dm()
    queue_dm_tracker_save(principal, tracker).result()


def queue_dm_tracker_save(principal: Principal, tracker: InitiativeTracker) -> Future[None]:
    principal.require_dm()
    return _SAVE_EXECUTOR.submit(save_tracker, deepcopy(tracker))


def save_dm_tracker_snapshot(principal: Principal, tracker: InitiativeTracker) -> None:
    principal.require_dm()
    save_tracker_snapshot(tracker)


def make_combatant(name: str, initiative: int, hit_points: int) -> Combatant:
    return Combatant(
        id=uuid4().hex,
        name=name,
        initiative=initiative,
        dead=False,
        visible=True,
        current_hp=hit_points,
        max_hp=hit_points,
    )


def advance_turn(principal: Principal, tracker: InitiativeTracker) -> None:
    principal.require_dm()
    living = [actor for actor in tracker.combatants if not actor.dead]
    if not living:
        raise ValueError("No living combatants.")
    current_index = next(
        (index for index, actor in enumerate(living) if actor.id == tracker.current_turn_id),
        -1,
    )
    tracker.current_turn_id = living[(current_index + 1) % len(living)].id


def reorder_combatants(principal: Principal, tracker: InitiativeTracker) -> None:
    principal.require_dm()
    tracker.combatants.sort(key=lambda actor: actor.initiative, reverse=True)


def add_bestiary_combatant(
    principal: Principal, name: str, initiative: int, hit_points: int, slug: str
) -> None:
    principal.require_dm()
    tracker = get_dm_tracker(principal)
    combatant = make_combatant(name, initiative, hit_points)
    combatant.creature_slug = slug
    combatant.visible = False
    tracker.combatants.append(combatant)
    save_dm_tracker(principal, tracker)
