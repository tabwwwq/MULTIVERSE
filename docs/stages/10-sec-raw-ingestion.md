# Stage 10 — SEC raw ingestion и source archive

| Поле | Значение |
|---|---|
| Этап | 10 — SEC raw ingestion и source archive |
| Дата | 2026-10-29 |
| Статус | REVIEW |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/10_SEC_RAW_INGESTION.md` |
| Основание | `docs/04` (SEC operational contract, слой raw), `docs/12` (provenance, licence), ADR-0005, ADR-0016, решение владельца **D-09** от 2026-10-29 |
| Решение | ADR-0017 — сырой архив SEC |

## 1. Scope и решение владельца

Решение **D-09** владелец принял в чате 2026-10-29:

- разрешён небольшой sample — submissions и company facts через API для 10 кандидатов каталога — и один HEAD-запрос к `companyfacts.zip`;
- оценка была 20–40 запросов, не быстрее 5 в секунду, меньше 150 MB на диске, жёсткий лимит 200 MB;
- контакт для User-Agent — email владельца. Он записан только в локальный `.env` (`.gitignore`) и не попадает в репозиторий, каталог, manifest и логи;
- bulk-загрузка не разрешена (решение D-10).

Решение записано в каталог: у `sec-edgar` теперь `approved`, область `sample`, дата 2026-10-29. Шаг 1 плана отмечен датой решения. Остальные источники и шаги ждут владельца.

## 2. План

| # | Подзадача | Результат |
|---|---|---|
| 1 | Contracts 0.7.0 | `DownloadDecision.scope` (sample / bulk) и `AcquisitionStep.decided_on`; D-09 в каталоге |
| 2 | Замки загрузки | Переключатель на одну команду, User-Agent с именем и email, решение в каталоге; bulk требует `bulk` |
| 3 | HTTP-клиент | Официальные хосты, throttle 2 запроса в секунду, backoff и `Retry-After`, 403 = стоп, лимит размера |
| 4 | Неизменяемый архив | Файлы по SHA-256, read-only, атомарный перенос, append-only индекс, manifest запуска, `verify` |
| 5 | Коннекторы | Submissions (со страницами старых filings), Company Facts, bulk ZIP (`companyfacts.zip`, `submissions.zip`, квартальный FSDS) |
| 6 | Проверка файлов | JSON и ZIP до попадания в архив |
| 7 | Тесты на fixtures | 429, 5xx, 403, обрыв, неполный ответ, повреждённый ZIP, устаревший кэш, бюджет, восстановление |
| 8 | Sample | HEAD `companyfacts.zip`, затем 10 CIK; coverage report |
| 9 | Web | Бейдж решения с областью, шаг плана «решено», тексты Data Catalog |

## 3. Отчёт этапа

### Done

- **Модуль `multiverse_pipelines.sec`** (ADR-0017):
  - `gate.py` — три замка;
  - `client.py` — HTTP-клиент;
  - `validate.py` — проверка JSON и ZIP;
  - `archive.py` — архив, индекс, manifest, `verify`;
  - `ingest.py` — коннекторы и запуск;
  - `coverage.py` — отчёт по sample;
  - `cli.py` — команды `status`, `sample`, `probe`, `bulk`, `verify`, `coverage`;
  - `cik.py` — CIK из 10 цифр и CIK-число.
- **Отдельные raw connectors** строят адреса по шаблонам каталога:
  - Submissions API: `CIK##########.json` и страницы `CIK##########-submissions-NNN.json`, которые он перечисляет;
  - Company Facts API;
  - bulk: `companyfacts.zip`, `submissions.zip`, квартальные Financial Statement Data Sets `YYYYqN.zip`.
- **Каждый запрос:**
  - declared User-Agent и `Accept-Encoding: gzip, deflate`;
  - один throttle на процесс, 2 запроса в секунду;
  - только `www.sec.gov` и `data.sec.gov` по HTTPS, проверка и после redirect.
- **Повторы:**
  - 429 и 5xx — до 3 повторов, backoff 10 / 20 / 40 с плюс jitter, или `Retry-After`, если он длиннее; `Retry-After` больше 10 минут — отказ без ожидания;
  - оборванное соединение и тело короче `Content-Length` повторяются так же;
  - 403 останавливает весь запуск, и manifest записывается со статусом `aborted`.
