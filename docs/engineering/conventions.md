# Инженерные соглашения

Как писать код в MULTIVERSE, чтобы его понимал junior и проверяли машины. Решения — в `docs/adr/`.

## Структура модуля

- Python: `<module>/pyproject.toml`, `<module>/src/<package>/`, `<module>/tests/`, `<module>/README.md` с ответственностью и номером этапа.
- TypeScript: `<module>/package.json` с `exports`, `src/index.ts` как единственный публичный entry point, `test/`.
- Новый модуль: добавить в workspace (`pyproject.toml` / `package.json`), в import-linter и ADR-0009, в `tests/smoke/test_modules.py`.

## Python

| Правило | Как обеспечено |
|---|---|
| Строгая типизация, без `Any` в публичных API | mypy `strict = true`, плагин pydantic |
| Contracts — strict Pydantic, `extra="forbid"`, `frozen=True` | `ContractModel` |
| Деньги — `decimal.Decimal` в расчётах, decimal-строки на границах | ADR-0008 |
| Даты — с часовым поясом (`AwareDatetime`) | contracts |
| Абсолютные импорты | ruff `TID252` |
| Настройки читает только composition root | ADR-0009, ADR-0010 |
| Missing ≠ 0: отсутствующее значение — `None` с причиной | валидатор `MetricValue` |
| Форматирование и линт | `ruff format`, `ruff check` (line length 100) |

## TypeScript

| Правило | Как обеспечено |
|---|---|
| `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `verbatimModuleSyntax` | `tsconfig.base.json` |
| Импорт других модулей только по имени пакета, без deep imports | ESLint `no-restricted-imports` |
| Типы contracts только из `@multiverse/contracts` | ADR-0008, ADR-0009 |
| Форматирование | Prettier (print width 100) |
| Линт | ESLint flat config + `typescript-eslint` strict |

## Тесты

- Unit-тесты — рядом с модулем. Межмодульные — в `tests/` (`smoke`, `contract`, позже `integration`, `backtesting`, `e2e`).
- Имена тестов описывают правило: `test_missing_value_without_reason_is_rejected`, а не `test_1`.
- Негативные случаи обязательны: каждое правило имеет тест, который его нарушает.
- Общие примеры contracts — `packages/contracts/fixtures/`.
- Тестовые «ключи» не похожи на настоящие: сканер секретов проверяет и тесты.
- Предупреждения в pytest — ошибки (`filterwarnings = error`). Исключение добавляется точечно, с комментарием.

## Сгенерированные файлы

`packages/contracts/schemas/*.json` и `packages/contracts/ts/src/generated/*` не редактируются руками. После изменения contracts: `npm run contracts:gen`, затем коммит всех артефактов вместе.

## Секреты и данные

- Секреты — только в `.env` (игнорируется git) или в secret manager. В `.env.example` — только плейсхолдеры.
- Скачанные данные и артефакты — в `var/` (игнорируется git). В репозитории — только схемы и маленькие синтетические фикстуры.
- Сетевые загрузки выключены, пока владелец их не включит (ADR-0005).

## Документация и язык

- Код, комментарии, docstrings, публичный README — на английском. Проектная документация в `docs/` — на русском (решение D-08, ADR-0007).
- Каждый этап обновляет `CHANGELOG.md` и пишет отчёт в `docs/stages/`.

## Коммиты

Conventional Commits: `feat(contracts): add MetricValue`, `fix(config): reject negative budget`, `docs(adr): add ADR-0012`. Один коммит — одна логическая единица. Перед коммитом — `npm run check`.
