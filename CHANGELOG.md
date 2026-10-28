# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Версии продукта — V0…V4 из `docs/product/04-scope-matrix.md`.

## [Unreleased]

### Added — 2026-10-28 (Stage 03)

- `apps/web`: Next.js 16 + TypeScript strict + Tailwind CSS 4 web app with the MULTIVERSE design system.
- Design tokens from `docs/10` in `src/tokens/tokens.css`, with WCAG contrast tested from the file itself.
- Components: buttons, text / select / checkbox fields, native modal dialog, responsive data table, alerts, badges, skeleton; trust components for result mode, provenance, result header and "what this does not mean".
- Application shell: skip link, collapsible sidebar, top bar with breadcrumbs, swipeable navigation drawer below 1024px, footer; 20 sections, 18 of them honest placeholders that name their stage.
- Pages: Overview with the diverging-timelines hero, Methodology, Design system, 404.
- Tests: vitest (tokens, navigation) and Playwright at 1440, 768 and 390 px (overflow, axe WCAG 2.2, keyboard, dialog, drawer, motion, table, links); new `web` CI job.

### Changed — 2026-10-28

- Stage 02 accepted by the owner.

### Added — 2026-10-28 (Stage 02)

- Monorepo: uv workspace (8 Python packages, Python 3.12) and npm workspace (`@multiverse/contracts`), one command surface in `package.json`.
- Contracts as a single source of truth: Pydantic models → `contracts.schema.json` → generated TypeScript types, with drift checks (ADR-0008).
- Validated settings with `local / test / ci / production` profiles and safe defaults (ADR-0010).
- API composition root with `GET /api/v1/health`; worker composition root.
- Module boundaries enforced by import-linter and ESLint (ADR-0009).
- Quality gate `npm run check`, GitHub Actions CI (Ubuntu and Windows), secret scan test, gitleaks in CI.
- ADR-0001…0011, engineering conventions, root README with Windows / Linux quick start.

### Changed — 2026-10-28

- Stage 00 and Stage 01 accepted by the owner, including the defaults of all open questions.

### Added — 2026-10-28 (Stages 00–01)

- Stage 00: подтверждение мастер-промпта и реестр 14 научных рисков (`docs/stages/00-orchestrator-briefing.md`).
- Stage 01: продуктовые требования (`docs/product/`): PRD, personas, user stories и failure cases, scope matrix V0–V4, product risks, open questions с defaults, словарь финансовых величин, acceptance checklist.

### Notes

- Stages 00–01 contained documents only. Stage 02 adds infrastructure code; there is still no dataset, model or business logic. All acceptance matrix items remain TODO.
