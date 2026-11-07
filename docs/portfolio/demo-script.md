# Demo script, about three minutes

For a screen recording or a live walkthrough. Start the app first:

```bash
npm run app
```

1. **Limitations first (15 s).** Open the README: scenarios are not history, forecasts are not effects, intervals are model quantiles, no advice. Say that every number shown was measured here.
2. **Universe (20 s).** <http://localhost:3000/universe>. The 500 largest SEC filers by the public float on their 10-K, NVIDIA first. Point out the note: this is not market capitalisation, and companies without a 10-K are missing.
3. **Dossier (30 s).** Open a company. Quarterly figures from filings with their lineage, then the research forecast: p10, p50 and p90, the warning that the model is not approved, and the coverage measured on 2024–2026.
4. **Decision (30 s).** Build a decision for it: an R&D change of 20% of the previous budget. Validate: the builder shows the decision in dollars at the cutoff.
5. **Run (30 s).** Press Run, then Run simulation. The estimate, approval and progress go through the local queue; the worker computes 1 000 paired paths and the result opens.
6. **Report (30 s).** Open Report Studio for the run: ten sections, every number with a claim number, every claim with a pointer and sources, SEC filings linked. Download the Markdown, print to PDF.
7. **Replay (15 s).** In a terminal: `python -m multiverse_simulation replay --manifest docs/case-studies/rnd-allocation/rnd-up/manifest.json --case var/data/cases/case-50863-20261106.json` prints `identical` for each file.
8. **Honest failure (15 s).** Open [the R&D case study](../case-studies/rnd-allocation/README.md): raising R&D only costs value in the model, because the return on R&D could not be estimated. That is the result, and the report says so.
