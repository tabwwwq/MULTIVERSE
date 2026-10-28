# @multiverse/contracts (TypeScript)

TypeScript types generated from `../schemas/contracts.schema.json`, which is generated from the Python models in `../python/` (ADR-0008). Files in `src/generated/` must never be edited by hand.

```ts
import { CONTRACTS_VERSION, type MetricValue } from "@multiverse/contracts";
```

Regenerate: `npm run contracts:gen`. Check for drift: `npm run contracts:check`.
