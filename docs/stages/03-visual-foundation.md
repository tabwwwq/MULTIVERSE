# Stage 03 — Design system и frontend shell

| Поле | Значение |
|---|---|
| Этап | 03 — Design system и frontend shell |
| Дата | 2026-10-28 |
| Статус | REVIEW — ждёт приёмки владельцем |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/03_VISUAL_FOUNDATION.md` |
| Основание | `docs/02_USER_EXPERIENCE.md`, `docs/10_DESIGN_SYSTEM.md`, PRD (`docs/product/01-prd.md`), ADR-0007…0010 |

## 1. Scope

Визуальная система «dark analytical observatory» и общий каркас для 20 будущих экранов в `apps/web`. Реальные функции разделов (поиск компаний, формы решений, графики) — **не** в этом этапе. Нереализованные разделы честно помечены и не изображают готовность.

## 2. Подзадачи

| # | Подзадача | Измеримый результат |
|---|---|---|
| 1 | Next.js + TypeScript strict в `apps/web` | `next build` проходит, контракты из `@multiverse/contracts` используются в UI |
| 2 | Токены: цвет, типографика, отступы, радиусы, тени, motion | Один источник — `src/tokens/tokens.css`; тест проверяет контраст всех текстовых пар ≥ 4.5:1 и границ контролов ≥ 3:1 |
| 3 | Компоненты: Button, Input, Select, Checkbox, Modal, Table, Skeleton, Alert, Badge | Каждый есть на странице `/design-system` во всех состояниях |
| 4 | Trust UX: InferenceModeBadge, SourceBadge, TrustHeader, «Что это НЕ значит», ComingSoon | Режимы и происхождение данных из contracts; статус не передаётся только цветом |
| 5 | Shell: sidebar (сворачиваемый), topbar, breadcrumb, mobile drawer, skip link | 20 разделов в навигации; 3 работают, 17 помечены как планируемые с номером этапа |
| 6 | Страницы: Landing, Methodology, Design system, страница-заглушка раздела, 404 | Нет неработающих CTA: каждая ссылка отвечает 200 |
| 7 | Доступность | axe: 0 нарушений WCAG 2.2 A/AA; клавиатурный проход; reduced motion |
| 8 | Адаптивность | 1440×900, 768×1024, 390×844 без горизонтального overflow |
| 9 | Тесты и CI | vitest (токены, навигация), Playwright (viewport, axe, клавиатура, dialog, drawer, ссылки), задача в CI |

## 3. Риски

| Риск | Митигация |
|---|---|
| «Красивый» shell выдаёт себя за готовый продукт | Заглушки без чисел и контролов, явная пометка этапа, CTA сценария выключен |
| Анимация мешает людям с вестибулярными нарушениями | Одна короткая анимация загрузки, при `prefers-reduced-motion: reduce` — статичное конечное состояние |
| Тёмная тема с недостаточным контрастом | Контраст считается тестом из токенов, а не на глаз |
| Тяжёлые зависимости | Нативные `<dialog>` и popover вместо UI-библиотек; GSAP только для одного hero-момента |

## 4. Acceptance criteria (из промпта)

Нет неработающих CTA; таблица читается на всех ширинах; навигация понятна; нет горизонтального overflow на трёх размерах; focus виден; reduced motion соблюдается; недоступные функции помечены.

## 5. Дизайн-план

### Направление

Бриф (`docs/10`) задаёт палитру, шрифты и настроение: «scientific observatory meets Bloomberg terminal». Палитра и шрифты взяты точно из брифа. Свобода остаётся в композиции, иерархии и в том, где тратится смелость.

**Одна запоминающаяся вещь — hero «расходящиеся вселенные».** Это не декоративная картинка, а грамматика графиков продукта: серо-голубая линия наблюдаемой истории доходит до вертикального маркера решения и расходится на три пути — пунктирный синий baseline, мятная альтернатива A и фиолетовая B, с полупрозрачной полосой квантилей. Вокруг точки ветвления — орбитальное кольцо из логотипа. Одна оркестрованная анимация при загрузке: история прорисовывается, маркер встаёт, ветви расходятся. Всё остальное — тихое и дисциплинированное.

### Токены

| Роль | Значение |
|---|---|
| Canvas / surface / inset | `#07101B` / `#0D1928` / `#102536` |
| Линии: декоративная / граница контрола | `#254255` / `#5B7A90` (добавлен: `#254255` даёт 1.8:1 и не годится для границ полей, нужно ≥ 3:1) |
| Текст / вторичный | `#EEF6F7` / `#91AABA` |
| Серии графиков | observed `#A9BCCB`, baseline `#6389EF` (пунктир), alternate A `#5DEEC9`, alternate B `#AD8CFF` |
| Статусы | warning `#FFC673`, negative `#FF8496`; всегда с текстом и иконкой |
| Шрифты | Space Grotesk — заголовки и крупные числа; DM Sans — текст и интерфейс; tabular numerals для всех чисел |
| Шкала шрифта | 12 / 14 / 16 / 18 / 21 / 24 / 36 / 48 / 60 (классическая шкала Bringhurst) |
| Сетка | базовый шаг 8 px, sidebar 248 px (свёрнутый 72 px), 12 колонок, max width 1500 px |
| Радиусы по иерархии | 6 px контролы, 10 px панели, 16 px только рамка hero |
| Тени | только у top-layer (dialog, drawer); панели отделяются поверхностью и линией, а не тенью |

