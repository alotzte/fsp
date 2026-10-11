from enum import StrEnum

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.services.db.base import Base
from app.services.db.types import str_enum_column_type


class Specialization(Base):
    """Направление из справочника, например «Backend-разработка»."""

    __tablename__ = "specializations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))

    def __str__(self) -> str:
        return self.title


class Grade(Base):
    """Грейд из справочника. По `level` грейды упорядочиваются: тест на уровень ниже или выше."""

    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(unique=True)

    def __str__(self) -> str:
        return self.title


class SkillKind(StrEnum):
    TECHNOLOGY = "technology"
    SOFT = "soft"


class Skill(Base):
    """Навык из справочника: технология или софт-скилл.

    aliases: синонимы в нижнем регистре («js», «javascript»): по ним свой тег кандидата
    сопоставляется со справочником, и фильтр по стеку не дробится на варианты написания.
    """

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[SkillKind] = mapped_column(str_enum_column_type(SkillKind), index=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(128)), default=list)

    def __str__(self) -> str:
        return self.title


class Industry(Base):
    """Отрасль компании, например «Финтех»."""

    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(128))

    def __str__(self) -> str:
        return self.title
