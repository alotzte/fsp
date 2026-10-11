from enum import StrEnum

from sqlalchemy import Enum


def str_enum_column_type(enum_cls: type[StrEnum]) -> Enum:
    """Хранит StrEnum строкой (value, а не имя) без нативного enum Postgres.

    Нативный enum требует отдельной миграции на каждое новое значение; varchar с CHECK: нет.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
