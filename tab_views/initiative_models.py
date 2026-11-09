from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class Combatant(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    id: str
    name: str
    initiative: int
    dead: bool
    visible: bool
    current_hp: int
    max_hp: int
    creature_slug: str | None = None

    @model_validator(mode="after")
    def validate_hp(self) -> Self:
        if self.max_hp < 1 or not 0 <= self.current_hp <= self.max_hp:
            raise ValueError("Combatant hit points are invalid.")
        return self


class InitiativeTracker(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    combatants: list[Combatant]
    current_turn_id: str | None
