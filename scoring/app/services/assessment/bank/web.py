"""Компетенция «Веб-платформа: HTML, CSS, браузер». Ответы считаются по правилам CSS."""

from random import Random

from app.services.assessment.bank.base import Item, choice, family, text

COMPETENCY = "web"


@family("web.semantic", competency=COMPETENCY, a=1.0, b=-1.4)
def _semantic(rng: Random) -> Item:
    cases = {
        "<nav>": "блок со ссылками главного меню сайта",
        "<button>": "элемент, по нажатию на который отправляется форма или открывается модалка",
        "<main>": "основное содержимое страницы, уникальное для неё",
        "<article>": "самостоятельная запись блога, которую можно опубликовать отдельно",
        "<label>": "подпись к полю ввода, по клику на которую фокус переходит в поле",
    }
    correct = rng.choice(list(cases))
    others = [tag for tag in cases if tag != correct]
    return choice(
        rng,
        f"Какой элемент семантически подходит лучше всего: {cases[correct]}?",
        correct,
        [*rng.sample(others, 2), "<div>"],
    )


@family("web.box_model", competency=COMPETENCY, a=1.2, b=-0.5)
def _box_model(rng: Random) -> Item:
    width = rng.randrange(100, 400, 20)
    padding = rng.randrange(4, 24, 4)
    border = rng.randint(1, 4)
    sizing = rng.choice(["content-box", "border-box"])
    code = (
        ".card {\n"
        f"  box-sizing: {sizing};\n  width: {width}px;\n  padding: {padding}px;\n"
        f"  border: {border}px solid;\n  margin: 10px;\n}}"
    )
    answer = width if sizing == "border-box" else width + 2 * (padding + border)
    return text(
        "Какова итоговая ширина рамки элемента .card (от внешнего края border до внешнего края), "
        "в пикселях?",
        answer,
        code,
    )


# селектор → (id, классы, теги); все селекторы подходят к <p id="intro" class="lead note">.
_SELECTORS = {
    "p": (0, 0, 1),
    ".lead": (0, 1, 0),
    ".note": (0, 1, 0),
    "p.lead": (0, 1, 1),
    ".lead.note": (0, 2, 0),
    "#intro": (1, 0, 0),
    "p#intro": (1, 0, 1),
}
_COLORS = ["red", "green", "blue", "orange", "purple"]


@family("web.specificity", competency=COMPETENCY, a=1.4, b=0.3)
def _specificity(rng: Random) -> Item:
    selectors = rng.sample(list(_SELECTORS), 3)
    colors = rng.sample(_COLORS, 3)
    rules = list(zip(selectors, colors, strict=True))
    # Побеждает наибольшая специфичность, при равенстве: правило ниже по тексту.
    winner = max(range(3), key=lambda i: (_SELECTORS[rules[i][0]], i))
    code = '<p id="intro" class="lead note">Текст</p>\n\n' + "\n".join(
        f"{sel} {{ color: {color}; }}" for sel, color in rules
    )
    return choice(
        rng,
        "Каким цветом будет текст?",
        rules[winner][1],
        [c for _, c in rules] + ["black"],
        code=code,
    )


@family("web.flex_grow", competency=COMPETENCY, a=1.4, b=0.6)
def _flex_grow(rng: Random) -> Item:
    while True:
        bases = [rng.randrange(40, 120, 20) for _ in range(3)]
        grows = [rng.randint(0, 3) for _ in range(3)]
        width = rng.randrange(400, 800, 40)
        free = width - sum(bases)
        target = rng.randrange(3)
        if sum(grows) and free > 0 and (free * grows[target]) % sum(grows) == 0:
            break
    answer = bases[target] + free * grows[target] // sum(grows)
    items = "\n".join(
        f'  <div style="flex: {g} 0 {b}px">{i + 1}</div>'
        for i, (g, b) in enumerate(zip(grows, bases, strict=True))
    )
    code = f'<div style="display: flex; width: {width}px">\n{items}\n</div>'
    return text(
        f"Какой будет ширина элемента {target + 1} в пикселях? Отступов и рамок нет.",
        answer,
        code,
    )


_SAFE_OUTPUT = [
    "el.textContent = value",
    "el.append(document.createTextNode(value))",
    "В JSX: <p>{value}</p>",
]
_UNSAFE_OUTPUT = [
    "el.innerHTML = value",
    "el.insertAdjacentHTML('beforeend', value)",
    "document.write(value)",
    "В JSX: <p dangerouslySetInnerHTML={{ __html: value }} />",
]


