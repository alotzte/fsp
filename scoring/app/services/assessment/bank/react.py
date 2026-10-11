"""Компетенция «React». Поведение: React 18+, продакшен-сборка (без двойного вызова
эффектов StrictMode)."""

import itertools
from random import Random

from app.services.assessment.bank.base import Item, choice, family, text

COMPETENCY = "react"


_KEY_SCENARIOS = [
    (
        (
            "{todos.map((todo, index) => <TodoRow key={index} todo={todo} />)}\n"
            "// пользователь добавляет задачу в начало списка; в TodoRow есть <input>"
        ),
        "Введённый текст «съедет» на соседние строки: ключ привязан к позиции, а не к задаче",
    ),
    (
        "{todos.map((todo) => <TodoRow key={Math.random()} todo={todo} />)}",
        "Строки пересоздаются на каждом рендере: теряется фокус и локальное состояние",
    ),
    (
        (
            "<ProfileForm key={userId} userId={userId} />\n"
            "// userId меняется, когда пользователь выбирает другого сотрудника"
        ),
        "Форма монтируется заново и сбрасывает состояние: так задумано, это корректный приём",
    ),
    (
        "{todos.map((todo) => <TodoRow todo={todo} />)}",
        "React предупредит об отсутствии key и сопоставит строки по позиции",
    ),
]


@family("react.keys", competency=COMPETENCY, a=1.1, b=-0.7)
def _keys(rng: Random) -> Item:
    code, correct = rng.choice(_KEY_SCENARIOS)
    return choice(
        rng,
        "Что произойдёт с компонентами из-за такого key?",
        correct,
        [outcome for _, outcome in _KEY_SCENARIOS if outcome != correct],
        code=code,
    )


_INPUT_SCENARIOS = [
    (
        "<input value={name} />",
        "Поле не меняется при вводе: значение задано, а onChange нет",
    ),
    (
        "<input defaultValue={name} />",
        "Ввод работает, но состояние name не обновляется (неконтролируемое поле)",
    ),
    (
        "<input value={name} onChange={(e) => setName(e.target.value)} />",
        "Ввод работает, и name всегда совпадает с текстом поля",
    ),
    (
        "<input value={name} onChange={(e) => setName(e.target.value.toUpperCase())} />",
        "Ввод работает, текст в поле сразу становится заглавными буквами",
    ),
]


@family("react.controlled_input", competency=COMPETENCY, a=1.2, b=-0.2)
def _controlled_input(rng: Random) -> Item:
    jsx, correct = rng.choice(_INPUT_SCENARIOS)
    code = f"const [name, setName] = useState('')\n\nreturn {jsx}"
    return choice(
        rng,
        "Что увидит пользователь, когда начнёт печатать в поле?",
        correct,
        [outcome for _, outcome in _INPUT_SCENARIOS if outcome != correct],
        code=code,
    )


@family("react.batching", competency=COMPETENCY, a=1.5, b=0.4)
def _batching(rng: Random) -> Item:
    start = rng.randint(0, 5)
    calls: list[str] = []
    current = start
    for _ in range(rng.randint(2, 4)):
        k = rng.randint(1, 3)
        if rng.random() < 0.5:
            # Значение из замыкания: count это снимок на момент рендера.
            calls.append(f"  setCount(count + {k})")
            current = start + k
        else:
            calls.append(f"  setCount((c) => c + {k})")
            current += k
    code = (
        f"const [count, setCount] = useState({start})\n\n"
        "function handleClick() {\n" + "\n".join(calls) + "\n}"
    )
    return text(
        "Каким станет count после одного клика (до клика был первый рендер)?",
        current,
        code,
    )


