# backend

API платформы для обоих кабинетов: профили, тест на грейд, подбор, приглашения, вакансии, ФСП ID.
FastAPI, async SQLAlchemy, Alembic, админка SQLAdmin на `/admin`. Владеет базой данных; расчёты
(сборка теста, IRT, ранжирование) делегирует сервису `scoring` по HTTP.

## Устройство

| Каталог | Что в нём |
|---|---|
| `app/api/` | ручки: принимают запрос, вызывают сервис, возвращают схему |
| `app/services/` | логика: `assessment`, `hiring`, `invitations`, `candidates`, `fsp`, `cases`, `trust` и др. |
| `app/services/db/` | модели SQLAlchemy и сессия |
| `app/services/auth/` | вход через Keycloak (Authorization Code + PKCE), сессии |
| `app/schemas/` | схемы запросов и ответов (Pydantic) |
| `migrations/` | миграции Alembic |
| `tests/` | тесты правил: грейд, ФСП, видимость, доверие, разбор резюме |
| `validation/` | валидация разбора PDF-резюме, пишет `docs/validation-resume.md` |

Бизнес-ошибки сервисов наследуют классы из `app/errors.py`; общий обработчик переводит их в
HTTP-коды, имя класса уходит во фронт полем `error`. Все ручки с кодами ошибок описаны в OpenAPI
(`/docs` на стенде).

## Запуск и проверки

Обычно backend запускается вместе со всем стендом (`docker compose up -d --build` из корня). Для
разработки нужен Postgres (`docker compose up -d postgres`) и `backend/.env` по образцу
`.env.example`:

```sh
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload
uv run ruff format . && uv run ruff check . && uv run mypy app migrations
uv run pytest
```

Вход работает только через gateway: redirect URI Keycloak указывает на `PUBLIC_URL`.

Демо-данные (кандидаты, проходящие настоящий тест, и компания с историей приглашений):

```sh
uv run python -m app.demo_seed 90
```