@family("web.xss", competency=COMPETENCY, a=1.3, b=1.2)
def _xss(rng: Random) -> Item:
    source = rng.choice(
        ["комментарий пользователя", "имя из URL-параметра", "ответ чужого API"]
    )
    if rng.random() < 0.5:
        return choice(
            rng,
            f"Нужно вывести на странице {source} (value). Какой способ безопасен от XSS?",
            rng.choice(_SAFE_OUTPUT),
            rng.sample(_UNSAFE_OUTPUT, 3),
        )
    return choice(
        rng,
        f"Нужно вывести на странице {source} (value). Какой из способов уязвим для XSS?",
        rng.choice(_UNSAFE_OUTPUT),
        _SAFE_OUTPUT,
    )


@family("web.render_perf", competency=COMPETENCY, a=1.3, b=1.7)
def _render_perf(rng: Random) -> Item:
    effect, correct, distractors = rng.choice(
        [
            (
                "плавно сдвинуть панель на 300px вправо",
                "transform: translateX()",
                ["left", "margin-left", "width"],
            ),
            (
                "плавно скрыть всплывающее окно",
                "opacity",
                ["height", "display", "padding"],
            ),
            (
                "плавно увеличить карточку при наведении",
                "transform: scale()",
                ["width и height", "padding", "font-size"],
            ),
        ]
    )
    return choice(
        rng,
        f"Анимация должна идти 60 fps на слабом телефоне: нужно {effect}. Какое свойство "
        "анимировать, чтобы браузер не пересчитывал раскладку (layout) на каждом кадре?",
        correct,
        distractors,
    )


# Скрипты на странице https://app.example.com: вид → разметка.
_SCRIPTS = {
    "self": '<script src="/static/app.js"></script>',
    "cdn": '<script src="https://cdn.example.com/lib.js"></script>',
    "cdn_http": '<script src="http://cdn.example.com/lib.js"></script>',
    "lookalike": '<script src="https://cdn.example.com.evil.net/x.js"></script>',
    "subdomain": '<script src="https://static.example.com/x.js"></script>',
    "inline": "<script>init()</script>",
    "nonce_ok": '<script nonce="{nonce}">init()</script>',
    "nonce_bad": '<script nonce="{other}">init()</script>',
}


def csp_allows(kind: str, *, has_nonce: bool, unsafe_inline: bool) -> bool:
    """Выполнится ли скрипт при политике script-src 'self' https://cdn.example.com
    [+ 'nonce-...'] [+ 'unsafe-inline'] на странице https://app.example.com."""
    # Если в политике есть nonce, браузер игнорирует 'unsafe-inline' (CSP Level 2+).
    inline_ok = unsafe_inline and not has_nonce
    return {
        # 'self': ровно источник страницы; поддомены и другая схема не подходят.
        "self": True,
        "cdn": True,
        "cdn_http": False,
        "lookalike": False,
        "subdomain": False,
        "inline": inline_ok,
        "nonce_ok": has_nonce or inline_ok,
        "nonce_bad": inline_ok,
    }[kind]


@family("web.csp", competency=COMPETENCY, a=1.4, b=1.9)
def _csp(rng: Random) -> Item:
    has_nonce, unsafe_inline = rng.choice([(True, False), (False, True), (True, True)])
    nonce, other = rng.sample(["r4nd0m", "x9Kq2", "Zp7tw", "m0Rn1"], 2)
    sources = ["'self'", "https://cdn.example.com"]
    if has_nonce:
        sources.append(f"'nonce-{nonce}'")
    if unsafe_inline:
        sources.append("'unsafe-inline'")
    inline = rng.sample(["inline", "nonce_ok", "nonce_bad"], 2)
    external = rng.sample(["self", "cdn", "cdn_http", "lookalike", "subdomain"], 3)
    kinds = inline + external
    rng.shuffle(kinds)
    allowed = [
        str(n)
        for n, kind in enumerate(kinds, 1)
        if csp_allows(kind, has_nonce=has_nonce, unsafe_inline=unsafe_inline)
    ]
    page = "\n".join(
        f"{n}. {_SCRIPTS[kind].format(nonce=nonce, other=other)}"
        for n, kind in enumerate(kinds, 1)
    )
    return text(
        "Страница https://app.example.com отдаётся с заголовком CSP ниже. Какие скрипты "
        "выполнятся? Перечислите номера через пробел; если ни один: напишите «нет».",
        " ".join(allowed) or "нет",
        f"Content-Security-Policy: script-src {' '.join(sources)}\n\n{page}",
    )


