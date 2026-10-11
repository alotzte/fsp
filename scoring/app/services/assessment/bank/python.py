"""Компетенция «Python». Ответы вычисляются исполнением фрагмента (run_python)."""

from random import Random

from app.services.assessment.bank.base import Item, choice, family, run_python, text

COMPETENCY = "python"
_WORDS = [
    "algorithm",
    "backend",
    "database",
    "frontend",
    "keyboard",
    "terminal",
    "variable",
]
_NAMES = ["items", "data", "values", "acc", "bucket", "store"]


@family("py.slice", competency=COMPETENCY, a=1.1, b=-1.6)
def _slice(rng: Random) -> Item:
    word = rng.choice(_WORDS)
    start = rng.randint(0, 3)
    stop = rng.randint(start + 2, len(word))
    step = rng.choice(["", ":2"])
    code = f's = "{word}"\nprint(s[{start}:{stop}{step}])'
    return text("Что выведет программа?", run_python(code), code)


@family("py.alias", competency=COMPETENCY, a=1.3, b=-0.9)
def _alias(rng: Random) -> Item:
    first, second = rng.sample(_NAMES, 2)
    size = rng.randint(2, 4)
    appends = rng.randint(1, 3)
    copy = rng.choice(["", "[:]", ".copy()"])
    lines = [f"{first} = list(range({size}))", f"{second} = {first}{copy}"]
    lines += [f"{second}.append({i})" for i in range(appends)]
    lines.append(f"print(len({first}))")
    code = "\n".join(lines)
    return text("Что выведет программа?", run_python(code), code)


@family("py.dict_count", competency=COMPETENCY, a=1.2, b=-0.6)
def _dict_count(rng: Random) -> Item:
    letters = "".join(rng.choice("abcab") for _ in range(rng.randint(7, 11)))
    target = rng.choice("abc")
    code = (
        "counts = {}\n"
        f'for ch in "{letters}":\n'
        "    counts[ch] = counts.get(ch, 0) + 1\n"
        f'print(counts.get("{target}", 0))'
    )
    return text("Что выведет программа?", run_python(code), code)


@family("py.sorted_key", competency=COMPETENCY, a=1.2, b=-0.1)
def _sorted_key(rng: Random) -> Item:
    names = rng.sample(["ann", "bob", "kate", "max", "olga", "ivan", "lev"], 5)
    ages = [rng.randint(20, 25) for _ in names]
    pairs = list(zip(names, ages, strict=True))
    reverse = rng.choice([True, False])
    code = (
        f"people = {pairs!r}\n"
        f"people.sort(key=lambda p: p[1], reverse={reverse})\n"
        "print(people[0][0], people[-1][0])"
    )
    return text(
        "Что выведет программа? Учтите, что сортировка в Python устойчивая.",
        run_python(code),
        code,
    )


@family("py.mutable_default", competency=COMPETENCY, a=1.5, b=0.3)
def _mutable_default(rng: Random) -> Item:
    calls = rng.randint(2, 4)
    fn = rng.choice(["add", "collect", "push"])
    default = rng.choice(["[]", "None"])
    if default == "[]":
        body = f"def {fn}(x, acc=[]):\n    acc.append(x)\n    return acc\n"
    else:
        body = (
            f"def {fn}(x, acc=None):\n    if acc is None:\n        acc = []\n"
            "    acc.append(x)\n    return acc\n"
        )
    calls_code = "\n".join(f"result = {fn}({i})" for i in range(calls))
    code = f"{body}\n{calls_code}\nprint(len(result))"
    return text("Что выведет программа?", run_python(code), code)


@family("py.generator_exhaust", competency=COMPETENCY, a=1.4, b=0.6)
def _generator_exhaust(rng: Random) -> Item:
    n = rng.randint(3, 6)
    container = rng.choice(
        ["(x * x for x in range({n}))", "[x * x for x in range({n})]"]
    )
    code = f"squares = {container.format(n=n)}\nfirst = sum(squares)\nsecond = sum(squares)\n"
    code += "print(first, second)"
    return text("Что выведет программа?", run_python(code), code)


