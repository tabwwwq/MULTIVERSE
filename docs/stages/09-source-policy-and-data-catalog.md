# Stage 09 — Source policy и Data Catalog

| Поле | Значение |
|---|---|
| Этап | 09 — Source policy и Data Catalog |
| Дата | 2026-10-29 |
| Статус | REVIEW |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/09_SOURCE_POLICY_AND_DATA_CATALOG.md` |
| Основание | `docs/04` (источники, слои, SEC operational contract), `docs/12` (licence management, data card), `docs/09`, PRD FR-MO-01 (Data Catalog: coverage, freshness, lineage, license), NFR-SEC-01, `17_ACCEPTANCE_MATRIX` DATA-05 |

## 1. Scope

Каталог источников **только из метаданных**: ни одного байта данных не загружается. Автоматические загрузки остаются выключенными (`MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=false`) до решения владельца. Результат — проверяемый каталог, реестр рисков, приоритет первых компаний и секторов, план загрузки.

## 2. Подзадачи

| # | Подзадача | Результат |
|---|---|---|
| 1 | Перепроверить официальную документацию 2026-10-29 | SEC APIs, fair access, FSDS, Notes data sets, политика сайта SEC; FRED API, terms, real-time periods, release dates; ECB Data Portal API и usage policy; World Bank API v2, базовые вызовы, terms for datasets, WDI archives |
| 2 | Contract `SourceCatalog` (contracts 0.6.0) | Источники, наборы данных, словарь полей, лицензия, ключ, rate limit, повторы, checksums, revision semantics, решение о загрузке, риски, рубрика, кандидаты, план |
| 3 | Содержимое каталога и генератор | `python -m multiverse_contracts.source_catalog` → `catalog/sources.json`, проверка drift |
| 4 | Реестр рисков | Регион и GAAP, survivorship, пропуски XBRL-тегов, квартализация, restatements, время публикации, валюты и масштаб, terms of use и др. |
| 5 | Приоритет секторов и 10 компаний | По пригодности (рубрика), не по известности; метаданные сверены вручную по submissions SEC |
| 6 | Data Catalog в web-приложении | `/data-catalog` с поиском и фильтром доступа, страница источника со словарём, страница плана |
| 7 | ADR-0016 | Каталог как contract, gate загрузок, политика resale |
| 8 | Тесты | pytest (инварианты и отказы), vitest (поиск, параметры URL), e2e (поиск, фильтр, ссылки, axe) |

## 3. Риски этапа

| Риск | Мера |
|---|---|
| Описание API устарело | Каждое утверждение — из официальной страницы, проверенной в этот день; дата `verified_on` в каталоге |
| Бесплатный API принят за свободную лицензию | Отдельные поля: категория доступа, ключ, redistribution, resale; resale по умолчанию «не предоставлено» |
| Случайная загрузка | Нет кода загрузки; решение по каждому источнику `awaiting_owner_decision`; тест проверяет, что одобренных нет |
| Выдуманные факты о компаниях | В каталоге только сверенные поля (CIK, SIC, конец года, категория filer); всё остальное помечено «ожидается, проверить на Stage 10–11» |

## 4. Отчёт этапа

### Done

- **Документация перепроверена 2026-10-29** на официальных страницах. Результат записан в каталог с датой `verified_on`:
  - SEC: EDGAR APIs, fair access, политика сайта, Financial Statement Data Sets, Financial Statement and Notes Data Sets, шаблоны адресов архивов;
  - FRED: series/observations, terms of use, real-time periods, release dates, series/vintagedates, series;
  - ECB: обзор API и запросы данных Data Portal (прочитаны в браузере: автоматический запрос получил 503), usage policy ESCB;
  - World Bank: Indicators API, базовые вызовы, Terms of Use for Datasets, WDI archives.
- **Contract `SourceCatalog`** (contracts 0.6.0), содержимое в `source_catalog.py`, генератор `catalog/sources.json` встроен в `contracts:gen` и `contracts:check`. В каталоге:
  - 4 источника и 12 наборов данных;
  - 73 поля в словаре данных, у каждого роль для point-in-time: идентификатор, период, knowledge time, значение, единица, ревизия;
  - 21 ссылка на официальную документацию.
- **Три вида доступа разделены:**
  - public access: SEC, ECB, World Bank;
  - free API key: FRED;
  - licensed: цены с выбывшими компаниями и corporate actions, транскрипты звонков. Поставщик не выбран, использование не раньше V3.
- **Resale отдельно от доступа:**
  - SEC и FRED — «not granted»;
  - ECB и World Bank — «allowed by licence», с условиями и исключениями для данных третьих лиц.
- **SEC, операционный contract:**
  - declared User-Agent с email (без него настройки не разрешают загрузку);
  - `Accept-Encoding: gzip, deflate`;
  - 2 запроса в секунду при документированных 10;
  - история — из bulk-файлов, которые пересобираются каждую ночь около 03:00 ET, а не циклами API;
  - повторы только для 429/5xx, не больше 3, с backoff и `Retry-After`; при 403 остановка;
  - SHA-256 считаем сами: SEC checksums не публикует.
- **FRED:**
  - vintages через `realtime_start` / `vintage_dates`, `output_type` 2 и 4;
  - даты релизов — без времени суток, поэтому значение используется со следующего дня;
  - серии третьих лиц (`Copyright` в notes) требуют разрешения владельца данных.
- **Реестр рисков — 15 пунктов:**
  - регион и GAAP, survivorship, пропуски XBRL-тегов, квартализация, restatements, время публикации, валюта и масштаб — с вероятностью, влиянием, мерой, способом обнаружения и этапом;
  - также идентификаторы, сегменты, terms of use, блокировка доступа, ошибки в данных, ревизии macro, смена API, объём.
- **Приоритет:**
  - 10 групп секторов: P1, P2, P3 и исключённые — банки, страховщики, REIT, asset managers, blank-check;
  - рубрика из 7 критериев (максимум 26 баллов);
  - 10 компаний ранжированы по пригодности.
- **Метаданные 10 компаний сверены** вручную: 10 страниц SEC submissions открыты в браузере по одной, с паузой. Сверены CIK, SIC, конец финансового года (у всех 1231), категория filer (у всех large accelerated), формы 10-K без 20-F. В каждой строке 4 из 7 критериев проверены, 3 — ожидания.
- **Data Catalog в интерфейсе:**
  - `/data-catalog` — поиск по источникам, наборам, идентификаторам, форматам и полям; работает без JavaScript; фильтр доступа; группы по виду доступа; метка «Downloads off» на каждом источнике;
  - `/data-catalog/[source]` — доступ и ключ, лицензия, лимиты, повторы, checksums, документация, наборы данных со словарём;
  - `/data-catalog/plan` — шаги загрузки, реестр рисков, секторы, рубрика, 10 компаний с предупреждением «реальные компании, данных нет».
- **ADR-0016:** каталог как contract, загрузки по решению владельца, бесплатный доступ ≠ лицензия.
- **Ни одного файла данных не загружено,** кода загрузки нет.

### Data acquisition plan и решения владельца

| Шаг | Что | Объём | Решение владельца |
|---|---|---|---|
| 1 | Разрешить загрузки SEC: User-Agent (имя и email) в `.env`, бюджет диска | — | **D-09** |
| 2 | Submissions 10 кандидатов через API | 10 JSON | входит в D-09 |
| 3 | Company facts 10 кандидатов; размер `companyfacts.zip` — одним HEAD | 10 JSON | входит в D-09 |
| 4 | Нормализация и coverage report на 10 компаниях (Stage 11) | без загрузки | — |
| 5 | Financial Statement Data Sets для исходных vintages, только если шаг 4 покажет нужду | 71 файл, 13 KB — 122 MB каждый | **D-10** |
| 6 | Аккаунт и ключ FRED (создаёт владелец), 6 серий-кандидатов с vintages | ~6 серий | **D-11** |
| 7 | ECB EUR/USD и несколько индикаторов WDI, только если они нужны модели | несколько серий | **D-12** |

Лицензированные данные — не раньше V3 и только по письменным условиям.

### Files

| Файл | Что |
|---|---|
| `packages/contracts/python/src/multiverse_contracts/sources.py` | Contract каталога |
| `packages/contracts/python/src/multiverse_contracts/source_catalog.py` | Содержимое каталога и генератор |
| `packages/contracts/catalog/sources.json` | Сгенерированный каталог |
| `packages/contracts/python/tests/test_sources.py` | 23 теста |
| `packages/contracts/ts/src/sources.ts` | Вход `@multiverse/contracts/sources` |
| `apps/web/src/sources/*` | Подписи, поиск, параметры URL |
| `apps/web/src/components/sources/source-parts.tsx` | Карточки, факты, ссылки на документацию |
| `apps/web/src/app/data-catalog/**` | Три страницы |
| `apps/web/src/components/ui/data-table.tsx`, `globals.css` | Перенос длинного текста в колонке (`wrap`) |
| `apps/web/src/lib/safe-url.ts` | Официальные хосты документации |
| `apps/web/src/navigation/*` | Data Catalog доступен; breadcrumbs «Source» и «Acquisition plan» |
| `apps/web/test/sources.test.ts`, `apps/web/e2e/sources.spec.ts` | vitest и e2e |
| `apps/web/e2e/gate-a.spec.ts`, `pages.spec.ts` | Обход маршрутов включает каталог; 9 разделов в плане |
| `docs/adr/0016-source-catalog.md` | Решение |
| `pipelines/README.md` | Ссылка на каталог и правило загрузок |

### Tests

Все команды запущены локально (Windows 11) 2026-10-29.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **177 passed** (23 новых в `test_sources.py`: инварианты каталога и 12 видов сломанного каталога) |
| vitest contracts / web | 4 / **200 passed** (14 новых: поиск, параметры URL, allowlist ссылок, breadcrumbs) |
| contracts drift | schema 0.6.0, demo-компании, каталог интервенций, **каталог источников**, mock-результаты, TS — up to date |
| Playwright на 1440 / 768 / 390 | **532 passed, 11 skipped** (по замыслу); 42 новых: 24 в `sources.spec.ts`, 18 новых маршрутов в обходе Gate A |

Что проверяют новые тесты:

| Проверка | Где |
|---|---|
| Ни один источник не одобрен для загрузки; `automatic_downloads` = disabled | pytest, vitest |
| Отказ каталога: нет terms, чужой хост, `http://`, resale без лицензии, ключ не согласован с доступом, скорость выше документированной, одобрение без даты, неизвестный источник в риске, неверная сумма баллов, нарушен порядок рангов, загрузки включены, короткий CIK | pytest |
| В каталоге нет email-адресов | pytest |
| Все ссылки документации проходят allowlist официальных хостов | vitest |
| Поиск по полю словаря показывает, где нашлось; все слова в одном источнике; фильтр доступа | vitest, e2e |
| Поиск без JavaScript | e2e |
| Страница SEC: 2 запроса в секунду, 10 документированных, User-Agent, остановка на 403, ссылка с `rel="noopener noreferrer"`, `acceptanceDateTime` в словаре | e2e |
| План: 15 рисков, 10 кандидатов, Celgene без тикера и «Acquired», предупреждение о реальных компаниях | e2e |
| 404 для неизвестного источника; axe 0 нарушений; нет переполнения, ошибок консоли и битых ссылок на всех новых маршрутах | e2e |

Визуальная проверка нашла 2 дефекта, оба исправлены:

| Дефект | Исправление |
|---|---|
| Таблицы рисков и кандидатов не переносили текст: строка описания растягивала таблицу на тысячи пикселей с горизонтальной прокруткой | Колонка `wrap` в общей таблице; колонки плана объединены (вероятность / влияние, мера и проверка) |
| На вложенных страницах каталога breadcrumbs показывали «Details» | «Source» и «Acquisition plan» |

### Measured results

Финансовых и ML-метрик нет. Размер каталога: 4 источника, 12 наборов, 73 поля, 21 официальная ссылка, 15 рисков, 10 групп секторов, 10 кандидатов, 7 шагов плана.

### Known limitations

- **Поля Financial Statement Data Sets** (SUB, NUM) записаны по документации DERA. PDF с определениями таблиц здесь не читается машинно, поэтому список полей проверяется на первой загрузке (Stage 10).
- **Часовой пояс `acceptanceDateTime`** в submissions не подтверждён: значение приходит с суффиксом `Z`. До правил утечки (Stage 10–12) его сверяют со страницей filing index.
- **FRED, ECB и World Bank не публикуют лимиты.** Выбран 1 запрос в секунду; это наш выбор, а не их правило.
- **Страница World Bank Terms of Use for Datasets** при автоматическом чтении отдала общие условия сайта. Лицензия CC BY 4.0 для datasets подтверждена страницей data catalog licences и текстом условий в результатах поиска. Перед загрузкой перечитать вручную.
- **Баллы рубрики частично — ожидания** (история XBRL, пригодность для решений, простота отчётности). Они проверяются на данных.
- **Это не юридическая консультация:** сводки условий короче оригиналов, решение о загрузке принимает владелец.

### Decisions

- Каталог — contract с тестами (ADR-0016); web и будущий API читают один файл.
- Resale по умолчанию «not granted»; лицензированные данные никогда не перепродаются.
- Первые 10 компаний — только с календарным финансовым годом, US GAAP и 10-K; одна выбывшая компания (Celgene) для проверки survivorship.
- Финансовые компании исключены из V2: их отчётность другого вида.
- В таблицах длинный текст переносится (`wrap`), а не растягивает таблицу.

### Next prompt

`10_SEC_RAW_INGESTION.md` — только по команде владельца и после решения D-09.

## 5. Acceptance

| Критерий промпта 09 | Evidence | Статус |
|---|---|---|
| Source catalog до загрузки: официальные URL, лицензии, rate limits, форматы, freshness, provenance, identifiers, revision semantics, data dictionary | `SourceCatalog`, `catalog/sources.json`, страницы источников | ✅ |
| Перепроверена текущая официальная документация | `verified_on` 2026-10-29, 21 ссылка | ✅ |
| SEC EDGAR API, bulk XBRL archives, FRED/ALFRED, ECB SDMX, World Bank | 4 источника, 12 наборов | ✅ |
| Разделены public access, API key, licensed | Группы в каталоге и интерфейсе | ✅ |
| Бесплатный API не считается лицензией на resale | Поле resale и правило contract; тест | ✅ |
| SEC: User-Agent, throttle, nightly bulk, retries, checksums | Страница SEC, тест `test_sec_contract_follows_fair_access` | ✅ |
| FRED: vintage dates и release timestamps | Наборы observations, vintagedates, release dates; даты без времени суток — правило следующего дня | ✅ |
| Structured catalog (metadata only) и source risk register | 15 рисков, все обязательные категории (тест) | ✅ |
| Приоритет 10 компаний и секторов по пригодности | Рубрика, 10 кандидатов, 10 групп секторов | ✅ |
| Catalog searchable | Поиск с JavaScript и без него (e2e) | ✅ |
| Все источники с primary docs | Правило contract и тест; ссылки только на официальные хосты | ✅ |
| Key / licensing status explicit | Поля ключа, redistribution, resale у каждого источника | ✅ |
| Автоматические загрузки не запускаются без решения пользователя | `automatic_downloads: disabled`, все `awaiting_owner_decision`, кода загрузки нет | ✅ |
| Data acquisition plan и остановка | 7 шагов, решения D-09…D-12 | ✅ |

`17_ACCEPTANCE_MATRIX`: **DATA-05** («source coverage transparent») — источники и их условия описаны; coverage по компаниям появится только с данными (Stage 11). Пункт остаётся **TODO**.
