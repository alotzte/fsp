"""Компетенция «JavaScript». Ответы вычисляются по явной модели семантики языка.

Код считается выполняемым как ES-модуль (строгий режим) в современном браузере.
"""

from collections import deque
from random import Random

from app.services.assessment.bank.base import Item, choice, family, text

COMPETENCY = "js"

# (левая часть, правая часть, результат ==, результат ===)
_EQUALITY = [
    ("'1'", "1", True, False),
    ("null", "undefined", True, False),
    ("0", "''", True, False),
    ("NaN", "NaN", False, False),
    ("[]", "false", True, False),
    ("'abc'", "'abc'", True, True),
    ("null", "0", False, False),
    ("0", "'0'", True, False),
]


def _js_bool(value: bool) -> str:
    return "true" if value else "false"


@family("js.equality", competency=COMPETENCY, a=1.1, b=-1.3)
def _equality(rng: Random) -> Item:
    left, right, loose, strict = rng.choice(_EQUALITY)
    code = f"console.log({left} == {right}, {left} === {right})"
    return text(
        "Что выведет код? Ответ: два значения через пробел.",
        f"{_js_bool(loose)} {_js_bool(strict)}",
        code,
    )


@family("js.array_methods", competency=COMPETENCY, a=1.2, b=-0.6)
def _array_methods(rng: Random) -> Item:
    nums = [rng.randint(1, 9) for _ in range(rng.randint(5, 7))]
    k = rng.randint(2, 4)
    t = rng.randint(8, 20)
    reducer = rng.choice(["length", "sum"])
    mapped = [x * k for x in nums if x * k > t]
    if reducer == "length":
        tail, answer = ".length", len(mapped)
    else:
        tail, answer = ".reduce((s, x) => s + x, 0)", sum(mapped)
    code = f"const nums = [{', '.join(map(str, nums))}]\n"
    code += f"console.log(nums.map((x) => x * {k}).filter((x) => x > {t}){tail})"
    return text("Что выведет код?", answer, code)


@family("js.closure_counter", competency=COMPETENCY, a=1.3, b=-0.2)
def _closure_counter(rng: Random) -> Item:
    start = rng.randint(0, 5)
    prefix = rng.choice([True, False])
    inc = "++n" if prefix else "n++"
    calls_first = rng.randint(1, 3)
    calls_second = rng.randint(1, 2)
    lines = [
        "function makeCounter(start) {",
        "  let n = start",
        f"  return () => {inc}",
        "}",
        f"const a = makeCounter({start})",
        f"const b = makeCounter({start})",
        *["a()"] * calls_first,
        *["b()"] * calls_second,
        "console.log(a())",
    ]
    # До console.log счётчик a вызван calls_first раз; b: независимое замыкание.
    answer = start + calls_first + (1 if prefix else 0)
    return text("Что выведет код?", answer, "\n".join(lines))


@family("js.var_let_loop", competency=COMPETENCY, a=1.4, b=0.2)
def _var_let_loop(rng: Random) -> Item:
    n = rng.randint(3, 4)
    keyword = rng.choice(["var", "let"])
    code = (
        f"for ({keyword} i = 0; i < {n}; i++) {{\n"
        "  setTimeout(() => console.log(i), 0)\n"
        "}"
    )
    answer = (
        " ".join([str(n)] * n) if keyword == "var" else " ".join(map(str, range(n)))
    )
    return text("Что выведет код? Значения перечислите через пробел.", answer, code)


@family("js.shallow_copy", competency=COMPETENCY, a=1.4, b=0.5)
def _shallow_copy(rng: Random) -> Item:
    nested_new = rng.randint(2, 9)
    flat_new = rng.randint(2, 9)
    method, deep = rng.choice(
        [
            ("{ ...a }", False),
            ("Object.assign({}, a)", False),
            ("structuredClone(a)", True),
        ]
    )
    code = (
        "const a = { inner: { v: 1 }, top: 1 }\n"
        f"const b = {method}\n"
        f"b.inner.v = {nested_new}\n"
        f"b.top = {flat_new}\n"
        "console.log(a.inner.v, a.top)"
    )
    answer = f"{1 if deep else nested_new} 1"
    return text("Что выведет код? Ответ: два числа через пробел.", answer, code)


_TASKS = {
    "sync": "console.log('{x}')",
    "micro": "Promise.resolve().then(() => console.log('{x}'))",
    "micro2": "queueMicrotask(() => console.log('{x}'))",
    "macro": "setTimeout(() => console.log('{x}'), 0)",
}


@family("js.event_loop", competency=COMPETENCY, a=1.6, b=0.9)
def _event_loop(rng: Random) -> Item:
    kinds = ["sync", "micro", "macro"] + [
        rng.choice(list(_TASKS)) for _ in range(rng.randint(1, 2))
    ]
    rng.shuffle(kinds)
    letters = "ABCDE"[: len(kinds)]
    lines = [
        _TASKS[kind].format(x=letter)
        for kind, letter in zip(kinds, letters, strict=True)
    ]
    # Сначала весь синхронный код, затем очередь микрозадач по порядку постановки,
    # затем макрозадачи (таймеры) по порядку постановки.
    phase = {"sync": 0, "micro": 1, "micro2": 1, "macro": 2}
    order = sorted(range(len(kinds)), key=lambda i: (phase[kinds[i]], i))
    answer = " ".join(letters[i] for i in order)
    return text(
        "В каком порядке выведутся буквы? Перечислите через пробел.",
        answer,
        "\n".join(lines),
    )