### Layout

```text
Desktop 1440                                   Mobile 390
+--------+-------------------------------+     +---------------------+
| brand  | breadcrumb          mode chip |     | [=] brand    chip   |
|--------+-------------------------------|     +---------------------+
| nav    |  H1 headline (left aligned)   |     | H1                  |
| groups |  lede                         |     | lede                |
|  ...   |  [hero: diverging timelines]  |     | [hero]              |
|        |  trust header specimen        |     | trust header        |
| [<<]   |  plain lists, no card grid    |     | lists               |
+--------+-------------------------------+     +---------------------+
```

Текст выровнен по левому краю, длина строки ≤ 72 символов. Разделы страницы отделены заголовком и интервалом, а не карточками.

### Принципы

1. Структура несёт информацию: группы навигации — это реальные этапы пути пользователя (Explore → Build → Analyse → Record), нумерация только там, где есть последовательность (фазы разработки).
2. Статус всегда словами: «Demo data», «Planned for Stage 05», а не только цветом.
3. Числа в интерфейсе — tabular, с единицами и валютой.
4. Тишина вокруг hero: один акцентный момент на страницу.

### Проверка плана против шаблонов

| Первая идея | Почему шаблон | Что сделано вместо |
|---|---|---|
| Сетка из 6 одинаковых карточек «возможности» на landing | SaaS-card kit: одинаковые карточки, одна тень | Один живой образец trust-шапки и короткие списки |
| ALL-CAPS подписи над каждым заголовком группы навигации | template chrome | Названия групп обычным регистром, меньшим кеглем |
| Моноширинный шрифт для подписей данных | template chrome | Tabular numerals в DM Sans |
| «→» в тексте кнопок | template chrome | Глагол действия: «Read the methodology» |
| Бесконечная медленная орбита в hero | движение без запроса пользователя, нужен pause | Однократная анимация загрузки около 2 s, затем статика |

## 6. Отчёт этапа

### Done

- **Приложение `apps/web`:** Next.js 16.4 (App Router, Turbopack), React 19.3, TypeScript strict с базовым `tsconfig`, Tailwind CSS 4.3. Все 24 страницы — статические. Типы режимов, происхождения данных и неопределённости берутся из `@multiverse/contracts`.
- **Токены (`src/tokens/tokens.css`):** точная палитра `docs/10`, плюс `line-strong #5B7A90` для границ контролов. Стандартная палитра Tailwind выключена, поэтому в компонентах нет случайных цветов. Шкала шрифта 12–60 px, радиусы по иерархии, тень только у top-layer, easing-токены.
- **Компоненты:** Button / ButtonLink (4 варианта, 2 размера, выключенное состояние с пунктирной рамкой), TextField (подпись, подсказка, ошибка с иконкой, единица измерения), SelectField (нативный `<select>`), CheckboxField, Modal (нативный `<dialog>` + `showModal()`), DataTable (sticky-заголовки, карточки на узкой ширине), Alert (4 тона, иконка + текст), Badge, Skeleton + LoadingRegion.
- **Trust UX:** InferenceModeBadge (4 режима), SourceBadge (observed / forecast / simulated + synthetic), TrustHeader (Mode, Evidence, As of, Model, Uncertainty, Audit ID), NotClaims («Что это НЕ значит»), ChartLegend (грамматика графиков: стиль линии отличается вместе с цветом).
- **Shell:** skip link, сворачиваемый sidebar (248 / 72 px, выбор сохраняется), topbar с хлебными крошками и плашкой «Prototype, demo data only», выдвижное меню ниже 1024 px (popover со свайпом, IntersectionObserver, `inert` на странице, возврат фокуса), footer.
- **Навигация:** 20 разделов информационной архитектуры в 6 группах. 2 работают (Overview, Methodology), 18 запланированных помечены иконкой часов, у них есть подсказка и текст для скринридера с номером этапа. Внизу навигации — подпись «Planned, not built yet».
- **Страницы:** Overview (hero «расходящиеся вселенные», образец trust-шапки, «что не утверждаем», прогресс по фазам), Methodology (уровни вывода, режимы, неопределённость, PIT, таблица источников, ограничения), Design system (все токены с контрастом, рассчитанным при сборке, все компоненты и состояния), заглушка для 18 разделов, 404.
- **Нет неработающих CTA:** «Launch a scenario» выключена и объясняет причину через `aria-describedby`. Все внутренние ссылки отвечают 200 (тест).
- **CI:** новая задача `web` — сборка, установка Chromium, Playwright, отчёт при падении.

