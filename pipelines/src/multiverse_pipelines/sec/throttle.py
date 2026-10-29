"""Process-wide request pacing: one request at a time, evenly spaced."""

import time
from collections.abc import Callable
from decimal import Decimal


class Throttle:
    """Spaces requests at least 1/rate seconds apart, retries and HEAD requests included."""

    def __init__(
        self,
        rate_per_second: Decimal,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate must be positive")
        self._interval = float(1 / rate_per_second)
        self._clock = clock
        self._sleep = sleep
        self._next: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._next is not None and now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self._interval
