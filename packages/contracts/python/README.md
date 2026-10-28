# multiverse-contracts (Python)

Pydantic models that define every value crossing a module or language boundary. This package is the **single source of truth** for contracts (ADR-0008): the JSON Schema in `../schemas/` and the TypeScript types in `../ts/` are generated from it.

Regenerate after any change: `npm run contracts:gen`.
