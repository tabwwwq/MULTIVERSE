# MULTIVERSE — Product Requirements Document

| Поле | Значение |
|---|---|
| Продукт | MULTIVERSE — Financial Parallel Universe Engine |
| Документ | PRD, Stage 01 |
| Версия | 0.1 |
| Дата | 2026-10-28 |
| Статус | ACCEPTED 2026-10-28 (defaults D-01…D-08 приняты владельцем) |
| Владелец | Maxim Leshchenko |
| Основание | `00_MASTER_ORCHESTRATOR.md`, `docs/01_PRODUCT_VISION.md`, `docs/02_USER_EXPERIENCE.md`, сверка с docs 03–18 |
| Связанные файлы | [Personas](02-personas.md) · [User stories и failure cases](03-user-stories.md) · [Scope matrix](04-scope-matrix.md) · [Product risks](05-product-risks.md) · [Open questions](06-open-questions.md) · [Metric definitions](07-metric-definitions.md) · [Acceptance checklist](08-acceptance-checklist.md) |

> Этот документ описывает требования. Код, данные и модели на Stage 01 не создавались. Исторического coverage пока нет: любые цифры покрытия появятся только после Stage 14.

---

## 1. Резюме

MULTIVERSE помогает финансовым консультантам и аналитикам задавать вопрос «что могло бы случиться, если в момент *t* компания приняла бы другое решение» и получать **проверяемый набор сценариев**, а не одну «правильную» альтернативную историю.

Пользователь выбирает компанию, исторический cutoff (as-of) и формально определённую интервенцию: R&D, реструктуризацию, M&A, дивестицию, CAPEX или рефинансирование. Система строит baseline и альтернативные траектории revenue, EBITDA, FCF, net debt и EV. Каждое число несёт происхождение, единицы, тип неопределённости и уровень вывода (descriptive / predictive / causal).

## 2. Проблема

1. Плановые модели в консалтинге и FP&A скрывают источники и допущения. Коллега не может проверить, откуда взялась цифра.
2. Типичные forecasting-дашборды отвечают «что будет с revenue», но не «что было бы при другом решении в момент *t*, если история до *t* не меняется».
3. ML-демо часто выдают точечные прогнозы без калибровки и смешивают корреляцию с причинностью. Финансовые ревьюеры такому не доверяют.
4. Исторические бэктесты часто «знают будущее»: используют данные по `period_end`, а не по дате публикации.

## 3. Цели и не-цели

### Цели

| ID | Цель | Как измеряем |
|---|---|---|
| G-01 | У каждого показанного числа есть происхождение | UI-аудит: 100% чисел на экране результата имеют `source_id`, `assumption_id` или `model_id` (NFR-PROV-01) |
| G-02 | Режим и статус результата всегда видны | Trust-шапка (Mode / Evidence / As-of / Model / Uncertainty / Audit) на 100% экранов результата (FR-RE-04) |
| G-03 | Результаты воспроизводимы | Одинаковые seed + config + model + snapshot дают идентичные числа (NFR-REPRO-01, SIM-01) |
| G-04 | Консультант проходит путь company → report без обучения | Юзабилити-тест Stage 08: 3 из 3 участников завершают demo-путь; медианное время — фиксируется, не обещается заранее |
| G-05 | Прогнозная и причинная оценки разделены | Ни один экран и отчёт не показывает causal label без пройденной диагностики (FR-CA-02) |
| G-06 | Проект доказуем для портфолио | 3 воспроизводимых case studies с evidence (V4, PORT-01) |

### Не-цели

| ID | Чего продукт не делает |
|---|---|
| NG-01 | Не даёт инвестиционных и торговых рекомендаций |
| NG-02 | Не предсказывает цену акции и не называет результат «fair market value» |
| NG-03 | Не утверждает, что исторический counterfactual «доказан» |
| NG-04 | Не покрывает «все компании мира»: старт — 20–50 US-GAAP компаний (D-02) |
| NG-05 | Не использует real-time рыночные данные и платные фиды без отдельного решения |
| NG-06 | Не генерирует нарратив LLM без структурированных событий и ссылок |
| NG-07 | Не запускает облачные вычисления и не публикует ничего без разрешения владельца |
| NG-08 | Не имеет native mobile app: только адаптивный web |

## 4. Пользователи, роли и страницы

Подробные personas — в [02-personas.md](02-personas.md).

| Persona | Системная роль | Основной режим |
|---|---|---|
| P1 Strategy consulting analyst | Analyst | Сравнение вариантов, отчёт для партнёра |
| P2 Equity research / corporate finance analyst | Analyst | Чувствительность FCF, EV, net debt |
| P3 CFO / FP&A lead | Researcher (+ Analyst для ревью) | Формулировка решения, лаги, ликвидность |
| P4 Student / researcher | Researcher | Воспроизведение экспериментов, baselines, confounders |
| — | Visitor | Чтение концепции и demo без регистрации |
| — | Admin (владелец) | Данные, модели, бюджеты, доступы |

