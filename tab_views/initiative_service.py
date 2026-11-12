from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from .initiative_models import Combatant, InitiativeTracker, SavedEncounter
from .initiative_store import (
    create_encounter,
    delete_encounter,
    list_encounters,
    load_encounter,
    load_tracker,
    overwrite_encounter,
    rename_encounter,
    save_tracker,
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
    return _SAVE_EXECUTOR.submit(load_tracker).result()


def list_dm_encounters(principal: Principal) -> list[SavedEncounter]:
    principal.require_dm()
    return list_encounters()


def _encounter_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Enter an encounter name.")
    if len(name) > 200:
        raise ValueError("Encounter name must be at most 200 characters.")
    return name


def create_dm_encounter(principal: Principal, name: str) -> SavedEncounter:
    principal.require_dm()
    name = _encounter_name(name)
    return _SAVE_EXECUTOR.submit(lambda: create_encounter(name, load_tracker())).result()


def overwrite_dm_encounter(principal: Principal, encounter_id: str) -> None:
    principal.require_dm()
    _SAVE_EXECUTOR.submit(lambda: overwrite_encounter(encounter_id, load_tracker())).result()


def load_dm_encounter(principal: Principal, encounter_id: str) -> InitiativeTracker:
    principal.require_dm()

    def load_and_save() -> InitiativeTracker:
        tracker = load_encounter(encounter_id).tracker
        save_tracker(tracker)
        return tracker

    return _SAVE_EXECUTOR.submit(load_and_save).result()


def rename_dm_encounter(principal: Principal, encounter_id: str, name: str) -> None:
    principal.require_dm()
    rename_encounter(encounter_id, _encounter_name(name))


def delete_dm_encounter(principal: Principal, encounter_id: str) -> None:
    principal.require_dm()
    delete_encounter(encounter_id)


def save_dm_tracker(principal: Principal, tracker: InitiativeTracker) -> None:
    principal.require_dm()
    queue_dm_tracker_save(principal, tracker).result()


def queue_dm_tracker_save(principal: Principal, tracker: InitiativeTracker) -> Future[None]:
    principal.require_dm()
    return _SAVE_EXECUTOR.submit(save_tracker, deepcopy(tracker))


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


def _combatant(principal: Principal, tracker: InitiativeTracker, combatant_id: str) -> Combatant:
    principal.require_dm()
    actor = next((item for item in tracker.combatants if item.id == combatant_id), None)
    if actor is None:
        raise ValueError("Combatant no longer exists.")
    return actor


def add_combatant(
    principal: Principal, tracker: InitiativeTracker, name: str, initiative: int, hit_points: int
) -> None:
    principal.require_dm()
    name = name.strip()
    if not name:
        raise ValueError("Enter a character or monster name.")
    tracker.combatants.append(make_combatant(name, initiative, hit_points))


def set_combatant_initiative(
    principal: Principal, tracker: InitiativeTracker, combatant_id: str, initiative: int
) -> None:
    _combatant(principal, tracker, combatant_id).initiative = initiative


def set_combatant_hp(
    principal: Principal, tracker: InitiativeTracker, combatant_id: str, current_hp: int
) -> None:
    actor = _combatant(principal, tracker, combatant_id)
    actor.current_hp = min(current_hp, actor.max_hp)


def set_combatant_visibility(
    principal: Principal, tracker: InitiativeTracker, combatant_id: str, visible: bool
) -> None:
    _combatant(principal, tracker, combatant_id).visible = visible


def toggle_combatant_death(
    principal: Principal, tracker: InitiativeTracker, combatant_id: str
) -> None:
    actor = _combatant(principal, tracker, combatant_id)
    actor.dead = not actor.dead
    if actor.dead and tracker.current_turn_id == actor.id:
        tracker.current_turn_id = None


def remove_combatant(principal: Principal, tracker: InitiativeTracker, combatant_id: str) -> None:
    actor = _combatant(principal, tracker, combatant_id)
    tracker.combatants.remove(actor)
    if tracker.current_turn_id == actor.id:
        tracker.current_turn_id = None


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
