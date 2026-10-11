"""Компетенция «SQL». Ответы на запросы вычисляются в SQLite (run_sql).

Используется только синтаксис, одинаково работающий в SQLite и PostgreSQL.
"""

from collections.abc import Sequence
from random import Random

from app.services.assessment.bank.base import Item, choice, family, run_sql, text

COMPETENCY = "sql"
_DEPTS = ["sales", "dev", "ops", "hr", "qa"]
_PEOPLE = [
    "Анна",
    "Борис",
    "Вера",
    "Глеб",
    "Дина",
    "Егор",
    "Жанна",
    "Иван",
    "Кира",
    "Лев",
]
_EMPLOYEES = "CREATE TABLE employees (name TEXT, dept TEXT, salary INTEGER);"


def _employees(rng: Random, count: int, depts: int = 3) -> list[tuple[object, ...]]:
    names = rng.sample(_PEOPLE, count)
    chosen = rng.sample(_DEPTS, depts)
    return [
        (name, rng.choice(chosen), rng.randrange(80, 260, 10) * 1000) for name in names
    ]


def _table(rows: Sequence[tuple[object, ...]], header: str) -> str:
    lines = [header] + [
        " | ".join("NULL" if v is None else str(v) for v in row) for row in rows
    ]
    return "\n".join(lines)


@family("sql.where_count", competency=COMPETENCY, a=1.1, b=-1.4)
def _where_count(rng: Random) -> Item:
    rows = _employees(rng, rng.randint(6, 8))
    threshold = rng.randrange(120, 220, 10) * 1000
    op = rng.choice([">", ">="])
    query = f"SELECT COUNT(*) FROM employees WHERE salary {op} {threshold}"
    answer = run_sql(_EMPLOYEES, {"employees": rows}, query)
    code = f"-- employees\n{_table(rows, 'name | dept | salary')}\n\n{query};"
    return text("Какое число вернёт запрос?", answer, code)


@family("sql.group_having", competency=COMPETENCY, a=1.3, b=-0.3)
def _group_having(rng: Random) -> Item:
    rows = _employees(rng, rng.randint(7, 9), depts=4)
    k = rng.randint(2, 3)
    query = (
        "SELECT COUNT(*) FROM (\n  SELECT dept FROM employees\n  GROUP BY dept\n"
        f"  HAVING COUNT(*) >= {k}\n) t"
    )
    answer = run_sql(_EMPLOYEES, {"employees": rows}, query)
    code = f"-- employees\n{_table(rows, 'name | dept | salary')}\n\n{query};"
    return text("Какое число вернёт запрос?", answer, code)


@family("sql.count_null", competency=COMPETENCY, a=1.4, b=0.2)
def _count_null(rng: Random) -> Item:
    rows: list[tuple[object, ...]] = [
        (
            name,
            rng.choice([None, None, "@" + name.lower()[:3] + str(rng.randint(1, 99))]),
        )
        for name in rng.sample(_PEOPLE, rng.randint(6, 8))
    ]
    expr = rng.choice(
        ["COUNT(telegram)", "COUNT(*) - COUNT(telegram)", "COUNT(DISTINCT telegram)"]
    )
    query = f"SELECT {expr} FROM contacts"
    answer = run_sql(
        "CREATE TABLE contacts (name TEXT, telegram TEXT);", {"contacts": rows}, query
    )
    code = f"-- contacts\n{_table(rows, 'name | telegram')}\n\n{query};"
    return text("Какое число вернёт запрос?", answer, code)


@family("sql.left_join", competency=COMPETENCY, a=1.4, b=0.5)
def _left_join(rng: Random) -> Item:
    users = [
        (i, name) for i, name in enumerate(rng.sample(_PEOPLE, rng.randint(5, 7)), 1)
    ]
    orders = [
        (n, rng.choice(users)[0], rng.randrange(1, 50) * 100)
        for n in range(1, rng.randint(4, 8))
    ]
    variant = rng.choice(
        [
            "SELECT COUNT(*) FROM users u LEFT JOIN orders o ON o.user_id = u.id",
            (
                "SELECT COUNT(*) FROM users u LEFT JOIN orders o ON o.user_id = u.id\n"
                "WHERE o.id IS NULL"
            ),
            "SELECT COUNT(DISTINCT u.id) FROM users u JOIN orders o ON o.user_id = u.id",
        ]
    )
    answer = run_sql(
        "CREATE TABLE users (id INTEGER, name TEXT);"
        "CREATE TABLE orders (id INTEGER, user_id INTEGER, amount INTEGER);",
        {"users": users, "orders": orders},
        variant,
    )
    code = (
        f"-- users\n{_table(users, 'id | name')}\n\n-- orders\n"
        f"{_table(orders, 'id | user_id | amount')}\n\n{variant};"
    )
    return text("Какое число вернёт запрос?", answer, code)


@family("sql.index_choice", competency=COMPETENCY, a=1.3, b=0.8)
def _index_choice(rng: Random) -> Item:
    table, eq_col, range_col = rng.choice(
        [
            ("orders", "customer_id", "created_at"),
            ("events", "user_id", "occurred_at"),
            ("payments", "merchant_id", "paid_at"),
        ]
    )
    query = (
        f"SELECT * FROM {table}\nWHERE {eq_col} = $1 AND {range_col} >= $2\n"
        f"ORDER BY {range_col} DESC\nLIMIT 20;"
    )
    return choice(
        rng,
        "Таблица большая, запрос ниже выполняется часто. Какой индекс подходит лучше всего?",
        f"({eq_col}, {range_col})",
        [
            f"({range_col}, {eq_col})",
            f"Два отдельных: ({eq_col}) и ({range_col})",
            f"({range_col})",
        ],
        code=query,
    )