### Доступ к страницам

Обозначения: **R** — чтение, **W** — создание и изменение, **A** — администрирование, **—** — нет доступа. «Версия» — когда страница появляется (см. [04-scope-matrix.md](04-scope-matrix.md)).

| # | Страница | Visitor | Researcher | Analyst | Admin | Версия |
|---|---|---|---|---|---|---|
| 1 | Landing / Project | R | R | R | R | V1 |
| 2 | Universe Explorer | R (demo) | R | R | A | V1 fixtures → V2 |
| 3 | Company Dossier | R (demo) | R | R | A | V1 fixtures → V2 |
| 4 | Time Machine | R (demo) | W | W | A | V1 → V2 |
| 5 | Decision Builder | W (demo, без сохранения) | W | W | A | V1 |
| 6 | Assumption Matrix | R | W | W | A | V1 базовая → V3 |
| 7 | Launch Center | — | W | W | A | V1 (локальный demo run) → V2 |
| 8 | Simulation Monitor | — | R (свои jobs) | R (свои jobs) | A (все jobs) | V2 |
| 9 | Timeline Explorer | R (demo) | R | R | R | V1 |
| 10 | Universe Compare | R (demo) | W | W | R | V1 |
| 11 | Risk Observatory | — | R | R | R | V3 |
| 12 | Valuation Studio | — | W | W | R | V3 |
| 13 | Causal Map | R (методология) | R | W (ревью допущений) | A | V3 |
| 14 | Explainability Room | — | R | R | R | V2 → V3 |
| 15 | Research Notebook | — | W (свои) | W (свои) | A | V1 local → V4 server |
| 16 | Report Studio | R (demo-отчёт) | W | W (финализация ревизии) | A | V1 Markdown / CSV → V4 PDF |
| 17 | Model Observatory | — | R | R | A | V2 |
| 18 | Data Catalog | R (публичная часть) | R | R | A | V2 |
| 19 | About / Methodology | R | R | R | R | V1 |
| 20 | Settings / Privacy | R (локальные настройки) | W | W | A | V1 local → V4 accounts |

В V1 аккаунтов нет (D-07): Researcher и Analyst — это режимы одного локального пользователя. Разделение прав появляется в V4 (Stage 24).

## 5. Главный путь: company → as-of → action → simulation → report

| # | Шаг | Пользователь | Система проверяет | Выход | Отказ |
|---|---|---|---|---|---|
| 1 | Select company | Ищет по ticker, name или CIK | Stable company ID, ticker aliases по датам, поддержка (US-GAAP, история) | Company chip + coverage meter | FC-01 |
| 2 | Set historical cutoff | Выбирает as-of дату | Есть ли данные, поданные до этой даты | Dossier показывает только факты с `filed_at <= as_of` | FC-02, FC-03 |
| 3 | Confirm data availability | Смотрит coverage и пропуски | Минимум кварталов по метрикам, missingness | Статус: достаточно / partial / insufficient | FC-02 |
| 4 | Choose constrained decision | Выбирает тип и величину действия | Тип поддерживается, unit однозначна, eligibility | Валидная структура action | FC-05, FC-06 |
| 5 | Edit assumptions | Меняет лаги, costs, распределения | Диапазоны, cross-field invariants (financing = 100%) | Assumption set с источниками defaults | FC-05 |
| 6 | Validate / warnings | Нажимает «Validate» | OOD, extreme magnitude, отсутствие калибровки | Список warnings, кнопка Run активна только без blocking errors | FC-06 |
| 7 | Run research job | Видит оценку стоимости, нажимает «Run» | Бюджет, лимиты paths / horizon, idempotency | Job ID (V2+) или локальный demo run (V1) | FC-07 |
| 8 | Monitor | Следит за статусом, может закрыть вкладку | Heartbeat, state machine | Статус и прогресс | FC-08 |
| 9 | Inspect paths | Смотрит timeline, квантили, drivers | Значения графика = значения KPI | Timeline + таблица + «что это НЕ значит» | — |
| 10 | Compare | Сравнивает baseline, A, B | Совместимость currency, horizon, as-of | Delta distributions, waterfall | FC-09 |
| 11 | Save | Сохраняет сценарий | Schema version, место хранения (local в V1) | Неизменяемая revision | FC-10 |
| 12 | Export report | Экспортирует Markdown / CSV (V1), PDF (V4) | Manifest полный, synthetic watermark | Отчёт + reproducibility manifest | FC-10 |

**Инвариант пути:** любое изменение параметра либо пересчитывает результат, либо помечает его `stale — requires rerun`. Тихих обновлений нет.

