# scoring

Сервис расчётов без состояния: банк заданий, сборка теста, оценка уровня по IRT и ранжирование
кандидатов с объяснением. В базу не ходит, всё нужное присылает `backend`. Скрипты валидации
импортируют те же функции, поэтому метрики в `docs/validation-*.md` измеряют продакшен-код.

## Устройство

| Каталог | Что в нём |
|---|---|
| `app/services/assessment/bank/` | параметризованные семейства заданий: у каждой попытки свой экземпляр с общей структурой и сложностью |
| `app/services/assessment/assembly.py` | сборка теста по спецификации (LOFT) и добор заданий у порога грейда |
| `app/services/assessment/irt.py` | 2PL IRT, оценка уровня (EAP) и устойчивость решения о грейде |
| `app/services/matching.py` | скор совпадения с вкладом каждого фактора и причинами |
| `validation/` | валидация теста и подбора, пишет отчёты в `docs/` |
| `tests/` | тесты сборки, банка и матчинга |

## API

| Метод | Назначение |
|---|---|
| `GET /assessment/blueprints` | спецификации тестов по направлениям и грейдам |
| `POST /assessment/assemble` | собрать тест для попытки |
| `POST /assessment/score` | оценить ответы, решить о грейде или о продлении |
| `POST /assessment/extend` | добавить задания у порога грейда |
| `POST /assessment/case` | кейс недели |
| `POST /matching/rank` | ранжировать пул кандидатов под потребность |

Схема запросов и ответов: `/docs` запущенного сервиса.

## Запуск и проверки

```sh
uv sync
uv run uvicorn app.main:create_app --factory --port 8001 --reload
uv run ruff format . && uv run ruff check . && uv run mypy app
uv run pytest
uv run python -m validation.assessment > ../docs/validation-assessment.md
uv run python -m validation.matching > ../docs/validation-matching.md
```
