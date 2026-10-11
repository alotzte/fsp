# Библиотеки и лицензии

ТЗ (§3.4, §5) требует открытый код и рекомендует зависимости под MIT, Apache-2.0 или BSD. Ниже
перечислены все прямые зависимости с версиями из `backend/uv.lock`, `scoring/uv.lock` и
`frontend/pnpm-lock.yaml` и лицензиями из метаданных установленных пакетов.

Все прямые зависимости распространяются под MIT, BSD, Apache-2.0, ISC или OFL-1.1 (шрифты). Среди
транзитивных есть несколько других разрешительных лицензий, они перечислены в конце и с открытостью
кода не конфликтуют.

## Backend (`backend/`, Python 3.13, uv)

| Библиотека | Версия | Лицензия | Где | Зачем |
|---|---|---|---|---|
| aiosmtplib | 5.1.3 | MIT | рантайм | отправка писем (SMTP) |
| alembic | 1.20.0 | MIT | рантайм | миграции схемы БД |
| asyncpg | 0.31.0 | Apache-2.0 | рантайм | драйвер PostgreSQL |
| fastapi | 0.142.2 | MIT | рантайм | веб-API и OpenAPI |
| httpx | 0.28.1 | BSD | рантайм | HTTP-клиент (Keycloak, scoring) |
| itsdangerous | 2.2.0 | BSD | рантайм | подписанные cookie и ссылки |
| pdfplumber | 0.11.10 | MIT | рантайм | текст из PDF-резюме |
| pydantic-settings | 2.15.0 | MIT | рантайм | конфигурация из env |
| pyjwt | 2.15.1 | MIT | рантайм | проверка ID-токенов OIDC |
| python-multipart | 0.0.32 | Apache-2.0 | рантайм | загрузка файлов |
| reportlab | 5.0.1 | BSD | рантайм | генерация PDF-профиля |
| sqladmin | 0.32.0 | BSD-3-Clause | рантайм | админка /admin |
| sqlalchemy | 2.1.3 | MIT | рантайм | ORM |
| uvicorn | 0.54.0 | BSD-3-Clause | рантайм | ASGI-сервер |
| mypy | 2.4.0 | MIT | разработка | проверка типов |
| pytest | 9.1.1 | MIT | разработка | тесты |
| ruff | 0.16.10 | MIT | разработка | линтер и форматтер |
| types-reportlab | 5.0.0.20261006 | Apache-2.0 | разработка | типы для reportlab |

## Scoring (`scoring/`, Python 3.13, uv)

| Библиотека | Версия | Лицензия | Где | Зачем |
|---|---|---|---|---|
| fastapi | 0.142.2 | MIT | рантайм | веб-API и OpenAPI |
| pydantic-settings | 2.15.0 | MIT | рантайм | конфигурация из env |
| uvicorn | 0.54.0 | BSD-3-Clause | рантайм | ASGI-сервер |
| httpx | 0.28.1 | BSD | разработка | HTTP-клиент (Keycloak, scoring) |
| mypy | 2.4.0 | MIT | разработка | проверка типов |
| pytest | 9.1.1 | MIT | разработка | тесты |
| ruff | 0.16.10 | MIT | разработка | линтер и форматтер |

## Frontend (`frontend/`, Node 22, pnpm)