## 6. Режимы вывода и типы неопределённости

### Режимы результата

| Режим | Когда разрешён | Что можно утверждать | Метка в UI |
|---|---|---|---|
| `DEMO` | V1 и всегда, когда данные синтетические | Только как работает механика. Числа не описывают реальную компанию | Бейдж DEMO + водяной знак SYNTHETIC на графиках и в экспорте |
| `EMPIRICAL FORECAST` | После Stage 15–17: модель на PIT-данных с измеренным holdout | Прогноз распределения при выученных зависимостях. Не причинный эффект | Бейдж с model ID и статусом калибровки |
| `CAUSAL STUDY` | После Stage 19–20, только для типов действий с пройденной диагностикой | Оценка эффекта **при задокументированных допущениях** | Бейдж + ссылка на identification note и диагностику |
| `FICTIONAL EXPLORATORY` | Сценарии без наблюдаемых аналогов («Apple без iPhone») | Только иллюстрация допущений. Широкая uncertainty | Бейдж + предупреждение о structural extrapolation |

Режим выбирает система по доступным артефактам. Пользователь не может вручную «повысить» режим.

### Predictive и causal uncertainty: в чём разница

| | Predictive uncertainty | Causal (identification) uncertainty |
|---|---|---|
| Вопрос | Насколько разбросан будущий исход при выученных зависимостях | Можно ли разницу «интервенция минус baseline» приписать именно действию |
| Источник | Шум бизнеса, ошибка модели, макро-шоки, неизвестные будущие события | Confounding (скрытые ожидания U_t, состояние S_t, макро), selection, нарушение parallel trends, нет common support |
| Уменьшается ли данными и путями Monte Carlo | Частично: больше данных и калибровка помогают. Monte Carlo уменьшает только ошибку сэмплирования | **Нет.** Больше путей и больше эпох обучения её не уменьшают. Нужен дизайн исследования |
| Как измеряется | Out-of-time coverage 50 / 80 / 90%, pinball, CRPS, calibration plot | Balance, pre-trends, placebo, negative controls, sensitivity к hidden confounding |
| Как показывается | Полосы p10 / p50 / p90 с подписью «conditional model quantiles» и статусом калибровки | Статус идентификации: `not assessed` / `assumption-based` / `diagnostics passed` + список непроверенных допущений |
| Чего не означает | Полоса 80% не гарантирует попадание в 80% случаев, пока не откалибрована | «Diagnostics passed» не доказывает эффект: он верен только при допущениях |

Ещё два источника неопределённости показываются отдельно:

- **Assumption (parametric) uncertainty:** распределения, которые задал пользователь (например, ramp synergy 6–10 кварталов). В UI видны как priors с источником default.
- **Monte Carlo sampling error:** ошибка оценки квантилей из конечного числа путей. Показывается как MC standard error и convergence status.

## 7. Маркировка synthetic data

| ID | Правило |
|---|---|
| SYN-01 | Любой результат на синтетике имеет режим `DEMO`. Бейдж виден в trust-шапке и не скрывается при прокрутке |
| SYN-02 | На каждом графике с синтетикой — водяной знак `SYNTHETIC` и пометка в легенде |
| SYN-03 | Demo-компании — вымышленные (например, «Northwind Semiconductors (DEMO)»), без реальных тикеров (D-01) |
| SYN-04 | В API и файлах: поле `data_origin = "synthetic"` у каждой серии, рядом с `kind` (observed / forecast / simulated) |
| SYN-05 | Экспорт demo: имя файла с суффиксом `_DEMO`, первая строка отчёта и CSV — предупреждение о синтетике |
| SYN-06 | Синтетика и эмпирика не смешиваются на одном графике. Исключение — явно помеченное методическое сравнение |
| SYN-07 | Статус не передаётся только цветом: всегда текст + иконка |
| SYN-08 | Fallback на синтетику, когда модель недоступна, — только с явного согласия пользователя и с баннером |

## 8. Защита от ложной точности

| ID | Правило |
|---|---|
| FP-01 | Точечная оценка без интервала не показывается на экранах результата. Медиана всегда идёт вместе с p10–p90 |
| FP-02 | Округление по неопределённости: число значащих цифр не больше, чем позволяет ширина интервала (например, «$4.2 bn», а не «$4 213 587 912») |
| FP-03 | Вероятности подписаны «under assumed model» и статусом калибровки. Без калибровки — «not validated» |
| FP-04 | Слова «accuracy», «точность», «доказано» запрещены в UI-копирайте без измеренной метрики рядом (copy audit, UX-04) |
| FP-05 | Сценарий вне training support → флаг `out of distribution`: шире uncertainty или отказ от числового ответа |
| FP-06 | Рядом с результатом — панель «Что это НЕ значит» (REP-02) |
| FP-07 | Показывается размер выборки: число компаний и кварталов, на которых стоит оценка |
| FP-08 | Undefined-коэффициенты (net debt / EBITDA при EBITDA ≤ 0) показываются как «undefined» с причиной, а не как большое число |
| FP-09 | Шкалы графиков честные: zero baseline там, где сравнение этого требует; нет обрезанного масштаба без пометки |
| FP-10 | Causal-метка никогда не выставляется автоматически (FR-CA-02) |