- **Файл попадает в архив только после проверки:**
  - JSON разбирается целиком, CIK совпадает;
  - колонки таблицы filings одной длины, у каждого факта есть `accn`, `filed`, `end`, `val`, `form`;
  - ZIP проходит CRC каждого члена, у FSDS есть `sub.txt`, `num.txt`, `tag.txt`, `pre.txt`.
- **Неизменяемый архив** `var/raw/sec/<dataset>/<key>/<sha256>.<ext>`:
  - перенос из `.part` атомарный, файл получает атрибут read-only;
  - одинаковые байты не хранятся дважды, изменившийся файл становится новым объектом;
  - тело хранится как опубликовано: HTTP gzip снят, ZIP остаётся ZIP, сжатие на проводе записано в `content_encoding`.
- **Metadata table** `index.jsonl` — одна строка на файл: URL, SHA-256, размер, `Content-Length`, `Last-Modified`, `ETag`, `downloaded_at` (UTC), run, число filings, последний accession (filing ID) и дата подачи, лицензия, дата проверки terms, версия каталога.
- **Audit manifest** `runs/<run>.json` записывается на каждый запуск:
  - все запросы с исходом `new`, `unchanged`, `not_modified`, `fresh_in_archive`, `stale_response`, `probed` или `failed`;
  - число запросов, повторы включены;
  - решение владельца и скорость.
  - Вместо User-Agent записано имя настройки.
- **Idempotent download и stale cache:**
  - файл, который источник подтвердил за последние 12 ч, не запрашивается;
  - более старый перепроверяется (conditional-запрос, если есть validators);
  - 304 и те же байты ничего не добавляют;
  - ответ с `Last-Modified` старше архивного не сохраняется.
- **Восстановление после прерывания:**
  - `.part` прошлого запуска удаляется при старте;
  - файл без строки индекса принимается после сверки SHA-256;
  - `verify` находит изменённые, пропавшие, доступные для записи и неизвестные файлы.
- **Sample mode и bulk mode:**
  - sample — 10 кандидатов по умолчанию или `--cik`;
  - bulk — только явной командой `bulk` с `--max-mb`; сначала HEAD, и файл больше лимита или бюджета не загружается;
  - сейчас bulk отказывает: в каталоге одобрен только sample.
- **Настройки:** `MULTIVERSE_RAW_DIR` (`var/raw`) и `MULTIVERSE_RAW_BUDGET_MB` (200). Бюджет останавливает запуск до записи файла, который в него не помещается.
- **Contracts 0.7.0:**
  - `DownloadScope`, `DownloadDecision.scope`: область задана ровно тогда, когда решение — approved;
  - `AcquisitionStep.decided_on`: дата есть только у шага, которому нужно решение;
  - описание `automatic_downloads` («только явные команды, ничего по расписанию»).
- **Web:**
  - бейдж «Downloads approved by the owner: sample only» у SEC, у остальных «Downloads off»;
  - шаг 1 плана — «Owner decided on 2026-10-29», шаги 5–7 — «Owner decision needed»;
  - тексты Data Catalog: приложение не показывает данных источников, загруженное лежит в локальном архиве.
- **Документация:** `pipelines/README.md` (команды, раскладка архива, CIK, тикеры, US-GAAP и IFRS, доступ), ADR-0017.
- **Sample загружен** (раздел «Measured results»). Сырые файлы не закоммичены: `var/` в `.gitignore`.

### Пояснения, которые требует промпт

- **US-GAAP и IFRS / foreign filers:**
  - domestic filers сдают 10-K и 10-Q в таксономии `us-gaap`;
  - foreign private issuers сдают 20-F или 40-F и могут отчитываться в `ifrs-full`;
  - V2 берёт только domestic US-GAAP filers. Coverage report считает таксономии и формы 20-F / 40-F / 6-K у каждой компании, а не предполагает их. В sample `ifrs-full` и иностранных форм нет ни у одной из 10 компаний.
