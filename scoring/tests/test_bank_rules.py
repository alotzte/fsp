"""Правила, по которым вычисляются эталоны семейств без внешней проверки (у JS её даёт Node).

Случаи разобраны вручную: если правило поменяется, эталоны всех экземпляров станут неверными.
"""

from fractions import Fraction

from app.services.assessment.bank.http_api import fresh_seconds, token_bucket
from app.services.assessment.bank.ml import rejected_hypotheses
from app.services.assessment.bank.react import context_rerenders, effect_order
from app.services.assessment.bank.web import cookie_sent, csp_allows


def test_csp_nonce_disables_unsafe_inline() -> None:
    assert csp_allows("inline", has_nonce=False, unsafe_inline=True)
    assert not csp_allows("inline", has_nonce=True, unsafe_inline=True)
    assert csp_allows("nonce_ok", has_nonce=True, unsafe_inline=False)
    assert not csp_allows("nonce_bad", has_nonce=True, unsafe_inline=True)
    assert not csp_allows("subdomain", has_nonce=False, unsafe_inline=True)


def test_cookie_rules() -> None:
    host_only_lax = (False, "/", "Lax")
    domain_lax = (True, "/", "Lax")
    strict_cart = (False, "/cart", "Strict")
    none_cookie = (True, "/", "None")
    link = {"host": "shop.example", "cross_site": True, "top_level": True}
    # Межсайтовый переход по ссылке: Lax уходит, Strict: нет.
    assert cookie_sent(host_only_lax, path="/", method="GET", **link)
    assert not cookie_sent(strict_cart, path="/cart/items", method="GET", **link)
    # Межсайтовая отправка формы POST: Lax уже не уходит, None: уходит.
    assert not cookie_sent(host_only_lax, path="/", method="POST", **link)
    assert cookie_sent(none_cookie, path="/", method="POST", **link)
    # Поддомен: host-only cookie не уходит, cookie с Domain: уходит.
    api = {
        "host": "api.shop.example",
        "cross_site": False,
        "top_level": False,
        "method": "GET",
    }
    assert not cookie_sent(host_only_lax, path="/", **api)
    assert cookie_sent(domain_lax, path="/", **api)
    # Path: /cart подходит к /cart/items, но не к /cartoon.
    same = {
        "host": "shop.example",
        "cross_site": False,
        "top_level": False,
        "method": "GET",
    }
    assert cookie_sent(strict_cart, path="/cart/items", **same)
    assert not cookie_sent(strict_cart, path="/cartoon", **same)


def test_effect_order_layout_first_children_before_parent() -> None:
    tree = {"P": ["A", "B"], "A": ["C"], "B": [], "C": []}
    assert effect_order(tree, {"B", "P"}) == ["B", "P", "C", "A"]
    assert effect_order(tree, {"C"}) == ["C", "A", "B", "P"]


def test_context_rerenders() -> None:
    # memo со стабильным колбэком отсекает Toolbar; children не рендерятся без подписки.
    assert (
        context_rerenders(
            toolbar_memo=True, stable_toggle=True, status_memo=True, consumers=set()
        )
        == []
    )
    # Новая стрелочная функция ломает memo; подписчик рендерится и под memo.
    assert context_rerenders(
        toolbar_memo=True, stable_toggle=False, status_memo=True, consumers={"Status"}
    ) == ["Status", "Toolbar"]
    # Page подписан: его ребёнок Article рендерится вместе с ним.
    assert context_rerenders(
        toolbar_memo=False, stable_toggle=True, status_memo=False, consumers={"Page"}
    ) == ["Article", "Page", "Status", "Toolbar"]


def test_token_bucket() -> None:
    # Ёмкость 2, 1 токен/с: пачка из 3 в t=0, третий отклонён; к t=1 накопился 1 токен.
    assert token_bucket(2, 1, [0, 0, 0, 1, 1]) == [3, 5]


def test_cache_freshness() -> None:
    headers: dict[str, int | None] = {"max-age": 60, "s-maxage": 600}
    assert fresh_seconds(headers, 30, shared=False) == 30  # браузер: max-age − Age
    assert fresh_seconds(headers, 30, shared=True) == 570  # CDN: s-maxage − Age
    assert fresh_seconds(headers | {"private": None}, 30, shared=True) == 0
    assert fresh_seconds({"max-age": 60}, 90, shared=False) == 0


def test_multiple_testing_corrections() -> None:
    alpha = Fraction(1, 20)
    pvalues = [Fraction(p) for p in ("0.001", "0.012", "0.03", "0.5")]
    assert rejected_hypotheses(pvalues, "Бонферрони", alpha) == [1, 2]
    assert rejected_hypotheses(pvalues, "Холма", alpha) == [1, 2]
    assert rejected_hypotheses(pvalues, "Бенджамини-Хохберга", alpha) == [1, 2, 3]
    textbook = [Fraction(p) for p in ("0.01", "0.02", "0.03", "0.04", "0.05")]
    assert rejected_hypotheses(textbook, "Холма", alpha) == [1]
    assert rejected_hypotheses(textbook, "Бенджамини-Хохберга", alpha) == [
        1,
        2,
        3,
        4,
        5,
    ]