## 9. Финансовые величины

Полный словарь — в [07-metric-definitions.md](07-metric-definitions.md). Главные различия, которые продукт обязан соблюдать:

- **Enterprise value ≠ equity value ≠ price per share.** EV — стоимость операционной деятельности. Equity value = EV − net debt − прочие senior claims + non-operating assets. Price per share требует diluted shares и в V1–V3 не показывается (D-06).
- **FCFF ≠ FCFE ≠ CFO − CAPEX.** По WACC дисконтируется только FCFF.
- **EBITDA** считается как EBIT + D&A и подписывается «EBITDA (calculated)». Adjusted EBITDA — только с reconciliation (D-05).
- **Единицы и валюта:** одна canonical currency на сценарий (USD в V1–V3, D-04). Margins — доли, growth — относительные темпы, изменения долей — в percentage points (p.p.). Flow-величины имеют период (quarter / FY / TTM), stock-величины — дату.

## 10. Functional requirements

Приоритеты: **P0** — без этого версия не выпускается; **P1** — важно; **P2** — желательно. Трассировка — к `docs/17_ACCEPTANCE_MATRIX.md`.

### 10.1 Компании и данные (FR-CO)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-CO-01 | Поиск по ticker, названию и CIK, включая исторические ticker aliases | P0 | V1 fixtures, V2 | E2E: поиск по старому тикеру находит компанию с пометкой «alias до YYYY-MM-DD» | UX-01 |
| FR-CO-02 | Stable company ID отдельно от тикера и названия | P0 | V1 | Contract test: ID не меняется при смене тикера в fixture | DATA-04 |
| FR-CO-03 | Coverage meter: число валидных кварталов по каждой метрике на выбранный as-of | P0 | V1 fixtures, V2 | Unit test на расчёт coverage + отображение на fixture с пропусками | DATA-05 |
| FR-CO-04 | Dossier: история revenue, EBITDA (calculated), FCF, debt; у каждого значения источник; пропуск — «—» с причиной, никогда 0 | P0 | V1 fixtures, V2 | Test: fixture без R&D показывает missing, а не 0 | DATA-04 |
| FR-CO-05 | Состояние «компания не поддерживается» с причиной (IFRS / foreign filer, мало истории, нет XBRL) | P0 | V1 | E2E: неподдерживаемый тикер показывает причину и альтернативы | UX-01 |

### 10.2 Time Machine (FR-TM)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-TM-01 | Выбор as-of. Dossier и модели видят только факты с `filed_at <= as_of` | P0 | V1 fixtures, V2 | Fixture с future-dated filing не появляется на прошлую дату | DATA-02 |
| FR-TM-02 | Каждое значение показывает, когда оно стало публичным (`filed_at` / `release_at`) | P0 | V1 | UI test: tooltip значения содержит дату публикации | DATA-02 |
| FR-TM-03 | Смена as-of помечает зависимые результаты `stale — requires rerun` | P0 | V1 | E2E: сменить дату → результат помечен stale, Run снова доступен | UX-01 |

### 10.3 Decision Builder (FR-DE)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-DE-01 | Шесть типов действий: `rnd_change`, `workforce_restructure`, `acquisition`, `divestiture`, `capex_expansion`, `debt_refinance` | P0 | V1 | Schema test: каждый тип валидируется и проходит JSON roundtrip | CAUS-01 |
| FR-DE-02 | Каждая величина — типизированная пара `{value, unit}` с unit из перечня (например, `fraction_of_previous_rnd_budget`, `pp_of_revenue`, `usd`, `fraction_of_headcount`). Неоднозначный ввод отклоняется | P0 | V1 | Negative test: magnitude без unit отклоняется | CAUS-01 |
| FR-DE-03 | Каждый слайдер связан с числовым полем, единицами и проверкой диапазона | P0 | V1 | A11y + unit test на range errors | UX-01 |
| FR-DE-04 | Для M&A доли cash / debt / equity в сумме дают ровно 100% (decimal-сравнение) | P0 | V1 | Property test: любая комбинация ≠ 100% отклоняется | FIN-03 |
| FR-DE-05 | Тайминг: announced, effective, lag, ramp. `effective_date >= as_of` | P0 | V1 | Test: effective раньше as-of отклоняется | UX-01 |
| FR-DE-06 | Eligibility по отрасли и истории с предупреждениями (например, relocation для компании без производства) | P1 | V1 | Fixture-тесты warnings | — |
| FR-DE-07 | Кнопки Reset / Validate / Run. Defaults задокументированы и показывают источник | P0 | V1 | E2E: Reset возвращает documented defaults | UX-01 |
| FR-DE-08 | Объяснение механизма: какие статьи отчётности затрагивает действие | P1 | V1 | Copy review по каждому типу | REP-02 |

