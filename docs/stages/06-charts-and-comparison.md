# Stage 06 — Timeline charts и сравнение вселенных

| Поле | Значение |
|---|---|
| Этап | 06 — Timeline charts и сравнение вселенных |
| Дата | 2026-10-28 |
| Статус | ACCEPTED 2026-10-28 (CI run 40756212363: 7/7 задач зелёные) |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/06_CHARTS_AND_COMPARISON.md` |
| Основание | `docs/02` (Timeline Explorer, Universe Compare, страница сценария), `docs/08` (outputs, paired paths), `docs/09` (SimulationResult), `docs/10` (chart grammar, Trust UX), PRD FR-RE-01…07, FR-SI-06/07, SYN-01…07, FP-01…09, US-08, US-09, FC-09 |

## 1. Scope

Графики результатов на **явно помеченных mock-данных**. Результаты — фиксированные mock-сценарии из детерминированного генератора. Это не модель и не прогноз: симуляции собственного решения появятся с Monte Carlo (Stage 22), модели — с Phase C.

## 2. Подзадачи

| # | Подзадача | Измеримый результат |
|---|---|---|
| 1 | Contract результата 0.4.0: история, квантили p10/p50/p90 по сценариям, парные разности, распределение разностей, waterfall, события, manifest, состояние failed | Pydantic-правила: квантили упорядочены, waterfall складывается точно, demo ⇒ synthetic и не калибровано |
| 2 | Mock-генератор: baseline, alternate A, alternate B с общими шоками (paired) | Детерминированный JSON, drift check; нулевая интервенция = baseline на каждом пути (тест) |
| 3 | Timeline chart: observed / baseline / A / B, полосы p10–p90, граница history / forecast, маркер решения, события | SVG, легенда с переключателями, crosshair и tooltip с единицами, клавиатура |
| 4 | Режимы absolute / change / percent | Change и percent — парные квантили, а не разность полос |
| 5 | KPI = график | KPI берутся из тех же точек графика; тест сверяет их |
| 6 | Таблица-альтернатива и CSV | Таблица тех же точек; CSV с предупреждением в первой строке и суффиксом `_DEMO` |
| 7 | Распределение разностей и waterfall | Гистограмма парных разностей на горизонте; waterfall на средних, сумма шагов = разность |
| 8 | Universe Compare | KPI бок о бок, waterfall, распределения; несовместимые as-of, currency и horizon блокируются (FC-09) |
| 9 | Пустые и ошибочные состояния | Список без результата, failed с incident ID, неизвестный ID — 404 |
| 10 | Честные шкалы, 390 px, доступность | Absolute включает 0, change и percent симметричны около 0; summary для screen reader; axe |

## 3. Риски

| Риск | Митигация |
|---|---|
| Mock-цифры примут за прогноз | Бейдж DEMO, водяной знак SYNTHETIC на каждом графике, «mock» в легенде, CSV и trust-шапке |
| Разность полос выдадут за распределение разности | Генератор считает парные разности путь за путём и хранит их отдельно |
| KPI разойдутся с графиком | Один источник: KPI читают последнюю точку серии графика |
| Обрезанная шкала преувеличит эффект | Правила домена оси проверяются unit-тестом |
| Цвет как единственный носитель смысла | Стиль линии, легенда, подписи и таблица; палитра проверена валидатором dataviz по всем парам |

## 4. Отчёт этапа

### Done

- **Contract `ScenarioResult`** (contracts 0.4.0, ADR-0014). В нём:
  - история только из того, что подано к cutoff;
  - квантили p10 / p50 / p90 по baseline и alternates;
  - парные разности по путям в долларах и в доле baseline, где baseline всегда положителен;
  - распределение парной разности на горизонте;
  - waterfall на средних;
  - события решения;
  - manifest;
  - состояние failed с incident ID.

  Правила contract:
  - квантили упорядочены;
  - waterfall складывается точно;
  - demo ⇒ synthetic и не калибровано;
  - mock только в demo;
  - failed без чисел;
  - история не позже cutoff;
  - прогноз начинается после истории и покрывает горизонт.
- **Mock-генератор** `python -m multiverse_contracts.mock_results`:
  - 500 путей, 12 кварталов, seed 20261027;
  - выручка — случайное блуждание по собственной истории компании;
  - alternates берут те же шоки, что и baseline (paired paths);
  - неопределённые входы берутся из распределений самого решения.

  Результаты:
  - Northwind R&D +20% / +40%;
  - Northwind CAPEX USD 0.5bn / 1bn — тот же cutoff и seed, поэтому baseline общий;
  - Northwind −10% штата с cutoff 2022-06-30;
  - упавший запуск Halcyon.

  Всё помечено mock и demo.
- **Timeline Explorer** `/timeline/[id]`:
  - SVG-график: история, baseline (пунктир), A и B, полосы p10–p90, граница History / Forecast, маркер решения;
  - метка «Synthetic · mock» на графике (SYN-02);
  - переключатели метрики и режима absolute / change / percent; percent недоступен там, где baseline может пересечь ноль, с объяснением (FP-08);
  - легенда-переключатели серий и полос; цвет остаётся за серией;
  - crosshair с tooltip: все серии, единицы, источник для отчётных кварталов;
  - чтение стрелками и Home/End, объявление через live region;
  - сводка для screen reader и она же подпись графика;
  - KPI-карточки с медианой и p10–p90 (FP-01) из тех же точек;
  - таблица всех точек графика;
  - CSV: первая строка — предупреждение о синтетике, имя файла с `_DEMO`;
  - лента событий; панель «Что это НЕ значит»; trust-шапка.
- **Universe Compare** `/compare/[id]`:
  - KPI бок о бок: медиана, p10–p90 и парная разность с baseline;
  - waterfall от baseline к каждому alternate: шаги складываются точно;
  - гистограммы парных разностей с долей путей выше baseline «under the mock model, not validated» (FP-03);
  - сравнение с другим результатом: совместимые показываются, несовместимые блокируются с причинами (FC-09).
- **Пустые и ошибочные состояния**: список результатов, упавший запуск с incident ID и без чисел, 404 на неизвестный ID, отклонённые параметры ссылки — по имени, без вывода значения.
- **Числа и оси**:
  - округление по ширине интервала: USD 1.7bn, а не USD 1,672.3m (FP-02);
  - absolute включает 0, change и percent симметричны около 0 (FP-09).
- Launch Center перенесён на Stage 22. Окно Run в Decision Builder ведёт к mock-результатам. Черновик решения при round trip сохраняет свою версию contracts.

### Files

**Новые:**
- contracts (Python): `results.py`, `mock_results.py`, `tests/test_mock_results.py`;
- contracts (данные и TS): `packages/contracts/fixtures/mock/results.json`, `packages/contracts/ts/src/mock-results.ts`;
- web-логика: `apps/web/src/results/*` (repository, series, scale, format, compare, params);
- web-интерфейс: `apps/web/src/components/results/*` (series-style, timeline-chart, timeline-explorer, result-figures, result-header, result-list, compare-table), страницы `app/timeline/page.tsx`, `app/timeline/[resultId]/page.tsx`, `app/compare/page.tsx`, `app/compare/[resultId]/page.tsx`;
- тесты: `apps/web/test/results.test.ts`, `apps/web/e2e/results.spec.ts`;
- документы: `docs/adr/0014-result-model-and-charts.md`, `docs/stages/06-screens/*.png` (33 снимка), этот отчёт.

**Изменены:**
- contracts: `__init__.py`, `export.py`, `version.py`, сгенерированные schema, каталог и TS;
- web:
  - `tokens.css` и `color-tokens.ts` — цвета серий и их контраст;
  - `globals.css` — стили графиков;
  - `sections.ts` — Timeline и Compare доступны, Launch Center перенесён на Stage 22;
  - `breadcrumbs.ts` — «Result»;
  - `form.ts` и `decision-builder.tsx` — версия contracts;
  - `run-dialog.tsx`;
- тесты: `pages.spec.ts`, `interaction.spec.ts`, `navigation.test.ts`;
- конфигурация: `package.json`, `pyproject.toml` (знак «×» для ruff), `eslint.config.mjs`, `.prettierignore`;
- документы: ADR README, README, CHANGELOG.

### Tests

Все команды запущены локально (Windows 11) 2026-10-28.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **135 passed** (18 новых: результаты и mock-генератор) |
| vitest contracts / web | 4 / **158 passed** (24 новых: 19 — модель результата, 4 — контраст цветов серий, 1 — хлебные крошки) |
| contracts drift | schema 0.4.0, demo-компании, каталог, mock-результаты, TS — up to date |
| Playwright на 1440 / 768 / 390 | **279 passed, 9 skipped** (по замыслу); 81 новый |
| Палитра серий, валидатор dataviz (тёмная поверхность, все пары) | lightness band, chroma, CVD ΔE 9.3 (худшая пара), normal-vision ΔE 17.5, контраст ≥ 3:1 — все PASS |

Что проверяют новые тесты:

| Проверка | Где |
|---|---|
| Тот же seed даёт те же числа (SIM-01); нулевой эффект = baseline на каждом пути (SIM-02) | pytest |
| У двух результатов с одним seed baseline-квантили совпадают; квартал, кончившийся на cutoff, но поданный позже, идёт в прогноз | pytest |
| 9 видов сломанного результата отклоняются (waterfall не складывается, p10 > p50, demo «calibrated», mock вне demo, failed с числами…) | pytest |
| KPI — та же точка, что последняя точка серии (FR-RE-07); change берёт парные разности, не разность полос | vitest, e2e |
| Оси: absolute с нулём, change симметричен; округление по ширине интервала | vitest, e2e |
| CSV: предупреждение в первой строке, `_DEMO`, ровно точки графика с точными значениями | vitest, e2e (скачивание файла) |
| Совместимость: R&D и CAPEX — сопоставимы и парны, другой cutoff и упавший запуск — блок | vitest, e2e |
| Легенда скрывает серию и не перекрашивает остальные; клавиатура End/Home/Escape; hover с единицами | e2e |
| Percent выключен для net debt с причиной | vitest, e2e |
| Failed с incident ID без графика; 404; небезопасные параметры | e2e |
| axe WCAG 2.2: 0 нарушений на `/timeline`, результате, failed, `/compare`, сравнении и на режиме change с открытой таблицей | e2e |
| Нет горизонтального скролла на 390 px | e2e |

**Визуальная проверка по снимкам** (`docs/stages/06-screens/`) нашла 6 дефектов, все исправлены:

| Дефект | Исправление |
|---|---|
| В сравнении третья колонка обрезалась на desktop: место занимала боковая панель | Таблица на всю ширину, панель ниже |
| В хлебных крошках «Details» | «Result» |
| На 390 px подписи кварталов налезали друг на друга, последняя обрезалась | Шаг подписей от ширины (~72 px на подпись), крайние выровнены внутрь |
| Подпись «Forecast (mock)» пряталась под меткой Synthetic | Метка вынесена в строку над графиком, подпись прогноза — у его начала |
| В гистограмме и waterfall текст на 390 px был около 7 px | Уже viewBox и крупнее шрифт; подписи waterfall над полосами, а не в отдельной колонке |
| Подпись «Baseline» в гистограмме EBITDA обрезалась у правого края | Выравнивание внутрь графика |

Полный gate нашёл одну настоящую ошибку: после повышения версии contracts JSON round trip черновика решения подменял его версию на текущую. Теперь форма хранит версию самого черновика, это нужно и для миграций на Stage 07.

Четыре падения e2e были ошибками самих тестов:
- hover не прокручивал страницу к графику;
- «Mode» находился в скрытом меню;
- на телефоне карточный вид таблицы прячет строку заголовков;
- тест навигации ждал старый этап Launch Center.

### Measured results

Финансовых и ML-метрик нет: все числа на графиках — mock. Факты фикстуры:
- 4 результата: 3 завершённых, 1 упавший;
- 500 путей, 12 кварталов;
- история Northwind на cutoff 2022-12-31 — 11 кварталов.

### Known limitations

- **Только mock-результаты.** Это не прогноз и не модель: Monte Carlo — Stage 22, модели — Phase C. EV — 10 × trailing EBITDA, иллюстрация. В mock-FCF нет процентов и налогов.
- **«Plot snapshots» — это PNG-снимки в `docs/stages/06-screens/`.** Автоматического пиксельного сравнения нет: visual regression baselines — Gate A (Stage 08).
- **Подсказки к столбцам гистограммы — SVG `<title>`.** С клавиатуры их не открыть; все значения есть в таблице «Bins as a table».
- **На телефоне tooltip закрывает часть графика**, пока активен.
- **Сравнение двух результатов парно только при одном seed.** Это отмечено на экране.
- **Сохранения результатов и сравнения с историей нет** — это Stage 07.
- **Проверено только в Chromium.** Проверки со screen reader не было.

### Decisions

- ADR-0014: contract результата с парными разностями; одна модель данных для графика, KPI, таблицы, CSV и сводки.
- Waterfall на средних.
- Цвета серий — ступени палитры docs/10 внутри lightness band.
- Оси с нулём.
- Launch Center → Stage 22.
- Свой SVG вместо библиотеки графиков.

### Next prompt

`07_EXPERIMENT_LIBRARY.md` — только по команде владельца.

## 5. Acceptance

| Критерий промпта 06 | Evidence | Статус |
|---|---|---|
| Baseline / alternate A / alternate B, граница history / forecast | Timeline, снимки `timeline-chart-*` | ✅ |
| Revenue / EBITDA / FCF / debt / EV | Переключатель метрик, contract | ✅ |
| Interval bands, distributions, waterfall, annotated event timeline | Полосы, гистограммы, waterfall, лента событий, маркер решения | ✅ |
| Только явно помеченные mock data | `mock: true`, бейджи, метка на графике, CSV, trust-шапка | ✅ |
| Absolute / percent / delta, hover с единицами, source tooltip, legend toggles | e2e-тесты | ✅ |
| Таблица-альтернатива, mobile compact layout, empty / error results, CSV export | e2e-тесты, снимки на 390 px | ✅ |
| Значения графика = KPI, без независимой генерации | `kpisFromChart`, vitest и e2e | ✅ |
| Подписи интервалов: quantile, calibration status, модельная условность | Подпись под графиком, trust-шапка, сводка | ✅ |
| Оси, без misleading zoom, подписи на 390 px, клавиатура и screen reader summaries | Правила осей, e2e, визуальная проверка | ✅ |
| Plot snapshots, interaction tests, descriptions | `06-screens/`, `results.spec.ts`, этот отчёт | ✅ (снимки без автоматического сравнения) |

`17_ACCEPTANCE_MATRIX`:
- **SIM-01** и **SIM-02** (seed и парные шоки) проверены на mock-генераторе;
- **UX-03** (таблица и CSV у каждого графика) выполнен для timeline.

Формально все пункты остаются **TODO** до gate и реального движка.