@family("py.late_binding", competency=COMPETENCY, a=1.5, b=0.9)
def _late_binding(rng: Random) -> Item:
    n = rng.randint(3, 5)
    k = rng.randint(0, n - 1)
    mult = rng.randint(2, 5)
    bind = rng.choice(["lambda: i * {m}", "lambda i=i: i * {m}"]).format(m=mult)
    code = f"funcs = [{bind} for i in range({n})]\nprint(funcs[{k}]())"
    return text("Что выведет программа?", run_python(code), code)


_SPEEDUPS = {
    "multiprocessing / ProcessPoolExecutor": (
        "вычисляет хеши большого массива данных в чистом Python (нагрузка на CPU, 8 ядер)"
    ),
    "asyncio или ThreadPoolExecutor": "делает сотни HTTP-запросов к внешнему API и ждёт ответов",
    "Векторизовать на numpy или вынести горячий цикл в C-расширение": (
        "гоняет простой арифметический цикл по миллионам чисел, сервер одноядерный"
    ),
}


@family("py.gil", competency=COMPETENCY, a=1.3, b=1.3)
def _gil(rng: Random) -> Item:
    correct = rng.choice(list(_SPEEDUPS))
    return choice(
        rng,
        f"Сервис на CPython {_SPEEDUPS[correct]}. Что даст наибольшее ускорение?",
        correct,
        [*[s for s in _SPEEDUPS if s != correct], "Увеличить sys.setrecursionlimit"],
    )


@family("py.mro", competency=COMPETENCY, a=1.4, b=2.0)
def _mro(rng: Random) -> Item:
    a_name, b_name, c_name, d_name = rng.sample(
        ["Base", "Left", "Right", "Mixin", "Core"], 4
    )
    order = rng.choice([(b_name, c_name), (c_name, b_name)])
    call_super = rng.choice([True, False])
    b_body = "super().who() + 'B'" if call_super else "'B'"
    code = (
        f"class {a_name}:\n    def who(self):\n        return 'A'\n\n"
        f"class {b_name}({a_name}):\n    def who(self):\n        return {b_body}\n\n"
        f"class {c_name}({a_name}):\n    def who(self):\n        return super().who() + 'C'\n\n"
        f"class {d_name}({order[0]}, {order[1]}):\n    pass\n\n"
        f"print({d_name}().who())"
    )
    return text("Что выведет программа?", run_python(code), code)


@family("py.class_attr", competency=COMPETENCY, a=1.4, b=1.9)
def _class_attr(rng: Random) -> Item:
    cls = rng.choice(["Counter", "Session", "Pool", "Cache"])
    attr = rng.choice(["count", "hits", "total"])
    start, step, reset = rng.randint(0, 5), rng.randint(1, 3), rng.randint(10, 40)
    # self.x += 1 читает атрибут класса, а пишет в экземпляр; type(self).x += 1 меняет класс.
    target = rng.choice(["self", "type(self)"])
    code = (
        f"class {cls}:\n    {attr} = {start}\n\n    def __init__(self):\n"
        f"        {target}.{attr} += {step}\n\n\n"
        f"a = {cls}()\nb = {cls}()\n{cls}.{attr} = {reset}\nc = {cls}()\n"
        f"print(a.{attr}, b.{attr}, c.{attr})"
    )
    return text("Что выведет программа?", run_python(code), code)


@family("py.try_else", competency=COMPETENCY, a=1.4, b=2.3)
def _try_else(rng: Random) -> Item:
    limit = rng.randint(2, 6)
    arg = rng.randint(0, 9)
    # else не выполняется, если try завершился return; finally выполняется всегда: до того,
    # как вызывающий код получит результат.
    early_return = rng.choice([True, False])
    lines = [
        "def run(x):",
        "    try:",
        "        print('try', x, end=' ')",
        f"        if x > {limit}:",
        "            raise ValueError(x)",
    ]
    if early_return:
        lines.append("        return x * 2")
    lines += [
        "    except ValueError:",
        "        print('except', end=' ')",
        "        return -1",
        "    else:",
        "        print('else', end=' ')",
        "        return x * 3",
        "    finally:",
        "        print('finally', end=' ')",
        "",
        "",
        f"print(run({arg}))",
    ]
    code = "\n".join(lines)
    return text("Что выведет программа? Ответ: одной строкой.", run_python(code), code)
