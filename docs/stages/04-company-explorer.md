# Stage 04 — Company Explorer и dossier

| Поле | Значение |
|---|---|
| Этап | 04 — Company Explorer и dossier |
| Дата | 2026-10-28 |
| Статус | REVIEW — ждёт приёмки владельцем |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/04_COMPANY_EXPLORER.md` |
| Основание | `docs/02` (Universe Explorer, Company Dossier), `docs/04` (metric mapping, identifiers), `docs/09` (Company, FinancialFact, endpoints), PRD FR-CO-01…05, FR-TM-01…02, FC-01…03, D-01, D-04 |

## 1. Scope

Поиск компаний и их досье на **честно помеченных синтетических fixtures**. Никаких загрузок SEC. Интерфейс доступа к данным готов к замене fixtures на API (Stage 10–12) без переписывания страниц.

## 2. Подзадачи

| # | Подзадача | Измеримый результат |
|---|---|---|
| 1 | Contracts компаний: stable ID, история названий и тикеров, сектор, страна, lifecycle, стандарт отчётности, filings, coverage, quality flags, lineage значения | Pydantic-модели с правилами; JSON Schema и TS перегенерированы; `CONTRACTS_VERSION` 0.2.0 |
| 2 | Синтетические fixtures: 7 вымышленных компаний с разными состояниями | Детерминированный генератор, drift test, каждая запись валидируется contracts |
| 3 | Интерфейс репозитория (API adapter) | `CompanyRepository` + реализация на fixtures; соответствие будущим `/api/v1` endpoints описано в ADR-0012 |
| 4 | Поиск по тикеру (включая бывшие), названию (включая бывшие), CIK; фильтры сектор, страна, lifecycle, coverage | Unit-тесты на сопоставление и параметры; работает без JS (GET-форма) и с живым обновлением |
| 5 | Dossier: Revenue, EBITDA (calculated), FCF (CFO − CAPEX), net debt, R&D; filings; fiscal calendar; валюта; data quality | Missing — «—» с причиной, никогда 0 |
| 6 | Lineage toggletip у каждого значения | Concept, метод преобразования, filing, дата публикации, качество |
| 7 | Состояния: empty, no results, unsupported company, insufficient history, смена валюты отчётности | E2E-тесты на каждое |
| 8 | Safe URL | Параметры по allowlist, длина ограничена, неизвестные значения игнорируются с сообщением; внешние ссылки только на официальные хосты; у синтетики ссылок на filings нет |
| 9 | As-of в dossier | Значения, поданные после выбранной даты, становятся «Not public yet» |

## 3. Риски

| Риск | Митигация |
|---|---|
| Синтетика под видом реальных компаний | Вымышленные названия, тикеры и CIK вне выданного SEC диапазона; бейдж Synthetic; contracts запрещают ссылку на filing у синтетики |
| Выдуманные ссылки на источники | `url = null` для синтетических filings, проверено валидатором |
| Пропуски, похожие на нули | Валидатор MetricValue + отдельный UI-статус missing с причиной |
| Тикер принят за идентификатор | Маршрут dossier по stable company ID; тикеры — история с датами |
| Fixtures разойдутся с contracts | Генератор строит записи через Pydantic, drift test в CI |

## 4. Отчёт этапа

### Done

- **Contracts 0.2.0** (`packages/contracts/python/src/multiverse_contracts/companies.py`, `metrics.py`).
  - `Company`: stable UUID, CIK, история названий и тикеров с датами, сектор, страна, валюта, стандарт, фискальный календарь, lifecycle.
  - Остальные модели: `FilingReference`, `CoverageEntry`, `DataQualityFlag`, `CompanyDossier`, `Lineage`.
  - Правила в валидаторах:
    - периоды названий и тикеров идут по порядку и не пересекаются;
    - у синтетического filing нет ссылки на документ, а ссылка на реальный документ разрешена только на `https://www.sec.gov/`;
    - значение ссылается только на filing из того же досье;
    - суммы — только в валюте отчётности;
    - у неподдерживаемой компании нет значений;
    - у calculated-значения обязательна формула.
- **Схема для TypeScript** экспортируется в режиме serialization (уточнение ADR-0008): поля с default в TS обязательны.
- **Синтетические fixtures.** Генератор `python -m multiverse_contracts.demo` строит 7 вымышленных компаний:
  - 315 значений, из них 33 пропуска с причинами;
  - 65 filings, ни у одного нет ссылки;
  - CIK из диапазона 0099xxxxxx.

  Drift check входит в `contracts:check`.

| Компания | Что показывает |
|---|---|
| Northwind Semiconductors (NWSC) | Смена тикера NWMD → NWSC и названия; пропуск R&D за FY2021 Q3 |
| Halcyon Software (HLCN) | Фискальный год заканчивается 30 июня |
| Meridian Health Devices (MRDN) | 52/53-недельный год; FCF пропущен, потому что CAPEX не раскрыт |
| Aurora Grid Utilities (AGRU) | Куплена 2021-09-30, история сохранена (без survivorship bias); R&D не раскрывается |
| Tessaract Logistics (TSLG) | 7 кварталов — insufficient history (PRD FC-02) |
| Kestrel Instruments (KSTL) | Смена валюты отчётности CAD → USD; FY2020 — пропуски без конвертации |
| Valtrix AG (VLTX) | 20-F, IFRS, EUR — not supported (PRD FC-01) |

