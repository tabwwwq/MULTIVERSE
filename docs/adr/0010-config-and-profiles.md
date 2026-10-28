# ADR-0010 — Профили окружения и валидация конфигурации

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 02

## Контекст

Ошибка конфигурации, найденная через час работы job, стоит дороже, чем ошибка на старте. Секреты не должны попадать в логи, git и браузер (PRD SP-01).

## Решение

- `multiverse_config.Settings` (pydantic-settings) читает переменные `MULTIVERSE_*` и необязательный `.env`. Неизвестные ключи в `.env` — ошибка.
- Профили `MULTIVERSE_ENV`: `local`, `test`, `ci`, `production`.
- Безопасные defaults: сетевые загрузки выключены, облачный бюджет `0`, ключей нет.
- Правила на старте: загрузки требуют SEC User-Agent; User-Agent содержит email; `DEBUG` запрещён в `production`; бюджет не отрицательный.
- Секреты — `SecretStr`: не видны в `repr` и JSON-дампе.
- В production API не публикует OpenAPI и docs.
- Web (Stage 03) получает только несекретные `NEXT_PUBLIC_*` переменные из своего `.env.local`.

## Как проверяется

`packages/config/tests/test_settings.py` (включая проверку, что `.env.example` — валидная конфигурация), `services/api/tests/test_health.py` (docs скрыты в production), `tests/smoke/test_no_secrets.py`, gitleaks в CI.

## Последствия

Новая настройка = поле в `Settings` + строка в `.env.example` + тест на её правило.

## Отвергнутые альтернативы

`os.environ.get` по всему коду: нет валидации, нет единого списка настроек.
