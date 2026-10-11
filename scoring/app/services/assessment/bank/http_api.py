"""Компетенция «HTTP и проектирование API». Ситуационные вопросы с выбором и задачи,
ответ на которые вычисляется по правилам протокола (ограничение частоты, кеширование).

Устойчивость к утечке у вопросов с выбором: за счёт пула сценариев внутри семейства: ответ
зависит от сценария, а не от позиции варианта (варианты перемешиваются).
"""

from random import Random

from app.services.assessment.bank.base import Item, choice, family, text

COMPETENCY = "http_api"


@family("http.status", competency=COMPETENCY, a=1.1, b=-1.2)
def _status(rng: Random) -> Item:
    scenarios = {
        "201 Created": "POST /orders успешно создал заказ",
        "204 No Content": "DELETE /orders/42 успешно удалил заказ, тело ответа не нужно",
        "401 Unauthorized": "Запрос пришёл без токена авторизации",
        "403 Forbidden": "Пользователь вошёл, но пытается изменить чужой заказ",
        "404 Not Found": "Заказа с запрошенным id не существует",
        "409 Conflict": "Регистрация с email, который уже занят",
        "429 Too Many Requests": "Клиент превысил лимит запросов в минуту",
    }
    correct = rng.choice(list(scenarios))
    others = rng.sample([code for code in scenarios if code != correct], 3)
    return choice(
        rng,
        f"Какой код ответа подходит лучше всего? {scenarios[correct]}.",
        correct,
        others,
    )


@family("http.idempotent", competency=COMPETENCY, a=1.2, b=-0.4)
def _idempotent(rng: Random) -> Item:
    ask_idempotent = rng.choice([True, False])
    if ask_idempotent:
        correct = rng.choice(["PUT", "DELETE"])
        return choice(
            rng,
            "Какой из методов идемпотентен по спецификации HTTP, но при этом не является "
            "безопасным (меняет состояние)?",
            correct,
            ["POST", "PATCH", "GET"],
        )
    return choice(
        rng,
        "Какой из методов по спецификации HTTP не идемпотентен?",
        "POST",
        ["PUT", "DELETE", "GET", "HEAD"],
    )


@family("http.conditional", competency=COMPETENCY, a=1.3, b=0.4)
def _conditional(rng: Random) -> Item:
    outcomes = {
        "304 Not Modified без тела": 'GET с If-None-Match: "a1b2", ресурс не менялся',
        "200 OK с новым телом и новым ETag": 'GET с If-None-Match: "a1b2", ресурс изменился',
        "412 Precondition Failed": 'PUT с If-Match: "a1b2", а текущий ETag уже "c3d4"',
        "200 OK или 204: изменение применено": 'PUT с If-Match: "a1b2", текущий ETag "a1b2"',
    }
    correct = rng.choice(list(outcomes))
    return choice(
        rng,
        f"Сервер поддерживает ETag. Клиент отправляет {outcomes[correct]}. Что ответит "
        "корректный сервер?",
        correct,
        [o for o in outcomes if o != correct],
    )


@family("http.cors", competency=COMPETENCY, a=1.3, b=0.7)
def _cors(rng: Random) -> Item:
    preflight = "Сначала отправит OPTIONS (preflight) и проверит Access-Control-Allow-* в ответе"
    simple = (
        "Отправит запрос сразу, но отдаст ответ скрипту, только если есть "
        "Access-Control-Allow-Origin"
    )
    blocked = (
        "Отправит запрос, но не отдаст ответ скрипту: с credentials нельзя "
        "Access-Control-Allow-Origin: *"
    )
    request, correct = rng.choice(
        [
            ("fetch с методом PUT", preflight),
            ("fetch с заголовком Content-Type: application/json", preflight),
            ("fetch с собственным заголовком X-Request-Id", preflight),
            ("простой GET без дополнительных заголовков", simple),
            ("POST формы с Content-Type: application/x-www-form-urlencoded", simple),
            (
                "GET с credentials: 'include', сервер отвечает Access-Control-Allow-Origin: *",
                blocked,
            ),
        ]
    )
    return choice(
        rng,
        f"Фронт на app.example.ru делает запрос к api.example.ru: {request}. Как поступит "
        "браузер?",
        correct,
        [preflight, simple, blocked, "Заблокирует запрос, не обращаясь к серверу"],
    )


@family("http.pagination", competency=COMPETENCY, a=1.4, b=1.0)
def _pagination(rng: Random) -> Item:
    entity = rng.choice(["ленты событий", "списка заказов", "журнала платежей"])
    duplicates = "Записи будут повторяться на соседних страницах"
    skips = "Часть записей клиент так и не увидит: они «перепрыгнут» на уже прочитанные страницы"
    slow = "Запрос будет медленным: СУБД читает и отбрасывает все строки до OFFSET"
    situation, correct = rng.choice(
        [
            (
                "пока клиент листает, в начало постоянно добавляются новые записи",
                duplicates,
            ),
            ("пока клиент листает, старые записи из начала списка удаляются", skips),
            ("клиент запрашивает страницу 20 000 (OFFSET 2 000 000)", slow),
        ]
    )
    return choice(
        rng,
        f"API {entity} отдаёт страницы через LIMIT/OFFSET, по убыванию даты; {situation}. "
        "Что произойдёт? (Во всех случаях лечится keyset-пагинацией по (дата, id).)",
        correct,
        [duplicates, skips, slow, "Ничего: OFFSET стабилен и быстр"],
    )


