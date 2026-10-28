# Stage 05 — Decision Builder

| Поле | Значение |
|---|---|
| Этап | 05 — Decision Builder с финансово точными контролами |
| Дата | 2026-10-28 |
| Статус | REVIEW — ждёт приёмки владельцем |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/05_DECISION_BUILDER.md` |
| Основание | `docs/07` (intervention accounting, numerical invariants), `docs/08` (scenario definition), `docs/09` (`GET /interventions/types`, `POST /scenarios/validate`), `docs/16` (шаблон типа действия, первые шесть), PRD FR-DE-01…08, FR-TM-03, US-03…05, FC-01…03, FC-05, FC-06 |

## 1. Scope

Форма и contracts для шести типов решений: `rnd_change`, `workforce_restructure`, `acquisition`, `divestiture`, `capex_expansion`, `debt_refinance`. Решение проверяется до запуска и переводится в доллары на выбранную дату знаний компании.

Симуляции на этом этапе нет. Кнопка Run показывает готовность и JSON сценария; demo-результаты появятся на Stage 06, сохранение и история сценариев — на Stage 07.

## 2. Подзадачи

| # | Подзадача | Измеримый результат |
|---|---|---|
| 1 | Contracts 0.3.0: `ScenarioDraft`, шесть моделей решений (discriminated union по `type`), `Magnitude {value, unit}`, `Timing`, распределения (fixed / uniform / triangular), доли финансирования, настройки sensitivity | Pydantic-модели; JSON Schema и TS перегенерированы |
| 2 | Каталог типов действий как единый источник: для каждого параметра единица, жёсткий диапазон, planning range, default и его источник, объяснение механизма | `python -m multiverse_contracts.interventions` пишет JSON; drift check; это ответ будущего `GET /api/v1/interventions/types` |
| 3 | Межполевые правила в contracts | Доли = ровно 100% (decimal), сроки после as-of, эффект внутри горизонта, распределения упорядочены, sensitivity только по неопределённым параметрам, ненулевая величина |
| 4 | Те же правила в web | Общие fixtures `valid.json` / `invalid.json` проходят и в pytest, и в vitest с одинаковыми кодами ошибок |
| 5 | Eligibility по компании и дате | Unsupported, мало истории, нет базы для относительной единицы, выход компании с рынка, OOD, крупная сделка относительно выручки, net cash при рефинансировании |
| 6 | Перевод решения в доллары на as-of | «+40% от R&D» и «+2 p.p. выручки» показываются оба, с базой и датой подачи |
| 7 | Переиспользуемые поля | Число + слайдер + единица, распределение, доли с живой суммой без автонормализации |
| 8 | Reset / Validate / Run, пояснение механизма | Reset возвращает documented defaults; Run активен только без blocking errors |
| 9 | Stale | Смена as-of после проверки помечает результат «Stale — requires rerun», Run выключается |
| 10 | Assumption catalog `/assumptions` | Таблица всех параметров с диапазонами, defaults и источниками |

## 3. Риски

| Риск | Митигация |
|---|---|
| Двусмысленные единицы (+40% бюджета против +40 p.p.) | Единица — часть contract; у R&D единицу нужно выбрать явно; результат показывает обе интерпретации в долларах |
| Defaults выглядят как измеренные данные | У каждого default есть тип источника: правило учёта, ставка закона или placeholder дизайна. Planning range назван design default до Stage 14 |
| Python и TypeScript разойдутся в правилах | Диапазоны берутся из одного каталога; общие fixtures проверяются в обоих языках |
| Деньги через float | Decimal-строки в contracts, точная арифметика на BigInt в web |
| Тихая нормализация долей | Сумма показывается живьём, ошибка у поля, исправляет пользователь |
| Результат на устаревшей дате | Результат проверки хранит as-of и отпечаток решения; любое расхождение помечается |

## 4. Отчёт этапа

### Done

- **Contracts 0.3.0** (`decisions.py`, `distributions.py`, `interventions.py`).
  - `ScenarioDraft`: компания, as-of, горизонт, seed, решение, sensitivity.
  - Шесть моделей решений — discriminated union по `type`.
  - `Magnitude {value, unit}`: единица обязательна.
  - `Timing`: объявление, вступление в силу, лаг, разгон.
  - Распределения: fixed, uniform, triangular.
  - `FundingMix` — для пяти типов, `ProceedsAllocation` — для продажи бизнеса.
  - Нарушение правила несёт код и путь поля, например `[shares_sum] decision.financing: …`.
- **Каталог** (ADR-0013): 6 типов, 26 параметров, 7 вариантов единиц величины. Для каждого параметра:
  - смысл;
  - единица;
  - разрешённый диапазон;
  - planning-диапазон;
  - default и тип его источника.

  Для каждого типа:
  - механизм по трём отчётам;
  - «что это не значит»;
  - уровень доказательств: «unsupported hypothetical» до Stage 20.

  `python -m multiverse_contracts.catalog` пишет `packages/contracts/catalog/interventions.json`, drift check входит в `contracts:check`.
- **Defaults честно подписаны.** Фактов всего два:
  - 0% капитализации R&D (US GAAP, ASC 730);
  - ставка 21% на прибыль от продажи (федеральная ставка США с 2018 года).

  Остальные defaults — design default или placeholder с пометкой «not an estimate». Planning-диапазоны названы design defaults до Stage 14.
- **Правила, одинаковые в обоих языках:**
  - доли ровно 100% (decimal, без автонормализации);
  - объявление не раньше cutoff, вступление в силу не раньше объявления;
  - эффект начинается внутри горизонта;
  - распределения упорядочены и не выходят за диапазон;
  - ненулевая величина;
  - единица из списка типа;
  - у нового долга ставка выше 0;
  - sensitivity только по параметрам с диапазоном, не больше 3.
- **Web-валидатор** (`apps/web/src/decisions/`). Повторяет правила с теми же кодами и путями. Структурный парсер JSON называет ошибки как Pydantic. Чтение формы добавляет коды `required`, `not_a_number`, `not_integer`, `unit_required`. Вся арифметика точная, на BigInt (`src/lib/decimal.ts`).
- **Eligibility по компании и дате:**
  - unsupported (FC-01);
  - нет публичных данных (FC-03);
  - меньше 8 кварталов — только demo (FC-02);
  - нет базы для относительной единицы на cutoff (например, R&D не раскрыт или квартал в CAD);
  - решение вступает в силу после ухода компании с рынка;
  - горизонт заходит за дату ухода;
  - компания не раскрывает R&D;
  - сделка больше двух годовых выручек, CAPEX больше годовой выручки;
  - net cash при рефинансировании;
  - разводнение от нового equity не моделируется (D-06);
  - сегментных данных нет;
  - значение вне planning-диапазона — out of distribution.
- **Решение в долларах на cutoff.** Арифметика на point-in-time цифрах, без модели. «+40% бюджета R&D» показывается и в долларах, и в п.п. выручки, с базой (trailing four quarters) и датой последней подачи. Для сделки — sources = uses, проценты по новому долгу. Для CAPEX — амортизация. Для рефинансирования — изменение процентов и комиссии.
- **Decision Builder** `/decisions`:
  - выбор компании и cutoff;
  - шесть карточек типов;
  - переиспользуемые поля: число + слайдер + единица, распределение, доли с живой суммой;
  - Validate со сводкой ошибок: фокус на результат, ссылки ведут к полям;
  - Reset к documented defaults;
  - Run активен только для свежего валидного решения и показывает JSON сценария с кнопкой скачивания;
  - смена cutoff после проверки даёт «Stale — requires rerun» и выключает Run;
  - нетронутые даты переезжают вместе с cutoff;
  - тип и cutoff сохраняются в ссылке.
- **Assumption Matrix** `/assumptions`: таблица всех параметров по типам с диапазонами, defaults и источниками.
- Из досье есть ссылка «Build a decision for this company», она передаёт выбранный cutoff.

### Files

**Новые:**
- contracts (Python): `decisions.py`, `distributions.py`, `interventions.py`, `catalog.py`, `tests/test_decisions.py`;
- contracts (данные и TS): `packages/contracts/catalog/interventions.json`, `packages/contracts/ts/src/interventions.ts`;
- web-логика: `apps/web/src/decisions/*` (11 модулей: catalog, units, rules, parse, form, context, eligibility, resolve, validate, fields, params), `apps/web/src/lib/decimal.ts`;
- web-интерфейс: `apps/web/src/components/decisions/*` (5 компонентов), `apps/web/src/app/decisions/page.tsx`, `apps/web/src/app/assumptions/page.tsx`;
- тесты: `apps/web/test/decisions.test.ts`, `apps/web/e2e/decisions.spec.ts`;
- документы: `docs/adr/0013-decision-catalog.md`, `docs/stages/05-screens/*.png` (33 снимка), этот отчёт.

**Изменены:**
- contracts: `__init__.py`, `export.py`, `version.py`, общие fixtures (`valid.json` +8, `invalid.json` +17), `test_contracts.py` (проверка кода правила), сгенерированные schema и TS, `ts/package.json`;
- web: `field.tsx` (экспорт оболочки поля, предупреждения у полей), `globals.css` (слайдер), `sections.ts`, страница досье (ссылка);
- тесты: `pages.spec.ts`, `interaction.spec.ts`;
- конфигурация: `package.json` (генерация и проверка каталога), `eslint.config.mjs`, `.prettierignore`;
- документы: ADR README, README, CHANGELOG.

### Tests

Все команды запущены локально (Windows 11) 2026-10-28.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **117 passed** (47 новых: каталог и модели — 22, общие fixtures решений — 25) |
| vitest contracts / web | 4 / **134 passed** (63 новых в `decisions.test.ts`) |
| contracts drift | schema 0.3.0, fixtures (7 компаний), каталог (6 типов), TS — up to date |
| Playwright на 1440 / 768 / 390 | **198 passed, 9 skipped** (по замыслу; 3 новых — съёмка скриншотов только с `SAVE_SCREENS`) |

Что проверяют новые тесты:

| Проверка | Где |
|---|---|
| Каждая из 25 общих fixtures даёт в TS тот же код и путь, что и в Python | vitest |
| JSON round trip: draft → форма → draft совпадает для всех 8 валидных fixtures, по одной на каждый тип и больше | vitest |
| Поля каждой модели равны ключам каталога; defaults каждого типа образуют валидный сценарий | pytest |
| Доли: 300 случайных наборов, сумма ≠ 100% всегда отклоняется; 0.7 + 0.2 + 0.1 = 1 точно (во float это 0.9999999999999999) | pytest, vitest |
| US-03: «40» без единицы → `unit_required` у поля единицы; ссылка из сводки ставит фокус на select; после выбора единицы видны обе интерпретации | vitest, e2e |
| FC-06: R&D +600% → ошибка диапазона; +300% → предупреждение out of distribution, Run доступен | vitest, e2e |
| US-04: 60 / 30 / 5 → «Total 95%. It must be exactly 100%», ошибка, значения не изменены, Run выключен; 60 / 40 / 0 → валидно, JSON в Run содержит `"cash": "0.6"` | vitest, e2e |
| FR-TM-03: смена cutoff после проверки → «Stale — requires rerun», Run выключен; повторная проверка → свежо | vitest, e2e |
| То же решение на разных cutoff даёт разные доллары | vitest |
| Eligibility: Valtrix, Aurora (уход 2021-09-30), Tessaract (6 из 8 кварталов), Kestrel (квартал в CAD), Aurora без R&D | vitest, e2e |
| Reset, объявление до cutoff, дробный лаг, слайдер с клавиатуры (`aria-valuetext` «21 quarters») | vitest, e2e |
| Safe URL: `company=<script>`, неизвестный type и asOf → отклонены по имени, `<script>` не выведен | e2e |
| axe WCAG 2.2: 0 нарушений на `/decisions`, builder, unsupported, `/assumptions`, а также builder с ошибками на экране | e2e |
| Нет горизонтального скролла на 390 px | e2e |

**Визуальная проверка по снимкам** (`docs/stages/05-screens/`) нашла 4 дефекта, все исправлены:

| Дефект | Исправление |
|---|---|
| У цены покупки подсказка «In USD. Negative values are cuts.»: на деле ввод в миллионах, а отрицательные значения запрещены | Подсказка зависит от единицы: «In millions of US dollars: 1000 means USD 1bn.»; про сокращения — только там, где минимум отрицательный |
| axe `link-in-text-block` на `/assumptions`: ссылка в тексте подчёркивалась только при наведении | Постоянное подчёркивание |
| На телефоне JSON в окне Run уходил за край по горизонтали | Перенос строк внутри блока |
| Когда решение готово, Validate и Run обе выглядели основными кнопками | Validate становится вторичной, основной остаётся Run |

Ещё два расхождения нашли тесты; оба раза ошибался тест, а не приложение:
- комментарий в pytest утверждал, что 0.1 + 0.2 + 0.7 во float не равно 1, хотя равно; пример заменён на 0.7 + 0.2 + 0.1;
- e2e ждал у Tessaract 7 публичных кварталов на 2022-12-31, а приложение показало 6, и это верно: отчёт за FY2022 Q4 подан позже cutoff.

### Measured results

Финансовых и ML-метрик нет. Есть только факты каталога и fixtures:
- 6 типов, 26 параметров, 7 вариантов единиц;
- 8 валидных и 17 невалидных общих сценариев.

Доллары в результате проверки — арифметика на синтетических point-in-time цифрах, не прогноз.

### Known limitations

- **Симуляции нет.** Run показывает JSON сценария; demo-результаты — Stage 06.
- **Решение не сохраняется.** После перезагрузки остаются только компания, cutoff и тип из ссылки. Сохранение, история и импорт JSON — Stage 07.
- **Eligibility и перевод в доллары работают только в web.** Серверная версия появится вместе с `POST /api/v1/scenarios/validate`.
- **Почти все defaults — placeholders, planning-диапазоны и пороги относительного размера — design defaults.** Измеренные диапазоны — Stage 14, причинные оценки — Stage 20.
- **Не моделируются:** разводнение, валовой долг (в demo есть только net debt), фонд оплаты труда (это допущение пользователя), сегменты.
- **Форма требует JavaScript.** Страница рендерится на сервере, а проверка выполняется в браузере.
- **Проверено только в Chromium**, проверки со screen reader не было. Поле даты показывает формат локали браузера.

### Decisions

- ADR-0013: каталог как единый источник; одинаковые коды правил в Python и web; eligibility пока в web.
- У R&D нет единицы по умолчанию (US-03): «+40% бюджета» и «+40 п.п. выручки» — разные решения.
- `workforce_restructure` поддерживает и сокращение, и рост штата (docs/16, сценарии 03 и 04).
- Решение принимается на cutoff, поэтому объявление не раньше cutoff. Эффект должен начаться внутри горизонта.
- Run до Stage 06 показывает JSON, а не фиктивный результат.
- Assumption Matrix — справочник только для чтения. Фиксация параметров для парных сравнений перенесена на Stage 22 (Monte Carlo).

### Next prompt

`06_CHARTS_AND_COMPARISON.md` — только по команде владельца.

## 5. Acceptance

| Критерий промпта 05 | Evidence | Статус |
|---|---|---|
| Form и contracts для шести стратегий: action type, magnitude с unit, announcement / effective date, lag, cost, financing, distributions | Модели и каталог, `/decisions`, по одной валидной fixture на каждый тип и больше | ✅ |
| M&A: доли debt / cash / equity и acquisition financing | `FundingMix`, ставка по новому долгу, sources = uses в результате | ✅ |
| Layoffs: severance, savings, productivity risk | `one_off_cost_months`, `savings_realization`, `productivity_loss` | ✅ |
| R&D: incremental spending и adoption delay | Величина в двух единицах → доллары в год, `adoption_delay_quarters` | ✅ |
| Слайдеры однозначны: +40% R&D ≠ +40 п.п. выручки | Единица обязательна, видна у поля и в `aria-valuetext`; результат показывает обе интерпретации | ✅ |
| Industry eligibility, as-of, user warnings | `eligibility.ts`, тесты на 5 компаниях | ✅ |
| Schema validation, cross-field invariants, reset / defaults, reusable inputs, sensitivity configuration, пояснения механизмов | Pydantic + web-правила, Reset, `decision-fields.tsx`, sensitivity, MechanismPanel | ✅ |
| Смена as-of помечает рассчитанные сценарии stale | `freshness()`, e2e «marks a result stale» | ✅ |
| JSON roundtrip, range errors, sum-to-one financing, accessible mobile form, positive / negative tests | vitest round trip, fixtures, property test, axe на 390 px, 25 общих fixtures | ✅ |

`17_ACCEPTANCE_MATRIX`:
- по **UX-01** (компания, дата и интервенция валидируются; e2e и снимки ошибок) и **CAUS-01** (точное определение каждого действия; проверка схемы) теперь есть evidence на fixtures;
- **FIN-03** закрыт только в части financing mix; ограничений долга и денег без финансового движка нет (Stage 21).

Формально все пункты остаются **TODO** до gate.
