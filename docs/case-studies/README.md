# Case studies (Stage 25)

Three decisions on three real companies, each run twice to compare two ways of acting. Every number comes from a research report of [Report Studio](../adr/0034-report-studio.md): Markdown for reading, CSV for checking, the document as JSON, and a manifest that builds the report again byte for byte.

| Study | Company | Compared | Evidence level |
|---|---|---|---|
| [R&D allocation under uncertainty](rnd-allocation/README.md) | Intel | R&D +20% against −20% | Conditional simulation; the return on R&D is not estimated |
| [M&A stress and valuation](ma-stress/README.md) | Boeing | A USD 15bn acquisition paid 90% in debt, or half in shares | Conditional simulation; the target is invented |
| [Operating restructuring or exit](restructuring-exit/README.md) | Estée Lauder | 15% fewer staff against leaving 10% of revenue | Conditional simulation; payroll and segment are assumed |

**What these are not.** No study estimates a causal effect: the feasibility study of [Stage 20](../stages/20-causal-research-pipeline.md) found none of 24 designs feasible. Probabilities are shares of simulated paths under an assumed model, not calibrated. Values are model DCF values, not market values, and no price per share is given. The companies are real; the decisions and targets are hypothetical.

## Files of each run

| File | What it is |
|---|---|
| `decisions/<run>.json` | The decision exactly as the run used it |
| `<run>/report.md` | The report: ten sections, then every claim with a JSON pointer into the run, then every source |
| `<run>/report.csv` | Quantiles, values and risks in full units, one statistic per row |
| `<run>/document.json` | The same report as data (`ResearchReport`, contracts 0.23.0) |
| `<run>/manifest.json` | Case and decision hashes, settings, versions and the SHA-256 of the three files |
| `figures/*.svg` | Figures drawn from the runs, with a text description for screen readers |

## How they were made

```bash
python -m multiverse_simulation run --case var/data/cases/<case>.json --decision docs/case-studies/<study>/decisions/<run>.json --paths 3000 --seed 20261107 --sensitivity --out var/data/case-studies/<study>/<run>.json
```

```bash
python -m multiverse_simulation report --case var/data/cases/<case>.json --decision docs/case-studies/<study>/decisions/<run>.json --report var/data/case-studies/<study>/<run>.json --out docs/case-studies/<study>/<run>
```

The cases are built from SEC filings by `python -m multiverse_simulation companies` ([Stage 24b](../stages/24b-real-companies.md)). A report depends on the exact bytes of its case, so the three cases of the studies are frozen in `var/data/case-studies/cases`: a later export, which writes `var/data/cases` again, cannot change them. Each run took about 65 s on a laptop CPU.
