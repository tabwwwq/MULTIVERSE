# Stage 07 — Research notebook и ревизии сценариев

| Поле | Значение |
|---|---|
| Этап | 07 — Research notebook и ревизии сценариев |
| Дата | 2026-10-28 |
| Статус | ACCEPTED 2026-10-29 (CI run 40848057488: 7/7 задач зелёные) |
| Промпт | `MULTIVERSE_Documentation_Kit/prompts/07_EXPERIMENT_LIBRARY.md` |
| Основание | `docs/09` (ScenarioRevision, `GET /scenarios/{id}/revisions`), `docs/12` (privacy), PRD FR-LB-01…03, FR-RP-01…04, FR-ST-02, SP-02, NFR-PRIV-01, US-11, US-12, FC-09, FC-10 |

## 1. Scope

Сохранение сценариев **только в браузере этого устройства** (D-07, SP-02), с постоянной меткой «Only on this device». Серверного хранения, аккаунтов и синхронизации нет. Это V2+, и в отчёте будет список «сделано / запланировано на сервере».

## 2. Подзадачи

| # | Подзадача | Измеримый результат |
|---|---|---|
| 1 | Contracts 0.5.0: `ScenarioRecord` (name, tags, notes, неизменяемые revisions), `ScenarioRevision`, `ReportSnapshot`, файл `NotebookExport` со schema version | Pydantic-правила: номера revisions подряд, родитель раньше потомка, статус результата согласован, отчёты ссылаются на существующие revisions |
| 2 | Хранилище в localStorage | Quota, private mode, повреждённые данные и обновление страницы обработаны; при недоступном хранилище работа в памяти с баннером (FC-10) |
| 3 | Сохранение из Decision Builder | Новый сценарий или новая revision восстановленного сценария; старая revision не меняется |
| 4 | Notebook `/notebook` | Поиск по name / tags / notes / компании, фильтр по тегу, история revisions, правка метаданных |
| 5 | Restore form | Revision открывается в Decision Builder с теми же значениями (round trip) |
| 6 | Duplicate as revision | Дубль — новый сценарий со ссылкой на источник; оригинал не меняется |
| 7 | Compare | Разница параметров двух revisions; несовместимые as-of / horizon / currency блокируются, раз метода выравнивания нет |
| 8 | Отчёт Markdown + manifest | Неизменяемый snapshot с SHA-256; повторный экспорт создаёт новый snapshot и не трогает старый; revision после экспорта заблокирована |
| 9 | Import / export JSON | Битый JSON, чужой формат, новая версия, ломаные revisions отклоняются с причиной; Stage 05 JSON решения мигрируется |
| 10 | Settings & Privacy | Опись данных на устройстве и «удалить всё» с подтверждением (FR-ST-02) |

## 3. Риски

| Риск | Митигация |
|---|---|
| Пользователь думает, что данные на сервере | Метка «Only on this device» на notebook, в builder и в settings; экспорт JSON как резервная копия |
| Тихая потеря при переполнении или в private mode | Ошибка записи видна, предложен экспорт; работа продолжается в памяти |
| Повреждённые данные перезаписаны | Нечитаемые данные не стираются без явного действия; их можно скачать |
| Экспорт подменяет старый отчёт | Snapshot append-only, ID и хэш неизменны; тест |
| Импорт переписывает существующие сценарии | Конфликт ID даёт копию, не замену |
| Секреты в хранилище | Хранятся только сценарии и отчёты; лишние поля при импорте отклоняются |

## 4. Отчёт этапа

### Done

- **Contracts 0.5.0** (`notebook.py`, ADR-0015): `ScenarioRecord`, `ScenarioRevision`, `RevisionRef`, `ReportSnapshot`, `NotebookExport`. Каждая revision хранит:
  - компанию и knowledge cutoff;
  - структурированные параметры решения (`ScenarioDraft`);
  - seed;
  - режим модели (demo);
  - валюту;
  - статус результата и ID результата;
  - дату создания и номер revision;
  - родителя или источник дубля.
- **Notebook** `/notebook`:
  - метка «Only on this device» на странице, в окне сохранения и в настройках;
  - поиск по name / tags / notes / компании и фильтр по тегу;
  - правка name, tags и notes без новой revision;
  - история revisions;
  - «Open in Decision Builder» (restore form): сохранение создаёт следующую revision, старая не меняется;
  - «Duplicate as new scenario»: новый сценарий с `derived_from`;
  - сравнение двух любых revisions: разница параметров, а разные cutoff / horizon / currency блокируются;
  - экспорт отчёта Markdown с manifest и пометкой DEMO; каждый экспорт — новый неизменяемый snapshot с SHA-256; revision блокируется; повторная загрузка отдаёт тот же файл;
  - сценарий с отчётами удалить нельзя.
