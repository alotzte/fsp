import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.services.db.base import Base
from app.services.db.types import str_enum_column_type


class ConsentKind(StrEnum):
    # Раздельные согласия по 152-ФЗ: на обработку и на распространение (показ работодателям).
    DATA_PROCESSING = "data_processing"
    PROFILE_PUBLICATION = "profile_publication"
    # Получение результатов из реестра ФСП по привязанному ФСП ID (данные от третьего лица).
    FSP_DATA = "fsp_data"


class Consent(Base):
    """Факт согласия: какой документ, какой версии и когда принят. Строки не удаляются:
    при отзыве ставится revoked_at, так остаётся история для проверки."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ConsentKind] = mapped_column(str_enum_column_type(ConsentKind))
    document_version: Mapped[str] = mapped_column(String(32))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
