"""Composition root of the background worker.

Until the job queue exists (Stage 18) the worker only validates its configuration,
logs which profile it would run with, and exits with code 0.
"""

import logging

from multiverse_config import load_settings

log = logging.getLogger("multiverse_worker")


def main() -> int:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    log.info("worker configured for profile %r; job queue arrives in Stage 18", settings.env.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
