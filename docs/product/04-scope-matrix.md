# MULTIVERSE — Scope matrix V0–V4

| Поле | Значение |
|---|---|
| Документ | Scope matrix, Stage 01, версия 0.1, 2026-10-28 |
| Основание | `docs/01_PRODUCT_VISION.md` §6, `docs/14_ROADMAP.md` |
| Связано | [PRD](01-prd.md) · [Product risks](05-product-risks.md) |

## Версии

| Версия | Название | Этапы | Exit-критерий |
|---|---|---|---|
| **V0** | Documentation only | 00–01 | Спецификации, источники, дизайн, research protocol, prompts, PRD (этот комплект) |
| **V1** | Interactive prototype | 02–08 | Сайт честно работает на явно помеченной синтетике с воспроизводимыми сценариями. Gate A пройден |
| **V2** | Empirical forecasting | 09–18 | PIT-данные, baselines, измеренные out-of-time оценки, model card. Gate B и Gate C пройдены |
| **V3** | Intervention research | 19–23 | Verified events, причинная методология, finance engine, Monte Carlo, DCF. Causal assumptions отделены от прогноза |
| **V4** | Production research workspace | 24–26 | Security и privacy, accounts, Report Studio, case studies, deployment по разрешению владельца |

## Матрица возможностей

Обозначения: ✅ — входит полностью · ◐ — частично или на fixtures / синтетике · — — нет.

| Возможность | V0 | V1 | V2 | V3 | V4 |
|---|---|---|---|---|---|
| PRD, personas, risks, open questions | ✅ | ✅ | ✅ | ✅ | ✅ |
| Monorepo, CI, ADR | — | ✅ | ✅ | ✅ | ✅ |
| Дизайн-система и shell 20 экранов | — | ✅ | ✅ | ✅ | ✅ |
| Поиск компаний и dossier | — | ◐ fixtures | ✅ SEC | ✅ | ✅ |
| Time Machine (as-of) | — | ◐ fixtures | ✅ PIT | ✅ | ✅ |
| Decision Builder: 6 типов действий | — | ✅ | ✅ | ✅ | ✅ |
| Остальные 18 типов из библиотеки сценариев | — | — | — | ◐ по evidence | ◐ |
| Timeline, квантили, Compare | — | ◐ синтетика | ✅ эмпирический прогноз | ✅ | ✅ |
| Research Notebook, ревизии | — | ◐ local storage | ◐ local | ◐ local | ✅ server |
| Экспорт Markdown / CSV + manifest | — | ◐ demo | ✅ | ✅ | ✅ |
| Экспорт PDF, Report Studio | — | — | — | — | ✅ |
| SEC ingestion, XBRL normalization, PIT warehouse | — | — | ✅ | ✅ | ✅ |
| Macro vintages (FRED / ECB / World Bank) | — | — | ✅ | ✅ | ✅ |
| Data Catalog, data card | — | — | ✅ | ✅ | ✅ |
| Baselines (persistence, Ridge, boosting) | — | — | ✅ | ✅ | ✅ |
| Temporal neural net + калибровка | — | — | ✅ если реально лучше baseline | ✅ | ✅ |
| Training jobs: stop / resume / budget | — | — | ✅ | ✅ | ✅ |
| Model Observatory, model card | — | — | ✅ | ✅ | ✅ |
| Event registry с evidence | — | — | — | ✅ | ✅ |
| Causal Map, диагностика идентификации | — | — | — | ✅ | ✅ |
| Financial statement engine | — | ◐ упрощённые формулы demo | ◐ | ✅ | ✅ |
| Paired Monte Carlo | — | ◐ demo, в браузере | ◐ | ✅ сервер | ✅ |
| Valuation Studio (DCF, bridge, WACC × g) | — | — | — | ✅ | ✅ |
| Risk Observatory | — | — | — | ✅ | ✅ |
| Accounts, ownership, GDPR-процессы | — | — | — | — | ✅ |
| 3 портфолио case studies | — | — | — | ◐ | ✅ |
| Публичный deployment | — | — | — | — | ✅ с разрешения |

## Исключения по версиям

| Версия | Явно не входит |
|---|---|
| V1 | Реальные данные SEC и FRED; серверные jobs; аккаунты; PDF; любые эмпирические модели. Demo-компании вымышленные (D-01) |
| V2 | Причинные выводы; valuation; интервенции на реальных моделях (только action-free прогноз); не-USD компании (D-04) |
| V3 | Публичный хостинг; multi-user; price per share (D-06); экзотические counterfactuals без режима FICTIONAL EXPLORATORY |
| V4 | Лицензированные market data; командная работа и marketplaces (P2); локализация RU (P2) |

## Глобальные исключения (вне продукта)

- Инвестиционные и торговые рекомендации.
- Прогноз цены акции и «fair market value».
- Real-time рыночные данные и платные фиды без отдельного решения владельца.
- Native mobile app.
- LLM-нарратив без структурированных событий и ссылок.
- Покрытие «всех компаний мира» до доказанного coverage.
- Автоматические облачные расходы и публикация без разрешения.
