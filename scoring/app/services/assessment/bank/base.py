"""Семейства заданий: шаблон + генератор параметров + эталонный ответ.

Экземпляр строится детерминированно из seed: данные, имена и дистракторы у каждого кандидата
свои, а структура решения и сложность (параметры IRT a, b) общие для семейства. Выученный
ответ на чужой экземпляр не подходит к своему: переносится только умение, его и измеряем.

Эталонные ответы по возможности не пишутся руками, а вычисляются: Python-фрагменты
исполняются (`run_python`), SQL выполняется в SQLite (`run_sql`). Код фрагментов:
наш собственный шаблон, пользовательский ввод туда не попадает.
"""

import contextlib
import io
import re
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from random import Random


class ItemKind(StrEnum):
    # Выбор одного варианта.
    CHOICE = "choice"
    # Короткий ответ строкой (число, вывод программы). Сравнение без учёта регистра и
    # лишних пробелов.
    TEXT = "text"


@dataclass(frozen=True)
class Item:
    kind: ItemKind
    prompt: str
    answer: str
    code: str | None = None
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Family:
    id: str
    competency: str
    # Параметры 2PL. ponytail: экспертные, до калибровки на ответах пилота.
    a: float
    b: float
    generate: Callable[[Random], Item]


FAMILIES: dict[str, Family] = {}


def family(
    family_id: str, *, competency: str, a: float, b: float
) -> Callable[[Callable[[Random], Item]], Callable[[Random], Item]]:
    """Регистрирует генератор экземпляров как семейство заданий."""

    def register(generate: Callable[[Random], Item]) -> Callable[[Random], Item]:
        if family_id in FAMILIES:
            msg = f"Семейство {family_id} уже зарегистрировано"
            raise ValueError(msg)
        FAMILIES[family_id] = Family(family_id, competency, a, b, generate)
        return generate

    return register


_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


def normalize_answer(value: str) -> str:
    """Регистр, пробелы и разделители не важны: «0,42» = «0.42», «3, 3, 3» = «3 3 3»."""
    value = _DECIMAL_COMMA.sub(".", value.lower()).replace(",", " ")
    return " ".join(value.split())


def choice(
    rng: Random,
    prompt: str,
    correct: str,
    distractors: Sequence[str],
    code: str | None = None,
) -> Item:
    """Вопрос с выбором: варианты перемешиваются, дубли верного ответа отбрасываются."""
    options = [correct]
    for option in distractors:
        if normalize_answer(option) not in {normalize_answer(o) for o in options}:
            options.append(option)
    rng.shuffle(options)
    return Item(ItemKind.CHOICE, prompt, correct, code, options)


def text(prompt: str, answer: object, code: str | None = None) -> Item:
    return Item(ItemKind.TEXT, prompt, str(answer), code)


def run_python(code: str) -> str:
    """Исполняет фрагмент и возвращает напечатанное (без завершающего перевода строки)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(code, {"__name__": "__main__"})  # noqa: S102  # только собственные шаблоны
    return buffer.getvalue().rstrip("\n")


def run_sql(
    schema: str, rows: dict[str, Sequence[tuple[object, ...]]], query: str
) -> object:
    """Выполняет запрос в SQLite в памяти и возвращает единственное значение результата."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema)
        for table, table_rows in rows.items():
            if table_rows:
                placeholders = ", ".join("?" * len(table_rows[0]))
                connection.executemany(
                    f"INSERT INTO {table} VALUES ({placeholders})", table_rows
                )
        (value,) = connection.execute(query).fetchone()
    finally:
        connection.close()
    return value