- **Интерфейс репозитория** (ADR-0012): `CompanyRepository` с методами `search`, `getDossier`, `facets`, `listIds`. У каждого метода записан будущий `/api/v1` endpoint. Сейчас работает реализация на fixtures.
- **Universe Explorer** (`/universe`).
  - Поиск по тикеру, бывшему тикеру, названию, бывшему названию и CIK (с ведущими нулями и без).
  - Фильтры: сектор, страна, lifecycle, длина истории выручки.
  - Без JS работает GET-форма. С JS результаты обновляются при вводе, фокус остаётся в поле.
  - Есть состояние «ничего не найдено». Счётчик результатов — live region.
- **Company Dossier** (`/dossier`, `/dossier/[companyId]`).
  - Разделы: identity, история тикеров и названий, финансовая история (Revenue, EBITDA (calculated), FCF (CFO − CAPEX), net debt, R&D), coverage, флаги качества, filings, панель «Что это НЕ значит».
  - **Lineage toggletip** у каждого значения: concepts, метод, формула, filing, дата подачи, документ.
  - **As-of:** значение, поданное после выбранной даты, становится «Not public».
  - **Масштаб:** USD m / USD bn.
- **Safe URL.**
  - Параметры проверяются по allowlist.
  - Отклонённые параметры перечисляются только по имени, значение не выводится.
  - Поиск ограничен 64 символами.
  - Неизвестный ID компании — 404.
  - Внешние ссылки разрешены только на официальные хосты по HTTPS, без логина в URL и без порта.
- **Навигация.** Explorer и Dossier доступны. Time Machine перенесён на Stage 12 (сравнение срезов); as-of для одной компании уже есть в досье. Хлебные крошки и подсветка раздела работают для вложенной страницы.

### Files

**Новые:**
- contracts: `companies.py`, `demo.py`, `fixtures/demo/companies.json`, `test_companies.py`, `test_demo_fixtures.py`, `packages/contracts/ts/src/demo.ts`;
- web-логика: `apps/web/src/companies/*` (7 модулей), `apps/web/src/lib/safe-url.ts`;
- web-интерфейс: `apps/web/src/components/companies/*` (6 компонентов), `apps/web/src/app/universe/page.tsx`, `apps/web/src/app/dossier/page.tsx`, `apps/web/src/app/dossier/[companyId]/page.tsx`;
- тесты: `apps/web/test/companies.test.ts`, `apps/web/e2e/companies.spec.ts`;
- документы: `docs/adr/0012-company-repository.md`, `docs/stages/04-screens/*.png` (18 снимков), этот отчёт.

**Изменены:**
- contracts: `metrics.py`, `primitives.py`, `export.py`, `__init__.py`, `version.py`, сгенерированные schema и TS;
- web: `data-table.tsx` (id колонки), `globals.css` (toggletip, подпись таблицы на узкой ширине), `sections.ts`, `breadcrumbs.ts`, `nav-links.tsx`;
- тесты: `pages.spec.ts`, `interaction.spec.ts`, `navigation.test.ts`;
- конфигурация: `package.json` (генерация и проверка fixtures), `pyproject.toml` (ruff разрешает знак «−»), `eslint.config.mjs`, `.prettierignore`;
- документы: ADR-0008, README.

### Tests

Все команды запущены локально (Windows 11) 2026-10-28.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **70 passed**, из них 24 новых: fixtures — 11, правила досье — 13 |
| vitest contracts / web | 4 / **71 passed**, в web 29 новых: поиск, репозиторий, параметры URL, PIT, форматирование, safe URL, вложенные крошки |
| contracts drift | schema 0.2.0, fixtures (7 компаний), TS — up to date |
| Playwright на 1440 / 768 / 390 | **132 passed, 6 skipped** (по замыслу) |

Новые e2e-сценарии (каждый на трёх ширинах):

