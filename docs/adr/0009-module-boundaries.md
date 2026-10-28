# ADR-0009 — Границы модулей и правила импорта

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 02

## Контекст

Без автоматических правил модули быстро склеиваются: API начинает обучать модели, финансы импортируют веб-фреймворк, UI читает внутренние файлы других пакетов.

## Решение

Слои Python (сверху вниз; модуль может импортировать только нижние слои, соседи по слою независимы):

| Слой | Модули |
|---|---|
| Services (composition roots) | `multiverse_api`, `multiverse_worker` |
| Domain | `multiverse_finance`, `multiverse_causal`, `multiverse_forecast`, `multiverse_pipelines` |
| Base | `multiverse_contracts`, `multiverse_config` |

Дополнительно:

- API не импортирует `forecast`, `causal`, `pipelines` (ADR-0003).
- Contracts и domain-пакеты не импортируют `fastapi`, `starlette`, `uvicorn`.
- Только composition roots (`services/*/main.py`) вызывают `load_settings()`. Остальной код получает настройки аргументом.
- Импорты абсолютные (ruff `TID252`).

TypeScript (ESLint `no-restricted-imports`):

- другой модуль импортируется только по имени пакета (`@multiverse/contracts`), не относительным путём;
- запрещены deep imports (`@multiverse/*/src/**`) и импорт `generated/**` в обход entry point.

Когда появится `packages/simulation` (Stage 22), ему понадобятся `finance` и `forecast`. Это потребует нового слоя между Services и Domain — через новое ADR.

## Как проверяется

`uv run lint-imports` (конфигурация — `[tool.importlinter]` в корневом `pyproject.toml`) и `npx eslint .`. Оба входят в `npm run check` и CI. Нарушения проверены намеренно на Stage 02 (отчёт этапа).

## Последствия

Новый модуль сначала добавляется в import-linter и ADR, и только потом получает код.

## Отвергнутые альтернативы

Соглашение «на словах» в README: нарушается незаметно.
