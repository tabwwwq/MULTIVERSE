# multiverse-forecast

Forecasting research on point-in-time features: baselines first (Stage 15), then temporal neural networks (Stage 16) and calibration (Stage 17), following `docs/06`. **Status: skeleton.**

Heavy libraries are optional extras and are not installed by default:

```bash
uv sync --all-packages --extra boosting   # scikit-learn, LightGBM
uv sync --all-packages --extra ml         # PyTorch
```
