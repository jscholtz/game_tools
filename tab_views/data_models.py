from pydantic import BaseModel, ConfigDict, Field, field_validator


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
