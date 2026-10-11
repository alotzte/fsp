# Импорт модулей регистрирует их семейства в FAMILIES.
from app.services.assessment.bank import (
    algorithms,
    http_api,
    js,
    ml,
    python,
    react,
    sql,
    web,
)
from app.services.assessment.bank.base import (
    FAMILIES,
    Family,
    Item,
    ItemKind,
    normalize_answer,
)

__all__ = [
    "FAMILIES",
    "Family",
    "Item",
    "ItemKind",
    "algorithms",
    "http_api",
    "js",
    "ml",
    "normalize_answer",
    "python",
    "react",
    "sql",
    "web",
]
