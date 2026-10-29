# Release note — V1 Interactive prototype (Gate A)

| Поле | Значение |
|---|---|
| Версия | V1 — Interactive prototype (`docs/product/04-scope-matrix.md`) |
| Этапы | 02–08 |
| Дата | 2026-10-29 |
| Gate | Gate A — см. `docs/stages/08-frontend-test-gate.md` |
| Статус | Кандидат, ждёт приёмки владельца. Git tag и GitHub Release не созданы: только по отдельному разрешению |

Exit-критерий V1: «сайт честно работает на явно помеченной синтетике с воспроизводимыми сценариями. Gate A пройден».

## Что входит

| Раздел | Что работает | Данные |
|---|---|---|
| Overview, Methodology, Design system | Hero, «что MULTIVERSE не утверждает», прогресс этапов, токены и компоненты | — |
| Universe Explorer `/universe` | Поиск по ticker, бывшему ticker, имени и CIK; фильтры; работает без JavaScript | 7 вымышленных компаний |
| Company Dossier `/dossier/[id]` | Идентичность, история листинга, квартальные значения с lineage, cutoff «known as of», масштаб, coverage, качество данных, filings | Синтетика |
| Decision Builder `/decisions` | 6 типов решений, единицы и диапазоны из каталога, Validate, Reset, перевод в доллары на дату cutoff, stale при смене cutoff, Run только для свежего валидного решения | Каталог интервенций |
| Assumption Matrix `/assumptions` | Все параметры с диапазонами, default и источником | Каталог |
| Timeline Explorer `/timeline/[id]` | История и прогноз, полосы p10–p90, маркер решения, crosshair, клавиатура, таблица, CSV | Mock-результаты |
| Universe Compare `/compare/[id]` | KPI, waterfalls, распределения парных разниц, блокировка несовместимых сравнений | Mock-результаты |
| Research Notebook `/notebook` | Сценарии, неизменяемые revisions, restore, дубль, сравнение, отчёты Markdown с manifest и SHA-256, импорт и экспорт JSON | Только это устройство |
| Settings & Privacy `/settings` | Что хранится на устройстве, удаление всего | Только это устройство |

## Отличия от scope matrix V1

Владелец принял каждое отличие на своём этапе. Они записаны здесь, чтобы V1 не обещал больше, чем есть.

| Пункт матрицы V1 | Что сделано | Где будет |
|---|---|---|
| Time Machine (as-of) ◐ fixtures | Cutoff одной компании в Company Dossier и Decision Builder; отдельного экрана нет | Stage 12 |
| Paired Monte Carlo ◐ demo, в браузере | Нет запуска своих решений. Run показывает сценарий JSON и ведёт к фиксированным mock-результатам | Launch Center, Stage 22 |
| Financial statement engine ◐ упрощённые формулы demo | Формулы есть только в генераторе mock-результатов (Python), не в интерфейсе | Stage 21 |
| Экспорт Markdown / CSV + manifest ◐ demo | CSV графиков и отчёт Markdown с manifest; предпросмотра экспорта нет | Report Studio, Stage 25 |
| Настройки отображения FR-ST-01 (P1) | Не сделаны: у каждого числа есть единица, у Company Dossier свой масштаб | Backlog |

## Проверки Gate A

Полный gate `npm run check`, Playwright на 1440 / 768 / 390 с axe WCAG 2.2, обход всех 43 маршрутов, сквозной путь пользователя, клавиатура, обновление страницы, единицы, расхождения данных, ссылки, ошибки консоли. Результаты, дефекты и наблюдения производительности — в отчёте Stage 08.

## Ограничения

- **Все компании и числа вымышлены.** Реальные данные SEC появятся с Stage 10. Каждая страница помечена Prototype и Synthetic, Demo или Mock.
- **Нет моделей и симуляции.** Результаты — фиксированные mock-пути из генератора, не прогноз и не причинная оценка.
- **Notebook только в этом браузере.** Нет аккаунтов и синхронизации; JSON-экспорт — единственная копия.
- **Проверено в Chromium** (Playwright и Lighthouse). Ручной проверки со screen reader (NVDA, VoiceOver) и в Firefox и Safari не было.
- **Производительность измерена локально** на production-сборке, не на хостинге: публичного деплоя нет.

## Как запустить

```bash
uv sync --all-packages
```

```bash
npm install
```

```bash
npm run dev:web
```

Откройте <http://localhost:3000>. Полная проверка — `npm run check` (см. `README.md`).