| Библиотека | Версия | Лицензия | Где | Зачем |
|---|---|---|---|---|
| @fontsource-variable/inter | 5.3.0 | OFL-1.1 | рантайм | шрифт Inter |
| @fontsource-variable/jetbrains-mono | 5.3.0 | OFL-1.1 | рантайм | шрифт JetBrains Mono (брендбук ФСП) |
| @hookform/resolvers | 5.9.1 | MIT | рантайм | zod в react-hook-form |
| @tailwindcss/vite | 4.3.3 | MIT | рантайм | Tailwind в сборке |
| @tanstack/react-query | 5.104.1 | MIT | рантайм | запросы и кэш |
| class-variance-authority | 0.7.1 | Apache-2.0 | рантайм | варианты компонентов |
| cn | 0.4.0 | MIT | рантайм | склейка классов |
| lucide-react | 1.52.0 | ISC | рантайм | иконки |
| radix-ui | 1.6.7 | MIT | рантайм | доступные примитивы UI (shadcn/ui) |
| react | 19.3.0 | MIT | рантайм | UI |
| react-dom | 19.3.0 | MIT | рантайм | UI |
| react-hook-form | 7.89.0 | MIT | рантайм | формы |
| react-router | 8.4.0 | MIT | рантайм | маршрутизация |
| shadcn | 4.21.1 | MIT | рантайм | компоненты UI |
| tailwindcss | 4.3.3 | MIT | рантайм | стили |
| tw-animate-css | 1.4.0 | MIT | рантайм | анимации |
| zod | 4.6.5 | MIT | рантайм | валидация форм |
| @types/node | 24.19.1 | MIT | разработка | типы |
| @types/react | 19.3.0 | MIT | разработка | типы |
| @types/react-dom | 19.3.0 | MIT | разработка | типы |
| @vitejs/plugin-react | 6.1.1 | MIT | разработка | React в Vite |
| orval | 8.39.0 | MIT | разработка | генерация клиента из OpenAPI |
| oxlint | 1.86.0 | MIT | разработка | линтер |
| prettier | 3.9.9 | MIT | разработка | форматтер |
| prettier-plugin-tailwindcss | 0.8.1 | MIT | разработка | порядок классов |
| typescript | 6.0.3 | Apache-2.0 | разработка | типизация |
| vite | 8.3.2 | MIT | разработка | сборка |

Всего в `node_modules` фронта 440 пакетов: MIT 395, ISC 18, BSD 12, Apache-2.0 5,
остальные перечислены ниже.

## Инфраструктура (`docker-compose.yml`)

| Образ | Версия | Лицензия | Зачем |
|---|---|---|---|
| nginx | 1.29-alpine | BSD-2-Clause | gateway: единая точка входа |
| PostgreSQL (pgvector/pgvector) | 17 | PostgreSQL License (BSD-подобная) | основная БД и БД Keycloak |
| Keycloak | 26.8 | Apache-2.0 | регистрация, вход, подтверждение email; мок ФСП ID |
| Mailpit | 1.31 | MIT | перехват писем стенда (`/mail`) |
| astral-sh/uv (python3.13-bookworm-slim) | | Apache-2.0 / MIT | базовый образ Python-сервисов |
| fonts-dejavu-core | Debian | свободная лицензия Bitstream Vera / public domain | кириллица в PDF-профиле |

## Транзитивные зависимости вне MIT / BSD / Apache

| Пакет | Чей | Лицензия | Комментарий |
|---|---|---|---|
| certifi | httpx | MPL-2.0 | корневые сертификаты; файловый копилефт, код не меняем |
| pathspec | mypy (только разработка) | MPL-2.0 | в рантайм не попадает |
| typing_extensions | pydantic, SQLAlchemy | PSF-2.0 | разрешительная |
| greenlet | SQLAlchemy asyncio | MIT и PSF-2.0 | разрешительная |
| pillow | pdfplumber | MIT-CMU (HPND) | разрешительная |
| pypdfium2 | pdfplumber | BSD-3-Clause / Apache-2.0 + лицензии PDFium | PDFium: BSD-3-Clause |
| caniuse-lite | сборка фронта | CC-BY-4.0 | данные о браузерах, только сборка |
| lightningcss | Tailwind | MPL-2.0 | только сборка |
| argparse | сборка фронта | Python-2.0 | только сборка |
| isexe, minimatch | сборка фронта | BlueOak-1.0.0 | разрешительная, только сборка |
| @fontsource-variable/* | фронт | OFL-1.1 | шрифты, разрешено встраивать |
