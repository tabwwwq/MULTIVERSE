"""A new API token: shown once, stored by nobody but its holder.

    uv run python -m multiverse_api.tokens --name alice --role operator --days 30

Only the printed entry goes into ``MULTIVERSE_API_PRINCIPALS``. The token itself is high-entropy
and random, so a plain SHA-256 is enough: no password to guess, nothing to stretch.
"""

import argparse
import hashlib
import json
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from multiverse_config import ApiPrincipal, Role

PREFIX = "mv_"
MAX_DAYS = 90


def new_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def entry(token: str, name: str, role: Role, days: int, now: datetime) -> ApiPrincipal:
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"a token lives between 1 and {MAX_DAYS} days")
    return ApiPrincipal(
        name=name,
        role=role,
        token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now + timedelta(days=days),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="multiverse_api.tokens")
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=[role.value for role in Role], required=True)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)
    token = new_token()
    made = entry(token, args.name, Role(args.role), args.days, datetime.now(UTC))
    print(f"token, shown once: {token}")
    print(json.dumps(made.model_dump(mode="json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
