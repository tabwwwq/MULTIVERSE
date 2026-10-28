# apps/web

Next.js + TypeScript web application. **Status: not created yet.** It is scaffolded in Stage 03 (design system and frontend shell), so Stage 02 does not install Next.js.

Rules already in force: the web app imports shared types only from `@multiverse/contracts`, never from other modules by relative path (ADR-0009), and never holds secrets: only non-secret `NEXT_PUBLIC_*` variables may reach the browser (ADR-0010).
