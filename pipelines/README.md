# multiverse-pipelines

Data pipelines for SEC, FRED, ECB and World Bank (`docs/04`). They read the source catalog of Stage 09 (`packages/contracts/catalog/sources.json`, ADR-0016) and build up in stages:

| Stage | Pipeline | Status |
|---|---|---|
| 10 | SEC raw ingestion: Submissions API, Company Facts API, bulk ZIPs (ADR-0017) | **Done** |
| 11 | XBRL normalization | Planned |
| 12 | Point-in-time warehouse | Planned |
| 13 | Macro vintages | Planned |

Rules:

- No network access unless `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true` **and** the owner approved the source in the catalog.
- SEC fair access: a declared User-Agent with a contact email, 2 requests per second for the whole process.
- Raw files live in `var/raw/` and are never committed.

## SEC raw ingestion

`.env` (ignored by git) holds the contact and keeps downloads off:

```
MULTIVERSE_SEC_USER_AGENT="MULTIVERSE research name@example.com"
MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=false
MULTIVERSE_RAW_DIR=var/raw
MULTIVERSE_RAW_BUDGET_MB=200
```

Commands, run from the repository root:

| Command | Network | What it does |
|---|---|---|
| `uv run python -m multiverse_pipelines.sec status` | no | Switch, User-Agent present, owner decision, archive use against the budget |
| `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true uv run python -m multiverse_pipelines.sec sample` | yes | Submissions (with the older-filing pages they list) and company facts of the ten catalog candidates; `--cik 97476` (repeatable) for others; `--max-age-hours 12` reuses files confirmed recently |
| `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true uv run python -m multiverse_pipelines.sec probe companyfacts-zip` | one HEAD | Size and Last-Modified of a bulk file (`companyfacts-zip`, `submissions-zip`, `fsds --quarter 2024q1`) |
| `MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true uv run python -m multiverse_pipelines.sec bulk fsds --quarter 2024q1 --max-mb 150` | yes | One bulk ZIP after a HEAD shows it fits; refused until the catalog holds a `bulk` approval (decision D-10) |
| `uv run python -m multiverse_pipelines.sec verify` | no | Re-hashes every archived file; finds changed, missing, writable and unknown files |
| `uv run python -m multiverse_pipelines.sec coverage [--json]` | no | What the archived sample holds per candidate: filings by form, taxonomies, periods per V2 metric |

On Windows PowerShell, set the switch for one command with `$env:MULTIVERSE_ALLOW_NETWORK_DOWNLOADS='true'; uv run python -m multiverse_pipelines.sec sample; Remove-Item Env:MULTIVERSE_ALLOW_NETWORK_DOWNLOADS`.

Exit codes: 0 done, 1 some files failed, 2 refused or aborted (403, budget, permission), 3 the archive has problems.

### Archive layout

```
var/raw/sec/
  submissions/CIK0000097476/<sha256>.json                    company metadata and latest filings
  submissions/CIK0000097476/submissions-001/<sha256>.json    older filings
  companyfacts/CIK0000097476/<sha256>.json                   every XBRL fact with accn and filed date
  financial-statement-data-sets/2024q1/<sha256>.zip          bulk only
  index.jsonl                                                one RawObject per file (metadata table)
  runs/<run_id>.json                                         one RunManifest per command (audit)
  tmp/*.part                                                 unfinished downloads, removed at the next start
```

Files are read-only and named by their SHA-256. The same bytes are never stored twice, and a changed file becomes a new object next to the old one.

### Identifiers and taxonomies

- **CIK:** the API uses ten digits with leading zeros (`CIK0000097476.json`); Archives paths use the plain number (`/edgar/data/97476/`). Submissions JSON writes the CIK as a string without zeros, company facts as an integer. `multiverse_pipelines.sec.cik` handles all three forms.
- **Tickers change and are reused.** They are an observation with a date (`tickers` in submissions), never a key. Celgene, acquired in 2019, has no ticker today.
- **US-GAAP and IFRS:** domestic filers report in `us-gaap` on 10-K and 10-Q. Foreign private issuers file 20-F or 40-F and may report in `ifrs-full`. The V2 universe is domestic US-GAAP filers; the coverage report counts taxonomies and foreign forms instead of assuming them.
- **Access:** EDGAR data needs no account. EDGAR Next filer accounts are for submitting filings and are never used here. The only identity sent is the User-Agent.