- **Decision Builder**:
  - «Save to notebook» — новый сценарий или следующая revision;
  - восстановление формы по ссылке `restore=…&revision=…`; если revision нет на устройстве, это объясняется;
  - seed восстановленной revision сохраняется.
- **Import / export JSON**:
  - экспорт всего notebook с суффиксом `_DEMO`;
  - импорт проверяет файл целиком и мигрирует JSON решения из Stage 05;
  - отклоняется: битый JSON, чужой формат, новая версия схемы или contracts, изменённый после экспорта отчёт, разрывы в номерах revisions, лишние поля (например `api_token`);
  - слияние не перезаписывает: при конфликте ID сценарий входит как копия.
- **Отказы хранилища** (FC-10):
  - private mode — работа в памяти с предупреждением;
  - переполнение — видимая ошибка и совет экспортировать;
  - нечитаемые данные не перезаписываются: их можно скачать или сбросить после подтверждения;
  - обновление страницы и вторая вкладка — синхронизация через событие `storage`.
- **Settings & Privacy** `/settings`: опись всех ключей приложения с размерами; «Delete all data on this device» с подтверждением удаляет только ключи MULTIVERSE.

### Сделано сейчас и запланировано на сервере

| Возможность | V1 (сделано, Stage 07) | Сервер (запланировано) |
|---|---|---|
| Где хранится | localStorage этого браузера | `POST /api/v1/scenarios`, хранилище с владельцем (Stage 24) |
| Доступ с другого устройства | Только через экспорт / импорт JSON | Аккаунты и права (Stage 24) |
| Неизменяемые revisions | Да, append-only | Тот же contract, плюс audit log (FR-AD-03, V4) |
| Неизменяемые отчёты | Snapshot с SHA-256 в notebook | Подписанные URL и срок хранения (docs/09) |
| Результаты в revision | Только статус «not run» (симуляции нет) | Ссылка на результат Monte Carlo (Stage 22) |
| Отчёт | Markdown | Markdown, CSV и PDF в Report Studio (Stage 25) |
| Одновременная правка в двух вкладках | Последняя запись побеждает, вторая вкладка обновляется | Версии и проверка конфликтов на сервере |
| Резервная копия | Ручной экспорт JSON | Серверное хранение |

### Files

**Новые:**
- contracts (Python): `notebook.py`, `tests/test_notebook.py`;
- contracts (данные): `packages/contracts/fixtures/notebook/valid-export.json`;
- web-логика: `apps/web/src/notebook/*` (model, storage, use-notebook, import, report, compare), `apps/web/src/lib/download.ts`;
- web-интерфейс: `apps/web/src/components/notebook/*` (save-to-notebook, restore-gate, notebook-app, scenario-detail, storage-banner, privacy-settings), страницы `app/notebook/page.tsx`, `app/settings/page.tsx`;
- тесты: `apps/web/test/notebook.test.ts`, `apps/web/e2e/notebook.spec.ts`;
- документы: `docs/adr/0015-local-notebook.md`, `docs/stages/07-screens/*.png` (15 снимков), этот отчёт.

**Изменены:**
- contracts: `__init__.py`, `export.py`, `version.py`, сгенерированные schema, каталог, mock-результаты и TS; генератор TS (`maxItems: -1`);
- web: `decision-builder.tsx` (save, restore, seed, кнопки вне формы), `decisions/params.ts` (`restore`), `app/decisions/page.tsx`, `sections.ts`;
- тесты: `pages.spec.ts`;
- документы: ADR README, README, CHANGELOG.

### Tests

Все команды запущены локально (Windows 11) 2026-10-29.

| Проверка | Результат |
|---|---|
| `npm run check` (полный gate) | **EXIT 0** |
| pytest | **154 passed** (19 новых: общий файл notebook и 18 видов сломанного файла) |
| vitest contracts / web | 4 / **186 passed** (28 новых в `notebook.test.ts`) |
| contracts drift | schema 0.5.0, demo-компании, каталог, mock-результаты, TS — up to date |
| Playwright на 1440 / 768 / 390 | **327 passed, 9 skipped** (по замыслу); 48 новых |

Что проверяют новые тесты:

| Проверка | Где |
|---|---|
| Revision 1 не меняется после revision 2; родитель записан; revision другой компании отклоняется | vitest |
| Дубль ссылается на источник, оригинал не меняется; правка метаданных не трогает revisions | vitest, e2e |
| Повторный экспорт: новый ID, тот же manifest и хэш; первый отчёт не изменён; revision заблокирована; удаление запрещено | vitest, e2e (скачивание `.md`) |
| Хранилище: запись и чтение после «обновления»; quota → «quota»; private mode → «unavailable»; нечитаемые данные сохраняются и блокируют запись; удаляются только ключи приложения | vitest, e2e |
| Импорт: общий файл, round trip экспорта, миграция файла решения Stage 05, 7 видов отказа с причиной, битый JSON, слияние без перезаписи | vitest, e2e |
| Сравнение: разница параметров; разные cutoff блокируются | vitest, e2e |
| Сохранение из builder → обновление страницы → восстановление формы → revision 2 с родителем 1 | e2e |
| axe WCAG 2.2: 0 нарушений на `/notebook` (пусто и со сценарием) и `/settings` | e2e |

