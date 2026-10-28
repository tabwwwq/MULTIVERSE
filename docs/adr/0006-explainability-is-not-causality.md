# ADR-0006 — Explainability не равна причинности

- Статус: Accepted
- Дата: 2026-10-28
- Этап: 02 (решение из `docs/03` и `docs/05`)

## Контекст

Feature importance и SHAP показывают, на что опирается модель, но не доказывают эффект решения. Ложная причинная метка — главный риск доверия (PRD PR-02, научный риск SR-01).

## Решение

Причинный статус — отдельное поле `causal_status` (`not_assessed`, `assumption_based`, `diagnostics_passed`). Он никогда не повышается автоматически: `diagnostics_passed` возможен только в режиме `causal_study`, а causal study обязан указать статус. Sensitivity и attributions подписываются «predictive sensitivity, not causal».

## Как проверяется

Валидатор `ReproducibilityManifest` и фикстура «causal diagnostics claimed outside a causal study».

## Последствия

Модуль `packages/causal` (Stage 20) хранит артефакты диагностики. Без такого артефакта статус выше `assumption_based` невозможен.

## Отвергнутые альтернативы

Одна шкала «уверенности» для прогноза и причинности: смешивает разные вопросы.