@family("react.effect_runs", competency=COMPETENCY, a=1.4, b=0.8)
def _effect_runs(rng: Random) -> Item:
    values = [rng.randint(1, 3)]
    for _ in range(rng.randint(3, 5)):
        values.append(values[-1] if rng.random() < 0.5 else rng.randint(1, 3))
    deps = rng.choice(["[]", "[id]", ""])
    if deps == "[]":
        answer = 1
    elif deps == "[id]":
        answer = 1 + sum(1 for prev, cur in itertools.pairwise(values) if prev != cur)
    else:
        answer = len(values)
    deps_code = f", {deps}" if deps else ""
    code = (
        "function Profile({ id }) {\n"
        f"  useEffect(() => {{\n    loadProfile(id)\n  }}{deps_code})\n"
        "  return <div>...</div>\n}"
    )
    return text(
        f"Компонент отрендерился {len(values)} раз с id = {', '.join(map(str, values))} "
        "(по порядку). Сколько раз вызвался loadProfile?",
        answer,
        code,
    )


@family("react.memo", competency=COMPETENCY, a=1.4, b=1.3)
def _memo(rng: Random) -> Item:
    new_ref = (
        "Да: проп получает новую ссылку на каждом рендере, нужен useMemo/useCallback"
    )
    equal = "Нет: пропсы равны по Object.is, memo пропустит рендер"
    no_memo = (
        "Да: без React.memo дочерний компонент рендерится вместе с родителем всегда"
    )
    wrapped, prop, correct = rng.choice(
        [
            (True, "style={{ color: 'red' }}", new_ref),
            (True, "onSelect={() => setTick(0)}", new_ref),
            (True, 'title="Каталог"', equal),
            (True, "limit={10}", equal),
            (False, 'title="Каталог"', no_memo),
        ]
    )
    child = (
        "const Child = React.memo(function Child(props) { /* ... */ })"
        if wrapped
        else "function Child(props) { /* ... */ }"
    )
    code = (
        f"{child}\n\n"
        "function Parent() {\n  const [tick, setTick] = useState(0)\n"
        f"  return <Child {prop} />\n}}"
    )
    return choice(
        rng,
        "Parent перерендерился из-за setTick. Перерендерится ли Child?",
        correct,
        [new_ref, equal, no_memo],
        code=code,
    )


@family("react.stale_closure", competency=COMPETENCY, a=1.5, b=2.0)
def _stale_closure(rng: Random) -> Item:
    seconds = rng.randint(3, 9)
    updater, answer = rng.choice(
        [("setCount(count + 1)", 1), ("setCount((c) => c + 1)", seconds)]
    )
    code = (
        "function Timer() {\n  const [count, setCount] = useState(0)\n\n"
        "  useEffect(() => {\n"
        f"    const id = setInterval(() => {updater}, 1000)\n"
        "    return () => clearInterval(id)\n  }, [])\n\n"
        "  return <span>{count}</span>\n}"
    )
    return text(
        f"Какое число покажет компонент через {seconds}.5 секунды после монтирования?",
        answer,
        code,
    )


# Деревья: компонент → дети в порядке разметки. Корень: P.
_TREES = [
    {"P": ["A", "B"], "A": [], "B": []},
    {"P": ["A", "B"], "A": ["C"], "B": [], "C": []},
    {"P": ["A", "B"], "A": [], "B": ["C"], "C": []},
    {"P": ["A"], "A": ["B", "C"], "B": [], "C": []},
]


def effect_order(tree: dict[str, list[str]], layout: set[str]) -> list[str]:
    """Порядок эффектов при первом монтировании (React 18): сначала все useLayoutEffect,
    потом все useEffect; внутри каждой группы дети раньше родителя (обход в глубину,
    родитель после поддерева), соседи: по порядку."""

    def post_order(name: str) -> list[str]:
        return [x for child in tree[name] for x in post_order(child)] + [name]

    order = post_order("P")
    return [n for n in order if n in layout] + [n for n in order if n not in layout]


@family("react.effect_order", competency=COMPETENCY, a=1.4, b=1.9)
def _effect_order(rng: Random) -> Item:
    tree = rng.choice(_TREES)
    names = list(tree)
    layout = set(rng.sample(names, rng.randint(1, len(names) - 1)))
    blocks = []
    for name in reversed(names):
        hook = "useLayoutEffect" if name in layout else "useEffect"
        children = tree[name]
        if not children:
            markup = "null"
        elif len(children) == 1:
            markup = f"<{children[0]} />"
        else:
            inner = "\n".join(f"      <{child} />" for child in children)
            markup = f"(\n    <>\n{inner}\n    </>\n  )"
        blocks.append(
            f"function {name}() {{\n  {hook}(() => console.log('{name}'), [])\n"
            f"  return {markup}\n}}"
        )
    return text(
        "В каком порядке выведутся буквы при первом монтировании <P />? "
        "Перечислите через пробел.",
        " ".join(effect_order(tree, layout)),
        "\n\n".join(blocks),
    )


