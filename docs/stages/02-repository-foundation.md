# Stage 02 — Monorepo foundation

| Поле | Значение |
|---|---|
| Этап | 02 — Monorepo foundation |
| Дата | 2026-10-28 |
| Статус | REVIEW — ждёт приёмки владельцем |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/02_REPOSITORY_FOUNDATION.md` |
| Основание | `docs/03_SYSTEM_ARCHITECTURE.md`, `docs/11_VALIDATION_AND_TESTING.md`, Stage 01 (`docs/product/`) |

## 1. Scope

Только фундамент репозитория: структура модулей, contracts, composition root, профили окружения, границы зависимостей, версионирование, ADR, quality gates и smoke tests. Бизнес-логика (финансы, данные, модели, UI) **не** реализуется. Модули, которые появятся позже, получают пустой каркас с описанием ответственности и номером этапа.

Состояние до начала: в `pred/multiverse/` только `CHANGELOG.md` и `docs/` (Stage 00–01). Чужой работы нет, перезаписывать нечего.

## 2. Подзадачи

| # | Подзадача | Измеримый результат |
|---|---|---|
| 1 | Workspace: npm workspaces (TypeScript) + uv workspace (Python) | `uv sync --all-packages` и `npm install` проходят на чистой машине |
| 2 | Модули: contracts, config, finance, causal, forecast, pipelines, api, worker, web (каркас) | Каждый модуль импортируется, у каждого README с ответственностью |
| 3 | Contracts — единственный источник: Pydantic → JSON Schema → TypeScript | Генерация детерминирована, `contracts:check` падает при расхождении |
| 4 | Composition root и config validation | `create_app()` собирает API из провалидированных Settings, неверный env падает при старте |
| 5 | Границы зависимостей | `lint-imports` (Python) и ESLint (TS) проверяют правила, намеренное нарушение ловится |
| 6 | Strict typing и форматирование | mypy `--strict`, TypeScript `strict`, ruff, Prettier в одной команде |
| 7 | Smoke tests и quality gate | `npm run check` запускает всё и проходит |
| 8 | Secrets hygiene | `.env.example` без секретов, `.gitignore`, тест-сканер секретов, gitleaks в CI |
| 9 | CI | GitHub Actions: Python, TypeScript, contracts drift, secret scan на Ubuntu и Windows |
| 10 | Документация | Root README с запуском на Windows / Linux, ADR-0001…0011, conventions |

## 3. Риски этапа

| Риск | Митигация |
|---|---|
| Тяжёлые зависимости раньше времени (Next.js, torch) | Next.js — на Stage 03. ML-зависимости — только optional extras, по умолчанию не ставятся |
| Дублирование contracts между Python и TS | Один источник (Pydantic), остальное генерируется, drift check в CI |
| Сложный старт для новичка на Windows | Только uv и Node, без make и Docker. Команды проверены в PowerShell |
| Границы модулей только на бумаге | Автоматическая проверка в `npm run check` и CI, проверено намеренным нарушением |
| CI нельзя запустить локально | Честно отмечается: workflow написан, локально прогнаны те же команды |

## 4. Acceptance criteria

- Понятный workspace: дерево и ответственность модулей в README.
- Тестовые команды работают: `npm run check` проходит, результат записан в отчёт.
- Нет секретов: secret scan чистый, `.env` в `.gitignore`.
- Contracts не дублируются: один источник, drift check.
- Прямые границы модулей: import rules проверяются автоматически.

## 5. Отчёт этапа

### Done

- **Workspace:** uv workspace из 8 Python-пакетов (Python 3.12.13, один `uv.lock` на 80 пакетов) и npm workspace (Node 24.15, один `package-lock.json`). Одна командная поверхность — скрипты корневого `package.json`.
- **Модули:** `contracts`, `config`, `finance`, `causal`, `forecast`, `pipelines`, `api`, `worker` — с README, `src`-layout, `py.typed`. `apps/web` — каркас README, Next.js появится на Stage 03.
- **Contracts (ADR-0008):** Pydantic-модели `Quantity`, `Period`, `MetricValue`, `ReproducibilityManifest` и 8 enum'ов закрепляют правила PRD: missing ≠ 0, деньги — decimal-строки, даты с часовым поясом, observed empirical с источником, demo ⇔ synthetic, causal status не повышается автоматически. Генерация: JSON Schema 2020-12 → TypeScript (11 экспортов без дублей), обе с drift check.
- **Composition root:** `multiverse_api.main:create_app(settings)` и `multiverse_worker.main:main()`. Только они читают окружение.
- **Config (ADR-0010):** `Settings` с профилями `local / test / ci / production`, проверками на старте, `SecretStr`, безопасными defaults (загрузки выключены, облачный бюджет 0). `.env.example` — валидная конфигурация (проверено тестом).
- **Границы (ADR-0009):** 3 контракта import-linter (слои; API без forecast / causal / pipelines; domain без веб-фреймворков) + ESLint-правила против относительных межмодульных импортов, deep imports и импорта generated-файлов.
- **Quality gate:** `npm run check` = ruff check + ruff format + mypy strict + lint-imports + pytest + ESLint + Prettier + tsc strict + vitest + contracts drift.
- **CI:** `.github/workflows/ci.yml` — Python и TypeScript на Ubuntu и Windows, contracts drift, gitleaks.
- **Документация:** README (запуск на Windows и Linux, ограничения выше всего остального), ADR-0001…0011, `docs/engineering/conventions.md`, README у каждого будущего модуля.
- **Git:** `git init -b main` по default OQ-17. Коммитов нет.

### Files

106 файлов в `pred/multiverse/` (без `.venv`, `node_modules`, кэшей). Новые на этом этапе:

| Группа | Файлы |
|---|---|
| Корень | `pyproject.toml`, `.python-version`, `uv.lock`, `package.json`, `package-lock.json`, `tsconfig.base.json`, `eslint.config.mjs`, `.prettierrc.json`, `.prettierignore`, `.gitignore`, `.gitattributes`, `.editorconfig`, `.env.example`, `README.md` |
| CI | `.github/workflows/ci.yml` |
| Contracts | `packages/contracts/python/` (`version.py`, `primitives.py`, `metrics.py`, `manifest.py`, `export.py`, `__init__.py`, тесты), `packages/contracts/schemas/contracts.schema.json` (generated), `packages/contracts/ts/` (`scripts/generate.mjs`, `src/index.ts`, `src/generated/*` (generated), тесты), `packages/contracts/fixtures/{valid,invalid}.json` |
| Config | `packages/config/` (`settings.py`, `__init__.py`, тесты) |
| Каркасы domain | `packages/finance/`, `packages/causal/`, `packages/forecast/` (extras `ml`, `boosting`), `pipelines/` |
| Services | `services/api/` (`main.py`, `routes/health.py`, тесты), `services/worker/` (`main.py`, тесты) |
| Межмодульные тесты | `tests/smoke/test_modules.py`, `tests/smoke/test_no_secrets.py`, `tests/contract/test_schema_export.py`, `tests/README.md` |
| Документация | `docs/adr/README.md`, `docs/adr/0001…0011`, `docs/engineering/conventions.md`, README в `apps/web`, `configs`, `data/schemas`, `notebooks/research`, `infra` |

### Tests

Все команды запущены локально (Windows 11, PowerShell и Git Bash) 2026-10-28.

| Проверка | Результат |
|---|---|
| `uv sync --all-packages` на чистом окружении | OK, Python 3.12.13 скачан uv автоматически |
| `uv lock --check`, `npm ci` | OK, lockfiles согласованы |
| `npm run check` (полный gate) | **EXIT 0** |
| ruff check / ruff format | All checks passed |
| mypy strict | Success: no issues found in 18 source files |
| lint-imports | 3 kept, 0 broken |
| pytest | **46 passed** (config 10, contracts 17, api 2, worker 2, contract 4, smoke 11) |
| ESLint, Prettier, tsc strict | без ошибок |
| vitest | **4 passed** (включая type-level тесты и `@ts-expect-error` на число вместо decimal-строки) |
| contracts drift | schema и TS up to date |
| Реальный запуск API (`uvicorn ... --factory`) | `GET /api/v1/health` → `{"status":"ok","service":"multiverse-api","version":"0.1.0","environment":"local","contracts_version":"0.1.0"}`, `/api/docs` → 200 |
| Реальный запуск worker | exit 0, лог профиля |

**Негативные проверки (правила действительно ловят нарушения):**

| Намеренное нарушение | Что поймало |
|---|---|
| `multiverse_api` импортирует `multiverse_forecast` | import-linter: слои BROKEN + ADR-0003 BROKEN |
| `multiverse_finance` импортирует `fastapi` | import-linter: «domain stay free of web frameworks» BROKEN |
| `multiverse_contracts` импортирует `multiverse_config` | import-linter: слои BROKEN (соседи независимы) |
| TS: относительный импорт `../../../../services/...` и deep import `@multiverse/contracts/src/generated/...` | ESLint: 3 ошибки `no-restricted-imports` |
| Ручная правка `src/generated/version.ts` | `gen:check`: «Stale generated files: version.ts» |
| Изменение Python-модели без перегенерации | pytest `test_committed_schema_matches_python_contracts` упал до перегенерации |
| Фейковый ключ длиной 20+ символов, присвоенный переменной `secret` в тесте настроек | сканер секретов нашёл его, тест переписан. Позже сканер так же поймал цитату этого ключа в этом отчёте |
| Опечатка в `.env` (`MULTIVERSE_ALLOW_NETWORK_DOWNLOAD`) | `Settings` отклонил при старте |

Все пробные файлы удалены, после этого gate снова зелёный.

### Measured results

Только инфраструктурные: 46 + 4 теста, 0 нарушений границ, время pytest около 2 s, vitest около 0.2 s. Финансовых и ML-метрик нет: данных и моделей нет.

### Known limitations

- **CI проверен на GitHub** после публикации (2026-10-28, run [40673439972](https://github.com/tabwwwq/MULTIVERSE/actions/runs/40673439972)): все 6 задач `success` — Python и TypeScript на ubuntu-latest и windows-latest, Contracts drift, Secret scan (gitleaks).
- **gitleaks локально не установлен.** Локальный аналог — `tests/smoke/test_no_secrets.py`, он проще gitleaks.
- **Starlette 1.10 предупреждает,** что `httpx` в `TestClient` устарел, и предлагает другой пакет. Этот пакет не проверен, поэтому оставлен `httpx`, а предупреждение отключено точечно в `pyproject.toml` с комментарием.
- **mypy проверяет исходники пакетов, но не тесты.** Тесты проверяет ruff.
- **Межполевые правила contracts есть только в Python.** В TypeScript видны лишь типы. UI-валидация с теми же фикстурами — Stage 05.
- **ML extras (`torch`, `lightgbm`, `scikit-learn`) записаны в lock, но не устанавливались и не тестировались.**
- **Публичный README на английском,** внутренние документы на русском (ADR-0007). Перевод README — по желанию владельца.
- **Лицензия репозитория не выбрана.**

### Decisions

ADR-0007 (tooling), ADR-0008 (contracts), ADR-0009 (границы), ADR-0010 (конфигурация), ADR-0011 (версионирование). ADR-0001…0006 записаны из `docs/03` и связаны с механизмами, которые их проверяют.

### Next prompt

`03_VISUAL_FOUNDATION.md` — design system и frontend shell. Только по команде владельца.

## 6. Acceptance

| Критерий промпта | Evidence | Статус |
|---|---|---|
| Монорепозиторий: web, API, ETL, finance, neural research — отдельные модули | 8 пакетов + `apps/web`, слои import-linter | ✅ |
| Contracts, composition root, environment profiles, dependency boundaries, versioning, ADR | ADR-0007…0011, `create_app`, `Settings`, import-linter, `CONTRACTS_VERSION` | ✅ |
| Root README, project tree, `env.example` без секретов | `README.md`, `.env.example`, тест сканера секретов | ✅ |
| TypeScript strict, Python typing conventions, import rules, config validation, formatter | `tsconfig.base.json`, mypy strict, ruff, Prettier, ESLint, `conventions.md` | ✅ |
| Basic CI, test commands, architecture decisions | `.github/workflows/ci.yml` (зелёный на GitHub, run 40673439972), `npm run check`, ADR | ✅ |
| Без больших зависимостей без нужды, optional ML dependencies | Next.js отложен, torch / LightGBM / scikit-learn — extras | ✅ |
| Воспроизводимый старт Windows / Linux для новичка | README Quick start, проверен вручную на Windows; на Linux и Windows — те же команды с чистой установкой в CI (`uv sync --locked`, `npm ci`) | ✅ |
| Не перезаписывать постороннюю работу | До этапа в `multiverse/` были только Stage 00–01 docs и CHANGELOG, они сохранены | ✅ |
| Smoke tests и quality gates | 46 + 4 теста, `npm run check` EXIT 0 | ✅ |
| Нет секретов, contracts не дублируются, прямые границы модулей | Сканер, drift check, негативные пробы | ✅ |

Пункты `17_ACCEPTANCE_MATRIX` остаются **TODO**. Stage 02 готовит механизмы для SEC-02 (secret scan), SIM-01 (manifest с seed) и REP-01 (manifest с версиями), но эти пункты принимаются только с evidence на своих этапах.