- **CIK zero-padding:**
  - API требует 10 цифр с нулями: `CIK0000097476.json`;
  - пути Archives — число без нулей: `/edgar/data/97476/`;
  - в JSON submissions CIK — строка без нулей (`"97476"`), в company facts — целое число;
  - `cik.py` приводит все формы, проверка файла сравнивает CIK как число.
- **Mutable ticker mapping:**
  - тикеры меняются и переиспользуются, поэтому ключ — CIK; тикер — наблюдение с датой (`tickers` в submissions);
  - в sample тикеры совпали с каталогом. У Celgene (поглощена в 2019) тикера нет, последний filing — 2020-07-13.
- **Account permissions:**
  - для чтения EDGAR аккаунт не нужен;
  - аккаунты EDGAR Next (login.gov) нужны для подачи отчётности и здесь не используются;
  - единственная идентификация — declared User-Agent;
  - локально сырые файлы read-only, а `verify` доказывает их целостность.

### Files

| Файл | Что |
|---|---|
| `pipelines/src/multiverse_pipelines/sec/*.py` | Модуль ingestion (10 файлов) |
| `pipelines/tests/test_sec_ingestion.py` | Клиент, архив, коннекторы против fake SEC (`httpx.MockTransport`) |
| `pipelines/tests/test_sec_files.py` | CIK, проверка файлов, замки, coverage, CLI |
| `pipelines/tests/fixtures/sec/*` | Синтетические fixtures и README о том, что они выдуманы |
| `pipelines/pyproject.toml`, `uv.lock` | `httpx` (уже был в lock как dev-зависимость) и `pydantic` — явные зависимости pipelines; новых пакетов нет |
| `pipelines/README.md` | Команды и пояснения |
| `packages/config/src/multiverse_config/settings.py`, `.env.example`, тесты | `raw_dir`, `raw_budget_mb`; комментарий о включении на одну команду |
| `packages/contracts/python/src/multiverse_contracts/sources.py`, `source_catalog.py`, `version.py`, `__init__.py` | Contracts 0.7.0 и D-09 в каталоге |
| `packages/contracts/python/tests/test_sources.py` | D-09, план, 3 новых вида сломанного каталога |
| `packages/contracts/{catalog,schemas,fixtures,ts/src/generated}` | Перегенерировано |
| `apps/web/src/components/sources/source-parts.tsx`, `src/sources/catalog.ts` | Бейдж решения с областью |
| `apps/web/src/app/data-catalog/**` | Тексты и отметка решённого шага |
| `apps/web/test/sources.test.ts`, `apps/web/e2e/sources.spec.ts` | vitest и e2e |
| `docs/adr/0017-sec-raw-archive.md` | Решение |
| `docs/stages/10-screens/` | 18 скриншотов Data Catalog на 1440 / 768 / 390 |

### Tests

Все команды запущены локально (Windows 11) 2026-10-29.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **251 passed** (74 новых: 68 в pipelines, 2 в config, 4 в contracts) |
| vitest contracts / web | 4 / **200 passed** |
| contracts drift | schema 0.7.0, каталог источников, mock-результаты, TS — up to date |
| Playwright на 1440 / 768 / 390 | **529 passed, 14 skipped** (по замыслу, без `SAVE_SCREENS`) |
| ruff, mypy strict, import-linter | без замечаний |

Что проверяют новые тесты. Сеть в них не используется: настоящий HTTP-transport заблокирован, SEC имитирует `httpx.MockTransport`, данные синтетические.