**Визуальная проверка и прогоны нашли 5 дефектов, все исправлены:**

| Дефект | Исправление |
|---|---|
| Формы диалогов Run (со Stage 05) и Save лежали внутри формы builder. Это невалидный HTML: ошибка гидратации React #418, а кнопки диалога отправляли внешнюю форму, и Save ничего не сохранял | Панель действий вынесена после формы, Validate привязан к форме атрибутом `form` |
| Ссылка «Open in notebook» при клиентской навигации не открывала сценарий | Выбранный сценарий передаёт страница сервера (`searchParams`) |
| Импорт падал, если отчёт ссылался на revision, которая сама не прошла проверку | Проверка отчёта учитывает такую revision |
| На планшете поле поиска сжималось до «Name, tag,» | Поиск на отдельной строке до широкого экрана |
| У фильтра тегов и селектов сравнения была нативная стрелка, не как в остальном приложении | Общий `SelectField` |

Ошибки тестов, а не приложения:
- reload до завершения клиентской навигации;
- неточный селектор заголовка;
- запрещённые `!` в тестах.

Один прогон дал 8 падений за 10 минут: от отладки остался процесс dev-сервера. Повторный прогон — 36 из 36.

### Measured results

Финансовых и ML-метрик нет. Notebook хранит сценарии пользователя; общий fixture — 1 сценарий, 2 revisions, 1 отчёт.

### Known limitations

- **Только это устройство.** Нет синхронизации и сервера; данные пропадут при очистке данных сайта, если не экспортировать JSON.
- **Две вкладки одновременно:** побеждает последняя запись. Вторая вкладка обновляется по событию `storage`, но одновременные правки не сливаются.
- **Отчёт только Markdown.** CSV отчёта (FR-RP-01) и PDF — Report Studio (Stage 25). CSV графиков уже есть с Stage 06.
- **У всех revisions статус «not run»:** симуляций нет до Stage 22. `code_version` в manifest — «unversioned», коммит появится в собранном деплое (Stage 26).
- **Настройки отображения (FR-ST-01, P1) не сделаны** — запланированы на Gate A (Stage 08).
- **localStorage ограничен браузером** (обычно несколько MB). Для десятков сценариев этого хватает; при переполнении есть понятная ошибка.
- **Проверено только в Chromium.** Проверки со screen reader не было.

### Decisions

- ADR-0015: append-only revisions, неизменяемые отчёты, формат хранения = формат экспорта, импорт без перезаписи.
- Name, tags и notes — метаданные сценария, а не revision.
- Сценарий с отчётами не удаляется.
- Генератор TS игнорирует `maxItems`: верхние границы остаются правилами contract.
- Кнопки builder стоят вне формы.

### Next prompt

`08_FRONTEND_TEST_GATE.md` (Gate A: аудит frontend) — только по команде владельца.

## 5. Acceptance

| Критерий промпта 07 | Evidence | Статус |
|---|---|---|
| Сохранение и история сценариев | Notebook, revisions, e2e | ✅ |
| name / tags / notes / search | Метаданные, поиск, фильтр по тегу | ✅ |
| Duplication as revision | Дубль с `derived_from`; правка — новая revision с родителем | ✅ |
| Restore form | «Open in Decision Builder», round trip формы | ✅ |
| Compare | Разница revisions; несовместимые блокируются без метода | ✅ |
| Immutable report snapshot manifest | `ReportSnapshot`, SHA-256, повторный экспорт не заменяет | ✅ |
| «Only on this device» | Метка на notebook, в сохранении и в настройках | ✅ |
| Сценарий хранит company, as-of, параметры, seed, model mode, currency, result status, creation date, revision | `ScenarioRevision` | ✅ |
| Quota, malformed JSON, schema migrations, private mode, refresh | vitest и e2e | ✅ |
| Не хранить secrets | Хранятся только сценарии и отчёты; лишние поля отклоняются | ✅ |
| Roundtrip и отрицательные случаи | pytest, vitest, e2e | ✅ |
| Список «сделано против серверного хранения» | Таблица выше | ✅ |

`17_ACCEPTANCE_MATRIX`: по **REP-01** (manifest, неизменяемость отчёта) и **SEC-02** («удалить все локальные данные») теперь есть evidence. Формально все пункты остаются **TODO** до gate.
