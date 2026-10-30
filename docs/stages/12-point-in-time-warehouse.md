# Stage 12 — As-of warehouse и reproducible snapshots

| Поле | Значение |
|---|---|
| Этап | 12 — point-in-time warehouse |
| Дата | 2026-10-30 |
| Статус | ACCEPTED 2026-10-30 (CI run 40981425041: 7/7 задач зелёные; владелец: «Принять Stage 12») |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/12_POINT_IN_TIME_WAREHOUSE.md` |
| Основание | `docs/04` (слой Gold/PIT), `docs/09` (FeatureSnapshot), `docs/11` (PIT-тесты, honest metrics), `17_ACCEPTANCE_MATRIX` DATA-02, DATA-03, DATA-05; команда владельца 2026-10-30: «Делай Stage 12» |
| Решение | ADR-0019 — point-in-time warehouse |

## 1. Scope

Point-in-time слой поверх нормализации Stage 11. На любую дату он отвечает: что было public в SEC и какие значения из этого следуют. Новых загрузок данных нет: используется sample Stage 10 (решение D-09). Bulk (D-10), FRED (D-11) и ECB/World Bank (D-12) по-прежнему ждут решения владельца.

## 2. План

| # | Подзадача | Результат |
|---|---|---|
| 1 | Часы EDGAR | Момент public по времени приёма, не раньше даты filing (US Eastern); cutoff-дата — конец дня |
| 2 | Contracts 0.9.0 | `PitValue`, `PanelCell`, `ChronologyAlert`, `PitSnapshotManifest`, `EntityAttribute` |
| 3 | Интервалы знания | Нормализатор Stage 11 на каждый момент filing; интервалы `known_from … known_to` с причиной смены |
| 4 | `as_of(company, metric, timestamp)` | Виды vintage / original / latest; history поправок |
| 5 | Consistent quarterly panel | Компания × календарный квартал × метрика, полный, с mask и состояниями |
| 6 | Feature mask semantics | Mask только у observed / derived; features только из ячеек |
| 7 | Snapshot hash и lineage export | Канонические JSON lines, SHA-256, lineage до raw-файла |
| 8 | Effective dates | Название по `formerNames`; тикер, биржа, SIC — только с момента наблюдения; deregistration |
| 9 | Broken chronology alerts | 9 видов alerts |
| 10 | Coverage dashboard | HTML / Markdown / JSON с явными счётами firm-quarter × metric |
| 11 | Adversarial fixtures и leakage-тесты | Сценарии промпта; проверка на реальном sample |

## 3. Отчёт этапа

### Done

- **Часы EDGAR** (`pit/clock.py`).
  - Filing public с момента приёма EDGAR, но не раньше начала своей даты filing по US Eastern.
  - Вечерний filing, датированный следующим рабочим днём, относится к этому дню. Пример из sample: 10-K American Water Works за 2010 принят в пятницу 25.02.2011 в 20:58 ET, дата filing — понедельник 28.02.2011, public с 00:00 ET 28.02.
  - Если известна только дата (filings 1994–2002, полночь), filing public с конца дня. Так же для filing, которого нет в индексе.
  - Cutoff-дата — конец дня по Eastern. Время без offset отклоняется.
  - `acceptanceDateTime` в submissions — UTC. Проверено на всех 26 678 filings sample: принятые до своей даты filing приняты после 17:30 ET; периодические отчёты в день filing — до 17:30 (кроме 4).
  - Правила летнего времени США (1987–2006, с 2007) написаны в коде: на Windows в стандартной библиотеке нет базы часовых поясов.
- **Contracts 0.9.0** (`pit.py`):
  - `PitValue` — значение Stage 11 с интервалом `known_from … known_to`, причиной смены и моментом public каждого источника. Валидатор не даёт значению быть известным раньше своих источников;
  - `PanelCell` — ячейка panel. Mask = 1 ровно у observed и derived, значение есть ровно при mask = 1, у пустой ячейки всегда причина;
  - `ChronologyAlert`;
  - `PitSnapshotManifest` — отклоняет view `latest`; имя snapshot равно его hash; panel полный (компании × кварталы × метрики); snapshot сделан после cutoff;
  - `EntityAttribute` — атрибут компании с датами действия;
  - флаг `mixed_vintage` в `QualityFlag`.
- **Интервалы знания** (`pit/vintages.py`). Нормализатор Stage 11 запускается на каждый момент, когда filing компании стал public (42–72 раза на компанию), и только на фактах, public к этому моменту.
  - Соседние запуски сравниваются. Каждое изменение открывает интервал с причиной: `first_known`, `value_filled`, `value_revised`, `confirmed`, `requalified`, `value_withdrawn`.
  - Поэтому as-of по построению равен нормализации того, что было public: календарь, concept года, валюта и производные кварталы — только из прошлого.
  - Строки периодов, которые ещё не закончились, хранятся; запрос показывает только закончившиеся.
  - Estimates (факт кончается после своего filing) не входят ни в один запуск.
- **Provisional fiscal year** (опция календаря Stage 11). После последнего 10-K, как только вышел 10-Q следующего года, календарь добавляет provisional год. Конец года проецируется: снова конец месяца или +52 недели. Выход Stage 11 не меняется.
- **Флаг `mixed_vintage`** (нормализатор). Производное latest-значение складывает пересмотренную часть со старой, поданной до пересмотра.
  - Пример: Hubbell в 10-K за 2021 пересчитал 2019 год под продажу бизнеса, а кварталы 2019 года никто не пересчитал. FY − 9M дал бы Q4 на разных основаниях.
  - Значение сохраняется с warning. На sample — 116 строк latest.
- **`as_of(company, metric, timestamp)`** — `Warehouse.as_of` и команда `as-of`. Три вида:
  - `vintage` — последнее поданное до cutoff, default для features;
  - `original` — первое поданное до cutoff;
  - `latest` — hindsight, только для анализа revisions.

  `history` показывает все ответы одного периода во времени, то есть его поправки. `entity` — название, тикер, биржа, SIC и статус на момент.
- **Consistent quarterly panel** (`pit/panel.py`).
  - Строка — календарный квартал. Фискальный квартал относится к ближайшему концу календарного квартала: квартал, кончающийся 2 января, — это Q4.
  - Panel полный: каждая компания × каждый из последних N кварталов × 16 метрик.
  - Состояния: observed, derived, not_yet_filed, not_reported, blocked, inactive, not_covered.
  - `inactive` — после Form 15 без последующих отчётов, когда отчёт за первый квартал после Form 15 уже просрочен (больше 90 дней). Form 15 бывает и для одного класса бумаг.
  - `check_point_in_time` отказывает panel, если в ней есть что-то не public на cutoff. View `latest` panel не принимает.
- **Feature mask semantics** (`pit/features.py`): `ttm_<flow>` (сумма четырёх кварталов) для 10 потоков и `yoy_<flow>` для revenue, operating income, CFO.
  - Функции получают только ячейки panel.
  - Mask распространяется. Рост от нулевой или отрицательной базы не считается.
- **Snapshot** (`pit/snapshot.py`, команда `snapshot`).
  - Канонические JSON lines: header, компании на cutoff (название, тикер, SIC, статус или причина, почему неизвестно), все ячейки. Имя — `pit-<дата>-<12 hex SHA-256>`.
  - Рядом `panel.csv`, `features.csv`, `lineage.jsonl` (у каждого значения source facts, accession, момент public, точность времени, URL filing на sec.gov, SHA-256 raw-файла) и `manifest.json`.
  - Cutoff позже момента скачивания archive отклоняется: принятый в промежутке filing отсутствовал бы.
- **Effective dates**:
  - название — по `formerNames` с датами, например Old Dominion до 21.08.2019 «OLD DOMINION FREIGHT LINE INC/VA»;
  - тикер, биржа и SIC в submissions только текущие. Они действуют с момента наблюдения (29.10.2026) и назад не распространяются;
  - `resolve_ticker` находит компанию по тикеру на дату (тикер может перейти к другой).
- **Broken chronology alerts** (`pit/alerts.py` и `vintages.fact_alerts`): `period_after_filing` (blocking), `filing_date_mismatch`, `accepted_after_filing_date`, `missing_acceptance`, `amendment_before_original`, `report_out_of_order`, `late_report`, `quarters_do_not_sum`, `deregistration`.
- **Coverage dashboard** (`pit/coverage.py`, команда `coverage`): `coverage.html`, `.md`, `.json`. Разделы:
  - счёт firm-quarter × метрика по состояниям;
  - то же по компаниям;
  - сетка компания × квартал;
  - покрытие на каждый конец года 2009–2026;
  - revisions по метрикам;
  - alerts.
- **Хранилище** — SQLite из стандартной библиотеки (`var/data/pit/warehouse.sqlite`, не в git). Компании нормализуются параллельно.
- **`leakage-check`** пересобирает warehouse только из фактов и filings, public на cutoff (как будто archive скачан тогда), и сравнивает hash snapshot с полным archive.

### Tests

Все команды запущены локально (Windows 11) 2026-10-30.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **345 passed** (54 новых: 20 warehouse, 19 часы / календарь / features, 15 contract) |
| vitest contracts / web | 4 / **200 passed** |
| contracts drift | schema 0.9.0 и TS — up to date |
| Playwright на 1440 / 768 / 390 | **529 passed, 14 skipped** (по замыслу); web-код этапом не менялся |
| ruff, mypy strict, import-linter | без замечаний |

Adversarial fixtures промпта (`pipelines/tests/test_pit_warehouse.py`). Компании синтетические; файлы той же формы, что Company Facts и submissions:

| Сценарий промпта | Что проверено |
|---|---|
| Значение 2020Q4 опубликовано только в 2021 | На 31.12.2020 и в 16:29:59 ET 11.02.2021 Q4 `not_yet_filed`, FY пуст; с 16:30:00 (приём 10-K) Q4 = FY − 9M = 290, `known_from` = время приёма |
| Поздний 10-K amendment меняет старое значение | Q4 2020: пусто → 290 (`value_filled`) → 270 после 10-K/A (`value_revised`, `mixed_vintage`, restated) → 280 после 10-Q следующего года, пересчитавшего 9M (флаг снят) → 280 `confirmed` следующим 10-K; FY 1100 до 15.06.2021 и 1080 после; original остаётся 290 / 1100; latest = 280 на любую дату |
| Annual cumulative CFO vs Q4 | CFO подан только с начала года: Q2 = H1 − Q1 = 80, Q3 = 90, Q4 = FY − 9M = 100 ≠ FY 340; TTM = 345 из четырёх кварталов; TTM с неподанным кварталом замаскирован |
| Delisted company | Form 25 и Form 15 после Q3 2019: на 15.02.2020 Q4 2019 `not_yet_filed` (отчёт ещё не просрочен); на 30.06.2020 Q3 2019 = 103, Q4 2019 – Q2 2020 `inactive`; компания остаётся в panel (4 × 16 ячеек) |
| Missing R&D | Все ячейки R&D `not_reported` или `not_yet_filed`, значение пусто, mask 0, TTM замаскирован — нигде не 0 |
| Fiscal 53-week | FY2020 2019-12-29…2021-01-02: Q4 = 98 дней = 1400, флаг 53 недель, календарный квартал 2020Q4; 10-K принят на 4 дня позже даты filing — public с приёма, alert |
| Renamed ticker | ALP → ALPX с 01.06.2020, ALP у другой компании с 01.03.2022: `resolve_ticker` по дате; текущий тикер из submissions неизвестен до даты наблюдения |
| Cutoff 2021-12-31 и filing 2022 | 10-Q/A принят 31.12.2021 в 18:10 ET, датирован 03.01.2022: на 31.12 Q3 = 320, на 03.01 — 325 |
| Estimate в 10-K | Выручка «за 2021 год» в 10-K за 2020 не входит ни в один вид; blocking alert `period_after_filing` |
| Leakage | As-of равен нормализации фактов, public в каждый момент знания и за 1 мкс до него (3 компании); поздние filings переписывают прошлое (999 999 999, отрицательный CFO, новый R&D, Form 15), но snapshot и features на 31.12.2021 бит-в-бит те же; сборка «скачано на cutoff» даёт тот же hash; panel с значением позже cutoff отклоняется |
| Прочее | Provisional год; alerts индекса; названия по `formerNames`; файлы snapshot и lineage; cutoff позже скачивания отклоняется; все команды CLI на archive |

`pipelines/tests/test_pit_clock.py`: переходы летнего времени 2005 и 2021 года, границы дня, правила момента public, разбор cutoff, порядок stamp, индекс filings и Form 15 одного класса бумаг, ближайший календарный квартал, окно panel, TTM и YoY с mask.

`packages/contracts/python/tests/test_pit.py`: значение известно раньше источника; ячейка с mask без значения или значение без mask; пустая ячейка без причины или с «0»; snapshot в виде latest, с чужим hash, неполный, сделанный до cutoff.

### Measured results

Sample Stage 10: 10 компаний, `var/data/pit/` (не в git). Машина — Windows 11, 8 ядер.

**Сборка warehouse:**

| Что | Значение |
|---|---|
| Моменты знания (filings с фактами) | 42–72 на компанию, 663 всего |
| Интервалы знания (`PitValue`) | **70 934** |
| Полная сборка с нуля | около 50 с (48,5–52,2 с в трёх прогонах) |
| Estimates, не вошедшие ни в один вид | 42 факта, все вне карты метрик (будущая амортизация, ожидаемые взносы и т. п.) |
| Причины интервалов (latest) | first_known 14 250, value_filled 7 833, confirmed 16 067, requalified 4 591, value_revised **1 104** |
| Причины интервалов (original) | value_revised 82: 53 — смена concept года, 11 — Q4 позже подан напрямую |
| `mixed_vintage` у текущих значений | 116 |
| Chronology alerts | 20: `quarters_do_not_sum` 10 (warning), `late_report` 9 (info, 1990-е), `deregistration` 1 (Celgene) |

Время приёма: 25 094 filings с точным временем, 317 вечерних с датой следующего дня, 1 267 только с датой (1994–2002).

**Правило промпта на реальных данных (cutoff 2021-12-31, 20 кварталов, vintage):**

| Что | Значение |
|---|---|
| Snapshot | `pit-20211231-d082c5ff34e0` |
| Ячеек | 3 200 = 10 компаний × 20 кварталов × 16 метрик |
| Состояния | observed 1 646, derived 781, not_yet_filed 144, not_reported 485, inactive 144 (Celgene) |
| Источников с датой filing 2022 и позже | **0**; самый поздний источник подан 08.11.2021 |
| Features | 2 600, из них с mask 1 777 |
| Original-view snapshot | `pit-20211231-9f1d3b29a506`; значение отличается от vintage в 98 ячейках |

Примеры:
- TXN, выручка Q4 2021: на 31.12.2021 пусто (`not_yet_filed`), с 04.02.2022 12:34 ET (приём 10-K) — 4 832 млн, FY — 18 344 млн.
- Hubbell, выручка за 2019 год: vintage 4 591,0 млн до 11.02.2022, затем 3 946,6 млн (`restated`, пересчёт в 10-K за 2021 год). Original остаётся 4 591,0 млн.

**Воспроизводимость и отсутствие утечки:**

| Проверка | Результат |
|---|---|
| Тот же snapshot дважды | identical bytes |
| Новая сборка warehouse с нуля → snapshot 2021-12-31 | тот же id |
| `leakage-check`: сборка только из того, что было public на cutoff, против полного archive | **8 из 8 identical** |

| Cutoff | Snapshot | Ячеек с mask из 3 200 | Время проверки |
|---|---|---|---|
| 2010-12-31 | `pit-20101231-91025f8f30d9` | 764 | 12 с |
| 2013-06-30 | `pit-20130630-c7b6e81d0934` | 2 235 | 15 с |
| 2016-12-31 | `pit-20161231-fb20c45f4ef5` | 2 494 | 20 с |
| 2019-12-31 | `pit-20191231-f6cd29fac996` | 2 534 | 30 с |
| 2021-12-31 | `pit-20211231-d082c5ff34e0` | 2 427 | 36 с |
| 2023-12-31 | `pit-20231231-e90371f89653` | 2 298 | 43 с |
| 2025-12-31 | `pit-20251231-c2ac3d09102d` | 2 261 | 53 с |
| 2026-09-30 | `pit-20260930-75838f0de254` | 2 258 | 58 с |

**Coverage на 2026-10-28** (последние 20 кварталов, vintage, snapshot `pit-20261028-7f9d62faf498`; скриншоты — `docs/stages/12-screens/`). Ячеек с значением — 2 329 из 3 200 (72,8%). Firm-quarters с значением по метрикам (из 200):

| Метрика | С значением | Not yet filed | Not reported | Inactive |
|---|---|---|---|---|
| revenue | 172 | 4 | 4 | 20 |
| cogs | 117 | 4 | 59 | 20 |
| operating_income, net_income, D&A, CFO, capex, cash, FCF, EBITDA | 176 каждая | 4 | 0 | 20 |
| rnd | 58 | 4 | 118 | 20 |
| long_term_debt | 42 | 4 | 134 | 20 |
| long_term_debt_noncurrent, debt_current | 157 каждая | 4 | 19 | 20 |
| shares_diluted | 131 | 4 | 45 | 20 |
| shares_outstanding | 87 | 4 | 89 | 20 |

20 inactive в каждой метрике — это Celgene за все 20 кварталов. Not yet filed — 2026Q3 у четырёх компаний, ещё не подавших 10-Q на 28.10.2026.

Покрытие на конец каждого года (последние 8 кварталов): 0% на 2009-12-31 (XBRL 10-K ещё нет), 43,5% на 2010, 69–73% в 2011–2019, 65% в 2021–2025 (Celgene inactive), 70,7% на 2026-10-28.

Revisions после первого public (vintage, по метрикам): EBITDA 163, operating income 131, CFO 130, FCF 124, COGS 95, D&A 91, net income 78, capex 64, diluted shares 63, revenue 59. Медианы изменения: revenue 0,80%, CFO 2,79%, diluted shares 50%. Revisions числа акций — это stock splits (Union Pacific и Celgene 2:1 в 2014 году, Old Dominion 3:2 в 2012 и 2020) и ошибка масштаба TXN 2010–2011.

### Known limitations

- **Тикер и сектор в прошлом неизвестны.** В submissions только текущие значения, и они не протягиваются назад. Celgene сегодня без тикера. История SIC и названия на каждый filing есть в Financial Statement Data Sets SEC (bulk, решение D-10). Механизм effective dates проверен на синтетической истории тикеров.
- **`original` — первое значение того concept, который выбран по знанию на cutoff.** Если поздний filing меняет concept года, меняется и original. Пример — Hubbell 2021: CFO стал `...ContinuingOperations` после продажи бизнеса. На sample 82 таких смены у original против 1 104 у vintage: 53 — смена concept, 11 — Q4, позже поданный напрямую вместо FY − 9M.
- **Coverage начинается с первого XBRL 10-K.** До него нет фискального календаря, и кварталы из первых XBRL 10-Q 2009 года не размещаются. На cutoff 31.12.2009 значений 0.
- **Provisional год проецируется.** Конец текущего фискального года (снова конец месяца или +52 недели) — оценка до выхода 10-K. У 52/53-недельного года 53-я неделя видна только из 10-K.
- **`inactive` наступает через 90 дней после конца первого квартала после Form 15.** До этого квартал `not_yet_filed`, потому что Form 15 бывает и для одного класса бумаг. Компания, ушедшая с биржи, но продолжившая отчитываться по 15(d), остаётся активной.
- **Момент public — время приёма EDGAR,** а не время, когда filing увидели рынки. Расхождение — минуты. Правила дня filing сдвигают знание только позже.
- **`mixed_vintage` — warning, а не blocking:** значение остаётся в panel с флагом. Отличить пересчёт базы от исправления одного Q4 по Company Facts нельзя.
- **`quarters_do_not_sum` (10 alerts)** показывает, где кварталы и год поданы на разных основаниях (Hubbell 2019, AWK 2012, Akamai 2011). Alert ничего не исправляет и не скрывает.
- **Sample — 10 компаний** (D-09). Скорость на 10 компаниях: полная сборка около 50 с на 8 ядрах. Для bulk (тысячи компаний) понадобится инкрементальная сборка: новый filing пересчитывает только свою компанию.
- **Число акций не пересчитано на splits.** На cutoff после split свежие кварталы — после split, а старые (которые не повторил ни один поздний filing) — до него. Per-share features нужно пересчитывать по событиям split; в Company Facts их нет, это задача Stage 14/19.
- **Хранилище — SQLite**, а не DuckDB/Parquet из docs/03: новые пакеты не ставились. Contracts от этого не зависят.

### Decisions

- Интервалы знания вместо материализации на каждую дату; as-of = одно условие `known_from <= cutoff < known_to` (ADR-0019).
- Пересчёт нормализации на каждый момент filing: точность важнее скорости, и as-of равен нормализации прошлого по построению.
- Момент public = max(время приёма, начало даты filing по Eastern); cutoff-дата = конец дня по Eastern.
- Features и модели — только на `vintage` или `original`. `latest` — hindsight, panel и snapshot его не принимают.
- Текущие тикер и SIC не протягиваются назад; неизвестное остаётся неизвестным с причиной.
- Snapshot назван hash содержимого; manifest с временем сборки не хешируется; cutoff позже скачивания archive отклоняется.
- `mixed_vintage` и `quarters_do_not_sum` — предупреждения, не исправления.

### Next prompt

`13_MACRO_VINTAGE_INTEGRATION.md` — только по команде владельца. Для него нужен ключ FRED (решение D-11: ключ регистрирует владелец) и решение D-12 по ECB и World Bank.

## 4. Acceptance

| Критерий промпта 12 | Evidence | Статус |
|---|---|---|
| На 2021-12-31 нет доступа к отчётности, впервые поданной в 2022 | Тест `test_a_cutoff_never_sees_a_filing_dated_after_it` (10-Q/A принят 31.12 в 18:10 ET, датирован 03.01.2022, не виден); на sample у snapshot 2021-12-31 0 источников с датой 2022+ | ✅ |
| Хранятся observation period, filed/released timestamp, source version, corrections | `PitValue`: период, источники с accession и датой filing, момент public с точностью, интервал знания и причина смены; `history` | ✅ |
| `as_of(company, metric, timestamp)` | `Warehouse.as_of`, команда `as-of`; тест равенства нормализации public-фактов в каждый момент | ✅ |
| Consistent quarterly panel | `build_panel`: полный, по календарным кварталам, с mask и состояниями | ✅ |
| Snapshot hash | `pit-<дата>-<SHA-256>`; одинаковый при повторе, при новой сборке и при сборке только из прошлого | ✅ |
| Restatement policy (original / vintage / latest) | `KnowledgeView`; latest отклоняется panel и snapshot; тест 10-K/A | ✅ |
| Financial coverage dashboard | `coverage.html` / `.md` / `.json`; скриншоты `docs/stages/12-screens/` | ✅ |
| Broken chronology alerts | 9 видов; тесты на синтетике; на sample 20 alerts | ✅ |
| Feature mask semantics | `PanelCell.mask`, состояния с причиной; features только из ячеек, mask распространяется | ✅ |
| Тикеры и sector classification по effective dates | `EntityAttribute`, `attribute_as_of`, `resolve_ticker`; текущие значения назад не протягиваются; история SIC ждёт D-10 | ✅ (механизм; история на sample — только названия) |
| Adversarial fixtures: 2020Q4 только в 2021, 10-K amendment, annual CFO vs Q4, delisted, missing R&D, 53-week, renamed ticker | `test_pit_warehouse.py`, по тесту на каждый | ✅ |
| Никакая функция feature building не leakage | Равенство as-of нормализации прошлого; поздние filings не меняют snapshot и features; `check_point_in_time`; features получают только ячейки | ✅ |
| Reproducible identical as-of snapshot for same cutoff | Повтор, новая сборка, сборка «скачано на cutoff» — тот же hash (раздел Measured results) | ✅ |
| Explicit coverage count (firm-quarter vs metric) | Таблица «By metric» в dashboard и в Measured results | ✅ |
| No future filings | `check_point_in_time`, тесты, `leakage-check` 8 из 8 на sample | ✅ |
| Unit tests for restatements | 10-K/A: 290 → 270 (`mixed_vintage`) → 280 → confirmed; original остаётся 290; latest не зависит от даты | ✅ |
| Data lineage export | `lineage.jsonl`: source facts, accession, момент public, URL filing, SHA-256 raw-файла | ✅ |
| Только затем 13 | Stage 13 не начат | ✅ |

`17_ACCEPTANCE_MATRIX`:

- **DATA-02** (filed-at as-of snapshots enforced, deliberately future-dated fixture) — ✅: estimate в 10-K, 10-Q/A вечером 31.12, «отравленные» поздние filings;
- **DATA-03** (квартализация и restatement, unit tests) — ✅, дополнено тестами restatement во времени;
- **DATA-05** (source coverage transparent, generated data card) — ✅: coverage dashboard на cutoff.

Exit B (docs/14) требует ещё Stage 13 (macro vintages) и Stage 14 (quality gate). Часть «идентичный snapshot для любой фирмы и даты без знания будущих filings» для SEC-данных sample выполнена.
