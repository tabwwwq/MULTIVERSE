"""HTTP access to the SEC under its fair access rules (catalog sec-edgar, ADR-0017).

Every request carries the declared User-Agent and Accept-Encoding: gzip, deflate, goes
through one process-wide throttle and only to the official hosts, redirects included.
429 and 5xx are retried with exponential backoff, or Retry-After when the SEC sends it;
a cut connection or a body shorter than Content-Length is retried the same way. 403
stops the whole run. Bodies are streamed to a temporary file next to the archive.
"""

import email.utils
import random
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit

import httpx

from multiverse_pipelines.sec.errors import (
    AccessDeniedError,
    HostNotAllowedError,
    HttpStatusError,
    RetriesExhaustedError,
    TooLargeError,
)
from multiverse_pipelines.sec.throttle import Throttle

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
KEPT_HEADERS = ("content-type", "content-length", "content-encoding", "last-modified", "etag")
# A Retry-After longer than this means the SEC wants us gone for now: give up instead.
MAX_RETRY_AFTER_SECONDS = 600.0
CHUNK_BYTES = 1 << 16


@dataclass(frozen=True)
class Validators:
    """Conditional request headers from the archived copy, so an unchanged file costs nothing."""

    etag: str | None = None
    last_modified: str | None = None

    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    requests: int
    headers: Mapping[str, str] = field(default_factory=dict)
    path: Path | None = None
    size_bytes: int = 0

    @property
    def content_length(self) -> int | None:
        value = self.headers.get("content-length")
        return int(value) if value is not None and value.isdigit() else None


class _ShortBodyError(Exception):
    """The connection ended before Content-Length bytes arrived."""


def parse_retry_after(value: str, now: datetime) -> float | None:
    """Seconds to wait from a Retry-After header: a number of seconds or an HTTP date."""
    text = value.strip()
    if text.isdigit():
        return float(text)
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


class SecClient:
    def __init__(
        self,
        *,
        user_agent: str,
        allowed_hosts: Iterable[str],
        rate_per_second: Decimal,
        tmp_dir: Path,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        jitter: Callable[[], float] = random.random,
        max_retries: int = 3,
        backoff_seconds: float = 10.0,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._hosts = frozenset(allowed_hosts)
        self._tmp_dir = tmp_dir
        self._sleep = sleep
        self._now = now
        self._jitter = jitter
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self.requests_made = 0
        self._throttle = Throttle(rate_per_second, clock=clock, sleep=sleep)
        self._http = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=True,
            max_redirects=3,
            transport=transport,
            event_hooks={"request": [self._check_request]},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self._hosts:
            raise HostNotAllowedError(
                f"{url} is not on an official host ({', '.join(sorted(self._hosts))})"
            )

    def _check_request(self, request: httpx.Request) -> None:
        # Runs for redirects too, so a redirect cannot lead away from the official hosts.
        self.check_url(str(request.url))

    def head(self, url: str) -> Fetched:
        return self._request("HEAD", url, {}, max_bytes=0)

    def get(self, url: str, *, max_bytes: int, validators: Validators | None = None) -> Fetched:
        return self._request("GET", url, validators.headers() if validators else {}, max_bytes)

    def _request(self, method: str, url: str, headers: dict[str, str], max_bytes: int) -> Fetched:
        self.check_url(url)
        problem = "no response"
        attempts = self._max_retries + 1
        for attempt in range(1, attempts + 1):
            self._throttle.wait()
            self.requests_made += 1
            delay = self._backoff_delay(attempt)
            try:
                with self._http.stream(method, url, headers=headers) as response:
                    status = response.status_code
                    kept = {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers}
                    if status == 403:
                        raise AccessDeniedError(
                            f"HTTP 403 for {url}: the SEC refused access. Stop and check the "
                            "User-Agent and the request rate before any new run."
                        )
                    if status in RETRYABLE_STATUS:
                        problem = f"HTTP {status}"
                        delay = self._retry_after(response.headers.get("retry-after"), delay)
                    elif status == 304 or (method == "HEAD" and status == 200):
                        return Fetched(url, status, attempt, kept)
                    elif status != 200:
                        raise HttpStatusError(f"HTTP {status} for {url}")
                    else:
                        path, size = self._receive(response, max_bytes)
                        return Fetched(url, status, attempt, kept, path, size)
            except (httpx.TransportError, httpx.DecodingError, _ShortBodyError) as exc:
                problem = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                self._sleep(delay)
        raise RetriesExhaustedError(f"{url}: {problem}, {attempts} requests made")

    def _backoff_delay(self, attempt: int) -> float:
        return float(self._backoff * 2 ** (attempt - 1) * (1 + 0.25 * self._jitter()))

    def _retry_after(self, header: str | None, backoff: float) -> float:
        if header is None:
            return backoff
        wait = parse_retry_after(header, self._now())
        if wait is None:
            return backoff
        if wait > MAX_RETRY_AFTER_SECONDS:
            raise RetriesExhaustedError(
                f"the SEC asked to wait {wait:.0f} s (Retry-After); try later"
            )
        return max(wait, backoff)

    def _receive(self, response: httpx.Response, max_bytes: int) -> tuple[Path, int]:
        declared = response.headers.get("content-length")
        expected = int(declared) if declared is not None and declared.isdigit() else None
        if expected is not None and expected > max_bytes:
            raise TooLargeError(f"{response.url} declares {expected} bytes, {max_bytes} allowed")
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        handle = NamedTemporaryFile(dir=self._tmp_dir, suffix=".part", delete=False)  # noqa: SIM115
        path = Path(handle.name)
        size = 0
        try:
            with handle:
                for chunk in response.iter_bytes(chunk_size=CHUNK_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLargeError(
                            f"{response.url} is larger than the {max_bytes} bytes left"
                        )
                    handle.write(chunk)
            # Content-Length counts the bytes on the wire, before gzip is removed.
            if expected is not None and response.num_bytes_downloaded != expected:
                raise _ShortBodyError(
                    f"{response.num_bytes_downloaded} of {expected} bytes arrived"
                )
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path, size