@family("sql.window_top", competency=COMPETENCY, a=1.5, b=1.2)
def _window_top(rng: Random) -> Item:
    rows = _employees(rng, rng.randint(8, 10), depts=3)
    n = rng.randint(1, 2)
    fn = rng.choice(["ROW_NUMBER()", "RANK()", "DENSE_RANK()"])
    # Одинаковые зарплаты делают разницу между ROW_NUMBER и RANK видимой.
    rows[1] = (rows[1][0], rows[0][1], rows[0][2])
    query = (
        "SELECT COUNT(*) FROM (\n"
        f"  SELECT {fn} OVER (PARTITION BY dept ORDER BY salary DESC) AS r\n"
        f"  FROM employees\n) t\nWHERE r <= {n}"
    )
    answer = run_sql(_EMPLOYEES, {"employees": rows}, query)
    code = f"-- employees\n{_table(rows, 'name | dept | salary')}\n\n{query};"
    return text("Какое число вернёт запрос?", answer, code)


_NON_REPEATABLE = "Неповторяющееся чтение: повторный SELECT видит чужие коммиты"
_WRITE_SKEW = "Аномалия сериализации (write skew): обе транзакции проверили условие и записали каждая своё"
_RETRY = "Повторять транзакцию при ошибке сериализации (SQLSTATE 40001)"


@family("sql.isolation", competency=COMPETENCY, a=1.4, b=2.0)
def _isolation(rng: Random) -> Item:
    question, correct = rng.choice(
        [
            (
                (
                    "PostgreSQL, READ COMMITTED. Что возможно на этом уровне, но уже невозможно "
                    "на REPEATABLE READ?"
                ),
                _NON_REPEATABLE,
            ),
            (
                (
                    "PostgreSQL, REPEATABLE READ. Что возможно на этом уровне, но уже невозможно "
                    "на SERIALIZABLE?"
                ),
                _WRITE_SKEW,
            ),
            (
                "PostgreSQL, SERIALIZABLE. Что обязательно должно уметь приложение?",
                _RETRY,
            ),
        ]
    )
    return choice(
        rng,
        question,
        correct,
        [
            _NON_REPEATABLE,
            _WRITE_SKEW,
            _RETRY,
            "Грязное чтение: видны незакоммиченные изменения другой транзакции",
        ],
    )


_STAFF = "CREATE TABLE staff (id INTEGER, name TEXT, manager_id INTEGER);"


@family("sql.recursive_cte", competency=COMPETENCY, a=1.4, b=1.9)
def _recursive_cte(rng: Random) -> Item:
    n = rng.randint(8, 10)
    names = rng.sample(_PEOPLE, n)
    while True:
        # Дерево подчинения: начальник каждого это кто-то из добавленных раньше.
        manager_of = {i: rng.randint(1, i - 1) for i in range(2, n + 1)}
        children: dict[int, list[int]] = {}
        for employee, manager in manager_of.items():
            children.setdefault(manager, []).append(employee)
        # Начальник с подчинёнными второго уровня: без рекурсии ответ не получить.
        roots = [
            m
            for m, kids in sorted(children.items())
            if any(k in children for k in kids)
        ]
        if roots:
            break
    root = rng.choice(roots)
    rows: list[tuple[object, ...]] = [
        (i, names[i - 1], manager_of.get(i)) for i in range(1, n + 1)
    ]
    query = (
        "WITH RECURSIVE team(id) AS (\n"
        f"  SELECT id FROM staff WHERE manager_id = {root}\n"
        "  UNION ALL\n"
        "  SELECT s.id FROM staff s JOIN team t ON s.manager_id = t.id\n"
        ")\nSELECT COUNT(*) FROM team"
    )
    answer = run_sql(_STAFF, {"staff": rows}, query)
    code = f"-- staff\n{_table(rows, 'id | name | manager_id')}\n\n{query};"
    return text("Какое число вернёт запрос?", answer, code)


_PAYMENTS = "CREATE TABLE payments (id INTEGER, day INTEGER, amount INTEGER);"


@family("sql.window_frame", competency=COMPETENCY, a=1.5, b=2.3)
def _window_frame(rng: Random) -> Item:
    n = rng.randint(6, 8)
    # Дней меньше, чем платежей: обязательно есть платежи в один день.
    days = sorted(rng.randint(1, 5) for _ in range(n))
    rows: list[tuple[object, ...]] = [
        (i, day, rng.randrange(100, 1000, 50)) for i, day in enumerate(days, 1)
    ]
    tied = [day for day in set(days) if days.count(day) > 1]
    # Первый платеж дня с несколькими платежами: на нём RANGE по умолчанию (все «равные»
    # по ORDER BY строки входят в рамку) расходится с подсчётом по строкам.
    target = days.index(rng.choice(sorted(tied))) + 1
    window = rng.choice(
        [
            "ORDER BY day",
            "ORDER BY day, id",
            "ORDER BY day, id ROWS BETWEEN 1 PRECEDING AND CURRENT ROW",
        ]
    )
    query = (
        "SELECT total FROM (\n"
        f"  SELECT id, SUM(amount) OVER ({window}) AS total\n"
        "  FROM payments\n"
        f") t\nWHERE id = {target}"
    )
    answer = run_sql(_PAYMENTS, {"payments": rows}, query)
    code = f"-- payments\n{_table(rows, 'id | day | amount')}\n\n{query};"
    return text("Какое число вернёт запрос?", answer, code)