### 10.4 Симуляция и jobs (FR-SI)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-SI-01 | Запуск создаёт run с ID. V1 — локальный demo run с меткой DEMO. V2+ — серверный job с `Idempotency-Key` | P0 | V1, V2 | Integration test: повтор с тем же ключом возвращает тот же job | OPS-01 |
| FR-SI-02 | Статусы по state machine (`VALIDATING → QUEUED → RUNNING → COMPLETED / FAILED / CANCELLED`, pause-ветка) с ARIA live | P0 | V2 | UI test каждого состояния | UX-02 |
| FR-SI-03 | Закрытие вкладки не останавливает job. После возврата виден статус и результат | P0 | V2 | Browser integration test с refresh | UX-02, OPS-01 |
| FR-SI-04 | «Stop after checkpoint», resume, предупреждение при force kill | P0 | V2 | Checkpoint recovery test | ML-05 |
| FR-SI-05 | Оценка ресурсов и стоимости до запуска. Лимиты на paths и horizon | P0 | V2 | Test: запрос сверх лимита отклоняется с объяснением | OPS-02 |
| FR-SI-06 | Фиксированный seed: одинаковый seed + config дают одинаковый результат | P0 | V1 | Repeated-run test, идентичные выходы | SIM-01 |
| FR-SI-07 | Paired shocks: baseline и intervention используют одни внешние шоки | P0 | V1 demo, V3 | Test: нулевая интервенция = baseline на каждом пути | SIM-02 |

### 10.5 Результаты и сравнение (FR-RE)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-RE-01 | Timeline по chart grammar: observed / baseline / alternate, полосы p10–p90 с типом квантилей и статусом калибровки | P0 | V1 | Visual snapshot + copy audit | SIM-03 |
| FR-RE-02 | Переключатель absolute / change / percent. Tooltip с единицами, валютой и источником | P0 | V1 | Interaction test | UX-01 |
| FR-RE-03 | У каждого графика есть таблица-альтернатива и экспорт CSV | P0 | V1 | Screen-reader check | UX-03 |
| FR-RE-04 | Trust-шапка: Mode / Evidence / As-of / Model / Uncertainty / Audit | P0 | V1 | UI audit всех экранов результата | UX-04 |
| FR-RE-05 | Панель «Что это НЕ значит» рядом с результатом | P0 | V1 | Copy audit | REP-02 |
| FR-RE-06 | Compare блокирует несовместимые currency / horizon / as-of без явного метода | P0 | V1 | Negative E2E | — |
| FR-RE-07 | Значения на графиках совпадают с KPI: один источник данных, без независимой генерации | P0 | V1 | Test: сверка chart data и KPI cards | — |
| FR-RE-08 | Top drivers и sensitivity tornado с подписью «predictive sensitivity, not causal» | P1 | V2 | Copy audit | CAUS-03 |

### 10.6 Valuation и риск (FR-VA)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-VA-01 | DCF на FCFF с разложением WACC. Отказ при WACC ≤ g | P0 | V3 | Known-answer DCF test | FIN-02 |
| FR-VA-02 | EV и equity value — отдельные выходы с явным bridge | P0 | V3 | Property test на bridge | FIN-02 |
| FR-VA-03 | Матрица чувствительности WACC × g и доля terminal value в EV | P1 | V3 | Test на известном кейсе | FIN-02 |
| FR-VA-04 | Вероятности covenant breach / cash shortfall / negative FCF с подписью «under assumed model» | P1 | V3 | Copy audit + simulation test | SIM-03 |

### 10.7 Причинность (FR-CA)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-CA-01 | Causal Map: DAG с confounders, mediators и обоснованиями | P1 | V3 | Review + schema check | CAUS-03 |
| FR-CA-02 | Causal status у каждого результата: `not assessed` / `assumption-based` / `diagnostics passed`. Никогда не выставляется автоматически | P0 | V1 (`not assessed`), V3 | Test: без артефакта диагностики статус не может быть выше `assumption-based` | CAUS-03 |
| FR-CA-03 | Event registry: evidence URL, документ, абзац, reviewer, confidence | P0 | V3 | Manual label QA | CAUS-02 |

### 10.8 Библиотека сценариев (FR-LB)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-LB-01 | Сохранение сценария: name, tags, notes. В V1 — local storage с меткой «Only on this device» | P0 | V1 | Roundtrip test | UX-02 |
| FR-LB-02 | Revision неизменяема после экспорта отчёта. Изменения создают новую revision | P0 | V1 | Test: правка экспортированной revision создаёт новую | REP-01 |
| FR-LB-03 | Import / export JSON со schema version и migration. Битый JSON отклоняется | P1 | V1 | Negative tests | — |

