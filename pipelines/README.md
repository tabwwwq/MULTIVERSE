# multiverse-pipelines

Data pipelines for SEC, FRED, ECB and World Bank (`docs/04`): source catalog (Stage 09), SEC raw ingestion (Stage 10), XBRL normalization (Stage 11), point-in-time warehouse (Stage 12), macro vintages (Stage 13). **Status: skeleton.**

Rules: no network access unless `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true`; SEC fair access (declared User-Agent with contact email, conservative throttle); raw files live in `var/` and are never committed.
