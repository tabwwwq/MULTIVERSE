"""Forecasting research of MULTIVERSE.

Responsibility: persistence / Ridge / boosting baselines (Stage 15), temporal neural
networks (Stage 16) and calibration (Stage 17), all on point-in-time features (docs/06).

Heavy ML libraries are optional extras and are never imported at package import time:
    uv sync --all-packages --extra boosting   # scikit-learn, LightGBM
    uv sync --all-packages --extra ml         # PyTorch"""

__version__ = "0.1.0"
