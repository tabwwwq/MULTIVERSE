# Stage 01 — Отчёт и acceptance checklist

| Поле | Значение |
|---|---|
| Этап | 01 — Product requirements, scope и use cases |
| Дата | 2026-10-28 |
| Статус | ACCEPTED — владелец принял этап и defaults открытых вопросов 2026-10-28 |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/01_PRODUCT_REQUIREMENTS.md` |

## Отчёт этапа

**Done.** Создан комплект продуктовых требований без программирования: PRD, 4 personas с JTBD, 15 user stories, 10 failure cases, путь company → as-of → action → simulation → report, scope V0–V4 с исключениями, доступ к 20 страницам по ролям, различие predictive и causal uncertainty, правила маркировки синтетики, защита от ложной точности, 3 case studies, 10 продуктовых рисков, словарь величин, FR и NFR с ID, security / privacy, failure modes, offline UX, 20 открытых вопросов с defaults.

**Files.**

| Файл | Содержание |
|---|---|
| `docs/product/README.md` | Индекс документов этапа |
| `docs/product/01-prd.md` | PRD |
| `docs/product/02-personas.md` | 4 personas и JTBD |
| `docs/product/03-user-stories.md` | 15 user stories, 10 failure cases |
| `docs/product/04-scope-matrix.md` | Scope V0–V4, исключения |
| `docs/product/05-product-risks.md` | 10 продуктовых рисков |
| `docs/product/06-open-questions.md` | 20 открытых вопросов с defaults |
| `docs/product/07-metric-definitions.md` | Величины, единицы, валюты |
| `docs/product/08-acceptance-checklist.md` | Этот отчёт |
| `docs/stages/00-orchestrator-briefing.md` | Stage 00: понимание и 14 научных рисков |
| `CHANGELOG.md` | Запись о Stage 00–01 |

**Tests.** Не применимо: этап без кода. Выполнена проверка структуры: внутренние ссылки между документами и наличие всех обязательных разделов (см. checklist ниже).

**Measured results.** Нет: данных и моделей нет. Исторический coverage не заявляется.

**Known limitations.**

- Personas — гипотезы без интервью с пользователями. Проверка — на юзабилити-тесте Stage 08.
- XBRL-теги в словаре величин — кандидаты, финальный mapping — Stage 11.
- Цели производительности (p95 < 2 s, INP < 200 ms) — целевые значения, не измерения.
- Мастер-промпт требует ждать prompt 01 после подтверждения. Stage 01 выполнен сразу по прямой просьбе пользователя.

**Decisions.** D-00 (репозиторий в `pred/multiverse/`) и D-01…D-08 — см. [PRD §16](01-prd.md#16-решения-этапа) и [открытые вопросы](06-open-questions.md).

**Next prompt.** `02_REPOSITORY_FOUNDATION.md` — только по команде владельца.

## Acceptance checklist

Требования из `prompts/01_PRODUCT_REQUIREMENTS.md`.

| # | Требование промпта | Где выполнено | Статус |
|---|---|---|---|
| 1 | Зрелый PRD для финансовых консультантов без программирования | [01-prd.md](01-prd.md) | ✅ |
| 2 | 4 personas | [02-personas.md](02-personas.md) P1–P4 | ✅ |
| 3 | JTBD для personas | [02-personas.md](02-personas.md), по 3 JTBD на persona | ✅ |
| 4 | 15 user stories | [03-user-stories.md](03-user-stories.md) US-01…US-15 | ✅ |
| 5 | 10 failure cases | [03-user-stories.md](03-user-stories.md#failure-cases) FC-01…FC-10 | ✅ |
| 6 | Journey company → as-of → action → simulation → report | [PRD §5](01-prd.md#5-главный-путь-company--as-of--action--simulation--report) | ✅ |
| 7 | Scopes V0 / V1 / V2 / V3 / V4 и exclusions | [04-scope-matrix.md](04-scope-matrix.md) | ✅ |
| 8 | Какие страницы нужны каждой роли | [PRD §4](01-prd.md#4-пользователи-роли-и-страницы) | ✅ |
| 9 | Чем predictive uncertainty отличается от causal | [PRD §6](01-prd.md#6-режимы-вывода-и-типы-неопределённости) | ✅ |
| 10 | Как маркировать synthetic data | [PRD §7](01-prd.md#7-маркировка-synthetic-data) SYN-01…SYN-08 | ✅ |
| 11 | Защита от ложной точности | [PRD §8](01-prd.md#8-защита-от-ложной-точности) FP-01…FP-10 | ✅ |
| 12 | 3 приоритетные портфолио case studies | [PRD §15](01-prd.md#15-приоритетные-портфолио-case-studies) CS-1…CS-3 | ✅ |
| 13 | 10 продуктовых рисков | [05-product-risks.md](05-product-risks.md) PR-01…PR-10 | ✅ |
| 14 | Revenue / EBITDA / FCF / EV / equity / price, units, currency | [07-metric-definitions.md](07-metric-definitions.md) | ✅ |
| 15 | Functional requirements с ID и измеримостью | [PRD §10](01-prd.md#10-functional-requirements) | ✅ |
| 16 | Nonfunctional requirements с ID и измеримостью | [PRD §11](01-prd.md#11-non-functional-requirements) | ✅ |
| 17 | Security / privacy | [PRD §12](01-prd.md#12-безопасность-и-приватность) SP-01…SP-09 | ✅ |
| 18 | Failure modes | [PRD §13](01-prd.md#13-failure-modes-системы) FM-01…FM-10 | ✅ |
| 19 | Offline UX | [PRD §14](01-prd.md#14-offline-ux) OFF-01…OFF-07 | ✅ |
| 20 | Никакой выдуманной historical coverage | Во всех документах coverage — «неизвестен до Stage 14» | ✅ |
| 21 | Отдельные файлы PRD, personas, user stories, scope matrix, risks, таблица открытых вопросов | 7 файлов в `docs/product/` | ✅ |
| 22 | Acceptance checklist в конце, дальше не переходить | Этот файл; Stage 02 не начат | ✅ |

## Статус acceptance matrix

Все 31 пункт `docs/17_ACCEPTANCE_MATRIX.md` остаются **TODO**: Stage 01 задаёт требования, а не реализацию. Трассировка требований к пунктам matrix — в [PRD §18](01-prd.md#18-трассировка-к-acceptance-matrix).
