# Stage 08 — Gate A: аудит frontend

| Поле | Значение |
|---|---|
| Этап | 08 — Gate A: quality audit frontend |
| Дата | 2026-10-29 |
| Статус | ACCEPTED 2026-10-29 (CI run 40904304678: 7/7 задач зелёные). Gate A по тест-кейсам: **PASS** (20 из 20, все P0). Открыто 2 пункта матрицы, где нужен человек: проверка со screen reader (UX-03) и user study (REP-02) |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/08_FRONTEND_TEST_GATE.md` |
| Основание | `docs/10` (design spec, prototype acceptance), `docs/11`, `docs/14` (Gate A), `17_ACCEPTANCE_MATRIX` (UX-01…04, SIM-03, REP-02), PRD NFR-A11Y, NFR-RESP, NFR-PERF-01…03, SYN-01…08, FP-01…09 |
| Release note | `docs/releases/v1-interactive-prototype.md` |

## 1. Scope

Приёмка интерфейса Stage 03–07. Новых крупных функций нет: только тесты, аудит и исправление найденных дефектов. Gate объявляется PASS только если все тест-кейсы приоритета P0 проходят.

## 2. Тест-кейсы

| ID | Проверка | P | Как проверяется |
|---|---|---|---|
| TC-01 | Сквозной путь: поиск компании → cutoff → решение → mock-запуск → сравнение → сохранение → экспорт | P0 | e2e `gate-a.spec.ts` |
| TC-02 | Неподдерживаемая компания: объяснение, без чисел | P0 | e2e (explorer, dossier, builder) |
| TC-03 | Пропуски данных: «—» с причиной, нет базы для относительной единицы | P0 | e2e + vitest |
| TC-04 | Отказы хранилища: private mode, quota, нечитаемые данные | P0 | e2e + vitest |
| TC-05 | Только клавиатура: skip link, путь через builder, диалоги, график | P0 | e2e |
| TC-06 | Имена для screen reader у всех элементов управления, один h1 на странице | P0 | axe на всех маршрутах + проверка заголовков |
| TC-07 | Видимый фокус и его контраст | P0 | e2e: outline ≥ 2px у фокуса; контраст токенов (vitest) |
| TC-08 | Reduced motion | P1 | e2e |
| TC-09 | Вёрстка на 1440 / 768 / 390 без горизонтального скролла на всех маршрутах | P0 | e2e-обход маршрутов |
| TC-10 | Обновление страницы сохраняет состояние (builder, timeline, notebook) | P0 | e2e |
| TC-11 | Доступность графиков: таблица, сводка, клавиатура | P0 | e2e |
| TC-12 | Перевод единиц: % ↔ доля, USD m ↔ USD | P0 | e2e + vitest |
| TC-13 | Stale при смене cutoff | P0 | e2e |
| TC-14 | Метки demo / synthetic / mock на всех страницах с данными | P0 | e2e-обход + аудит текста |
| TC-15 | Нет битых внутренних ссылок | P0 | e2e-обход всех маршрутов |
| TC-16 | Нет ошибок в консоли и ошибок страницы | P0 | e2e-обход всех маршрутов |
| TC-17 | Нет расхождений данных: dossier ↔ builder ↔ fixtures, график ↔ KPI | P0 | e2e |
| TC-18 | Аудит текста: нет устаревших обещаний этапов, нет слов «accuracy» без метрики (FP-04) | P0 | ручной аудит + e2e |
| TC-19 | WCAG 2.2 A/AA (axe) на всех маршрутах и в состояниях с ошибками | P0 | e2e |
| TC-20 | Производительность: вес JS и время загрузки ключевых страниц | P1 | наблюдения (Playwright, production build) |

Маршруты обхода (43): 20 разделов навигации, `/design-system`, 7 dossiers, 7 builder-страниц (по одной на компанию), 4 timelines и 4 compare (все mock-результаты, включая failed). Плюс notebook с сохранённым сценарием.

## 3. Результаты

Прогон 2026-10-29, Windows 11, Chromium (Playwright 1.64), production-сборка (`next build` + `next start`), ширины 1440 / 768 / 390.

| ID | Результат | Evidence |
|---|---|---|
| TC-01 | **PASS** | `gate-a.spec.ts` «the whole journey works» на 3 ширинах: поиск «nwsc» → dossier → cutoff 2022-12-31 → Build a decision → R&D +40% → Validate → Run (JSON `"value": "0.4"`) → Timeline Explorer → Compare → Save to notebook → Export report (`*_r1_DEMO.md`). Нашёл дефект D-01 |
| TC-02 | **PASS** | `companies.spec.ts` «explains an unsupported company and shows no financial values»; `decisions.spec.ts` «explains an unsupported company and shows no form» |
| TC-03 | **PASS** | `companies.spec.ts`: пропуск «—» с причиной, не ноль; значения, ещё не опубликованные на cutoff; кварталы до смены валюты не конвертируются. vitest: `base_unavailable` и `no_rnd_history` |
| TC-04 | **PASS** | `notebook.spec.ts`: private window, полное хранилище, нечитаемые данные не перезаписываются; vitest storage |
| TC-05 | **PASS** | `gate-a.spec.ts`: Validate → фокус на «Validation» → Run → Escape → фокус на Run; Tab до графика и чтение стрелкой. Skip link (`interaction.spec.ts`), слайдер с клавиатуры (`decisions.spec.ts`), диалоги и drawer |
| TC-06 | **PASS** | axe: 0 нарушений на 43 маршрутах × 3 ширины и на notebook со сценарием; ровно один `h1` на каждом маршруте. Lighthouse Accessibility 100 на `/`, timeline, builder. Проверки настоящим screen reader не было (см. Known limitations) |
| TC-07 | **PASS** | 40 стопов Tab в builder: у каждого outline ≥ 2px (mint). Контраст mint ≥ 3:1 на canvas, surface, inset (vitest `tokens.test.ts`). Наблюдение O-1 |
| TC-08 | **PASS** | С `prefers-reduced-motion: reduce` 0 запущенных анимаций на `/`, timeline, builder |
| TC-09 | **PASS** | Горизонтальное переполнение 0 px на 43 маршрутах × 3 ширины |
| TC-10 | **PASS** | Builder: тип и cutoff после reload; Timeline: метрика и режим после reload; Notebook: сохранение → reload → restore (`notebook.spec.ts`) |
| TC-11 | **PASS** | `results.spec.ts`: таблица всех точек, CSV, сводка, чтение с клавиатуры с `aria-live`; axe с открытой таблицей |
| TC-12 | **PASS** | Acquisition 1500 (USD m) → `"value": "1500000000"`; deal costs 2.5% → `"0.025"`; cash 60% → `"0.6"`. vitest: точная десятичная арифметика |
| TC-13 | **PASS** | `decisions.spec.ts` «marks a result stale when the cutoff changes (FR-TM-03)» |
| TC-14 | **PASS** | Бейдж Prototype в шапке на 43 маршрутах; Synthetic / Mock / Demo в самой странице на 22 маршрутах с числами |
| TC-15 | **PASS** | Все уникальные внутренние ссылки со всех маршрутов (больше 40) отвечают 200 |
| TC-16 | **PASS** | 0 ошибок консоли и `pageerror` на 43 маршрутах × 3 ширины и в сквозном пути |
| TC-17 | **PASS** | Builder «Previous R&D budget: USD 944.4m» = сумма R&D за FY2021 Q4…FY2022 Q3 из fixture; выручка FY2022 Q3 в таблице timeline = значение dossier; KPI = сводка графика (`results.spec.ts`, FR-RE-07) |
| TC-18 | **PASS** после исправлений | Ручной аудит нашёл D-02…D-06. Автопроверка на всех маршрутах: нет «arrives in / planned for / planned with / In progress, Stage 03–08» и нет утверждений «accurate / proven» вне оговорок |
| TC-19 | **PASS** | axe на всех маршрутах, плюс состояния ошибок: builder с ошибками, failed run, неподдерживаемая компания, notebook со сценарием |
| TC-20 | **PASS** (наблюдение) | См. «Performance observations» |

**Итог: 20 из 20 PASS, все P0 пройдены → Gate A PASS.**

## 4. Дефекты

| ID | Дефект | P | Статус |
|---|---|---|---|
| D-01 | Universe Explorer: клик по результату в первые 300 мс после ввода отменялся. Отложенный поиск запускал свою навигацию и возвращал на explorer | P2 | Исправлен: при уходе фокуса из поля ожидающий поиск запускается сразу, переход по ссылке идёт после него. Регрессия: TC-01 кликает сразу после ввода |
| D-02 | Overview: выключенная кнопка «Launch a scenario» и текст «builder arrives in Stage 05». Это неправда со Stage 05 | P1 | Исправлен: ссылка «Build a scenario» на Decision Builder и честная пометка про вымышленные компании и mock-результаты |
| D-03 | Overview: фаза A «In progress, Stage 03» | P2 | Исправлен: «final review» |
| D-04 | Design system: пример бейджа «Planned for Stage 05» — этап уже сделан | P2 | Исправлен: «Planned for Stage 22» |
| D-05 | Settings и описание раздела обещали настройки отображения «with Gate A (Stage 08)». Gate A не добавляет функций | P1 | Исправлен: честно «не сделано», в backlog (FR-ST-01) |
| D-06 | Settings: «Delete everything» удаляет «display settings», которых нет. На деле удаляется положение sidebar | P2 | Исправлен текст и диалог подтверждения |

Ошибок P0 не найдено. Ошибки тестов, а не приложения:
- селектор бейджа Prototype находил скрытый мобильный вариант;
- у поля даты последний стоп Tab — кнопка календаря браузера с собственной рамкой фокуса (O-1);
- после остановки фоновой задачи остался процесс `next start` на порту 3100. Playwright переиспользовал его после новой сборки, и первый прогон дал ложные падения. Процесс остановлен, повторный прогон зелёный.

Наблюдения, которые не исправлялись:

| ID | Наблюдение | P | Почему не сейчас |
|---|---|---|---|
| O-1 | Кнопка календаря в поле даты получает белую рамку фокуса браузера, а не mint. Она видна и контрастна | P2 | Косметика: стиль внутренней части браузера |
| O-2 | `docs/10` «prototype acceptance» просит export preview. Есть скачивание CSV и Markdown, предпросмотра нет | P2 | Функция Report Studio (Stage 25) |
| O-3 | `docs/10` упоминает timeout error. Состояние ошибки запуска есть (`worker_lost`, failed run); отдельного примера timeout нет | P2 | Тот же компонент; запуски появятся со Stage 22 |
| O-4 | Notebook рисует список после гидратации (данные в браузере), поэтому его LCP выше остальных: 424 мс медиана | P2 | В пределах бюджета |

## 5. Performance observations

Как мерил: `OBSERVE_PERF=1 npx playwright test performance --project=desktop` (`e2e/performance.spec.ts`). Production-сборка на этом компьютере, холодная загрузка в новом контексте, 10 загрузок на страницу. Сеть сужена через CDP до профиля Lighthouse desktop: 40 мс RTT, 10 Mbit/s. В этой версии Chromium задержка CDP **не применяется к самому HTML-документу**, только к подресурсам (проверено: TTFB не меняется при 0 / 40 / 400 мс). Поэтому к временам ниже нужно прибавить ≈ 40 мс.

| Страница | TTFB медиана | Load медиана / p95 | LCP медиана / p95 | CLS max | JS: сжато / распаковано |
|---|---|---|---|---|---|
| `/` | 6 мс | 345 / 356 мс | 292 / 312 мс | 0 | 147 / 481 KB |
| `/universe` | 20 мс | 349 / 392 мс | 276 / 308 мс | 0 | 152 / 492 KB |
| `/dossier/…` | 34 мс | 344 / 359 мс | 280 / 292 мс | 0 | 149 / 485 KB |
| `/decisions?company=…` | 14 мс | 367 / 386 мс | 280 / 312 мс | 0 | 175 / 573 KB |
| `/timeline/…` | 18 мс | 347 / 366 мс | 280 / 300 мс | 0 | 155 / 501 KB |
| `/compare/…` | 30 мс | 350 / 359 мс | 288 / 304 мс | 0 | 149 / 485 KB |
| `/notebook` | 10 мс | 367 / 386 мс | 424 / 452 мс | 0 | 173 / 566 KB |

Самое долгое взаимодействие (Event Timing, оценка INP), 5 прогонов:

| Взаимодействие | CPU ×1 медиана / max | CPU ×4 медиана / max |
|---|---|---|
| Поиск в Universe Explorer, ввод «north» | 32 / 32 мс | 40 / 48 мс |
| Decision Builder, Validate | 40 / 40 мс | 96 / 104 мс |
| Timeline: метрика, режим, таблица | 32 / 48 мс | 72 / 80 мс |

| Требование | Цель | Измерено | Вывод |
|---|---|---|---|
| NFR-PERF-01 shell | p95 < 2 s, desktop, хорошая сеть | Load p95 ≤ 392 мс (+ ≈ 40 мс документ) | Выполнено локально. Это не RUM: публичного деплоя нет |
| NFR-PERF-02 отклик | INP < 200 ms | max 48 мс (CPU ×1), 104 мс (CPU ×4) | Выполнено |
| NFR-PERF-03 demo run вне main thread | — | Расчёта в браузере нет | Не применимо до Stage 22 |

Lighthouse (через Chrome DevTools, без категории Performance): Accessibility, Best Practices, SEO — 100 на `/` и timeline (desktop) и на builder (mobile).

Самые тяжёлые страницы — builder и notebook (≈ 175 KB JS сжато). Общий shell ≈ 145 KB. Оптимизация не нужна для бюджета; если понадобится — разделить код каталога и валидатора.

## 6. Отчёт этапа

### Done

- 20 формальных тест-кейсов с фактическим результатом; Gate A PASS по всем P0.
- `e2e/gate-a.spec.ts`: обход 43 маршрутов на 3 ширинах (HTTP 200, ошибки консоли, переполнение, один h1, Prototype и Synthetic / Mock / Demo, аудит текста, axe), проверка ссылок, сквозной путь, клавиатура, фокус, reduced motion, refresh, единицы, сверка данных.
- `e2e/performance.spec.ts`: воспроизводимые наблюдения загрузки и взаимодействий (только по `OBSERVE_PERF=1`).
- Исправлены 6 дефектов: 1 в поведении (D-01), 5 в тексте интерфейса (D-02…D-06).
- Release note V1: `docs/releases/v1-interactive-prototype.md`. Git tag и GitHub Release не созданы.

### Files

| Файл | Что |
|---|---|
| `apps/web/e2e/gate-a.spec.ts` | Новый: проверки Gate A |
| `apps/web/e2e/performance.spec.ts` | Новый: наблюдения производительности |
| `apps/web/e2e/interaction.spec.ts` | Тест кнопки запуска заменён проверкой ссылки на Decision Builder |
| `apps/web/src/components/companies/explorer-form.tsx` | D-01 |
| `apps/web/src/app/page.tsx` | D-02, D-03 |
| `apps/web/src/app/design-system/page.tsx` | D-04 |
| `apps/web/src/components/notebook/privacy-settings.tsx` | D-05, D-06 |
| `apps/web/src/navigation/sections.ts` | D-05 |
| `docs/releases/v1-interactive-prototype.md` | Release note V1 |
| `docs/stages/08-frontend-test-gate.md` | Этот отчёт |
| `docs/stages/08-screens/` | 19 скриншотов на 3 ширинах |
| `README.md`, `CHANGELOG.md` | Статус |

### Tests

Все команды запущены локально (Windows 11) 2026-10-29.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **154 passed** |
| vitest contracts / web | 4 / **186 passed** |
| contracts drift | schema 0.5.0, demo-компании, каталог, mock-результаты, TS — up to date |
| Playwright на 1440 / 768 / 390 | **490 passed, 11 skipped**; 160 новых в `gate-a.spec.ts` |

11 skipped по замыслу: 6 тестов sidebar и drawer на неподходящей ширине; 2 обхода ссылок на 768 и 390 (ссылки те же, что на 1440); 3 наблюдения производительности без `OBSERVE_PERF=1`.

### Measured results

Финансовых и ML-метрик нет. Измерены только производительность интерфейса (раздел 5) и счёт тестов.

### Known limitations

- **Проверено только в Chromium.** Firefox и Safari не запускались.
- **Нет проверки настоящим screen reader** (NVDA, VoiceOver, Narrator). Имена и роли проверены через accessibility tree, axe и Lighthouse. Этого требует UX-03; нужна ручная проверка человеком.
- **Нет user study** для REP-02: оговорки видны на странице результата, но то, что их замечают, не проверено.
- **Производительность измерена локально,** не на хостинге и не у пользователей (RUM). Задержка документа добавлена оценкой.
- **Run и Cancel** (UX-02) — только диалог готового сценария. Своих запусков нет до Stage 22.
- Наблюдения O-1…O-4 не исправлялись (P2).

### Decisions

- Gate A PASS объявлен по формальным тест-кейсам. UX-03 (screen reader) и REP-02 (user study) остаются частичными: их не может закрыть автоматическая проверка, решение за владельцем.
- Наблюдения производительности — отдельная спека по флагу, без порогов в CI: время на CI-машинах шумит.
- Release note без git tag: тег и Release — только с разрешения владельца.
- Visual regression baselines не добавлены: шрифты на Windows и Linux CI рисуются по-разному, и сравнение пикселей давало бы ложные падения. Вёрстку проверяют обход маршрутов (переполнение, axe) и скриншоты.
- Из 113 снятых скриншотов в репозитории 19: по каждому экрану и состоянию, на разных ширинах.

### Next prompt

`09_*` (Phase B: data inventory и source gateway) — только по команде владельца.

## 7. Acceptance

| Критерий промпта 08 | Evidence | Статус |
|---|---|---|
| Формальные test cases, фактический PASS/FAIL | Разделы 2–3 | ✅ |
| E2E: search → cutoff → decision → mock run → comparison → save → export | TC-01 | ✅ |
| Unsupported company; missing data; storage failure | TC-02, TC-03, TC-04 | ✅ |
| Keyboard-only, screen-reader names, focus contrast, reduced motion | TC-05…TC-08 | ✅ (names без живого screen reader) |
| 1440 / 768 / 390, refresh, chart accessibility | TC-09…TC-11 | ✅ |
| Unit conversions, stale status, demo badges | TC-12…TC-14 | ✅ |
| Broken links, console errors, data discrepancies | TC-15…TC-17 | ✅ |
| Найденные дефекты и fix priority | Раздел 4 | ✅ |
| Performance observations | Раздел 5 | ✅ |
| Исправить дефекты без рефакторинга чужих файлов | 6 точечных правок | ✅ |
| Release note | `docs/releases/v1-interactive-prototype.md` | ✅ |

`17_ACCEPTANCE_MATRIX`, пункты Gate A:

| Пункт | Требование | Evidence | Статус |
|---|---|---|---|
| UX-01 | Компания, дата, интервенция валидируются | `decisions.spec.ts`, скриншоты `decision-errors-*` | ✅ на синтетике |
| UX-02 | Запуск, отмена, сохранение работают после refresh | Сохранение и restore после refresh ✅; запуска и отмены нет до Stage 22 | ◐ |
| UX-03 | Графики доступны как таблицы, screen-reader check | Таблица, CSV, клавиатура ✅; живого screen reader нет | ◐ |
| UX-04 | Метки demo и empirical различимы | TC-14, аудит текста; `SourceBadge` | ✅ |
| SIM-03 | Вероятности симуляции помечены как условные | «conditional model quantiles, not calibrated» на графиках | ✅ на mock |
| REP-02 | Ограничения видны в точке результата | Видны (TrustHeader, «what this does not mean»); user study нет | ◐ |
