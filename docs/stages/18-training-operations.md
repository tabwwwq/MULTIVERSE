# Stage 18 — Training jobs: start, status, stop, resume

| Поле | Значение |
|---|---|
| Этап | 18 — training operations |
| Дата | 2026-11-05 |
| Статус | REVIEW (CI run 42124978629: 7/7 задач зелёные, commit `3095a35`); ждёт приёмки владельца |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/18_TRAINING_OPERATIONS.md` |
| Основание | `docs/13`, ADR-0003; команды владельца 2026-11-05: «делай дальше и иди к некст шагу», показать прогресс от 1 до 100 |
| Решение | ADR-0026 — training jobs |

## 1. Scope

Долгое обучение вне HTTP-запроса: durable queue, worker с арендой и heartbeat, настоящий checkpoint, stop, pause, resume, бюджеты, реакция на сбои, статус на экране.

Вне этапа:

- Облако и оплата: `cloud_spend_limit_usd = 0`, задачи идут на своей GPU.
- Аутентификация: API слушает только 127.0.0.1, роли — Stage 24.
- Симуляции: те же очереди понадобятся на Stage 22.

## 2. План

| # | Подзадача | Результат |
|---|---|---|
| 1 | Contracts 0.16.0 | `JobRequest`, `JobEstimate`, `JobStatus`, `JobView`, `JobLogLine`, `JobDetail` |
| 2 | Очередь | `multiverse_jobs`: SQLite, идемпотентность, аренда, heartbeat, переходы, журнал без секретов, оценка |
| 3 | Checkpoint | `multiverse_forecast.resumable`: полное состояние, атомарная запись, отказ при несовместимости |
| 4 | Worker | `multiverse_worker.runner`, `training`, команды `run`, `status`, `kill` |
| 5 | API | `/api/v1/jobs`: submit, estimate, approve, pause, stop, resume, logs |
| 6 | Экран | `/models`: статусы, прогресс 0–100%, heartbeat, стоимость, alerts, действия |
| 7 | Приёмка | Сценарии на реальном датасете настоящими процессами |

## 3. Отчёт этапа

### Done

- **Очередь** `multiverse_jobs.store`: SQLite в WAL, транзакция на каждое изменение, таблица разрешённых переходов. Задачи, метрики эпох, журнал и alerts переживают любой процесс.
- **Одобрение до запуска.** Задача ждёт в очереди с оценкой времени, GPU-памяти, диска и стоимости. Worker её не трогает, пока оценка не одобрена.
- **Идемпотентный submit:** тот же ключ и запрос возвращают ту же задачу, другой запрос с тем же ключом — отказ 409.
- **Worker** выходит, когда очередь пуста. Он продлевает аренду из отдельного потока, а потеряв её, перестаёт писать.
- **Checkpoint** с моделью, optimizer, scheduler, всеми RNG, счётчиками и нормализацией. `last.pt` после каждой эпохи, `best.pt` при улучшении, атомарная запись, SHA-256, `weights_only=True`.
- **Resume** отказывает при другом датасете, последовательностях, фолде, признаках, нормализации, архитектуре, размере, dropout, уровнях квантилей или seed.
- **Stop и pause** ждут безопасной точки. **Принудительный kill** предупреждает о потере эпохи и требует `--yes`.
- **Сбои:** потери не число — alert и `failed` без retry; нехватка памяти — retry с половиной batch от checkpoint; прочее — retry, пока есть попытки; отказ проверки — `failed` сразу.
- **Бюджеты** считаются по всем попыткам. Resume нового лимита не даёт. Больше 4 часов — только с `overnight: true`. Платной задаче нужен лимит денег.
- **Журнал** чистится от ключей, токенов, почты и длинных hash до записи.
- **Экран `/models`** (Model Observatory, раньше заглушка): девять статусов, полоса прогресса 0–100%, эпохи, лучшая эпоха, потери, время, лимит, стоимость, попытка, batch, журнал, alerts, предупреждение о молчащем worker, действия по состоянию. Там же честный статус кандидата Stage 17. Браузер можно закрыть: экран только читает состояние и передаёт запросы.
- **Главная страница** больше не говорит «no data yet» и «Planned» про сделанные фазы.

### Files

- **Новые:** `packages/contracts/python/src/multiverse_contracts/jobs.py`; `packages/jobs/` (пакет `multiverse_jobs`, тесты); `packages/forecast/src/multiverse_forecast/resumable.py`, `tests/test_resumable.py`; `services/worker/src/multiverse_worker/runner.py`, `training.py`, `tests/test_runner.py`, `tests/test_training.py`; `services/api/src/multiverse_api/routes/jobs.py`, `tests/test_jobs.py`; `apps/web/src/models/jobs.ts`, `src/components/models/job-board.tsx`, `src/app/models/page.tsx`, `test/models.test.ts`, `e2e/models.spec.ts`; `docs/adr/0026-training-jobs.md`; `docs/stages/18-training-operations.md`, `18-screens/`.
- **Изменённые:** contracts 0.16.0 (схема, TS, каталоги и фикстуры с версией), `neural.py` (цикл обучения по шагам), `neural_run.py`, `services/worker/src/multiverse_worker/main.py`, `services/api/src/multiverse_api/main.py`, `packages/config` (`web_origins`), `pyproject.toml`, `uv.lock`, `apps/web/src/navigation/sections.ts`, `apps/web/src/app/page.tsx`, `apps/web/e2e/gate-a.spec.ts`, `tests/smoke/test_modules.py`, `README.md`, `CHANGELOG.md`, `docs/adr/README.md`.

### Tests

Все команды запущены локально (Windows 11, RTX 4070 Laptop) 2026-11-05.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0**, 6 мин 24 с |
| pytest | **501 passed** (43 новых; на Stage 17 было 458) |
| vitest contracts / web | 4 / **205 passed** (5 новых) |
| contracts drift | schema 0.16.0 и TS — up to date |
| Playwright на 1440 / 768 / 390 | **544 passed, 14 skipped** (15 новых: 5 тестов × 3 размера) |
| ruff, mypy strict, import-linter, secret scan, Prettier | без замечаний (3 контракта import-linter, 0 нарушено) |

- **`packages/jobs/tests/test_store.py`** (CI): повторный submit, ожидание одобрения, один worker на задачу, потеря молчащего worker, исчерпание попыток, состояние переживает соединения, запросы стоп и пауза, запрос во время проверки, бюджет после resume, retry и batch, журнал без секретов, оценка и отказы.
- **`services/worker/tests/test_runner.py`** (CI, trainer-заглушка без PyTorch): полный прогон, стоп и продолжение, пауза, бюджет времени и денег, NaN, нехватка памяти, retry до конца попыток, отказ, потерянная аренда, выход при пустой очереди.
- **`services/worker/tests/test_training.py`** (CI): задача без датасета, с чужим hash, без последовательностей, протокола или фолда отклоняется.
- **`services/api/tests/test_jobs.py`** (CI): оценка до задачи, идемпотентность по HTTP, запросы, 404, 409, 422, CORS только для своего web.
- **`packages/forecast/tests/test_resumable.py`** (где установлен PyTorch): стоп и resume побайтно равны непрерывному обучению, отказ по каждому полю совместимости, меньший batch допустим, повреждённый checkpoint отклоняется, сбой записи оставляет прежний файл, cleanup.
- **`apps/web/test/models.test.ts`** и **`e2e/models.spec.ts`:** все статусы названы, действия зависят от состояния, сервис выключен, прогресс, одобрение, молчащий worker, alert, axe.

### Measured results

**Приёмочные сценарии: реальный датасет, настоящие процессы API и worker, RTX 4070 Laptop.** Задача: GRU, фолд 2026, `hidden=64`, seed 20261030, до 80 эпох. Вся серия заняла 6 мин 5 с.

| # | Сценарий | Результат |
|---|---|---|
| 1 | Задача без одобрения | Worker её не взял, статус `queued`; остановлена до старта |
| 2 | Непрерывный прогон | 15 эпох, лучшая 7, 45 с; checkpoint `d22a5ab8c2a6…` совпал с обучением Stage 16 |
| 3 | Stop после эпохи 6, resume | Те же потери на всех эпохах, тот же SHA-256 checkpoint |
| 4 | Pause после эпохи 5, другой worker не трогает, resume | Тот же SHA-256 |
| 5 | Kill worker во время эпохи 8 | Статус остался `running`, новый worker до конца аренды ничего не взял, после него продолжил с checkpoint: попытка 2, те же потери, тот же SHA-256 |
| 6 | Лимит времени 3 с | `stopped` после эпохи 1: `budget: runtime limit of 3 s reached` |
| 7 | Лимит денег 3 USD при 3600 USD/час | `stopped` после эпохи 1: потрачено 26,45 USD условно |
| 8 | Чужой hash датасета | `failed` на первой попытке, alert, без retry |
| 9 | 20 000 с без `overnight` | 409 |
| 10 | Тот же ключ: другой запрос / тот же запрос | 409 / 200 |

Сценарии 3–5 — главное доказательство: остановка в любой из трёх форм не меняет результат ни на бит.

**Экран с настоящим API в настоящем браузере.** Собранный web и работающий API: 8 задач, прогресс 0, 1, 1, 100, 100, 100, 100, 0, ноль ошибок в консоли на 1440 и 390 px. Resume и Stop через кнопки дошли до API и вернулись новым статусом. Снимки: `18-screens/models-1440.png`, `18-screens/models-390.png`.

**Оценка против факта.** Для этой задачи оценка 34,7 с, факт обучения около 15 с плюс 30 с загрузки данных: 45 с. Память: PyTorch зарезервировал 224 МБ на пике. Контекст CUDA в оценку не входит.

**Обучение Stage 16 не изменилось** после разбиения цикла на шаги: контрольное обучение совпало по SHA-256.

### Known limitations

- **Бюджет проверяется только в безопасных точках.** Перерасход — до одной эпохи и загрузки данных: сценарий 6 при лимите 3 с остановился на 29,5 с, сценарий 7 условно потратил 26,45 USD при лимите 3 USD. Для дорогих задач лимит надо ставить с запасом; настоящий платный запуск запрещён.
- **Загрузка данных (около 30 с) считается временем задачи** и повторяется при каждой попытке.
- **Время между последней эпохой и kill теряется** в `elapsed_seconds`: учёт обновляется после эпохи.
- **Память CUDA не проверена в бою.** Реакция на нехватку памяти проверена инъекцией исключения, настоящий OOM не вызывался: задача занимает 224 МБ из 8 ГБ.
- **Одна машина.** SQLite не годится для нескольких хостов.
- **API без аутентификации,** только 127.0.0.1. Экран тоже рассчитан на локальный запуск.
- **Экран опрашивает API каждые 2 секунды,** журнал читается при открытии. Потокового режима нет.
- **Один тип задачи:** обучение одного фолда. Полный протокол из многих фолдов пока запускается командой `evaluate`, а не задачами.
- **Воспроизводимость побайтная только на этой машине.**
- **Кандидат Stage 17 не подписан.** Откат модели и её продвижение на экране не сделаны: продвигать нечего.

### Decisions

- Очередь — SQLite, а не брокер: одна машина, ноль новых сервисов (ADR-0026).
- Новый пакет `multiverse_jobs`, чтобы API не импортировал обучение.
- Источник правды — база задач, а не код выхода процесса.
- Бюджет считается по всем попыткам вместе.
- Добавлен статус `stop_requested`.
- Worker завершается при пустой очереди; `--watch` только по просьбе.

### Next prompt

`19_CORPORATE_EVENT_ONTOLOGY.md` — только по команде владельца. Сначала нужны решения владельца: приёмка Stage 16–18 и подпись пакета `model-20261028-9ce4d4180aa9`.

## 4. Acceptance

| Критерий промпта 18 | Evidence | Статус |
|---|---|---|
| Отдельные workers и durable state | `multiverse_jobs`, `multiverse_worker` | ✅ |
| Параметры: модель, hash данных, seed, устройство, эпохи, runtime, spend, owner | `JobRequest` | ✅ |
| Оценка ресурсов и одобрение до запуска | `JobEstimate`, сценарий 1 | ✅ |
| Durable queue, idempotent submit | Тесты, сценарий 10 | ✅ |
| Heartbeat, потоковый журнал без секретов | Аренда; журнал по курсору, опрос раз в 2 с; `redact` | ✅ |
| Настоящий checkpoint: модель, optimizer, scheduler, RNG, нормализация; best и last | `resumable.py`, тесты | ✅ |
| Graceful stop, pause/resume, предупреждение о kill | Сценарии 3–5 | ✅ |
| Отказ при несовместимой схеме | Тест на каждое поле | ✅ |
| Браузер может закрыться | Экран только читает; worker — отдельный процесс | ✅ |
| Статусы UI, heartbeat, время, метрики, стоимость | `/models`, e2e | ✅ |
| Retry, OOM recovery, NaN alert, budget stop, early stopping, cleanup | `runner.py`, `resumable.clean`; OOM — инъекцией | ✅ |
| Small authorized test run | Сценарий 2, команда владельца | ✅ |
| Controlled stop/resume from checkpoint | Сценарии 3, 4 | ✅ |
| Forced worker failure | Сценарий 5 | ✅ |
| Idempotency checks | Сценарий 10 | ✅ |
| Cost guardrails | Сценарии 6, 7, 9 | ✅ |
| No unintended overnight training | Выход при пустой очереди, лимит 4 часа | ✅ |
