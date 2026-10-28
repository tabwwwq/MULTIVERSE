# @multiverse/web

Next.js 16 + TypeScript (strict) + Tailwind CSS 4. **Status: Stage 03** — design system and application shell. Sections that are not built yet render an honest placeholder that names the stage which builds them; no page shows real company data.

```bash
npm run dev:web        # http://localhost:3000
npm run build:web      # production build
npm run test:e2e       # Playwright at 1440, 768 and 390 px (needs `npm run build:web` first)
```

First run of the browser tests on a new machine needs Chromium once:

```bash
npx playwright install chromium
```

## Layout

| Path | What |
|---|---|
| `src/tokens/tokens.css` | Design tokens, the single source for colour, type, radius, elevation and motion |
| `src/components/ui/` | Button, TextField, SelectField, CheckboxField, Modal (native dialog), DataTable, Alert, Badge, Skeleton |
| `src/components/trust/` | InferenceModeBadge, SourceBadge, TrustHeader, NotClaims (types from `@multiverse/contracts`) |
| `src/components/brand/`, `src/components/charts/` | Logo, hero illustration, chart legend |
| `src/layouts/` | App shell, sidebar, navigation drawer, breadcrumbs, page header |
| `src/navigation/sections.ts` | The 20 screens, their groups and status; navigation, breadcrumbs and placeholders read it |
| `src/app/` | Routes: `/`, `/methodology`, `/design-system`, `/[section]` placeholders, 404 |
| `test/` | Vitest: token contrast, navigation and breadcrumbs |
| `e2e/` | Playwright: overflow, axe WCAG 2.2, keyboard, dialog, drawer, motion, table, links |

## Rules

- Colours come only from tokens (the Tailwind default palette is switched off). Contrast is tested.
- Status is never colour alone: badges carry text and an icon.
- Motion is opt-in under `prefers-reduced-motion: no-preference`; the default is the static end state.
- Native elements first: `<dialog>` for modals, `popover` for the drawer, `<select>` and `<input>` for forms.
- Only non-secret `NEXT_PUBLIC_*` variables may reach the browser (ADR-0010).
