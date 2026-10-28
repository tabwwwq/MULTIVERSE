# ADR-0007 — Monorepo: npm workspaces + uv workspace

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 02

## Контекст

Проект двуязычный: web на TypeScript, API, ETL, финансы и ML на Python. Владелец — один разработчик на Windows. Нужен воспроизводимый старт без Docker, make и ручной установки Python.

## Решение

- Репозиторий — `pred/multiverse/` (решение D-00): корень `pred` остаётся хранилищем Obsidian.
- **Python:** uv workspace. Каждый модуль — отдельный пакет со своим `pyproject.toml` и `src/`-layout. Python 3.12 закреплён в `.python-version`, uv скачивает его сам. Один общий `uv.lock`.
- **TypeScript:** npm workspaces (npm уже идёт с Node). Node ≥ 22, проверено на Node 24. Один общий `package-lock.json`.
- **Командная поверхность:** скрипты корневого `package.json` (`npm run check`, `npm run dev:api` и т.д.). Они одинаково работают в PowerShell и bash.
- **Тяжёлые зависимости опциональны:** PyTorch, scikit-learn и LightGBM — extras пакета `multiverse-forecast` (`--extra ml`, `--extra boosting`), по умолчанию не ставятся. Next.js появится на Stage 03.
- **Платформы:** Windows, Linux, macOS arm64 (`[tool.uv] environments`). macOS Intel исключён: PyTorch больше не выпускает для него wheels.

## Как проверяется

`uv sync --all-packages --locked` и `npm ci` в CI на Ubuntu и Windows. Локально: `npm run check`.

## Последствия

Публичный README — на английском (лицо репозитория для международного портфолио, как и UI по D-08). Внутренние документы (`docs/`) — на русском.

## Отвергнутые альтернативы

- pnpm / Turborepo / Nx: дополнительная установка и сложность без выигрыша при одном TS-пакете.
- Poetry: медленнее, нет встроенного управления версиями Python и workspace.
- Docker для локальной разработки: тяжело для новичка на Windows. Контейнеры появятся вместе с очередью (Stage 18).
- Make: нет на Windows по умолчанию.