def context_rerenders(
    *,
    toolbar_memo: bool,
    stable_toggle: bool,
    status_memo: bool,
    consumers: set[str],
) -> list[str]:
    """Кто отрендерится заново после setTheme в ThemeProvider (кроме него самого)."""
    rendered = set(consumers)  # подписчики контекста рендерятся при смене value всегда
    # Toolbar и Status создаются в рендере ThemeProvider: рендерятся вместе с ним,
    # если memo не отсечёт рендер по равным пропсам.
    if not (toolbar_memo and stable_toggle):
        rendered.add("Toolbar")
    if not status_memo:
        rendered.add("Status")
    # Page и Footer пришли как children: тот же элемент, React их пропускает.
    # Article создаётся в рендере Page.
    if "Page" in rendered:
        rendered.add("Article")
    return sorted(rendered)


def _component(name: str, *, memo: bool, consumes: bool, props: str, body: str) -> str:
    hook = "  const theme = useContext(ThemeContext)\n" if consumes else ""
    content = body.replace("{label}", "{theme}" if consumes else name)
    function = f"function {name}({props}) {{\n{hook}  return {content}\n}}"
    return f"const {name} = memo({function})" if memo else function


@family("react.context_rerender", competency=COMPETENCY, a=1.5, b=2.3)
def _context_rerender(rng: Random) -> Item:
    toolbar_memo, stable_toggle, status_memo = (
        rng.choice([True, False]) for _ in range(3)
    )
    consumers = {
        name for name in ["Status", "Page", "Article", "Footer"] if rng.random() < 0.4
    }
    toggle = (
        "  const toggle = useCallback(\n"
        "    () => setTheme((t) => (t === 'light' ? 'dark' : 'light')),\n    [],\n  )\n"
        if stable_toggle
        else ""
    )
    on_toggle = (
        "toggle"
        if stable_toggle
        else "() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))"
    )
    blocks = [
        "const ThemeContext = createContext('light')",
        _component(
            "Toolbar",
            memo=toolbar_memo,
            consumes=False,
            props="{ onToggle }",
            body="<button onClick={onToggle}>Тема</button>",
        ),
        _component(
            "Status",
            memo=status_memo,
            consumes="Status" in consumers,
            props="",
            body="<p>{label}</p>",
        ),
        _component(
            "Article",
            memo=False,
            consumes="Article" in consumers,
            props="",
            body="<article>{label}</article>",
        ),
        _component(
            "Page",
            memo=False,
            consumes="Page" in consumers,
            props="",
            body="<Article />",
        ),
        _component(
            "Footer",
            memo=False,
            consumes="Footer" in consumers,
            props="",
            body="<footer>{label}</footer>",
        ),
        (
            "function ThemeProvider({ children }) {\n"
            "  const [theme, setTheme] = useState('light')\n"
            f"{toggle}"
            "  return (\n    <ThemeContext.Provider value={theme}>\n"
            f"      <Toolbar onToggle={{{on_toggle}}} />\n"
            "      <Status />\n      {children}\n    </ThemeContext.Provider>\n  )\n}"
        ),
        (
            "function App() {\n  return (\n    <ThemeProvider>\n      <Page />\n"
            "      <Footer />\n    </ThemeProvider>\n  )\n}"
        ),
    ]
    rerendered = context_rerenders(
        toolbar_memo=toolbar_memo,
        stable_toggle=stable_toggle,
        status_memo=status_memo,
        consumers=consumers,
    )
    return text(
        "Пользователь нажал «Тема». Какие компоненты, кроме ThemeProvider, отрендерятся заново? "
        "Перечислите имена через пробел в алфавитном порядке; если ни один: напишите «нет».",
        " ".join(rerendered) or "нет",
        "\n\n".join(blocks),
    )