# Cookie сайта https://shop.example: (варианты имени, Domain задан, Path, варианты SameSite).
_COOKIES = [
    (["sid", "session"], False, "/", ["Lax", "Strict"]),
    (["cart", "basket"], False, "/cart", ["Strict", "Lax"]),
    (["prefs", "lang"], True, "/", ["Lax", "None"]),
    (["ads", "track"], True, "/", ["None", "Lax"]),
    (["adm", "staff"], False, "/admin", ["Strict", "None"]),
]
# Сценарий → (откуда, хост запроса, межсайтовый, навигация верхнего уровня, метод).
_REQUESTS = {
    "fetch со страницы https://shop.example/catalog на": (
        "shop.example",
        False,
        False,
        "GET",
    ),
    "переход по ссылке со страницы https://news.example на": (
        "shop.example",
        True,
        True,
        "GET",
    ),
    "отправка формы методом POST со страницы https://news.example на": (
        "shop.example",
        True,
        True,
        "POST",
    ),
    # Другой origin: без credentials: 'include' fetch cookie не отправит вовсе, и ответ «нет»
    # был бы верным при любых атрибутах: тогда задание проверяло бы не SameSite.
    "fetch(url, {credentials: 'include'}) со страницы https://shop.example/catalog на поддомен": (
        "api.shop.example",
        False,
        False,
        "GET",
    ),
    "загрузка во iframe на странице https://news.example адреса": (
        "shop.example",
        True,
        False,
        "GET",
    ),
}


def cookie_sent(
    cookie: tuple[bool, str, str],
    *,
    host: str,
    path: str,
    cross_site: bool,
    top_level: bool,
    method: str,
) -> bool:
    """Отправит ли браузер cookie сайта shop.example (Secure, запрос по https; RFC 6265bis)."""
    has_domain, cookie_path, same_site = cookie
    # Без Domain cookie «host-only»: только тот же хост, без поддоменов.
    domain_ok = host == "shop.example" or (
        has_domain and host.endswith(".shop.example")
    )
    path_ok = (
        cookie_path == "/" or path == cookie_path or path.startswith(cookie_path + "/")
    )
    # Межсайтовый запрос: None пропускает всё, Lax: только навигацию верхнего уровня
    # безопасным методом, Strict: ничего.
    site_ok = (
        not cross_site
        or same_site == "None"
        or (same_site == "Lax" and top_level and method == "GET")
    )
    return domain_ok and path_ok and site_ok


@family("web.cookie_samesite", competency=COMPETENCY, a=1.4, b=2.3)
def _cookie_samesite(rng: Random) -> Item:
    chosen = sorted(rng.sample(range(len(_COOKIES)), 4))
    cookies = [
        (
            rng.choice(_COOKIES[i][0]),
            (_COOKIES[i][1], _COOKIES[i][2], rng.choice(_COOKIES[i][3])),
        )
        for i in chosen
    ]
    scenario = rng.choice(list(_REQUESTS))
    host, cross_site, top_level, method = _REQUESTS[scenario]
    path = rng.choice(["/", "/cart/items", "/admin/users"])
    sent = [
        name
        for name, cookie in cookies
        if cookie_sent(
            cookie,
            host=host,
            path=path,
            cross_site=cross_site,
            top_level=top_level,
            method=method,
        )
    ]
    headers = [
        f"Set-Cookie: {name}=1{'; Domain=shop.example' if has_domain else ''}; "
        f"Path={cookie_path}; Secure; SameSite={same_site}"
        for name, (has_domain, cookie_path, same_site) in cookies
    ]
    return text(
        f"Сайт https://shop.example установил cookie (ниже). Запрос: {scenario} "
        f"https://{host}{path}. Какие cookie браузер отправит с этим запросом? Перечислите "
        "имена через пробел в порядке списка; если ни одной: напишите «нет».",
        " ".join(sent) or "нет",
        "\n".join(headers),
    )
