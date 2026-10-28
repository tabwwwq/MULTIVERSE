# MULTIVERSE — Словарь финансовых величин, единиц и валют

| Поле | Значение |
|---|---|
| Документ | Metric definitions, Stage 01, версия 0.1, 2026-10-28 |
| Основание | `docs/04_DATA_SOURCES.md` (metric mapping), `docs/07_FINANCIAL_ENGINE.md`, `docs/18_GLOSSARY.md` |
| Связано | [PRD](01-prd.md) §9 |

> XBRL-теги ниже — **кандидаты**. Окончательный concept mapping с иерархией и reconciliation делается на Stage 11 и сверяется с оригинальными filings.

## 1. Величины

| Величина | Определение и формула | Кандидаты US-GAAP | Тип | Частая путаница | Как подписывать в UI |
|---|---|---|---|---|---|
| Revenue | Признанная выручка по стандарту отчётности | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` (до 2018) | Flow, период | Разные теги у одной компании в разные годы; segment vs consolidated | «Revenue (reported)» |
| COGS | Себестоимость | `CostOfRevenue`, `CostOfGoodsAndServicesSold` | Flow | Включение D&A в COGS у части компаний | «Cost of revenue» |
| Gross profit | Revenue − COGS | `GrossProfit` | Flow | Не все компании раскрывают | «Gross profit» |
| R&D | Расходы на исследования и разработки | `ResearchAndDevelopmentExpense` | Flow | Тег есть не у всех; capitalization vs expensing | «R&D expense» |
| EBIT | Прибыль до процентов и налогов, близко к operating income | `OperatingIncomeLoss` | Flow | EBIT ≠ operating income при non-operating items | «Operating income (EBIT proxy)» |
| D&A | Амортизация основных средств и нематериальных активов | `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization` (cash flow statement) | Flow | Разные теги; D&A внутри COGS | «D&A» |
| EBITDA | EBIT + D&A (D-05) | Нет стандартного тега | Flow | Adjusted EBITDA из пресс-релизов ≠ calculated | «EBITDA (calculated)». Adjusted — только с reconciliation |
| Net income | Чистая прибыль | `NetIncomeLoss` | Flow | ≠ `NetIncomeLossAvailableToCommonStockholdersBasic` | «Net income» |
| CFO | Операционный денежный поток | `NetCashProvidedByUsedInOperatingActivities` | Flow, **YTD** в 10-Q | Значение в 10-Q — накопленное с начала года, а не квартал | «Operating cash flow» |
| CAPEX | Капитальные затраты | `PaymentsToAcquirePropertyPlantAndEquipment` | Flow, YTD | Исключение acquisitions; знак (outflow) | «CAPEX» (положительное число = расход) |
| FCF (simple) | CFO − CAPEX | Расчёт | Flow | Это **не** FCFF. С WACC не дисконтируется | «FCF (simple, CFO − CAPEX)» |
| FCFF | EBIT × (1 − t) + D&A − CAPEX − ΔNWC | Расчёт | Flow | Требует допущения о налоговой ставке t | «FCFF (unlevered, model)» |
| FCFE | FCFF − interest × (1 − t) + net borrowing | Расчёт | Flow | Дисконтируется по cost of equity, а не WACC | «FCFE (levered, model)» |
| ΔNWC | Изменение net working capital | Расчёт из balance sheet | Flow | Знак: рост NWC **уменьшает** FCF | «Change in NWC» |
| Cash | Денежные средства и эквиваленты | `CashAndCashEquivalentsAtCarryingValue` | Stock, дата | Restricted cash; short-term investments | «Cash & equivalents» |
| Debt | Процентный долг | `LongTermDebt`, `LongTermDebtCurrent`, `LongTermDebtNoncurrent`, `ShortTermBorrowings`, `CommercialPaper` | Stock | Двойной учёт current portion; leases (OQ-13) | «Interest-bearing debt» |
| Net debt | Debt − cash | Расчёт | Stock | Отрицательное значение = net cash, это не ошибка | «Net debt» (при < 0 — «Net cash») |
| Net debt / EBITDA | Net debt ÷ EBITDA (TTM) | Расчёт | Ratio | **Undefined** при EBITDA ≤ 0 | Число или «undefined (EBITDA ≤ 0)» |
| Enterprise value (DCF) | PV(FCFF) + PV(terminal value), TV = FCFF_{N+1} / (WACC − g), WACC > g | Модель | Stock, дата оценки | ≠ equity value ≠ рыночная капитализация | «Enterprise value (DCF, model)» |
| Equity value | EV − net debt − прочие senior claims + non-operating assets | Модель | Stock | ≠ EV; ≠ market cap | «Equity value (model)» |
| Price per share | Equity value ÷ diluted shares | `WeightedAverageNumberOfDilutedSharesOutstanding` (только для справки) | — | Требует corporate actions и market data | **Не показывается в V1–V3** (D-06) |
| Margins | Величина ÷ revenue | Расчёт | Доля | 0.25 в API = 25% в UI | «EBITDA margin, %» |
| Growth | (X_t − X_{t−k}) / \|X_{t−k}\| | Расчёт | Доля | Знаменатель около нуля — growth undefined | «Revenue growth, % YoY» |

## 2. Единицы

| Правило | Пример |
|---|---|
| В API и хранилище деньги — decimal в базовых единицах валюты с явным `unit` и `currency` | `{"value": "4213587912", "unit": "currency", "currency": "USD"}` |
| Масштаб — только при отображении, с суффиксом | «USD 4.2 bn», «USD 421 m» |
| Доли в API — дроби, в UI — проценты | API `0.40` ↔ UI «40%» |
| Изменение доли — в percentage points | «Маржа выросла на 2.0 p.p.», а не «на 2%» |
| Величина интервенции всегда с единицей из перечня | `fraction_of_previous_rnd_budget`, `pp_of_revenue`, `usd`, `fraction_of_headcount`, `quarters` |
| Flow всегда с периодом | `period: {"type": "fiscal_quarter", "fy": 2022, "q": 4}` или `TTM` с датой |
| Stock всегда с датой | `as_of_date: "2022-12-31"` |
| Нельзя складывать разные частоты | Квартал + год, YTD + квартал — ошибка валидации |

## 3. Валюта

| Правило | Пример |
|---|---|
| Одна canonical currency на сценарий, ISO 4217 | `USD` (D-04) |
| Другие валюты в V1–V3 блокируются с сообщением | «Компания отчитывается в EUR. V1–V3 поддерживает только USD» |
| Конвертация (с Stage 13) — с источником курса, датой и методом (spot на дату / средний за период) | `fx: {"source": "ECB", "date": "2022-12-30", "method": "period_average"}` |
| Compare несовместимых валют блокируется | FC-09 |

## 4. Обязательные поля каждой метрики в API

`kind` (observed / forecast / simulated) · `data_origin` (empirical / synthetic) · `currency` · `unit` · `period` или `as_of_date` · `as_of` (knowledge cutoff) · `sample_method` · `source_ids` · `uncertainty_type` (none / predictive_quantiles / conditional_model_quantiles / calibrated_interval).
