# multiverse-config

Runtime settings for Python services, read from `MULTIVERSE_*` environment variables and an optional `.env` file, validated at startup (ADR-0010). Only composition roots (`services/*/main.py`) call `load_settings()`; everything else receives settings as an argument.

Profiles: `local`, `test`, `ci`, `production`. See `.env.example` in the repository root.
