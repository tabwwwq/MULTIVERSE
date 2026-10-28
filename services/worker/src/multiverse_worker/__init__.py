"""Background worker of MULTIVERSE.

Responsibility: run queued simulation and training jobs outside HTTP requests, with
heartbeats, checkpoints, stop / resume and budget limits (docs/13). The queue arrives
in Stage 18; until then the worker only validates its configuration and exits."""

__version__ = "0.1.0"
