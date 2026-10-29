# multiverse-pipelines

Data pipelines for SEC, FRED, ECB and World Bank (`docs/04`): they read the source catalog of Stage 09 (`packages/contracts/catalog/sources.json`, ADR-0016) and add SEC raw ingestion (Stage 10), XBRL normalization (Stage 11), point-in-time warehouse (Stage 12), macro vintages (Stage 13). **Status: skeleton.**

Rules: no network access unless `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true` and the owner approved the source in the catalog; SEC fair access (declared User-Agent with contact email, conservative throttle); raw files live in `var/` and are never committed.
