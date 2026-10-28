# ADR-0008 — Contracts: Pydantic → JSON Schema → TypeScript

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 02

## Контекст

Одни и те же сущности (значение метрики, manifest, позже сценарии и действия) используют Python (API, worker, пайплайны) и TypeScript (web). Ручное дублирование типов в двух языках неизбежно расходится (acceptance Stage 02: «contracts не дублируются»).

## Решение

1. **Единственный источник** — Pydantic-модели в `packages/contracts/python/` (strict, `extra="forbid"`, `frozen=True`).
2. `python -m multiverse_contracts.export` пишет один документ JSON Schema 2020-12: `packages/contracts/schemas/contracts.schema.json` (детерминированно, ключи отсортированы).
3. `packages/contracts/ts/scripts/generate.mjs` генерирует TypeScript-типы и константу `CONTRACTS_VERSION` в `packages/contracts/ts/src/generated/`.
4. Обе генерации проверяются на дрейф: `npm run contracts:check` (и тест `tests/contract/test_schema_export.py`). В CI это отдельная задача.
5. Деньги и точные числа — строки decimal, не JSON floats. Даты — ISO 8601 с часовым поясом.
6. Межполевые правила (missing ≠ 0, demo ⇔ synthetic, правила causal status) живут в валидаторах Pydantic. JSON Schema их не выражает, поэтому общие примеры лежат в `packages/contracts/fixtures/valid.json` и `invalid.json`. На Stage 05 эти же фикстуры проверяет UI-валидация.

7. **Уточнение Stage 04:** схема экспортируется в режиме serialization, с `json_schema_serialization_defaults_required=True`. TypeScript-типы описывают то, что отправляют сервисы и получает web, поэтому поля с default (`source_ids`, `values`, `lineage`) в них обязательны. Если web начнёт отправлять данные (запросы сценариев, Stage 05), для них понадобятся отдельные типы в режиме validation.

## Как проверяется

`npm run contracts:check`, `uv run pytest packages/contracts tests/contract`, типовые тесты в `packages/contracts/ts/test/`.

## Последствия

Изменение contracts = правка Python-модели → `npm run contracts:gen` → коммит всех трёх артефактов вместе. Сгенерированные файлы не редактируются руками и исключены из ESLint и Prettier.

## Отвергнутые альтернативы

- JSON Schema как исходник: писать схемы руками дольше, а Python-модели всё равно нужны.
- OpenAPI из FastAPI как исходник: contracts нужны и вне HTTP (worker, пайплайны, фикстуры).
- Protobuf: лишний toolchain, плохо подходит для decimal-строк и человекочитаемых фикстур.
