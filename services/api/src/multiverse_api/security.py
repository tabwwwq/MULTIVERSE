"""The boundary of the API (Stage 24, ADR-0032): who is asking, and whether to listen.

Two layers. ``Guard`` wraps the whole app and turns away what no honest browser or client sends:
a Host this API does not answer to (DNS rebinding), a cross-site write (CSRF), a body that is
not JSON or is too large. ``Access`` is a dependency of every protected route: it finds the
principal, checks the role and the rate, and writes the audit row.

Without tokens this API trusts its own machine and nothing else, so ``local`` mode exists only
on the loopback address: settings refuse anything wider. An object that belongs to someone else
answers 404, the same as an object that does not exist.
"""

import hashlib
import hmac
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from multiverse_config import Role, Settings
from multiverse_jobs.store import JobStore

ANONYMOUS = "anonymous"
LOCAL_OWNER = "owner"
RANKS = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
RESPONSE_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
)
API_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class Principal:
    name: str
    role: Role

    def holds(self, role: Role) -> bool:
        return RANKS[self.role] >= RANKS[role]

    def may_see(self, owner: str) -> bool:
        return self.name == owner or self.role is Role.ADMIN


class BodyTooLargeError(Exception):
    """A body without a Content-Length grew past the limit while it was read."""


class RateLimiter:
    """A sliding minute per key, in this process. Keys leave memory with their last hit."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.hits: dict[str, deque[float]] = {}
        self.told: dict[str, float] = {}

    def _recent(self, key: str) -> deque[float]:
        now = self.clock()
        window = self.hits.setdefault(key, deque())
        while window and now - window[0] >= WINDOW_SECONDS:
            window.popleft()
        return window

    def wait(self, key: str, limit: int) -> int | None:
        """Seconds to wait when the key is over its limit, without counting this call."""
        window = self._recent(key)
        if len(window) < limit:
            if not window:
                del self.hits[key]
            return None
        return max(1, round(WINDOW_SECONDS - (self.clock() - window[0])))

    def hit(self, key: str) -> None:
        self._recent(key).append(self.clock())

    def first_refusal(self, key: str) -> bool:
        """Once per window: a flood of refused requests must not become a flood of writes."""
        now = self.clock()
        self.told = {k: at for k, at in self.told.items() if now - at < WINDOW_SECONDS}
        if key in self.told:
            return False
        self.told[key] = now
        return True

    def allow(self, key: str, limit: int) -> int | None:
        delay = self.wait(key, limit)
        if delay is None:
            self.hit(key)
        return delay


def host_of(header: str) -> str:
    """The name in a Host header, without the port, in lower case."""
    if header.startswith("["):
        return header[1:].split("]", 1)[0].lower()
    return header.rsplit(":", 1)[0].lower() if ":" in header else header.lower()


class Guard:
    """Outermost layer: it answers before anything inside sees the request."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.hosts = frozenset(host.lower() for host in settings.api_allowed_hosts)
        self.origins = frozenset(settings.web_origins)
        self.limit = settings.max_body_bytes

    def _refusal(self, scope: Scope, headers: Headers) -> tuple[int, str] | None:
        if host_of(headers.get("host", "")) not in self.hosts:
            return status.HTTP_400_BAD_REQUEST, "this API does not answer to that host"
        if scope["method"] in SAFE_METHODS:
            return None
        origin = headers.get("origin")
        if origin is not None and origin not in self.origins:
            return status.HTTP_403_FORBIDDEN, "cross-site requests may not change anything"
        if origin is None and headers.get("sec-fetch-site") == "cross-site":
            return status.HTTP_403_FORBIDDEN, "cross-site requests may not change anything"
        length = headers.get("content-length")
        has_body = length not in (None, "0") or "transfer-encoding" in headers
        kind = headers.get("content-type", "").split(";")[0].strip().lower()
        if has_body and kind != "application/json":
            return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "the body must be application/json"
        if length is not None and (not length.isdigit() or int(length) > self.limit):
            return status.HTTP_413_CONTENT_TOO_LARGE, "the body is too large"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        documented = scope["path"].startswith("/api/docs")
        added = RESPONSE_HEADERS if documented else (*RESPONSE_HEADERS, API_CSP)
        started = False

        async def marked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [*message.get("headers", []), *added]
            await send(message)

        refusal = self._refusal(scope, Headers(scope=scope))
        if refusal is not None:
            code, detail = refusal
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, marked)
            return
        read = 0

        async def counted() -> Message:
            nonlocal read
            message = await receive()
            read += len(message.get("body", b""))
            if read > self.limit:
                raise BodyTooLargeError
            return message

        try:
            await self.app(scope, counted, marked)
        except BodyTooLargeError:
            if started:
                raise
            answer = JSONResponse({"detail": "the body is too large"}, status_code=413)
            await answer(scope, receive, marked)


class Access:
    """Answers who is asking; every protected route goes through ``as_``."""

    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        limiter: RateLimiter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.limiter = limiter if limiter is not None else RateLimiter()
        self.clock = clock if clock is not None else (lambda: datetime.now(UTC))

    def _bearer(self, request: Request) -> str | None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        return token.strip() if scheme.lower() == "bearer" and token.strip() else None

    def _token_principal(self, token: str) -> Principal | None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        found = None
        for entry in self.settings.api_principals:
            if hmac.compare_digest(digest, entry.token_sha256):
                found = entry
        if found is None or self.clock() >= found.expires_at:
            return None
        return Principal(found.name, found.role)

    def _limited(self, key: str, actor: str, action: str, seconds: int) -> HTTPException:
        if self.limiter.first_refusal(key):
            self.store.audit(actor, action, None, "limited")
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many requests",
            headers={"Retry-After": str(seconds)},
        )

    def _authenticate(self, request: Request, action: str) -> Principal:
        if self.settings.auth_mode == "local":
            return Principal(LOCAL_OWNER, Role.ADMIN)
        client = f"failures:{request.client.host if request.client else 'unknown'}"
        delay = self.limiter.wait(client, self.settings.rate_failures_per_minute)
        if delay is not None:
            raise self._limited(client, ANONYMOUS, action, delay)
        token = self._bearer(request)
        principal = self._token_principal(token) if token else None
        if principal is None:
            self.limiter.hit(client)
            self.store.audit(ANONYMOUS, action, None, "denied")
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "a valid token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return principal

    def as_(self, role: Role, action: str) -> Callable[[Request], Awaitable[Principal]]:
        """A dependency: the principal, or the reason there is none."""

        async def check(request: Request) -> Principal:
            principal = self._authenticate(request, action)
            read = request.method in SAFE_METHODS
            limit = (
                self.settings.rate_reads_per_minute
                if read
                else self.settings.rate_writes_per_minute
            )
            kind = "reads" if read else "writes"
            key = f"{kind}:{principal.name}"
            delay = self.limiter.allow(key, limit)
            if delay is not None:
                raise self._limited(key, principal.name, action, delay)
            if not principal.holds(role):
                self.store.audit(principal.name, action, None, "denied")
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"this needs the role {role.value}")
            return principal

        return check

    def owned(self, principal: Principal, job_id: str, action: str) -> None:
        """The object check. Someone else's job and no job answer the same, and are audited."""
        try:
            owner = self.store.owner_of(job_id)
        except KeyError:
            owner = None
        if owner is None or not principal.may_see(owner):
            self.store.audit(principal.name, action, None, "not_found")
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job {job_id}")
        self.store.audit(principal.name, action, job_id, "allowed")