| Случай промпта | Тест |
|---|---|
| 429 | ждёт `Retry-After`, затем успех; слишком длинный `Retry-After` — отказ без ожидания; 429 внутри запуска учтён как лишний запрос |
| 5xx | backoff 10 / 20 / 40 с, затем `RetriesExhausted` после 4 запросов |
| 403 | один запрос, остановка всего запуска, manifest `aborted` |
| Partial response | тело короче `Content-Length` повторяется, `.part` не остаётся; обрезанный JSON отклонён и не попадает в архив |
| Download interruption | обрыв соединения посреди тела повторяется, временный файл удалён; `.part` прерванного запуска удаляется при следующем старте; файл без строки индекса принимается после сверки |
| Corrupted ZIP | CRC-ошибка, обрезанный ZIP, HTML вместо ZIP, нет нужного члена — отказ; в bulk повреждённый ZIP не сохраняется |
| Stale cache | свежий архив — 0 запросов; устаревший — conditional-запрос и 304; те же байты — без дубля; изменившиеся — новый объект; `Last-Modified` старше архивного — не сохраняется |
| Idempotent download | одинаковые байты — один файл и одна строка индекса |
| Замки | переключатель, User-Agent без имени или email, источник без решения, bulk при одобрении sample; CLI `sample` без переключателя и `bulk` при sample — exit 2 без сети |
| Прочее | только официальные хосты и HTTPS, redirect на чужой хост, бюджет, `verify`, битая строка индекса, gzip снят и записан, throttle 0,5 с между запросами (HEAD тоже), адреса из шаблонов каталога, CIK |

Визуальная проверка скриншотов: бейдж «sample only» у SEC, «Owner decided on 2026-10-29» у шага 1, новый текст предупреждений. Без дефектов.

### Measured results

Sample загружен 2026-10-29 после решения D-09. Это измерения, а не оценки.

| Что | Значение |
|---|---|
| HEAD `companyfacts.zip` | 1 запрос; **1 413 044 331 байт** (1347,6 MiB); `Last-Modified: Thu, 29 Oct 2026 04:28:03 GMT` |
| Sample | **34 запроса** за 18,4 с (≈1,85 в секунду при лимите 2); 0 повторов, 0 ошибок |
| Файлы | 34: 10 submissions, 14 страниц старых filings, 10 company facts |
| Объём на диске | **39 370 658 байт** (37,5 MiB) из бюджета 200 MiB |
| Самый большой / маленький файл | 3 937 163 / 31 334 байт |
| Сжатие на проводе | gzip у всех 34; `Content-Length` пришёл у 28 из 34, у остальных chunked |
| `Last-Modified` / `ETag` у API JSON | **нет ни у одного** из 34 |
| Повторный запуск | 0 запросов, 0 новых байт: все 34 `fresh_in_archive` |
| `verify` | 34 файла, 0 проблем |

**Sample coverage** (`python -m multiverse_pipelines.sec coverage`). Строки 1–10 — кандидаты в порядке каталога. «Filings with facts» — число разных accession в company facts.

| # | Company | SIC и FYE как в каталоге | Filings | 10-K | 10-Q | Подачи | us-gaap concepts | Taxonomies | Filings with facts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Texas Instruments | да | 3223 | 28 | 100 | 1994-01 — 2026-10 | 482 | dei, ffd, invest, us-gaap | 72 |
| 2 | Stryker | да | 2875 | 28 | 98 | 1994-02 — 2026-10 | 594 | dei, us-gaap | 69 |
| 3 | AMETEK | да | 2334 | 24 | 79 | 1998-02 — 2026-08 | 528 | dei, srt, us-gaap | 69 |
| 4 | Union Pacific | да | 3650 | 30 | 99 | 1994-01 — 2026-10 | 449 | dei, srt, us-gaap | 71 |
| 5 | Waste Management | да | 3264 | 31 | 96 | 1994-03 — 2026-10 | 646 | dei, ffd, srt, us-gaap | 72 |
| 6 | Celgene (acquired) | да | 2017 | 24 | 75 | 1995-04 — 2020-07 | 627 | dei, invest, us-gaap | 42 |
| 7 | Hubbell | да | 3435 | 27 | 99 | 1994-02 — 2026-10 | 528 | dei, ffd, invest, us-gaap | 67 |
| 8 | Old Dominion | да | 1615 | 29 | 91 | 1996-02 — 2026-10 | 300 | dei, ecd, us-gaap | 66 |
| 9 | American Water Works | да | 1623 | 18 | 57 | 2007-08 — 2026-10 | 599 | dei, invest, us-gaap | 66 |
| 10 | Akamai | да | 2642 | 25 | 80 | 1999-08 — 2026-09 | 546 | dei, ffd, srt, us-gaap | 69 |

