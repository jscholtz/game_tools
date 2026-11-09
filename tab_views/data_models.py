from fractions import Fraction

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    username: str
    password_hash: str = Field(repr=False)
    role: str


class BestiaryEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    slug: str
    name: str
    type: str
    size: str
    challenge_rating: str
    cr: float
    document__title: str
    hit_points: int | None = None


class CustomCreature(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    slug: str
    revision: str
    name: str
    type: str
    size: str
    alignment: str = ""
    challenge_rating: str
    armor_class: str
    hit_points: int = Field(ge=1)
    hit_dice: str = ""
    speed: str
    strength: int = Field(ge=1)
    dexterity: int = Field(ge=1)
    constitution: int = Field(ge=1)
    intelligence: int = Field(ge=1)
    wisdom: int = Field(ge=1)
    charisma: int = Field(ge=1)
    saving_throws: str = ""
    skills: str = ""
    damage_vulnerabilities: str = ""
    damage_resistances: str = ""
    damage_immunities: str = ""
    condition_immunities: str = ""
    senses: str = ""
    languages: str = ""
    traits: str = ""
    actions: str = ""
    bonus_actions: str = ""
    reactions: str = ""
    legendary_actions: str = ""
    lair_actions: str = ""
    notes: str = ""

    @field_validator("name", "type", "size", "armor_class", "speed")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be empty.")
        return value

    @field_validator("challenge_rating")
    @classmethod
    def validate_challenge_rating(cls, value: str) -> str:
        value = value.strip()
        try:
            rating = float(Fraction(value))
        except (ValueError, ZeroDivisionError, OverflowError) as error:
            raise ValueError("Challenge rating must be a non-negative number or fraction.") from error
        if rating < 0 or rating == float("inf"):
            raise ValueError("Challenge rating must be a non-negative number or fraction.")
        return value

    def as_bestiary_entry(self) -> BestiaryEntry:
        return BestiaryEntry(
            slug=self.slug, name=self.name, type=self.type, size=self.size,
            challenge_rating=self.challenge_rating, cr=float(Fraction(self.challenge_rating)),
            document__title="Custom", hit_points=self.hit_points,
        )


class BestiaryDisplay(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    inline: str
    sizes: list[int]

    @field_validator("inline")
    @classmethod
    def validate_html(cls, html: str) -> str:
        if "<head>" not in html or "</body>" not in html:
            raise ValueError("Creature stat block has invalid HTML or dimensions.")
        return html

    @field_validator("sizes")
    @classmethod
    def validate_sizes(cls, sizes: list[int]) -> list[int]:
        if len(sizes) != 2 or any(size <= 0 for size in sizes):
            raise ValueError("Creature stat block has invalid HTML or dimensions.")
        return sizes


class CharacterClass(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    class_name: str
    class_url: str
    subclass_name: str
    subclass_url: str
    levels: str


class CharacterData(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    character: str = ""
    race: str = ""
    gender: str = ""
    passive_perception: int | None = None
    passive_insight: int | None = None
    armor_class: int | None = None
    max_hp: int | None = None
    classes: list[CharacterClass] = Field(default_factory=list)
    portrait: bytes | None = None
    initiative_bonus: int = 0
    character_description: str = ""
    background: str = ""
    story: str = ""


class PrivateNote(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    id: str
    text: str
    created_at: str


class ChatMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    sender: str
    recipient: str
    timestamp: str
    text: str
    dm_read: bool | None = None


class PublicNote(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    header: str
    date: str
    text: str
    visible: bool
    images: list[str]

    @field_validator("images")
    @classmethod
    def validate_images(cls, images: list[str]) -> list[str]:
        if any(not image.startswith("image:") or len(image) == len("image:") for image in images):
            raise ValueError("Invalid public note image reference.")
        return images


class PublicBoard(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)

    notes: list[PublicNote]
    revision: str