| Сценарий | Проверка |
|---|---|
| Список | 7 из 7 компаний, предупреждение о синтетике |
| Поиск с клавиатуры | Ввод «nwmd» → 1 результат, «Matched former ticker NWMD, used until 2019-06-30»; фокус в поле; Enter по ссылке открывает досье |
| CIK | «99000106» без нулей находит Kestrel |
| Пустой поиск | «zzzz» → 0 из 7, сообщение и ссылка «Clear search and filters» |
| Неподдерживаемый тикер | «AAPL» → объяснение, что реальных тикеров в demo нет |
| Фильтры | Lifecycle и coverage сужают список до ожидаемых компаний |
| Safe URL | Плохие значения sector, country и status отклонены по имени, `<script>` не выведен; 300 символов поиска → обрезано до 64 |
| Без JavaScript | GET-форма находит Kestrel |
| Досье | Stable ID, история тикеров и названий, крошка «Company profile» |
| Lineage | Toggletip у Revenue FY2022 Q4: `us-gaap:Revenues`, «Fiscal year minus the first nine months», 10-K, «None: this filing is synthetic»; Esc закрывает |
| Missing ≠ 0 | R&D FY2021 Q3 показан как «—», в подсказке причина |
| As-of | Cutoff 2022-06-30: FY2022 Q2 — «Not public on 2022-06-30: filed on 2022-08-…». Cutoff 2021-12-31: FY2021 Q4 ещё не публичен, хотя квартал закончился |
| Масштаб | USD bn — два знака после запятой, `aria-current` |
| Невалидные параметры | `asOf=2099-01-01` и `scale=trillion` отклонены, показан последний срез |
| Смена валюты | Kestrel: флаг CAD → USD, FY2020 — пропуск «Reported in CAD» |
| Unsupported | Valtrix: алерт, нет финансовой истории, в filings 20-F |
| Short history | Tessaract: insufficient history, 7 из 8 кварталов |
| 404 | Неизвестный ID компании |
| axe WCAG 2.2 | 0 нарушений на `/universe`, досье Northwind и Valtrix, `/time-machine` |

**Визуальная проверка по снимкам** (`docs/stages/04-screens/`) нашла 3 дефекта, все исправлены:

| Дефект | Исправление |
|---|---|
| Пустой контейнер алертов давал лишний отступ под заголовком досье | `empty:hidden` |
| На телефоне подсказка lineage прилипала к левому верхнему углу | Явное центрирование, потому что CSS reset убирает стандартные отступы popover |
| В карточном режиме подпись таблицы сжималась в колонку по одному слову | `caption { display: block }` в контейнерном запросе |

Тест масштаба сначала ожидал значение FY2021 Q4 на дату 2021-12-31. Право было приложение: 10-K за этот квартал подан в феврале 2022. Исправлен тест, теперь он проверяет это явно.

### Measured results

Есть только интерфейсные результаты и данные fixtures: 7 компаний, 315 значений, 33 пропуска с причинами, 65 синтетических filings без ссылок. Финансовых и ML-метрик нет.

### Known limitations

- **Данные синтетические.** Реальные компании появятся только после SEC-пайплайна (Stage 10–12).
- **PIT считается в web-слое поверх досье на последнюю дату.** Restatements (original, vintage, latest) и сравнение срезов — Stage 12.
- **Проверено только в Chromium.** Toggletip использует Popover API (Baseline с января 2025). В Safari вживую не проверялся.
- **Проверки со screen reader не было.** Только axe и проверка доступных имён в e2e.
- **Сумма в ячейке хранится как `Number` и служит только для отображения.** Расчёты будут на decimal (Stage 21).
- **Пустые фильтры остаются в URL** (`sector=` и т. п.) при отправке формы. Это безвредно: парсер их игнорирует.
- **Глобальной горячей клавиши для поиска нет:** односимвольный шорткат нарушил бы WCAG 2.1.4.

### Decisions

- ADR-0012: репозиторий как будущий API adapter.
- Уточнение ADR-0008: serialization-схема для TS.
- Time Machine → Stage 12.
- Маршрут досье по stable ID.
- Toggletip вместо hover-tooltip: `interestfor` и `popover="hint"` пока поддерживаются ограниченно.

### Next prompt

`05_DECISION_BUILDER.md` — только по команде владельца.

## 5. Acceptance

| Критерий промпта 04 | Evidence | Статус |
|---|---|---|
| Поиск по ticker / name / CIK, sector, country, lifecycle, coverage | `/universe`, unit- и e2e-тесты | ✅ |
| Dossier: Revenue / EBITDA / FCF / debt, filing references, fiscal calendar, валюта, data quality | `/dossier/[id]`, снимки | ✅ |
| Только честно обозначенные fixtures | Бейджи Synthetic, вымышленные CIK, filings без ссылок (валидатор) | ✅ |
| Stable ID отдельно от ticker aliases, смена названий и листинга | `Company.names` и `listings` с датами, раздел Listing history | ✅ |
| Missingness вместо нулей | Валидатор, «—» с причиной, тест | ✅ |
| Интерфейс будущего API adapter без массовой загрузки SEC | `CompanyRepository`, ADR-0012; сеть не использовалась | ✅ |
| Keyboard search, empty state, unsupported-company state, lineage tooltip, safe URL | e2e-тесты выше | ✅ |
| Тесты на пустой поиск, неподдерживаемый тикер, смену валюты, доступность | `companies.spec.ts`, axe на трёх ширинах | ✅ |
| Фактический состав файлов и скриншоты QA | Разделы Files и Tests, `docs/stages/04-screens/` | ✅ |

`17_ACCEPTANCE_MATRIX`: у **DATA-02** (as-of по `filed_at`) есть механизм и тест на fixtures. Принять его можно только на реальных данных (Stage 12). Все пункты остаются **TODO**.
