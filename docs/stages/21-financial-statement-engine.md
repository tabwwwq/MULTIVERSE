# Stage 21 — Финансовый движок

| Поле | Значение |
|---|---|
| Этап | 21 — accounting-consistent forecast engine |
| Дата | 2026-11-06 |
| Статус | REVIEW; ждёт CI и приёмки владельца |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/21_FINANCIAL_STATEMENT_ENGINE.md` |
| Основание | `docs/07_FINANCIAL_ENGINE.md`, команда владельца «Принять и Stage 21» |
| Решение | ADR-0029 — решение становится проводками, стоимость следует из отчётности |
| Whitepaper | [`docs/finance/financial-engine-whitepaper.md`](../finance/financial-engine-whitepaper.md) |

## 1. Scope

Чистый движок `multiverse_finance`: три связанных отчёта, учёт шести решений, FCFF, FCFE, WACC, DCF и мост к equity. Без экрана, API и нейросетей. Выборка параметров — Stage 22, Valuation Studio — Stage 23.

**Числа этого этапа синтетические.** Движок проверен на выдуманной компании и на случайных компаниях. К данным SEC он ещё не применялся.

## 2. План

| # | Подзадача | Результат |
|---|---|---|
| 1 | Точная арифметика | `exact.py`: контекст Decimal, отказ от плохих чисел, undefined с причиной |
| 2 | Лаги | `schedules.py`: ramp, shifted, spread |
| 3 | Проводки | `ledger.py`: 10 видов проводок, таблицы sources / uses |
| 4 | Движок | `engine.py`, `statements.py`, `checks.py`: три отчёта, ликвидность, реконсиляция |
| 5 | Шесть решений | `interventions.py`, `decisions.py`: журнал проводок, мост от контракта |
| 6 | Стоимость | `valuation.py`: WACC, DCF с кварталами, мост |
| 7 | Стрессы | `stress.py` |
| 8 | Whitepaper | Метод, журналы, ограничения US GAAP и IFRS, пример |

## 3. Отчёт этапа

### Done

- **Отчётность:** выручка по сегментам, COGS, R&D, SG&A, one-off, EBITDA и adjusted EBITDA, D&A, EBIT, проценты, налоги с переносом убытков, CFO, CAPEX, NWC, долг по траншам, revolver, ковенанты.
- **Шесть решений** с описанным учётом: R&D сейчас и отдача позже, выходные пособия и фонд оплаты, покупка со смесью долга и акций и синергиями, продажа актива, CAPEX с амортизацией и загрузкой, рефинансирование.
- **Стоимость только из отчётности.** Решение не может изменить KPI напрямую.
- **CFO − CAPEX, FCFF и FCFE разделены.** Мост между ними точен на каждом квартале, включая кварталы с убытками.
- **EV по FCFF и WACC,** мост к equity вычитает чистый долг и старшие требования.
- **Отрицательный кэш:** не появляется. Дефицит сверх лимита revolver становится именованным shortfall.
- **Отказ от невозможного:** NaN, float, WACC ≤ g, смесь финансирования не 100%, погашение больше долга, отрицательный goodwill. Отношения при неположительном знаменателе undefined.
- **Whitepaper** с ограничениями US GAAP и IFRS и определением корректировок EBITDA.

### Files

- **Новые:** `packages/finance/src/multiverse_finance/` (`exact`, `schedules`, `model`, `ledger`, `statements`, `engine`, `checks`, `interventions`, `decisions`, `valuation`, `stress`, `example`); `packages/finance/tests/` (`conftest`, `test_basics`, `test_engine`, `test_interventions`, `test_valuation`, `test_properties`, `test_stress`, `test_decisions`, `test_whitepaper`); `docs/finance/financial-engine-whitepaper.md`; `docs/adr/0029-financial-engine.md`; этот отчёт.
- **Изменённые:** `packages/finance/__init__.py`, `pyproject.toml`, `README.md` (версия 0.2.0); корневой `pyproject.toml` (hypothesis, контракт import-linter); `uv.lock`; `.gitignore`; `README.md`; `CHANGELOG.md`; `docs/adr/README.md`.
- **Контракты не менялись:** 0.18.0.

### Tests

Все команды запущены локально (Windows 11) 2026-11-06.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | Прошёл до конца за 6 мин 46 с. После него добавлена одна проверка в `test_whitepaper.py`, поэтому `npm run check:py` запущен заново: **EXIT 0** |
| pytest | **731 passed** (185 новых: все в `packages/finance/tests`; на Stage 20 было 546) |
| vitest contracts / web | 4 / **216** passed |
| contracts drift | schema 0.18.0 и TS — up to date |
| Playwright на 1440 / 768 / 390 | **586 passed, 14 skipped** |
| ruff, mypy strict, import-linter, secret scan, Prettier | без замечаний (4 контракта import-linter, 0 нарушено) |

- **Property-тесты** (`test_properties.py`, hypothesis, одинаковые примеры на всех машинах). На случайной компании и 1–3 случайных решениях из шести:
  - все тождества сходятся, кэш не отрицателен, revolver в лимите, налог не отрицателен (300 примеров);
  - sources = uses (200);
  - решение нулевого размера точно равно baseline (150, все шесть типов);
  - один вход даёт один путь (100);
  - DCF конечен при WACC > g и всегда отвергается при WACC ≤ g.
- **Известные ответы:** квартал, посчитанный вручную; рента 100 при 10% = 1000; Гордон 100 / 0,08 = 1250; WACC из частей; мост. Поток с постоянным ростом имеет одну стоимость при любом горизонте.
- **Лаги:** R&D, синергии, ввод и амортизация, стройка, выходное пособие, накладные начинаются в нужном квартале.
- **Стрессы:** выручка −20%, маржа, ставки +200 bps, закрытый рынок, NWC, ковенант, задержка синергий, провал сделки.
- **Реконсиляция ловит подделку:** изменённый кэш и таблица с разными источниками и использованием отвергаются.
- **Мутационная проверка (вручную, не в CI):** 23 намеренные поломки движка, оценки и решений. Первый прогон поймал 22; выжила поломка актива в стройке при продаже части бизнеса, на неё добавлен тест. Итог на финальном коде: 23 из 23.

### Measured results

Единственные числа этапа — свойства движка и пример на выдуманной компании.

| Свойство | Значение |
|---|---|
| Наибольший остаток тождества на примере | ниже 1e−30 USD (порог 0,01) |
| Один путь, 12 кварталов | около 1 мс |
| Прогон `packages/finance/tests` | 185 тестов за 14 с |

Пример **SYNTHETIC**, 20 кварталов, WACC 8,25%, g 2,5%: EV 9 406,04, equity 8 506,04, доля terminal value 77,7%. Таблица решений в разделе 14 whitepaper, все её числа проверяет `test_whitepaper.py`.

Эти числа показывают работу движка и ничего не говорят ни об одной реальной компании.

### Known limitations

- **Реальные данные не подключены.** Сопоставление со статьями SEC, включая вынос D&A из COGS, — работа Stage 22.
- **Отложенных налогов нет,** налог в отчёте равен уплаченному. Лимитов на убытки нет.
- **Стандарты не реализованы.** Различия US GAAP и IFRS перечислены в whitepaper, движок считает одну упрощённую модель.
- **Проводки не взаимодействуют:** эффекты складываются от baseline.
- **WACC постоянен:** EV не реагирует на рефинансирование и способ оплаты сделки.
- **Размещение цены покупки и сроки амортизации** — заглушки `Accounting` до измерений.
- **Отдача R&D равна нулю** по умолчанию: она не измерена.
- **Terminal value** вечно множит эффект решения без реакции спроса: в примере это завышает эффект штата и CAPEX.
- **Банкротства нет:** shortfall только сигнализирует.
- **Рецессия и FX-кризис** из `docs/07` не реализованы: первая относится к Stage 22, второй требует второй валюты.
- **Мутационная проверка** разовая и покрыла 23 выбранные поломки, а не весь код.

### Decisions

- Решение становится проводками, KPI напрямую не меняются.
- Несошедшийся путь не выходит из `project`.
- Плохой вход отвергается, вход без смысла даёт undefined с причиной.
- Кэш не уходит в минус: дефицит становится shortfall.
- Вероятность сделки не масштабирует проводки.
- Контракты не меняются до появления потребителя (Stage 22).
- hypothesis — новая dev-зависимость.

### Next prompt

`22_*.md` (Paired Monte Carlo universe simulator) — только по команде владельца.

## 4. Acceptance

| Критерий промпта 21 | Evidence | Статус |
|---|---|---|
| Движок независим от UI и нейросетей | Контракт import-linter, тест импорта | ✅ |
| Revenue by segment, GP, OPEX/R&D, EBIT, D&A, EBITDA, taxes, CFO, capex, NWC, FCFF, cash, net debt, financing, covenants | `statements.py`, `test_engine.py` | ✅ |
| Шесть решений с описанным учётом | `interventions.py`, whitepaper §9, `test_interventions.py` | ✅ |
| Value из согласованных путей | `Plan` → `project` → `enterprise_value` | ✅ |
| CFO−CAPEX, FCFE, FCFF разделены | Whitepaper §7, мост в `checks.py` | ✅ |
| EV через FCFF/WACC, мост вычитает net debt и claims | `valuation.py`, `test_valuation.py` | ✅ |
| IFRS/US GAAP limitation и EBITDA adjustments | Whitepaper §4, §15 | ✅ |
| Отказ от невозможных настроек, NaN, ratios | Whitepaper §11, тесты | ✅ |
| Unit и property tests: sources=uses | `test_properties.py` | ✅ |
| Accounting reconciliation | `checks.py`, property-тест | ✅ |
| Negative cash case | `test_engine.py`, `test_stress.py` | ✅ |
| WACC>g | `test_valuation.py`, property-тест | ✅ |
| Finite DCF | Property-тест | ✅ |
| Time-lag schedules | `test_basics.py`, `test_interventions.py` | ✅ |
| Zero-effect identity | `test_interventions.py`, property-тест | ✅ |
| Отдельный finance whitepaper | `docs/finance/financial-engine-whitepaper.md` | ✅ |