@family("http.idempotency_key", competency=COMPETENCY, a=1.4, b=1.9)
def _idempotency_key(rng: Random) -> Item:
    key = (
        "Клиент шлёт уникальный Idempotency-Key, сервер хранит результат по ключу и на "
        "повтор возвращает его"
    )
    lock = "Оптимистическая блокировка: версия/ETag в запросе (If-Match), при расхождении: 412"
    dedupe = (
        "Дедупликация по id события: уникальный индекс в таблице обработанных событий"
    )
    situation, correct = rng.choice(
        [
            (
                (
                    f"Мобильный клиент делает POST на {rng.choice(['списание оплаты', 'перевод'])}; "
                    "при таймауте сети повторяет запрос, и операция иногда выполняется дважды"
                ),
                key,
            ),
            (
                (
                    "Два менеджера одновременно открыли карточку товара, каждый поменял своё поле "
                    "и сохранил целиком (PUT); правки первого пропали"
                ),
                lock,
            ),
            (
                (
                    "Платёжный провайдер присылает вебхук «оплачено» с повторами (at-least-once); "
                    "заказ иногда отгружается дважды"
                ),
                dedupe,
            ),
        ]
    )
    return choice(
        rng,
        f"{situation}. Какое решение надёжно?",
        correct,
        [key, lock, dedupe, "Увеличить таймауты и запретить клиентам повторы"],
    )


def token_bucket(capacity: int, rate: int, times: list[int]) -> list[int]:
    """Номера запросов (с 1), получивших 429: корзина ёмкостью capacity в начале полная,
    пополняется на rate токенов в секунду непрерывно (не выше ёмкости), запрос забирает
    один токен."""
    tokens, last, rejected = float(capacity), 0, []
    for n, t in enumerate(times, 1):
        tokens = min(capacity, tokens + (t - last) * rate)
        last = t
        if tokens >= 1:
            tokens -= 1
        else:
            rejected.append(n)
    return rejected


@family("http.token_bucket", competency=COMPETENCY, a=1.4, b=1.9)
def _token_bucket(rng: Random) -> Item:
    while True:
        capacity, rate = rng.randint(2, 4), rng.randint(1, 2)
        # Пачки запросов в одну секунду и паузы между ними.
        times: list[int] = []
        second = 0
        while len(times) < 9:
            times += [second] * rng.randint(2, 5)
            second += rng.randint(1, 2)
        times = times[:9]
        rejected = token_bucket(capacity, rate, times)
        # Часть запросов отклонена, часть нет: иначе ответ угадывается.
        if 0 < len(rejected) < len(times) - capacity:
            break
    return text(
        f"API ограничено по алгоритму token bucket: ёмкость {capacity} токена, пополнение "
        f"{rate} токен(а) в секунду (непрерывно, не выше ёмкости), в начале корзина полная, "
        "каждый запрос забирает 1 токен, без токена ответ 429. Запросы пришли в моменты "
        "(секунды) ниже. Какие запросы получат 429? Перечислите номера через пробел; если ни "
        "один: напишите «нет».",
        " ".join(map(str, rejected)) or "нет",
        code="\n".join(f"{n}. t = {t}" for n, t in enumerate(times, 1)),
    )


def fresh_seconds(directives: dict[str, int | None], age: int, *, shared: bool) -> int:
    """Сколько ещё секунд ответ свеж для кеша (0: сразу идти на сервер)."""
    if shared and "private" in directives:
        return 0  # общий кеш (CDN) не хранит private-ответы
    lifetime = directives.get("s-maxage") if shared else None
    if lifetime is None:
        lifetime = directives.get("max-age") or 0
    return max(0, lifetime - age)


@family("http.cache_freshness", competency=COMPETENCY, a=1.4, b=2.3)
def _cache_freshness(rng: Random) -> Item:
    max_age = rng.randrange(60, 601, 30)
    directives: dict[str, int | None] = {"max-age": max_age}
    if rng.random() < 0.6:
        directives["s-maxage"] = rng.randrange(max_age + 60, 3601, 60)
    if rng.random() < 0.3:
        directives["private"] = None
    age = rng.randrange(0, max_age, 10)
    shared = rng.choice([True, False])
    header = ", ".join(
        name if value is None else f"{name}={value}"
        for name, value in directives.items()
    )
    cache = "общем кеше CDN" if shared else "кеше браузера"
    return text(
        f"Ответ сервера пришёл через CDN с заголовками ниже. Сколько секунд он ещё будет "
        f"считаться свежим в {cache} (без обращения к серверу)? Если ни секунды: напишите 0.",
        fresh_seconds(directives, age, shared=shared),
        code=f"Cache-Control: {header}\nAge: {age}",
    )