### 10.9 Отчёты (FR-RP)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-RP-01 | Экспорт Markdown и CSV (V1), PDF (V4) | P0 | V1, V4 | Download test | REP-01 |
| FR-RP-02 | Отчёт содержит reproducibility manifest: scenario ID, revision, dataset snapshot, model ID, seed, code version, as-of, sources | P0 | V1 demo, V4 | Snapshot comparison | REP-01 |
| FR-RP-03 | Повторный экспорт не подменяет старый результат | P0 | V1 | Test immutable IDs | REP-01 |
| FR-RP-04 | Demo-экспорт несёт водяной знак и предупреждение (SYN-05) | P0 | V1 | Copy audit | UX-04 |

### 10.10 Данные и модели (FR-MO)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-MO-01 | Data Catalog: coverage, freshness, lineage, license по каждому источнику | P0 | V2 | Generated data card | DATA-05 |
| FR-MO-02 | Model Observatory: runs, dataset versions, метрики **только из реальных runs**, approval state | P0 | V2 | Artifact + config + hash | ML-02 |
| FR-MO-03 | Model card и data card | P0 | V2 | Review | ML-03 |

### 10.11 Администрирование (FR-AD)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-AD-01 | Admin утверждает версию модели для использования | P1 | V2 | Test: неутверждённая модель недоступна в Launch Center | ML-02 |
| FR-AD-02 | Admin задаёт бюджеты и лимиты вычислений | P0 | V2 | Induced budget-stop test | OPS-02 |
| FR-AD-03 | Audit log переходов jobs и защищённых чтений | P1 | V4 | Review лога | OPS-01 |

### 10.12 Landing, методология, настройки (FR-LM, FR-ST)

| ID | Требование | P | Версия | Как проверить | Трасс. |
|---|---|---|---|---|---|
| FR-LM-01 | Landing объясняет обещание **и ограничения**. CTA «Launch Scenario» и «Read Methodology» работают | P0 | V1 | Broken-link check, copy audit | REP-02 |
| FR-LM-02 | Methodology: источники, PIT, модели, уровни вывода, ограничения | P0 | V1 | Review | REP-02 |
| FR-ST-01 | Настройки отображения: масштаб (USD m / bn), формат чисел | P1 | V1 | UI test | — |
| FR-ST-02 | «Удалить все локальные данные» с подтверждением | P0 | V1 | Test: storage пуст после удаления | SEC-02 |

## 11. Non-functional requirements

| ID | Требование | Цель | Как измеряем |
|---|---|---|---|
| NFR-PERF-01 | Dashboard shell загружается быстро | p95 < 2 s на desktop, хорошая сеть | Lighthouse / RUM на Stage 08 |
| NFR-PERF-02 | Отклик интерфейса на ввод | INP < 200 ms | Chrome DevTools trace |
| NFR-PERF-03 | Локальный demo run не блокирует UI | Расчёт вне main thread (Web Worker) | Trace: нет long tasks > 200 ms при расчёте |
| NFR-A11Y-01 | Доступность | WCAG 2.2 AA; axe: 0 critical / serious; весь путь проходится клавиатурой | axe + ручной keyboard-only тест |
| NFR-A11Y-02 | Reduced motion | При `prefers-reduced-motion: reduce` все необязательные анимации выключены | E2E с эмуляцией media |
| NFR-RESP-01 | Адаптивность | Нет горизонтального overflow на 390, 768, 1440 px | Visual tests |
| NFR-REPRO-01 | Воспроизводимость | Одинаковые seed + config + model + snapshot → идентичные числа | Repeated-run test (SIM-01) |
| NFR-PROV-01 | Происхождение | 100% чисел результата имеют `source_id` / `assumption_id` / `model_id` | Автоматический audit контрактов |
| NFR-REL-01 | Надёжность jobs | Статус переживает закрытие браузера; падение worker восстанавливается по lease | Integration tests (OPS-01) |
| NFR-REL-02 | Idempotency | Повтор запроса с тем же ключом не создаёт второй job | Contract test |
| NFR-SEC-01 | Секреты | 0 находок secret scanner в CI; ключей нет во frontend bundle | CI secret scan (SEC-02) |
| NFR-PRIV-01 | Минимизация данных | V1 без аккаунтов и PII, аналитика выключена по умолчанию | Data inventory review |
| NFR-COST-01 | Контроль затрат | Ни один compute job без бюджета; облачные расходы = 0 без одобрения владельца | Budget guard test (OPS-02) |
| NFR-COMPAT-01 | Браузеры | Две последние версии Chrome, Edge, Firefox, Safari | E2E matrix |
| NFR-MAINT-01 | Сопровождаемость | TypeScript strict, typed Python, границы модулей проверяются линтером | CI |
| NFR-OBS-01 | Наблюдаемость | У каждого run есть trace ID, у ошибки — incident ID | Log review |
| NFR-I18N-01 | Язык | UI на английском в V1 (D-08); форматирование чисел учитывает locale; RU — P2 | Review |