@family("js.this_binding", competency=COMPETENCY, a=1.4, b=1.1)
def _this_binding(rng: Random) -> Item:
    name = rng.choice(["Ада", "Линус", "Грейс"])
    other = rng.choice(["Кен", "Деннис"])
    call, answer = rng.choice(
        [
            ("const fn = user.getName\nconsole.log(fn())", "TypeError"),
            ("console.log(user.getName())", name),
            (
                f"const fn = user.getName\nconsole.log(fn.call({{ name: '{other}' }}))",
                other,
            ),
            ("const fn = user.getName.bind(user)\nconsole.log(fn())", name),
        ]
    )
    code = f"const user = {{\n  name: '{name}',\n  getName() {{\n    return this.name\n  }},\n}}\n{call}"
    return choice(
        rng,
        "Что произойдёт при выполнении кода в ES-модуле (строгий режим)?",
        answer,
        [name, other, "undefined", "TypeError"],
        code=code,
    )


@family("js.promise_combinators", competency=COMPETENCY, a=1.5, b=1.9)
def _promise_combinators(rng: Random) -> Item:
    values = rng.sample(range(1, 10), 3)
    fail_at = rng.randrange(3)
    error = rng.choice(["timeout", "denied", "broken"])
    items = [
        f"fail('{error}')" if i == fail_at else f"ok({v})" for i, v in enumerate(values)
    ]
    method = rng.choice(["all", "allSettled", "any", "race"])
    fulfilled = [v for i, v in enumerate(values) if i != fail_at]
    # Все промисы уже завершены: реакции ставятся в очередь в порядке массива.
    answer: object
    if method == "all":
        result_expr, answer = "r.length", error
    elif method == "allSettled":
        result_expr, answer = (
            "r.filter((x) => x.status === 'fulfilled').length",
            len(fulfilled),
        )
    elif method == "any":
        result_expr, answer = "r", fulfilled[0]
    else:
        result_expr, answer = "r", error if fail_at == 0 else values[0]
    code = (
        "const ok = (v) => Promise.resolve(v)\n"
        "const fail = (msg) => Promise.reject(new Error(msg))\n\n"
        f"Promise.{method}([{', '.join(items)}])\n"
        f"  .then((r) => console.log({result_expr}))\n"
        "  .catch((e) => console.log(e.message))"
    )
    return text("Что выведет код?", answer, code)


@family("js.getter_copy", competency=COMPETENCY, a=1.4, b=1.9)
def _getter_copy(rng: Random) -> Item:
    k = rng.randint(2, 9)
    first, later = rng.sample(range(1, 10), 2)
    # Spread и Object.assign вызывают геттер один раз и копируют значение;
    # Object.create наследует сам геттер: значение «живое».
    method, live = rng.choice(
        [
            ("{ ...src }", False),
            ("Object.assign({}, src)", False),
            ("Object.create(src)", True),
        ]
    )
    code = (
        f"let n = {first}\n"
        f"const src = {{\n  get value() {{\n    return n * {k}\n  }},\n}}\n"
        f"const copy = {method}\n"
        f"n = {later}\n"
        "console.log(src.value, copy.value)"
    )
    answer = f"{later * k} {(later if live else first) * k}"
    return text("Что выведет код? Ответ: два числа через пробел.", answer, code)


@family("js.async_order", competency=COMPETENCY, a=1.5, b=2.3)
def _async_order(rng: Random) -> Item:
    awaits = rng.randint(1, 2)
    chain = rng.randint(1, 2)
    letters = iter("ABCDEFGH")
    # Части async-функции между await: первая выполняется синхронно при вызове.
    segments = [next(letters) for _ in range(awaits + 1)]
    body = [f"  console.log('{segments[0]}')"]
    for letter in segments[1:]:
        body += ["  await null", f"  console.log('{letter}')"]
    statements = ["call", "then", "sync", rng.choice(["sync", "timeout"])]
    rng.shuffle(statements)
    lines = ["async function job() {", *body, "}", ""]
    out: list[str] = []
    timers: list[str] = []
    # Очередь микрозадач: (что, номер шага). await и каждое звено .then: один такт.
    queue: deque[tuple[str, int]] = deque()
    thens: list[str] = []
    for statement in statements:
        if statement == "call":
            lines.append("job()")
            out.append(segments[0])
            queue.append(("job", 1))
        elif statement == "then":
            thens = [next(letters) for _ in range(chain)]
            links = "".join(f".then(() => console.log('{x}'))" for x in thens)
            lines.append(f"Promise.resolve(){links}")
            queue.append(("then", 0))
        elif statement == "sync":
            letter = next(letters)
            lines.append(f"console.log('{letter}')")
            out.append(letter)
        else:
            letter = next(letters)
            lines.append(f"setTimeout(() => console.log('{letter}'), 0)")
            timers.append(letter)
    while queue:
        kind, step = queue.popleft()
        steps = segments if kind == "job" else thens
        out.append(steps[step])
        if step + 1 < len(steps):
            queue.append((kind, step + 1))
    return text(
        "В каком порядке выведутся буквы? Перечислите через пробел.",
        " ".join(out + timers),
        "\n".join(lines),
    )
