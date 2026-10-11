from pydantic import BaseModel, ConfigDict

from app.services.db.models import SkillKind


class SpecializationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str


class GradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    level: int


class SkillDictionaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: SkillKind
    title: str
    aliases: list[str]


class IndustryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