Различные периоды в USD из 10-K и 10-Q по черновому списку concepts. Это квартальные, YTD и годовые значения вместе, ещё до квартализации:

| # | revenue | operating income | R&D | operating cash flow | capex | long-term debt | cash |
|---|---|---|---|---|---|---|---|
| 1 | 121 (2007–2026) | 121 (2007–2026) | 113 (2007–2026) | 43 (2008–2026) | 77 (2007–2026) | 63 (2010–2026) | 76 (2006–2026) |
| 2 | 128 (2007–2026) | 111 (2007–2026) | 111 (2007–2026) | 88 (2007–2026) | 88 (2007–2026) | 67 (2009–2026) | 72 (2006–2026) |
| 3 | 122 (2007–2026) | 122 (2007–2026) | 18 (2008–2025) | 62 (2007–2026) | 74 (2007–2026) | 70 (2008–2026) | 75 (2006–2026) |
| 4 | 125 (2007–2026) | 125 (2007–2026) | нет | 57 (2007–2026) | 75 (2007–2026) | 71 (2008–2026) | 76 (2006–2026) |
| 5 | 124 (2007–2026) | 124 (2007–2026) | нет | 66 (2007–2026) | 75 (2007–2026) | 71 (2008–2026) | 76 (2006–2026) |
| 6 | 82 (2007–2019) | 71 (2007–2019) | 3 (2010) | 35 (2007–2019) | 47 (2007–2019) | 39 (2009–2019) | 48 (2006–2019) |
| 7 | 121 (2008–2026) | 107 (2008–2026) | нет | 64 (2008–2026) | 75 (2008–2026) | 67 (2009–2026) | 72 (2007–2026) |
| 8 | 61 (2016–2026) | 115 (2008–2026) | нет | 70 (2008–2026) | 70 (2008–2026) | 66 (2009–2026) | 72 (2007–2026) |
| 9 | 97 (2008–2026) | 122 (2008–2026) | нет | 69 (2008–2026) | 92 (2008–2026) | 67 (2009–2026) | 72 (2007–2026) |
| 10 | 125 (2007–2026) | 110 (2007–2026) | 110 (2007–2026) | 73 (2007–2026) | 73 (2007–2026) | нет | 74 (2006–2026) |

Что видно уже сейчас (вход для Stage 11):

- **Сверка с каталогом:** у всех 10 SIC и конец финансового года совпали с каталогом. Это проверки шага 2 плана, теперь на данных.
- **R&D:**
  - Union Pacific, Waste Management, Hubbell, Old Dominion, American Water Works не отчитываются о нём отдельно. Ни у одной из них в каталоге нет решения `rnd_change`;
  - у AMETEK (`rnd_change` в каталоге) 18 периодов R&D до 2025 — мало для этого решения;
  - у Celgene (`rnd_change`) concept `ResearchAndDevelopmentExpense` встречается только в 2010, то есть R&D записан под другим concept.
  - **Баллы рубрики C5 у AMETEK и Celgene нужно пересмотреть на Stage 11.**
- **Первый запуск coverage показал «нет данных» там, где они есть.** Причина — компании используют другие concepts:
  - `RevenueFromContractWithCustomerIncludingAssessedTax` (Old Dominion, Akamai);
  - `PaymentsToAcquireProductiveAssets` (Hubbell, Waste Management);
  - `LongTermDebtAndCapitalLeaseObligations` (Waste Management, American Water Works, Union Pacific).
  - Они добавлены в черновой список. Выручка Old Dominion до 2016 и долг Akamai (конвертируемые облигации) остаются без concept — это работа карты concepts Stage 11.

### Known limitations

