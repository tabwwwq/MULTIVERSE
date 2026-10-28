# ADR-0011 — Версионирование кода, contracts, продукта и результатов

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 02

## Контекст

Результат должен ссылаться на точные версии кода, данных, модели и contracts (`docs/03`, раздел Versioning). Разные вещи меняются с разной скоростью.

## Решение

| Что | Схема | Где |
|---|---|---|
| Пакеты (Python и TS) | SemVer `0.x`, пока все модули в lockstep | `pyproject.toml`, `package.json`, `__version__` |
| Contracts | SemVer отдельно от пакетов: MINOR — новые необязательные поля и модели, MAJOR — удаление или смена смысла поля | `multiverse_contracts.version.CONTRACTS_VERSION`, поле `x-contracts-version` в схеме |
| Продукт | V0…V4 из scope matrix | `docs/product/04-scope-matrix.md` |
| История изменений | Keep a Changelog | `CHANGELOG.md` |
| Коммиты | Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) | git |
| Результат | `ReproducibilityManifest`: `code_version` = git commit, `contracts_version`, dataset snapshot, model ID, seed | contracts |

## Как проверяется

`tests/smoke/test_modules.py` сверяет `__version__` каждого модуля с версией пакета. Manifest требует корректный SemVer contracts.

## Последствия

Каждый этап обновляет `CHANGELOG.md`. Изменение contracts без смены `CONTRACTS_VERSION` ловит review, а drift check ловит забытую генерацию.

## Отвергнутые альтернативы

Одна общая версия для всего, включая contracts: несовместимое изменение contracts становится незаметным.
