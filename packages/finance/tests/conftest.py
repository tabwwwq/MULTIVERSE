"""Property tests run the same examples on every machine: a failure can always be repeated."""

from hypothesis import settings

settings.register_profile("multiverse", derandomize=True, database=None, deadline=None)
settings.load_profile("multiverse")
