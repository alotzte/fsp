import pytest

from app.schemas.candidates import CONTACT_PLACEHOLDER, mask_contacts


@pytest.mark.parametrize(
    "contact",
    [
        "ivan.petrov@mail.ru",
        "+7 (999) 123-45-67",
        "8 999 123 45 67",
        "8 (999) 123-45-67",
        "89991234567",
        "+375 29 123-45-67",
        "https://github.com/ivan",
        "www.ivanov.dev",
        "t.me/ivan_petrov",
        "github.com/ivan",
        "ivanov.dev",
        "@ivan_petrov",
        "tg: ivan_petrov",
        "Телеграм: ivan_petrov",
        "9161234567",
        "916 123-45-67",
        "(916) 123-45-67",
    ],
)
def test_contact_is_masked(contact: str) -> None:
    masked = mask_contacts(f"Пишите: {contact}, отвечу быстро")
    # Ссылка может забрать соседнюю запятую, это не утечка.
    assert masked.startswith(f"Пишите: {CONTACT_PLACEHOLDER}")
    assert masked.endswith(" отвечу быстро")
    assert not any(ch.isdigit() for ch in masked)
    assert "ivan" not in masked


@pytest.mark.parametrize(
    "text",
    [
        "Python 3.11, Node.js, Vue.js, ASP.NET, CI/CD",
        "Писал Telegram-ботов на aiogram",
        "Работал в 2015-2019 и 2019–2023, с 01.02.2020-03.04.2021",
        "Сервис на 1 000 000 пользователей, вилка 250 000-300 000",
        "Вилка 950 000-1 200 000, 999 задач",
        "Конфиги в settings.json и docker-compose.yml",
    ],
)
def test_ordinary_text_is_kept(text: str) -> None:
    assert mask_contacts(text) == text
