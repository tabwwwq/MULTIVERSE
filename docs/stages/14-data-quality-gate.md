# Stage 14 — Gate B: financial dataset audit

| Поле | Значение |
|---|---|
| Этап | 14 — аудит финансового датасета, Gate B |
| Дата | 2026-10-30 |
| Статус | REVIEW (вердикт Gate B: **blocked**, честный отчёт) |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/14_DATA_QUALITY_GATE.md` |
| Основание | `docs/11` (Gate 2 SEC PIT dataset QA, dataset quality tests, honest metrics), `docs/14` (Exit B), `docs/06` (окно истории 12–24, горизонты 1/4/8/12/20), `17_ACCEPTANCE_MATRIX` DATA-01…DATA-05; команда владельца 2026-10-30: «Делай Stage 14» |
| Решение | ADR-0021 — Gate B |

## 1. Scope

Исчерпывающий аудит датасета Stage 10–13 без новых моделей:
- data card и визуальный отчёт о покрытии;
- checklist промпта;
- фактические размеры в usable examples;
- решения об исключении;
- доказательство отсутствия утечки;
- 10 ручных сверок с оригиналами SEC;
- manifest с hash.

Новых загрузок нет. Сеть использовалась только для ручного чтения 18 страниц filings на sec.gov при сверке: 7 `FilingSummary.xml` и 11 страниц отчётов.

## 2. План

| # | Подзадача | Результат |
|---|---|---|
| 1 | Contract `GateManifest`, `GateCheck` (0.11.0) | Статусы pass / warning / fail / blocked; вердикт следует из проверок |
| 2 | Checklist промпта | 15 проверок с измерениями и конкретными случаями |
| 3 | Usable examples | Счёт по H = 8/12/20 и h = 1/4/8/12/20, hash таблицы |
| 4 | Leakage proof | Пересборка из прошлого на 3 cutoff, сравнение snapshot и macro join |
| 5 | Ручная сверка | 10 производных значений против страниц filings, файл-данные |
| 6 | Data card и coverage report | Markdown и HTML с графиками по компании, сектору, метрике, году, валюте, стандарту |
| 7 | Решения | Включение по метрикам, причины |

## 3. Отчёт этапа

### Done

- **Модуль `multiverse_pipelines.audit`**, команда `run`. Пишет `var/data/gate/` (не в git):
  - `manifest.json` — `GateManifest`: компании и решения, examples, все проверки, вердикт, hash;
  - `examples.csv` — каждый trainable example;
  - `data-card.md`;
  - `coverage.html`.

  Код выхода: 0 — gate прошёл, 3 — blocked (отчёт пишется в обоих случаях), 2 — gate не может работать.
- **Contracts 0.11.0** (`quality.py`):
  - `GateCheck` — не прошедшая проверка обязана показать находки, не больше 40;
  - `ExampleCount`, `CompanyDecision` — исключённая компания говорит почему;
  - `GateManifest` — назван hash; вердикт `blocked` ровно при `fail` / `blocked`; при warnings — `passed_with_warnings`; view `latest` запрещён.
- **15 проверок checklist** (`audit/checks.py`) и **4 проверки gate** (`audit/run.py`: leakage, сверка, размер, макро).
- **Usable examples** (`audit/examples.py`):
  - история — лаги 1…H с выручкой в PIT panel на origin, только то, что было public;
  - цель — выручка через h кварталов как первый выпуск к data cutoff;
  - лаг 0 не входит в историю никогда.
- **Ручная сверка** (`data/reconciliation/stage-14-manual.json`) — 10 значений Q4 = FY − 9M у пяти компаний, которые Stage 11 не сверял. Gate перепроверяет их на каждом запуске.
- **Data card и coverage report** (`audit/report.py`):
  - тепловая карта компания × год;
  - покрытие по метрикам;
  - examples по истории и горизонту;
  - секторы, валюта и стандарт отчётности;
  - все проверки со статусом.
- Однометричная panel фильтруется в запросе (`build_panel`): gate строит panel на каждый из 67 origins.

### Tests

Все команды запущены локально (Windows 11) 2026-10-30.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **392 passed** (17 новых: 7 audit, 10 contract) |
| vitest contracts / web | 4 / **200 passed** |
| contracts drift | schema 0.11.0 и TS — up to date |
| Playwright на 1440 / 768 / 390 | **529 passed, 14 skipped** (по замыслу); web этапом не менялся |
| ruff, mypy strict, import-linter, secret scan | без замечаний |

После полного gate исправлен только HTML coverage report: дата cutoff по Eastern вместо UTC; полосы таблицей вместо SVG, у которого шрифт масштабировался и обрезался; выравнивание текстовых колонок. После этого повторены `npm run check:py` (392 passed) и `contracts:check` (up to date). Переполнения по ширине нет на 1440 / 768 / 390 в светлой и тёмной теме.

`pipelines/tests/test_audit.py` — синтетический эмитент за семь лет:

| Требование | Тест |
|---|---|
| Examples без утечки | История — только public кварталы (первый origin с 8 кварталами — 31.03.2014, потому что Q4 2013 вышел в феврале 2014); цель — через h кварталов и выпущена к cutoff (ничего после Q4 2017 при cutoff 30.06.2018); hash не зависит от порядка; H = 20 и h = 20 не помещаются — 0 |
| Чистые данные | Дубли, валюта, скачки, cumulative cash flow, пробелы и revisions — pass; survivorship — warning |
| Скачок | Выручка Q2 2016 ×3 найдена и названа |
| Сверка | 10 совпадений — pass; одно расхождение — fail с MISMATCH; 9 записей или нет файла — blocked |
| Честная блокировка | 1 компания — blocked; 40 компаний и 1 200 examples — pass; нет макро — blocked |
| Команда | Сборка PIT из archive, gate с leakage proof и сверкой: код 3 (blocked), все четыре файла, manifest назван hash, CSS без незакрытых блоков, data card говорит про usable examples |

`packages/contracts/python/tests/test_quality.py`:
- не прошедшая проверка без находок и больше 40 находок отклоняются;
- исключённая компания без причины отклоняется;
- manifest не назван hash, origins назад, вердикт не по проверкам, warnings при `passed`, причины отсутствуют, view `latest` — всё отклоняется.

### Ручная сверка с оригинальными отчётами SEC

Страницы отчётов (`R*.htm`, собственный XBRL-рендер filing на sec.gov) открыты вручную 2026-10-30 во встроенном браузере: сначала `FilingSummary.xml`, потом нужная страница. Сверяется revision `original` (первый выпуск): Q4 = FY из 10-K минус 9M из 10-Q за Q3.

| Компания | Метрика | FY в 10-K | 9M в 10-Q | Q4 по отчётам | MULTIVERSE | Совпало |
|---|---|---|---|---|---|---|
| Stryker, FY2024 ($ млн) | CFO | 4 242 | 2 311 | 1 931 | 1 931 | ✅ |
| Stryker, FY2024 ($ млн) | Capex (PP&E) | 755 | 489 | 266 | 266 | ✅ |
| Old Dominion, FY2024 ($ тыс.) | Revenue | 5 814 810 | 4 428 981 | 1 385 829 | 1 385 829 | ✅ |
| Old Dominion, FY2024 ($ тыс.) | Operating income | 1 543 998 | 1 209 978 | 334 020 | 334 020 | ✅ |
| Waste Management, FY2024 ($ млн) | CFO | 5 390 | 3 879 | 1 511 | 1 511 | ✅ |
| Waste Management, FY2024 ($ млн) | Capex | 3 231 | 2 116 | 1 115 | 1 115 | ✅ |
| Akamai, FY2024 ($ тыс.) | CFO | 1 519 171 | 1 175 383 | 343 788 | 343 788 | ✅ |
| Akamai, FY2024 ($ тыс.) | Capex (PP&E) | 390 433 | 297 548 | 92 885 | 92 885 | ✅ |
| Celgene, FY2018 ($ млн) | Operating income | 5 191 | 3 384 | 1 807 | 1 807 | ✅ |
| Celgene, FY2018 ($ млн) | R&D | 5 673 | 4 535 | 1 138 | 1 138 | ✅ |

**10 из 10.** Accession и страницы — в файле сверки. Вместе со Stage 11 (75 значений) вручную сверено 85 чисел в 8 компаниях из 10.

Наблюдение из сверки: у Akamai «capex» в смысле компании включает капитализацию софта (294 834 тыс. за 2024 год, отдельная строка). Наш `capex` — только PP&E. Это записано в Known limitations.

### Measured results

Data cutoff 2026-10-28, view vintage, origins 2010Q1–2026Q3. Dataset `gate-b-20261028-a25e24a3b38e` (тот же id на двух запусках); PIT snapshot `pit-20261028-e698b2f9a4d6`. Время gate — 2 мин 41 с.

**Вердикт Gate B: `blocked`.** Механика данных проходит, а достаточность данных — нет:

| Статус | Проверки |
|---|---|
| pass (6) | future revisions, duplicated company-quarter, currency/FX, unrealistic jumps, **leakage proof**, **manual reconciliation 10/10** |
| warning (11) | concept drift, survivor-only sample, lost bankruptcies, missingness, revenue gaps, negative/undefined ratios, outliers, cumulative cash flow, misidentified CAPEX, reported vs calculated EBITDA, source conflicts |
| blocked (2) | **usable sample size**, **macro data** |

**Фактический размер (usable, не файлы):**

| Что | Значение |
|---|---|
| Компании в sample | 10 (34 raw-файла Stage 10) |
| Компании с ≥ 8 / 12 / 20 кварталами выручки | 10 / 10 / 10 (≥ 40 — 9, ≥ 60 — 7) |
| Company-quarters с выручкой | 611 |
| Ячейки panel 10 × 69 кварталов × 16 метрик / со значением | 11 040 / 8 648 |
| Trainable examples, всего строк (все H и h) | 5 864 |

Trainable examples (цель — выручка):

| История H \ горизонт h | 1 | 4 | 8 | 12 | 20 |
|---|---|---|---|---|---|
| 8 | 516 | 484 | 446 | 413 | 348 |
| 12 | 477 | **447** | 409 | 376 | 315 |
| 20 | 392 | 365 | 332 | 303 | 241 |

Порог gate (ADR-0021): ≥ 30 компаний и ≥ 1 000 examples при H = 12, h = 4. Есть 10 компаний и 447 examples.

**Missingness** там, где отчёт был public (658 company-quarters на метрику):

| Метрика | Нет значения |
|---|---|
| operating income, net income, CFO, cash | 0,0% |
| D&A, EBITDA | 0,3% |
| capex, FCF | 0,6% |
| revenue | 7,1% |
| long-term debt non-current | 18,4% |
| debt current | 20,1% |
| diluted shares | 22,9% (Q4 средних не выводится) |
| COGS | 36,5% |
| shares outstanding | 43,9% |
| R&D | 62,6% |
| long-term debt (итог) | 72,3% |

**Находки проверок:**
- **Leakage proof:** snapshot PIT на 2013-06-30, 2019-12-31, 2025-12-31 и macro join на синтетике побайтно совпали с полным archive. Future revisions: 1 104 значения пересмотрены после первого выпуска, ни один не доходит до раннего origin.
- **Concept drift:** 37 смен concept между годами (ASC 606 в 2016–2018, CFO continuing operations у Hubbell, TXN, UNP); 14 значений с `concept_disagreement`.
- **Revenue gaps:** American Water Works — 16 кварталов без выручки (2015Q3 и далее, concept вне карты), AMETEK — 1 (2021Q4).
- **Cumulative cash flow:** 316 company-years проверено; Q4, равного году, нет нигде; у Waste Management в 8 годах сумма кварталов CFO/capex расходится с годом (кварталы и год поданы в разных vintages).
- **Outliers:** 14 log-изменений с robust z > 6 — кризис 2008–2009 у TXN и AMETEK, списания Celgene 2015 и 2018, Akamai 2017Q4.
- **Скачков выручки больше 50% нет.**
- **Ratios:** 142 входа без положительной выручки (в основном пробел AWK); отрицательный capex один раз — TXN Q3 2008 (−197 млн, выведен из YTD двух разных vintages).
- **CAPEX:** `PaymentsToAcquirePropertyPlantAndEquipment` в 123 company-years, broader `PaymentsToAcquireProductiveAssets` в 57 (Hubbell, Waste Management — их строка «Capital expenditures»).
- **EBITDA:** reported EBITDA в US GAAP XBRL нет, сравнивать не с чем. 308 значений calculated EBITDA имеют narrower D&A.
- **Source conflicts:** `mixed_vintage` 116, `scale_mismatch` 5, `concept_disagreement` 14, alerts `quarters_do_not_sum` 10, blocking alerts 0.
- **Survivorship и банкротства:** 9 из 10 компаний сегодня листингуются; банкротств (8-K item 1.03) 0; одна deregistration (Celgene, поглощение).

**Где данных не хватает и кого исключать.** Для датасета выручки не исключается никто: все 10 имеют 12+ кварталов. Celgene даёт origins только до deregistration в декабре 2019. По метрикам:

| Метрика | Компаний с 12+ кварталами | Исключить из экспериментов с метрикой |
|---|---|---|
| revenue, operating income, net income, D&A, CFO, capex, cash, diluted shares, FCF, EBITDA | 10 | — |
| debt current | 9 | Akamai |
| long-term debt non-current | 8 | Celgene, Akamai |
| shares outstanding | 8 | TXN, Celgene |
| COGS | 7 | Union Pacific, Old Dominion, American Water Works |
| long-term debt (итог) | 6 | Stryker, Waste Management, Old Dominion, Akamai |
| R&D | 4 | Hubbell, Union Pacific, Waste Management, Old Dominion, AMETEK, American Water Works |

### Known limitations

- **Gate B blocked по размеру.** 10 компаний и 447 examples (H = 12, h = 4) не хватает для нейросети и для любых утверждений о компаниях вообще. Снять блокировку можно bulk-файлами SEC (решение D-10).
- **Gate B blocked по макро.** Реальных макроданных нет до D-11 (ключ FRED) и D-12.
- **Порог 30 компаний / 1 000 examples — предложение** (ADR-0021), в docs его нет. Это константа, её можно пересмотреть.
- **Один сектор — не больше одной компании:** секторные эффекты не учатся.
- **Capex — только PP&E,** без капитализированного софта (Akamai 2024: 294,8 млн отдельно) и без «productive assets», где компания тегирует так.
- **Сверка покрывает 8 компаний из 10** (Stage 11 + Stage 14) и 85 чисел; остальное проверено арифметикой contract и тестами.
- **Outliers и jumps** — warning, а не fail: кризис и списания реальны. Модели нужен их список, а не удаление.
- **Счёт examples — только для выручки.** Для других целей он пересчитывается той же функцией.

### Decisions

- Размер датасета — в usable examples; hash таблицы examples называет датасет (ADR-0021).
- `blocked` — честный статус; вердикт выводится из проверок, а не объявляется.
- Ручная сверка хранится как данные и перепроверяется на каждом запуске.
- Исключения — по метрикам, а не по компаниям целиком.

### Next prompt

`15_BASELINE_FORECASTING.md` — только по команде владельца. Gate B blocked, поэтому Stage 15 на sample возможен только как пилот, помеченный пилотом, и только если владелец так решит. Для полноценного Stage 15 нужны D-10 (полная вселенная SEC) и D-11/D-12 (макроэкономика).

## 4. Acceptance

| Критерий промпта 14 | Evidence | Статус |
|---|---|---|
| Exhaustive audit, никакой новой нейросети | 19 проверок; моделей нет | ✅ |
| Data card | `data-card.md` | ✅ |
| Visual coverage report по company, sector, metric, fiscal year, currency, reporting standard | `coverage.html`, скриншоты `docs/stages/14-screens/` | ✅ |
| Canonical derived amounts сравнены с SEC originals | 10 ручных сверок Q4 = FY − 9M, все совпали; перепроверяются автоматически | ✅ |
| Audit checklist (15 пунктов промпта) | `audit/checks.py`, раздел Measured results | ✅ |
| Firms с 8/12/20 кварталами, trainable examples по горизонтам, missingness %, effective size, source conflicts | Раздел Measured results, `manifest.json` | ✅ |
| Quality flags, где не хватает данных, кого исключить | Проверки со статусами; таблица исключений по метрикам | ✅ |
| Tests green или честный blocked report | Тесты зелёные; Gate B **blocked**: размер выборки и макро | ✅ (blocked report) |
| Dataset manifest with hash | `gate-b-20261028-a25e24a3b38e`, SHA-256 таблицы examples | ✅ |
| Leakage proof | 3 cutoff PIT + macro join, побайтно идентичны | ✅ |
| 10 manual source reconciliations | 10 из 10 | ✅ |
| Coverage chart | Тепловая карта, график по метрикам, таблица examples | ✅ |
| Не заявлять «большие данные» по числу файлов | Размер дан в usable examples (447 при H = 12, h = 4), рядом 34 файла | ✅ |

`17_ACCEPTANCE_MATRIX`:
- **DATA-01…DATA-04** подтверждены повторно: leakage proof, сверка;
- **DATA-05** — data card и coverage report.

**Exit B** (docs/14): для SEC-части выполнено (идентичный snapshot без будущих filings). Для датасета в целом — нет, пока не приняты D-10, D-11 и D-12.
