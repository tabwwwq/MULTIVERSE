# ADR-0012 — Доступ к данным компаний через репозиторий (будущий API adapter)

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 04

## Контекст

На Stage 04 Universe Explorer и Company Dossier работают на синтетических fixtures (D-01), а реальные данные появятся только после SEC-пайплайна (Stage 10–12). Если страницы будут читать fixtures напрямую, переход на API потребует переписать каждую из них.

## Решение

- Страницы зависят только от интерфейса `CompanyRepository` (`apps/web/src/companies/repository.ts`). Фабрика `getCompanyRepository()` сегодня отдаёт `createFixtureRepository()`; на Stage 10–12 её заменит HTTP-адаптер с тем же интерфейсом.
- Методы и будущие endpoints:

| Метод | Endpoint (`docs/09`) | Возвращает |
|---|---|---|
| `search(query)` | `GET /api/v1/companies?query=&sector=&country=&status=&coverage=` | `CompanyHit[]`: компания, статус поддержки, покрытие выручки, совпадение |
| `getDossier(id)` | `GET /api/v1/companies/{id}/dossier` | `CompanyDossier` или `null` |
| `facets()` | `GET /api/v1/companies/facets` | сектора, страны, всего компаний |
| `listIds()` | `GET /api/v1/companies?fields=id` | ID для статической генерации досье |

- Ответы описаны contracts (`CompanyDossier` и вложенные модели, ADR-0008), поэтому fixtures и API обязаны совпадать по форме и правилам.
- Репозиторий объявляет `dataOrigin`: интерфейс показывает бейдж Synthetic, пока он не `empirical`.
- Маршрут досье — по stable `company_id`, никогда по тикеру. Неизвестный ID — 404.
- Point-in-time фильтр (`buildDossierView`) работает на клиентской стороне поверх досье на последнюю дату. Когда появится PIT warehouse (Stage 12), cutoff перейдёт в параметр API (`as_of`), а функция останется для проверки.

## Как проверяется

`apps/web/test/companies.test.ts` (поиск, фильтры, PIT, параметры URL), `apps/web/e2e/companies.spec.ts` (страницы поверх репозитория), `packages/contracts/python/tests/test_demo_fixtures.py` (fixtures валидны по contracts).

## Последствия

Новый источник данных реализует интерфейс и добавляет свой contract test. Fixtures остаются для тестов и demo-режима.

## Отвергнутые альтернативы

- Импорт fixtures прямо в страницы: переход на API трогает каждую страницу.
- Mock HTTP-сервер для fixtures: лишний процесс и сеть ради статичных данных.
