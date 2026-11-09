"""Static HTML statblocks adapted from Valloric/statblock5e (Apache-2.0).

The original web components and Shadow DOM styles have been rewritten as
Python-generated HTML and ordinary CSS. See LICENSE.txt in this directory.
"""

import re
from html import escape
from textwrap import wrap

from ..data_models import BestiaryDisplay, CustomCreature

_STYLE = """
body { margin: 0; }
stat-block {
  display: inline-block;
  margin: 20px;
  width: 420px;
}
.bar {
  height: 5px;
  background: #E69A28;
  border: 1px solid #000;
  position: relative;
  z-index: 1;
}
.content {
  font-family: 'Noto Sans', 'Myriad Pro', Calibri, Helvetica, Arial, sans-serif;
  font-size: 13.5px;
  background: #FDF1DC;
  padding: 0.6em 0.6em 0.5em;
  border: 1px solid #DDD;
  box-shadow: 0 0 1.5em #867453;
  position: relative;
  margin: 0 2px;
  overflow-wrap: anywhere;
}
h1 {
  font-family: 'Libre Baskerville', 'Lora', 'Calisto MT', 'Bookman Old Style',
    Bookman, 'Goudy Old Style', Garamond, 'Hoefler Text', 'Bitstream Charter',
    Georgia, serif;
  color: #7A200D;
  font-weight: 700;
  margin: 0;
  font-size: 23px;
  letter-spacing: 1px;
  font-variant: small-caps;
}
.subtitle { font-weight: normal; font-style: italic; font-size: 12px; margin: 0; }
.top-stats { color: #7A200D; }
.rule {
  background: #922610;
  height: 5px;
  margin: 0.6em 0 0.35em;
  clip-path: polygon(0 0, 100% 50%, 0 100%);
}
.property-line { line-height: 1.4; padding-left: 1em; text-indent: -1em; }
.property-line strong { font-weight: bold; }
table { width: 100%; border: 0; border-collapse: collapse; }
th, td { width: 16.666%; text-align: center; }
.property-block { margin: 0.3em 0 0.9em; line-height: 1.5; white-space: pre-wrap; }
.property-block strong { font-weight: bold; font-style: italic; }
h3 {
  border-bottom: 1px solid #7A200D;
  color: #7A200D;
  font-size: 21px;
  font-variant: small-caps;
  font-weight: normal;
  letter-spacing: 1px;
  margin: 0 0 0.3em;
}
.content > :last-child { margin-bottom: 0; }
"""


def _property_line(label: str, value: str) -> str:
    if not value.strip():
        return ""
    return (
        f'<div class="property-line"><strong>{escape(label)}</strong> '
        f'{escape(value).replace(chr(10), "<br>")}</div>'
    )


def _section(label: str, value: str) -> str:
    if not value.strip():
        return ""
    blocks = []
    for paragraph in re.split(r"\n\s*\n", value.strip()):
        # A short first sentence is a conventional statblock ability name.
        match = re.match(r"^([^\n.]{1,80}\.)\s+(.+)$", paragraph, re.DOTALL)
        if match:
            content = f"<strong>{escape(match.group(1))}</strong> {escape(match.group(2))}"
        else:
            content = escape(paragraph)
        blocks.append(f'<div class="property-block">{content}</div>')
    return f"<h3>{escape(label)}</h3>{''.join(blocks)}"


def render_creature(creature: CustomCreature) -> BestiaryDisplay:
    subtitle = f"{creature.size} {creature.type}"
    if creature.alignment:
        subtitle += f", {creature.alignment}"
    hit_points = str(creature.hit_points)
    if creature.hit_dice:
        hit_points += f" ({creature.hit_dice})"
    primary = [
        ("Armor Class", creature.armor_class),
        ("Hit Points", hit_points),
        ("Speed", creature.speed),
    ]
    secondary = [
        ("Saving Throws", creature.saving_throws),
        ("Skills", creature.skills),
        ("Damage Vulnerabilities", creature.damage_vulnerabilities),
        ("Damage Resistances", creature.damage_resistances),
        ("Damage Immunities", creature.damage_immunities),
        ("Condition Immunities", creature.condition_immunities),
        ("Senses", creature.senses),
        ("Languages", creature.languages),
        ("Challenge", creature.challenge_rating),
    ]
    abilities = [
        ("STR", creature.strength), ("DEX", creature.dexterity),
        ("CON", creature.constitution), ("INT", creature.intelligence),
        ("WIS", creature.wisdom), ("CHA", creature.charisma),
    ]
    sections = [
        ("Traits", creature.traits), ("Actions", creature.actions),
        ("Bonus Actions", creature.bonus_actions), ("Reactions", creature.reactions),
        ("Legendary Actions", creature.legendary_actions), ("Lair Actions", creature.lair_actions),
        ("Notes", creature.notes),
    ]
    headings = "".join(f"<th scope=\"col\">{name}</th>" for name, _ in abilities)
    scores = "".join(
        f"<td>{score} ({(score - 10) // 2:+d})</td>" for _, score in abilities
    )
    primary_html = "".join(_property_line(label, value) for label, value in primary)
    secondary_html = "".join(_property_line(label, value) for label, value in secondary)
    sections_html = "".join(_section(label, value) for label, value in sections)
    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<style>{_STYLE}</style></head><body><stat-block>"
        '<div class="bar"></div><div class="content">'
        f'<h1>{escape(creature.name)}</h1><p class="subtitle">{escape(subtitle)}</p>'
        f'<div class="top-stats"><div class="rule"></div>{primary_html}'
        f'<div class="rule"></div><table><tr>{headings}</tr><tr>{scores}</tr></table>'
        f'<div class="rule"></div>{secondary_html}<div class="rule"></div></div>'
        f'{sections_html}</div><div class="bar"></div></stat-block></body></html>'
    )
    lines = sum(
        sum(max(1, len(wrap(line, width=45))) for line in value.split("\n"))
        for _, value in primary + secondary + sections if value.strip()
    )
    height = max(500, 300 + lines * 25 + sum(35 for _, value in sections if value.strip()))
    return BestiaryDisplay(inline=html, sizes=[height, 460])
