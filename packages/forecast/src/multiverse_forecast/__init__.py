"""Forecasting research of MULTIVERSE.

Responsibility: baselines (Stage 15), temporal neural networks (Stage 16) and calibration
(Stage 17), all on point-in-time features (docs/06). The Stage 15 baselines need numpy and
scikit-learn (core dependencies since ADR-0023); LightGBM and PyTorch stay optional extras:
    uv sync --all-packages --extra boosting   # LightGBM
    uv sync --all-packages --extra ml         # PyTorch

    python -m multiverse_forecast benchmark --dataset var/data/forecast/<dataset id>
"""

__version__ = "0.1.0"
