# Stage 11 — Canonical XBRL finance data model

| Поле | Значение |
|---|---|
| Этап | 11 — нормализация XBRL в канонические финансовые значения |
| Дата | 2026-10-29 |
| Статус | ACCEPTED 2026-10-30 (CI run 40956130754: 7/7 задач зелёные; владелец: «Принять Stage 11») |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/11_XBRL_NORMALIZATION.md` |
| Основание | `docs/04` (minimum viable metric mapping, слой silver), `docs/09` (FinancialFact), `17_ACCEPTANCE_MATRIX` DATA-03, DATA-04, DATA-05; команда владельца 2026-10-29: «делай некст шаг, все разрешаю» |
| Решение | ADR-0018 — канонические значения из XBRL |

## 1. Scope

Type-safe pipeline из сырых Company Facts (sample Stage 10) в стандартную таблицу с понятной схемой. Новых загрузок данных нет: bulk (D-10) по-прежнему ждёт решения. Сеть использовалась только для ручного чтения 12 страниц оригинальных отчётов SEC при сверке (раздел «Manual reconciliation»).

## 2. План

| # | Подзадача | Результат |
|---|---|---|
| 1 | Contract `NormalizedValue` (contracts 0.8.0) | Строка с lineage, ревизией, качеством; правила честности в валидаторе |
| 2 | Факты и ревизии | Группы «concept, единица, период», original и latest, дубли, конфликты |
| 3 | Фискальный календарь | Годы из 10-K, имя года из `fy`, концы кварталов, 52/53 недели |
| 4 | Карта concepts | 14 метрик с иерархией кандидатов; 2 вычисляемые с формулой |
| 5 | Квартализация | Reported → YTD-разности → FY − 9M → FY − 3Q; средние и instants не производятся |
| 6 | Restatements и масштаб | Флаги `restated` и `scale_mismatch` |
| 7 | Таблицы | JSONL, CSV, schema, coverage, manifest |
| 8 | Тесты | Синтетические сценарии промпта и contract |
| 9 | Ручная сверка | 3 компании против оригинальных 10-Q и 10-K |

## 3. Отчёт этапа

### Done

- **Contract `NormalizedValue`** (contracts 0.8.0, `normalized.py`). Одна строка — метрика компании за фискальный период (Q1–Q4, FY) в одной ревизии.
  - Поля:
    - CIK; фискальный год и период; вид (duration / instant) и даты;
    - значение или причина пропуска; единица и валюта;
    - concept, метод и формула; source facts со знаками;
    - accession и дата filing, сделавшего значение известным;
    - альтернативные concepts с разницей; `original_value` у restated; качество и флаги.
  - Валидатор отклоняет строку, если:
    - значение не равно сумме источников со знаками;
    - дата знания не последняя;
    - у reported-значения не один источник, у производного меньше двух;
    - у instant-значения есть начало периода;
    - пропуск подан как «0»;
    - blocking-значение не скрыто.
  - `LineageMethod` получил `fy_minus_three_quarters`.
- **Карта concepts с иерархией** (`xbrl/concepts.py`) — 14 метрик:
  - revenue, COGS, operating income, net income, R&D, D&A, CFO, capex;
  - cash, long-term debt (итог, non-current, current), weighted diluted shares, shares outstanding.

  У каждой — кандидаты с отношением primary / equivalent / narrower / broader:
  - `ProfitLoss` broader с флагом «включает minorities»;
  - `PaymentsToAcquireProductiveAssets` broader для capex;
  - `Depreciation` narrower для D&A.

  Concept выбирается один на компанию и год. Остальные кандидаты того же периода записаны как reconciliation evidence с разницей.
- **Фискальный календарь из фактов компании:**
  - годы — периоды 350–380 дней из 10-K;
  - имя года — `fy` из собственного 10-K (годы, кончающиеся в январе, тоже покрыты);
  - концы кварталов — из YTD и квартальных периодов;
  - 53-недельный год (≥ 368 дней) и 14-недельный квартал помечаются.
- **Квартализация** внутри одного concept и единицы:
  - reported-квартал;
  - Q2 = H1 − Q1, Q3 = 9M − H1;
  - Q4 = FY − 9M, иначе FY − Q1 − Q2 − Q3.

  Q4 никогда не годовой итог: годовой итог — отдельная строка FY. Weighted-average shares не вычитаются, поэтому Q4 у них пустой с причиной. Instant-значения берутся на конец квартала, включая comparative прошлого года, и не производятся.
- **Ревизии, amendments, restatements:**
  - `original` — факт как впервые подан, `latest` — как подан последним;
  - 10-K/A и 10-Q/A дают флаг `from_amendment`;
  - если latest ≠ original — флаг `restated` и `original_value`.
- **Проверки качества:**
  - единицы: валюта отчётности или `shares`; валюта не конвертируется (флаг `non_usd`);
  - длительность периода: факты вне слотов не используются, их число записано в manifest;
  - дубли одного accession отбрасываются, конфликт значений внутри accession скрывает значение (blocking);
  - округление компонентов (`mixed_rounding`); масштаб (`scale_mismatch`, потому что `decimals` в Company Facts нет);
  - отрицательный расход и отрицательный производный квартал — флаги, значение не меняется;
  - consolidation: Company Facts содержит только факты без dimensions, значит, сегменты не попадают.
- **Вычисляемые значения:** `free_cash_flow` = CFO − capex, `ebitda` = operating income + D&A с формулой, флаги компонентов наследуются. Adjusted EBITDA не выводится: достоверной reconciliation в XBRL нет.
- **Стандартные таблицы** в `var/data/normalized/sec/` (не в git): `values.jsonl` (эталон), `values.csv`, `schema.json`, `coverage.json`, `coverage.md`, `manifest.json` с SHA-256 входных raw-файлов.
- **CLI:** `python -m multiverse_pipelines.xbrl normalize | show`; документация — `pipelines/README.md`.
- **Web:** подпись нового метода в `METHOD_LABELS`. Интерфейс реальные значения не показывает: это Stage 12+.

### Tests

Все команды запущены локально (Windows 11) 2026-10-29.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **291 passed** (40 новых: 23 нормализации, 17 contract) |
| vitest contracts / web | 4 / **200 passed** |
| contracts drift | schema 0.8.0 и TS — up to date |
| Playwright на 1440 / 768 / 390 | **529 passed, 14 skipped** (по замыслу) |
| ruff, mypy strict, import-linter | без замечаний |

Первый полный прогон gate упал на одном старом тесте: `notebook.spec.ts:135` на desktop. Импорт JSON не сработал, сообщения не было; на tablet и mobile тот же тест прошёл. Изменения этапа notebook не трогают. Повтор файла 5 раз на трёх viewport дал 180 из 180 passed, и полный gate запущен заново. Это нестабильный тест; записан в Known limitations.

Сценарии промпта. Данные синтетические, той же формы, что Company Facts:

| Требование | Тест |
|---|---|
| Q1–Q4 | reported Q1–Q3 и Q4 = FY − 9M с источниками и датой знания; Q4 ≠ FY; cash flow через YTD-разности; Q4 = FY − 3Q без 9M |
| Overlapping concepts | `Revenues` и contract revenue: evidence с разницей 0 и 20, флаг расхождения; смена concept между годами без смешивания в одном Q4; fallback, broader, minorities |
| Restatement | original 460 и latest 455 с `original_value`, Q4 latest из пересчитанного года; amendment — latest с флагом |
| Negative expense | R&D −5 сохраняется с флагом; отрицательный производный capex с флагом |
| Foreign currency | EUR остаётся EUR с флагом, без конверсии; посторонняя единица не берётся |
| 53-week year | 371-дневный год, концы кварталов, Q4 = 98 дней, флаги у Q4 и FY, но не у Q2 |
| Прочее | средние не вычитаются; instants и comparative прошлого года; пропуск ≠ 0; дубли и конфликт (blocking); метка года по 10-K; масштаб и округление; FCF и EBITDA с формулой; таблицы и coverage; CLI на архиве |
| Contract | 16 видов нечестной строки, каждый отклонён по своей причине |

### Manual reconciliation с оригинальными отчётами SEC

Источник проверки — страницы финансовой отчётности filings на sec.gov (`R*.htm`, отображение XBRL самого filing). Страницы прочитаны 2026-10-29 во встроенном браузере вручную, по одной. Сравнивается revision `original` за fiscal 2025: Q3 и 9M из 10-Q за Q3, FY из 10-K. Q4 MULTIVERSE выводит как FY − 9M: в отчётах SEC отдельного Q4 нет, поэтому сверяется арифметика.

**Texas Instruments** (10-Q `0000097476-25-000060`, 10-K `0000097476-26-000059`), $ млн:

| Метрика | Q3 в 10-Q | 9M в 10-Q | FY в 10-K | Q4 = FY − 9M | MULTIVERSE Q3 / Q4 / FY | Совпало |
|---|---|---|---|---|---|---|
| Revenue | 4 742 | 13 259 | 17 682 | 4 423 | 4 742 / 4 423 / 17 682 | ✅ |
| Cost of revenue | 2 019 | 5 648 | 7 599 | 1 951 | 2 019 / 1 951 / 7 599 | ✅ |
| R&D | 518 | 1 562 | 2 083 | 521 | 518 / 521 / 2 083 | ✅ |
| Operating profit | 1 663 | 4 550 | 6 023 | 1 473 | 1 663 / 1 473 / 6 023 | ✅ |
| Net income | 1 364 | 3 838 | 5 001 | 1 163 | 1 364 / 1 163 / 5 001 | ✅ |
| CFO | — | 4 899 | 7 153 | 2 254 | 2 190 (9M − H1) / 2 254 / 7 153 | ✅ |
| Capex | — | 3 625 | 4 550 | 925 | Q1+Q2+Q3 = 3 625 / 925 / 4 550 | ✅ |
| Depreciation | — | 1 381 | 1 918 | 537 | Q1+Q2+Q3 = 1 381 / 537 / 1 918 | ✅ |
| Diluted shares, млн | 914 | — | 913 | не выводится | 914 / — / 913 | ✅ |
| Cash, конец периода | 3 311 | — | 3 225 | — | 3 311 / 3 225 | ✅ |

**Union Pacific** (10-Q `0000100885-25-000321`, 10-K `0000100885-26-000037`), $ млн:

| Метрика | Q3 в 10-Q | 9M в 10-Q | FY в 10-K | Q4 = FY − 9M | MULTIVERSE Q3 / Q4 / FY | Совпало |
|---|---|---|---|---|---|---|
| Total operating revenues | 6 244 | 18 425 | 24 510 | 6 085 | 6 244 / 6 085 / 24 510 | ✅ |
| Depreciation | 618 | 1 841 | 2 465 | 624 | 618 / 624 / 2 465 | ✅ |
| Operating income | 2 549 | 7 445 | 9 846 | 2 401 | 2 549 / 2 401 / 9 846 | ✅ |
| Net income | 1 788 | 5 290 | 7 138 | 1 848 | 1 788 / 1 848 / 7 138 | ✅ |
| CFO | — | 7 065 | 9 290 | 2 225 | 2 522 (9M − H1) / 2 225 / 9 290 | ✅ |
| Capital investments | — | 2 792 | 3 791 | 999 | Q1+Q2+Q3 = 2 792 / 999 / 3 791 | ✅ |
| Diluted shares, млн | 593,2 | — | 595,9 | не выводится | 593,2 / — / 595,9 | ✅ |
| Баланс 31.12.2025: cash / долг в течение года / долг после года / акций | — | — | 1 266 / 1 520 / 30 294 / 593,2 млн | — | 1 266 / 1 520 / 30 294 / 593,2 | ✅ |

**AMETEK** (10-Q `0001037868-25-000077`, 10-K `0001037868-26-000016`), $ тыс.:

| Метрика | Q3 в 10-Q | 9M в 10-Q | FY в 10-K | Q4 = FY − 9M | MULTIVERSE Q3 / Q4 / FY | Совпало |
|---|---|---|---|---|---|---|
| Net sales | 1 892 641 | 5 402 668 | 7 401 116 | 1 998 448 | 1 892 641 / 1 998 448 / 7 401 116 | ✅ |
| Cost of sales | 1 206 505 | 3 455 643 | 4 733 677 | 1 278 034 | 1 206 505 / 1 278 034 / 4 733 677 | ✅ |
| Operating income | 488 380 | 1 404 835 | 1 910 317 | 505 482 | 488 380 / 505 482 / 1 910 317 | ✅ |
| Net income | 371 416 | 1 081 541 | 1 480 142 | 398 601 | 371 416 / 398 601 / 1 480 142 | ✅ |
| D&A | — | 317 146 | 422 804 | 105 658 | Q1+Q2+Q3 = 317 146 / 105 658 / 422 804 | ✅ |
| CFO | — | 1 217 499 | 1 801 763 | 584 264 | 440 865 (9M − H1) / 584 264 / 1 801 763 | ✅ |
| Additions to PP&E | — | 73 251 | 130 248 | 56 997 | Q1+Q2+Q3 = 73 251 / 56 997 / 130 248 | ✅ |
| Diluted shares, тыс. | 231 670 | — | 231 259 | не выводится | 231 670 / — / 231 259 | ✅ |

Итог: **все 75 сверенных чисел совпали** (Q3, 9M и FY из оригиналов; Q4 и YTD-кварталы — арифметика на них).

Что сверка показала сверх совпадения:

- **TXN, D&A.** Строка «Depreciation» (1 918) помечена concept `us-gaap:Depreciation`, а «Amortization of capitalized software» (81) идёт отдельно. MULTIVERSE берёт `Depreciation` с флагом `narrower_concept`, и EBITDA TXN наследует этот флаг. У Union Pacific то же самое. У AMETEK concept `DepreciationAndAmortization` равен строке отчёта.
- **UNP, выручка.** Total operating revenues (24 510) = freight (23 220) + other revenues (1 290). Contract revenue в XBRL меньше `Revenues` на ~6%, и флаг `concept_disagreement` у UNP ловит это в 2018–2020: в эти годы в filings есть оба concept.
- **Capex.** Покупка бизнесов AMETEK (933 242 тыс. в 2025) в capex не попадает: concept — `PaymentsToAcquirePropertyPlantAndEquipment`.
- **AMETEK, R&D.** В отчёте о прибылях R&D нет. Он есть только годовой (236,1 млн) в примечаниях, поэтому квартальные строки R&D пустые с причиной.

### Measured results

Нормализация sample (10 компаний, `var/data/normalized/sec/`):

| Что | Значение |
|---|---|
| Строк | **27 000** (14 метрик + 2 вычисляемые × периоды × 2 ревизии) |
| Значений / пропусков с причиной | **20 958 / 6 042** |
| Blocking (конфликт внутри filing) | 0 |
| Restated (latest ≠ original) | 875 строк latest; у половины расхождение меньше 1% (медиана 0,8%) |
| `scale_mismatch` | 5 строк latest: TXN diluted shares, 4 квартала 2009–2011 (подано, например, «1196» вместо 1 196 000 000), Stryker shares outstanding 2014 Q4 |
| `concept_disagreement` | 14 строк latest, все по выручке: Union Pacific 2018–2020 (10) и Akamai 2017–2018 (4) |
| Методы (latest) | reported 7 163, calculated 1 670, FY − 9M 853, YTD 793 |
| Время | меньше 1 с на компанию |

Coverage, последние 8 / 20 / 40 кварталов, revision latest. Полная таблица — `coverage.md`:

- revenue, operating income, net income, CFO, capex, cash, FCF и EBITDA — 8/20/40 у большинства компаний;
- исключения по revenue: Old Dominion 8/20/36, American Water Works 8/17/26 (часть лет у AWK — под concept вне карты);
- weighted diluted shares — 6/15/30 у всех действующих компаний: Q4 по замыслу не выводится;
- R&D — только TXN, Stryker, Celgene, Akamai; у остальных шести отдельного R&D нет;
- COGS нет у Union Pacific, Old Dominion и American Water Works: они не показывают cost of revenue одной строкой;
- `long_term_debt` (итог) редок: его чаще тегируют только в примечаниях к годовому отчёту. Non-current и current покрыты лучше.

### Known limitations

- **«Original» — первая XBRL-подача.** Для 2006–2008 это comparative в первых XBRL-отчётах 2009–2010, а не исходный HTML-отчёт.
- **`decimals` нет в Company Facts.** Масштаб проверяется только по расхождению ревизий. Ошибку масштаба, которая не была исправлена позже, этот способ не увидит; полная проверка требует Financial Statement and Notes data sets (`dcml`, решение D-10).
- **Карта concepts покрывает частые теги.** Часть лет American Water Works, Old Dominion до 2016 и долг Akamai (конвертируемые облигации) используют другие concepts и остаются пустыми. Расширение карты — новые кандидаты с тестом.
- **Equivalent-отношение contract revenue к `Revenues`** — допущение, и его проверяет evidence. Где расхождение больше 0,5%, стоит флаг, но значение остаётся `Revenues`.
- **D&A берётся из cash flow** и может включать амортизацию нематериальных активов или, наоборот, не включать амортизацию ПО (TXN). Определение видно по concept и флагу.
- **Point-in-time на дату знания** (какая ревизия была известна на дату X) не строится: это Stage 12. Строки уже несут `filed` и обе ревизии.
- **Нестабильный e2e:** `notebook.spec.ts` «compares revisions and blocks different cutoffs» один раз не увидел результат импорта файла на desktop. 180 повторов прошли. Причину (вероятно, событие выбора файла до готовности обработчика) стоит найти отдельно.
- **Ручная сверка** покрывает 3 компании и один год (75 чисел). Остальное проверено арифметикой contract и тестами, а не глазами.

### Decisions

- Одна строка — метрика × фискальный период × ревизия; эталон — JSONL, CSV — для удобства (ADR-0018).
- Concept выбирается на год; производные значения не смешивают concepts.
- Q4 — производный квартал с методом и источниками; годовой итог — отдельная строка FY.
- Restatement — сравнение ревизий на уровне канонического значения: так ловятся и пересчёт, и смена concept, и ошибка масштаба.
- Adjusted EBITDA не выводится; EBITDA — operating income + D&A с формулой и флагами.

### Next prompt

`12_POINT_IN_TIME_WAREHOUSE.md` — только по команде владельца. Ему хватает этих таблиц: новых загрузок не нужно.

## 4. Acceptance

| Критерий промпта 11 | Evidence | Статус |
|---|---|---|
| Type-safe pipeline усложнённой нормализации на raw SEC data | `multiverse_pipelines.xbrl`, contract `NormalizedValue`, mypy strict | ✅ |
| Похожие теги не сведены без hierarchy и reconciliation evidence | Отношения кандидатов, один concept на год, `alternatives` с разницей, флаг расхождения (UNP) | ✅ |
| Concept mapping: revenue, COGS, operating income, net income, R&D, D&A, CFO, CAPEX, cash, debt, shares | 14 метрик в `concepts.py` | ✅ |
| Проверены units, currencies, decimals, period duration, segments, consolidation, fiscal calendars, YTD-to-quarter, Q4, amendments, duplicate accessions | Раздел «Done», тесты; decimals — косвенно (`scale_mismatch`, ограничение записано) | ✅ |
| Q4 не используется как annual total | Отдельные строки Q4 и FY; тест `test_q4_is_never_the_annual_total` | ✅ |
| Каждое число: source tag, filing date, CIK, accession, method, revision, quality | Поля `NormalizedValue`, валидатор | ✅ |
| Standardized tabular format с clear schema | `values.jsonl`, `values.csv`, `schema.json` | ✅ |
| Missing не заменяется нулём | Contract отклоняет «0» вместо пропуска; 6 042 пропуска с причиной | ✅ |
| Adjusted EBITDA только при достоверной reconciliation | Не выводится; EBITDA не adjusted, с формулой | ✅ |
| Balance sheet instant values | Instants на конец квартала, не производятся (тест) | ✅ |
| Fixtures: Q1–Q4, overlapping concepts, restatement, negative expense, foreign currency, 53-week year | `test_xbrl_normalize.py` | ✅ |
| Manual reconciliation 2–3 компаний с original SEC filing facts | 3 компании, 75 чисел, все совпали | ✅ |
| Реальную модель не обучать, остановиться | Обучения нет; стоп после отчёта | ✅ |

`17_ACCEPTANCE_MATRIX`:

- **DATA-03** (квартализация и restatements, unit tests) — ✅;
- **DATA-04** (валюта, масштаб, карта concepts, lineage record) — ✅;
- **DATA-05** (source coverage transparent, generated data card) — ✅: `coverage.md` генерируется при каждой нормализации.
