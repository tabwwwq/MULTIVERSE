# multiverse-forecast

Forecasting research on point-in-time features: baselines first (Stage 15), then temporal neural networks (Stage 16) and calibration (Stage 17), following `docs/06`. **Status: Stage 15 baselines.**

The dataset comes from the pipelines (`python -m multiverse_pipelines.forecastset build --universe data/universe/sec-1000-20261030.json`); this package never imports them (ADR-0009). The benchmark reads the dataset folder and the locked protocol `data/protocols/stage-15-baselines.json`:

```bash
uv run python -m multiverse_forecast benchmark --dataset var/data/forecast/<dataset id>
```

| Module | What it does |
|---|---|
| `data.py` | Loads a dataset folder and checks it against the SHA-256 in its manifest |
| `models.py` | persistence, seasonal naive, sector average, pooled dynamic panel (OLS), Ridge, ElasticNet, gradient boosting; train-only preprocessing |
| `benchmark.py` | The locked protocol: cold-start firms, rolling origin with yearly refits, validation then test |
| `scoring.py` | MAE, RMSE, median AE, WAPE, firm- and revenue-weighted MAE, bootstrap intervals over firms |
| `report.py` | `report.json` (`BenchmarkReport`), `report.md`, `report.html` |

numpy and scikit-learn are core dependencies (ADR-0023). Optional extras:

```bash
uv sync --all-packages --extra boosting   # LightGBM
uv sync --all-packages --extra ml         # PyTorch
```