## 12. Безопасность и приватность

| ID | Требование | Версия |
|---|---|---|
| SP-01 | Секреты (FRED key, SEC contact, cloud credentials) только в env / secret manager, никогда во frontend, git и логах | V1+ |
| SP-02 | В V1 нет аккаунтов: все пользовательские данные в local storage на устройстве, с явной меткой | V1 |
| SP-03 | Owner-scoped доступ к сценариям и отчётам, проверка ownership на каждом объекте API | V4 |
| SP-04 | Санитизация Markdown и HTML в отчётах (XSS) | V1 |
| SP-05 | Rate limits и лимиты на paths / horizon / jobs против cost abuse | V2 |
| SP-06 | Restricted и платные данные не попадают в публичный репозиторий и экспорт | V2 |
| SP-07 | Не загружать чужие torch checkpoints без проверки происхождения | V2 |
| SP-08 | GDPR: data inventory, retention, export / deletion — до появления аккаунтов | V4 |
| SP-09 | Импортированный JSON сценария валидируется по schema и не исполняется | V1 |

## 13. Failure modes системы

Пользовательские сбои с ожидаемым поведением — в [03-user-stories.md](03-user-stories.md#failure-cases) (FC-01…FC-10). Ниже — системные.

| ID | Сбой | Поведение | Запрещено |
|---|---|---|---|
| FM-01 | SEC недоступен | Cached snapshot с видимой датой свежести | Показывать кэш как свежие данные |
| FM-02 | SEC 429 / rate limit | Exponential backoff и перенос загрузки | Обходить ограничения |
| FM-03 | Нет XBRL-тега | Метрика пропущена с provenance warning | Подставлять 0 или соседний тег молча |
| FM-04 | Модель недоступна | Блок результата + предложение demo-fallback с согласия | Тихо подменять синтетикой |
| FM-05 | Падение worker | Lease истекает, retry по idempotency key, статус виден | Терять job или дублировать результат |
| FM-06 | GPU OOM | Checkpoint, меньший batch, отчёт о стоимости | Бесконечные retries |
| FM-07 | Исправление данных у источника | Новый snapshot, старые результаты ссылаются на старый | Мутировать историю |
| FM-08 | Object storage недоступен | Job → FAILED с incident ID, retry доступен | Частично записанный артефакт как готовый |
| FM-09 | Превышен бюджет | Job останавливается после checkpoint, владелец уведомлён | Продолжать вычисления |
| FM-10 | Timeout API | Понятная ошибка, idempotent retry | Повторный запуск без ключа |

## 14. Offline UX

| ID | Требование | Версия |
|---|---|---|
| OFF-01 | Приложение определяет потерю сети и показывает баннер «Offline» (текст + иконка) | V1 |
| OFF-02 | Локальная библиотека сценариев, просмотр сохранённых результатов и экспорт Markdown / CSV работают offline | V1 |
| OFF-03 | Действия, требующие сервера (новый job, загрузка данных), выключены с объяснением, а не падают | V2 |
| OFF-04 | Кэшированные данные компании показывают дату получения | V2 |
| OFF-05 | Нет тихой очереди: действия offline не отправляются автоматически при возврате сети без подтверждения | V2 |
| OFF-06 | Серверные jobs продолжаются, пока клиент offline. После возврата сети статус синхронизируется | V2 |
| OFF-07 | Demo run V1 считается локально и работает offline после первой загрузки приложения | V1 |

## 15. Приоритетные портфолио case studies

| # | Case study | Вопрос | Достижимый уровень вывода | Что показываем | Честное ограничение | Этапы |
|---|---|---|---|---|---|---|
| CS-1 | R&D allocation under uncertainty | Что было бы с revenue growth и маржой, если бы R&D intensity была выше на X p.p. начиная с квартала *t* | Predictive + observational (Level B / C) — только если Stage 19–20 найдут достаточно событий | Panel benchmark, лаги, sensitivity к hidden confounding, placebo dates | Эффект R&D отложен и плохо наблюдаем. Возможен вывод «эффект не идентифицирован» | 15–17, 19–20 |
| CS-2 | M&A stress and valuation | Как гипотетическая покупка (пример из vision: $15 bn, 60% долг / 40% акции, synergy ramp 8 кварталов, integration cost $1.5 bn) меняет EBITDA, FCF, leverage, EV и риск covenant | Structural scenario (Level D), без causal claim | Financing paths, dilution, EBITDA → FCF → EV, вероятность нарушения covenant under assumed model | Нужны допущения о target company. Цифры условны и не являются оценкой сделки | 21–23 |
| CS-3 | Operating restructuring / exit | Сокращение штата на 15% или выход из сегмента: one-off costs против устойчивой экономии | Mechanistic sandbox (Level A) + downside | Severance, retention, потеря выручки, stranded costs, хвостовые риски | Execution risk плохо измерим. Эффект на выручку — допущение | 21–22 |

## 16. Решения этапа

Каждое решение — default до ответа владельца (см. [06-open-questions.md](06-open-questions.md)).

| ID | Решение | Почему | Вопрос |
|---|---|---|---|
| D-01 | Demo-данные V1 — вымышленные компании без реальных тикеров | Синтетика с тикером AMD выглядит как реальные данные AMD | OQ-01 |
| D-02 | Стартовая эмпирическая выборка — 20–50 US-GAAP компаний из 1–2 секторов. Список — на Stage 09 по пригодности данных, а не по известности | Рекомендация `HOW_TO_USE_PROMPTS.md` и prompt 09 | OQ-02 |
| D-03 | Первый тип действия для causal-исследования — изменение R&D intensity | `docs/05`: одно действие с достаточной историей | OQ-03 |
| D-04 | Canonical currency — USD в V1–V3. Другие валюты блокируются с сообщением | Снимает класс FX-ошибок до Stage 13 | OQ-04 |
| D-05 | EBITDA = OperatingIncomeLoss + D&A с подписью «EBITDA (calculated)». Adjusted — только с reconciliation | EBITDA не стандартизирована в XBRL | OQ-10 |
| D-06 | Valuation через FCFF / WACC. Price per share вне scope V1–V3 | Нет лицензированных market data и corporate actions | OQ-12 |
| D-07 | V1 без аккаунтов, хранение только локально | Минимизация GDPR-риска (`docs/12`) | OQ-05 |
| D-08 | UI на английском, проектная документация на русском | Портфолио для международного рынка (Бельгия) | OQ-06 |

## 17. Допущения и зависимости

- SEC EDGAR и Financial Statement Data Sets остаются публично доступны на условиях fair access. Перепроверка — Stage 09.
- FRED API key владелец получает сам и передаёт через env (Stage 13).
- GPU-ресурсы не требуются до Stage 16. Решение о железе и бюджете — на Stage 16 / 18.
- Coverage неизвестен до Stage 14. Если данных окажется мало, scope V2–V3 сужается, а не заполняется синтетикой.

## 18. Трассировка к acceptance matrix

| ID matrix | Покрывается требованиями |
|---|---|
| UX-01 | FR-CO-01, FR-CO-05, FR-TM-03, FR-DE-03, FR-DE-05, FR-DE-07, FR-RE-02 |
| UX-02 | FR-SI-02, FR-SI-03, FR-LB-01 |
| UX-03 | FR-RE-03 |
| UX-04 | FR-RE-04, FR-RP-04, SYN-01…08, FP-04 |
| DATA-02 | FR-TM-01, FR-TM-02 |
| DATA-04 | FR-CO-02, FR-CO-04 |
| DATA-05 | FR-CO-03, FR-MO-01 |
| ML-02, ML-03 | FR-MO-02, FR-MO-03, FR-AD-01 |
| ML-05 | FR-SI-04 |
| CAUS-01 | FR-DE-01, FR-DE-02 |
| CAUS-02 | FR-CA-03 |
| CAUS-03 | FR-CA-01, FR-CA-02, FR-RE-08 |
| FIN-02 | FR-VA-01, FR-VA-02, FR-VA-03 |
| FIN-03 | FR-DE-04 |
| SIM-01 | FR-SI-06, NFR-REPRO-01 |
| SIM-02 | FR-SI-07 |
| SIM-03 | FR-RE-01, FR-VA-04, FP-03 |
| OPS-01 | FR-SI-01, FR-SI-03, NFR-REL-01, NFR-REL-02 |
| OPS-02 | FR-SI-05, FR-AD-02, NFR-COST-01 |
| SEC-01 | SP-06 |
| SEC-02 | SP-01, NFR-SEC-01, FR-ST-02 |
| REP-01 | FR-RP-01, FR-RP-02, FR-RP-03, FR-LB-02 |
| REP-02 | FR-RE-05, FR-LM-01, FR-LM-02 |
| PORT-01 | CS-1, CS-2, CS-3 |

DATA-01, DATA-03, ML-01, ML-04, CAUS-04, FIN-01 — технические требования этапов 10–23. Продуктовых FR для них нет, они проверяются на своих этапах.

Все пункты acceptance matrix остаются **TODO**: Stage 01 создаёт требования, а не реализацию.
