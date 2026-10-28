# Architecture Decision Records

Решения, которые трудно отменить позже. Каждое ADR неизменяемо после `Accepted`: чтобы изменить решение, создаётся новое ADR со статусом `Supersedes ADR-XXXX`.

| ADR | Решение | Статус |
|---|---|---|
| [0001](0001-explicit-uncertainty.md) | Явная модель неопределённости у каждого числа | Accepted |
| [0002](0002-point-in-time-invariant.md) | Point-in-time данные как ключевой инвариант | Accepted |
| [0003](0003-no-gpu-in-http.md) | Никаких обучений и тяжёлых расчётов внутри HTTP-запроса | Accepted |
| [0004](0004-immutable-experiment-records.md) | Неизменяемые записи экспериментов и результатов | Accepted |
| [0005](0005-official-source-first.md) | Сначала официальные источники | Accepted |
| [0006](0006-explainability-is-not-causality.md) | Explainability не равна причинности | Accepted |
| [0007](0007-monorepo-tooling.md) | Monorepo: npm workspaces + uv workspace | Accepted |
| [0008](0008-contracts-single-source.md) | Contracts: Pydantic → JSON Schema → TypeScript | Accepted |
| [0009](0009-module-boundaries.md) | Границы модулей и правила импорта | Accepted |
| [0010](0010-config-and-profiles.md) | Профили окружения и валидация конфигурации | Accepted |
| [0011](0011-versioning.md) | Версионирование кода, contracts, продукта и результатов | Accepted |
| [0012](0012-company-repository.md) | Доступ к данным компаний через репозиторий (будущий API adapter) | Accepted |

ADR-0001…0006 перечислены в `docs/03_SYSTEM_ARCHITECTURE.md` комплекта. ADR-0007…0011 приняты на Stage 02.

## Шаблон

```markdown
# ADR-XXXX — Название

- Статус: Proposed | Accepted | Superseded by ADR-YYYY
- Дата: YYYY-MM-DD
- Этап: NN

## Контекст
## Решение
## Как проверяется
## Последствия
## Отвергнутые альтернативы
```