- **API data.sec.gov не отдаёт `Last-Modified` и `ETag`.** Conditional-запросы и проверка «ответ старше архива» работают только для bulk-файлов на www.sec.gov. Для JSON API перепроверка заново загружает файл (gzip, около 1,5 MB на 28 файлов с известным размером), а дубль отсекает SHA-256.
- **Время `Last-Modified` у `companyfacts.zip`** — 04:28 GMT (00:28 ET), а не «около 03:00 ET», как написано в документации SEC. Одно наблюдение; расписание сборки проверяется на следующих HEAD.
- **Список полей FSDS** (SUB, NUM) не проверен на настоящем файле: bulk ждёт решения D-10. Проверка ZIP требует только имена четырёх таблиц.
- **Часовой пояс `acceptanceDateTime`** по-прежнему не сверен со страницей filing index: это лишние запросы вне D-09. Переходит в Stage 11–12.
- **Read-only — защита от случайной записи,** а не от владельца машины; доказательство целостности — `verify`.
- **Coverage считает concepts по черновому списку** и складывает квартальные, YTD и годовые периоды. Это не число годных кварталов: его даст Stage 11.
- **Тесты используют синтетические fixtures** той же формы, что ответы SEC. Форма настоящих ответов подтверждена sample: все 34 файла прошли те же проверки.

### Decisions

- Тело хранится как опубликовано (без HTTP gzip), имя файла — его SHA-256. Байты с провода зависят от сжатия сервера (ADR-0017).
- Индекс — append-only JSONL, manifest — по запуску. Таблицы появятся в хранилище Stage 12.
- `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS` включается на одну команду, а `.env` хранит `false`.
- Область решения владельца — часть contract (0.7.0): sample не открывает bulk.
- Страницы старых filings входят в sample: без них история submissions обрывается на последних 1000 filings.
- Email владельца хранится только в `.env`; manifest хранит имя настройки.

### Next prompt

`11_XBRL_NORMALIZATION.md` — только по команде владельца. Для него не нужно новых загрузок: хватает sample. Bulk (D-10), FRED (D-11), ECB и World Bank (D-12) по-прежнему ждут решений.

## 4. Acceptance

| Критерий промпта 10 | Evidence | Статус |
|---|---|---|
| Раздельные raw connectors: Company Facts, Submissions API, quarterly FSDS | `Connectors.companyfacts`, `.submissions` (+ страницы), `.bulk("fsds", quarter)` | ✅ |
| Доступ к сети и объём оценены заранее: small sample, rate limits, storage, разрешение пользователя | Оценка в вопросе D-09 (20–40 запросов, < 150 MB), факт 34 запроса и 37,5 MiB; 2 запроса в секунду; бюджет 200 MB | ✅ |
| Никакого агрессивного скрейпинга и обхода ограничений SEC | Только API и bulk-адреса каталога, throttle, 403 = стоп, `Retry-After` соблюдается | ✅ |
| Immutable raw object structure, metadata index, checksum, source URL, fetched timestamp, filing ID, original compression | `var/raw/sec/...`, `index.jsonl` (`sha256`, `url`, `downloaded_at`, `latest_filing_id`, `content_encoding`, `file_format`) | ✅ |
| Retries with backoff, idempotent download, validation JSON/ZIP, audit manifest | `client.py`, `archive.store`, `validate.py`, `runs/*.json`; повторный запуск — 0 запросов | ✅ |
| Valid User-Agent с контактом; secrets и config вне Git | `gate.check_user_agent`; email только в `.env` (`.gitignore`), не в manifest (тест) | ✅ |
| Sample mode на группе CIK, bulk только явной командой | `sample`, `bulk --max-mb`; bulk отказывает до решения D-10 | ✅ |
| Пояснены US-GAAP vs IFRS, CIK zero-padding, mutable tickers, account permissions | Раздел «Пояснения», `pipelines/README.md` | ✅ |
| Fixtures и тесты: partial response, 429, corrupted ZIP, download interruption, stale cache | `test_sec_ingestion.py`, `test_sec_files.py` | ✅ |
| Raw files не коммитятся | `var/` в `.gitignore`, `git check-ignore` | ✅ |
| Выход: ingestion module, metadata table, documented commands, small legal sample if authorized, test evidence, sample coverage | Модуль, `index.jsonl`, README, sample по D-09, 74 новых теста, coverage report | ✅ |
| Стоп до normalization 11 | Нормализации нет; coverage только считает | ✅ |

`17_ACCEPTANCE_MATRIX`: **DATA-05** («source coverage transparent») — coverage по 10 компаниям теперь измерен на сырых файлах. Coverage по метрикам и кварталам даст Stage 11, поэтому пункт остаётся **TODO**.
