from ..data_models import BestiaryAction, StandardCreature, StatblockCreature

_ABILITY_NAMES = (
    ("strength", "Str"), ("dexterity", "Dex"), ("constitution", "Con"),
    ("intelligence", "Int"), ("wisdom", "Wis"), ("charisma", "Cha"),
)


def _actions(entries: list[BestiaryAction] | None) -> str:
    paragraphs = []
    for entry in entries or []:
        name = entry.name.strip()
        description = entry.desc.strip()
        if name and description:
            paragraphs.append(f"{name.rstrip('.')}. {description}")
        else:
            paragraphs.append(name or description)
    return "\n\n".join(paragraphs)


def _speed(speed: dict[str, int | bool | str]) -> str:
    parts = []
    for mode, value in speed.items():
        if mode == "hover" and isinstance(value, bool):
            if value:
                parts.append("hover")
        elif mode == "notes" and isinstance(value, str):
            parts.append(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            label = "" if mode == "walk" else f"{mode.replace('_', ' ')} "
            parts.append(f"{label}{value} ft.")
        else:
            raise ValueError(f"Invalid creature speed field: {mode}")
    return ", ".join(parts)


def adapt_standard_creature(creature: StandardCreature) -> StatblockCreature:
    creature_type = creature.type
    if creature.subtype.strip():
        creature_type += f" ({creature.subtype})"
    armor_class = str(creature.armor_class)
    if creature.armor_desc and creature.armor_desc.strip():
        armor_class += f" ({creature.armor_desc})"
    saves = []
    for field, label in _ABILITY_NAMES:
        value = getattr(creature, f"{field}_save")
        if value is not None:
            saves.append(f"{label} {value:+d}")
    skills = ", ".join(
        f"{name.replace('_', ' ').title()} {modifier:+d}"
        for name, modifier in creature.skills.items()
    )
    legendary = _actions(creature.legendary_actions)
    if creature.legendary_desc.strip():
        legendary = "\n\n".join(part for part in (creature.legendary_desc, legendary) if part)
    notes = creature.desc
    if creature.spell_list:
        spell_references = "Spell references:\n" + "\n".join(creature.spell_list)
        notes = "\n\n".join(part for part in (notes, spell_references) if part.strip())
    return StatblockCreature(
        name=creature.name, type=creature_type, size=creature.size,
        alignment=creature.alignment, challenge_rating=creature.challenge_rating,
        armor_class=armor_class, hit_points=creature.hit_points, hit_dice=creature.hit_dice,
        speed=_speed(creature.speed), strength=creature.strength, dexterity=creature.dexterity,
        constitution=creature.constitution, intelligence=creature.intelligence,
        wisdom=creature.wisdom, charisma=creature.charisma,
        saving_throws=", ".join(saves), skills=skills,
        damage_vulnerabilities=creature.damage_vulnerabilities,
        damage_resistances=creature.damage_resistances,
        damage_immunities=creature.damage_immunities,
        condition_immunities=creature.condition_immunities,
        senses=creature.senses, languages=creature.languages,
        traits=_actions(creature.special_abilities), actions=_actions(creature.actions),
        bonus_actions=_actions(creature.bonus_actions), reactions=_actions(creature.reactions),
        legendary_actions=legendary, notes=notes,
    )