### Files

64 новых файла и 9 изменённых. Новые:

| Группа | Файлы |
|---|---|
| Конфигурация приложения | `apps/web/{package.json, next.config.ts, tsconfig.json, postcss.config.mjs, vitest.config.ts, playwright.config.ts}` |
| Токены и утилиты | `src/tokens/{tokens.css, contrast.ts, color-tokens.ts}`, `src/lib/{cn.ts, client-state.ts}` |
| Компоненты | `src/components/ui/*` (7), `src/components/trust/*` (4), `src/components/brand/*` (2), `src/components/charts/chart-legend.tsx` |
| Layouts | `src/layouts/{app-shell, sidebar, nav-links, mobile-nav, breadcrumbs, page-header}.tsx`, `src/layouts/drawer.css` |
| Навигация | `src/navigation/{sections.ts, breadcrumbs.ts}` |
| Маршруты | `src/app/{layout.tsx, globals.css, icon.svg, page.tsx, not-found.tsx}`, `src/app/methodology/page.tsx`, `src/app/design-system/page.tsx`, `src/app/[section]/page.tsx` |
| Тесты | `apps/web/test/{tokens, navigation}.test.ts`, `apps/web/e2e/{pages, interaction}.spec.ts` |
| Evidence | `docs/stages/03-screens/*.png` — 17 снимков: 4 страницы × 3 ширины + меню (768, 390) + диалог (3 ширины) |

Изменены: `package.json` (workspace `apps/web`, скрипты `check:web`, `dev:web`, `build:web`, `test:e2e`), `package-lock.json`, `eslint.config.mjs` (правила Next.js / React / jsx-a11y только для `apps/web`), `.github/workflows/ci.yml`, `.gitignore`, `README.md`, `apps/web/README.md`, `tests/README.md`, отчёт Stage 02 (статус ACCEPTED).

### Tests

Все команды запущены локально (Windows 11) 2026-10-28.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| Python: ruff, mypy strict, lint-imports, pytest | 46 passed, 3 контракта границ kept |
| ESLint (с Next.js core-web-vitals для web), Prettier, tsc strict | без ошибок |
| vitest: contracts | 4 passed |
| vitest: web | **42 passed**: 19 текстовых пар контраста ≥ 4.5:1, 6 пар границ / фокуса ≥ 3:1, палитра совпадает с брифом, 20 разделов, правила статуса, хлебные крошки |
| contracts drift | up to date |
| `next build` | 24 статические страницы |
| Playwright (1440×900, 768×1024, 390×844) | **57 passed, 6 skipped** (тесты sidebar пропускаются ниже 1024 px, тесты меню — на 1440, по замыслу) |

Что проверяет Playwright на каждой ширине:

| Проверка | Как |
|---|---|
| Нет горизонтального overflow | `scrollWidth − clientWidth ≤ 0` на 4 страницах |
| WCAG 2.2 A / AA | axe-core с тегами `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`: 0 нарушений на 4 страницах |
| Клавиатура | skip link — первая остановка Tab и переводит фокус в `<main>` |
| Выключенный CTA | `disabled` и описание «not built yet» |
| Sidebar (1440) | `aria-current="page"`, имена запланированных разделов со статусом, сворачивание с `aria-expanded` и сохранение после reload |
| Меню (768, 390) | открытие, фокус внутри, страница `inert`, Escape закрывает и возвращает фокус; переход по ссылке закрывает меню |
| Dialog | фокус на безопасном действии «Keep editing», Escape закрывает, фокус возвращается на кнопку |
| Motion | при `no-preference` анимация `motif-draw` идёт; при `reduce` — `animation: none`, линия нарисована полностью |
| Таблица | на 390 px — карточки с подписями из `data-label`, на 768 и 1440 — колонки |
| Заглушки | все 18 запланированных разделов отвечают 200, есть «Not built yet», нет таблиц и полей ввода |
| 404 и ссылки | неизвестный путь — 404 со ссылкой назад; все внутренние ссылки — 200 |

**Визуальная проверка по снимкам** выявила и исправила три дефекта:

| Дефект | Исправление |
|---|---|
| Пункты навигации обрезались («Universe Expl…») из-за тега «Stage 04» | Тег заменён иконкой часов, подсказкой и текстом для скринридера; подпись внизу навигации |
| Выключенная кнопка выглядела почти активной | Пунктирная рамка и приглушённый текст у `disabled` |
| На мобильном у скрытых крошек оставались разделители «> >» | Разделители скрыты вместе с крошками ниже 640 px |

### Measured results

Только интерфейсные, посчитаны из `tokens.css`: минимальный контраст текста — 5.35:1 (blue на surface), вторичный текст на canvas — 7.88:1; минимальный контраст границ контролов — 3.46:1 (line-strong на inset). Горизонтальный overflow — 0 px на трёх ширинах, нарушений axe — 0. Финансовых и ML-метрик нет: данных и моделей нет.

### Known limitations

- **Проверено только в Chromium** (Playwright). Firefox и Safari не тестировались. Выдвижное меню использует `scroll-initial-target` и scroll-driven animation с запасными вариантами из гайда, но в Safari вживую не проверено.
- **axe находит не всё:** ручной проход скринридером (NVDA, VoiceOver) не делался. Это часть Gate A (Stage 08).
- **Снимки не сравниваются автоматически.** Visual regression baselines (`toHaveScreenshot`) отложены до Stage 08: они зависят от ОС, и Windows-baseline сломали бы CI на Linux.
- **Производительность не измерялась.** p95 < 2 s и INP < 200 ms из PRD — цели для Stage 08 (Lighthouse / DevTools trace).
- **Шрифты загружаются через `next/font/google` при сборке:** для сборки нужна сеть. В браузер шрифты отдаются с того же домена.
- **GSAP, Lenis и React Bits не использованы.** Hero нарисован CSS-анимацией с `pathLength`: она видна с первой отрисовки, работает без JS и проще соблюдает reduced motion. GSAP оправдан на Stage 06 (переходы между сценариями), React Bits и Lenis — по необходимости, с соблюдением reduced motion.
- **Компонента Tooltip нет:** определения терминов (MethodologyTooltip) понадобятся на Stage 04–06, там стоит взять Popover API по гайду `interest-triggered-tooltips`.

### Decisions

- Нативные `<dialog>` и popover вместо UI-библиотек: меньше зависимостей, доступность из коробки (гайды `dialog`, `navigation-drawer`).
- Состояние на клиенте через `useSyncExternalStore` (`src/lib/client-state.ts`): этого требуют новые правила `react-hooks`, а localStorage подстрахован памятью.
- `next-env.d.ts` не хранится в git, typecheck выполняет `next typegen`.
- Browser-тесты лежат в `apps/web/e2e`, рядом с приложением, которое они запускают.

### Next prompt

`04_COMPANY_EXPLORER.md` — только по команде владельца.

## 7. Acceptance

| Критерий промпта 03 | Evidence | Статус |
|---|---|---|
| Tokens, typography, spacing, elevations, shadows, contrast, form states, chart grammar, provenance badges, responsive grid | `tokens.css`, `/design-system`, `test/tokens.test.ts` | ✅ |
| Component library: layout, sidebar, topbar, breadcrumb, button, input, select, modal, table, skeleton, alert | `src/components`, `src/layouts`, снимки | ✅ |
| Accessibility states, keyboard navigation, reduced motion | axe 0 нарушений, клавиатурные и motion-тесты | ✅ (без ручного прохода скринридером) |
| Не копировать чужой финансовый бренд | Собственный логотип и hero из грамматики графиков | ✅ |
| 1440×900, 768×1024, 390×844 без горизонтального overflow | Playwright на трёх проектах, 12 снимков | ✅ |
| Shell для 20 экранов без имитации готовности | 18 честных заглушек, тест «без данных и полей ввода» | ✅ |
| Структура components / layouts / tokens / tests | `src/components`, `src/layouts`, `src/tokens`, `test`, `e2e` | ✅ |
| Визуальная проверка desktop / mobile, focus, semantic contrast | 17 снимков, 3 дефекта найдены и исправлены | ✅ |
| Недоступные функции помечены или убраны | Часы + подсказка в навигации, выключенный CTA с объяснением | ✅ |
| Никаких неработающих CTA, читаемая таблица, понятная навигация | тест ссылок, адаптивная таблица, полные подписи в навигации | ✅ |

Пункты `17_ACCEPTANCE_MATRIX`: **UX-03** (графики доступны как таблицы) и **UX-04** (demo и empirical различимы) получили компоненты, но принимаются на Stage 06 и 08, когда появятся реальные графики. Все пункты остаются **TODO**.
