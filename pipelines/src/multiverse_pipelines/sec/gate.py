"""The three locks in front of every download (ADR-0016, ADR-0017).

1. ``MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true``, meant to be set for one command only.
2. ``MULTIVERSE_SEC_USER_AGENT`` with a name and a contact email (SEC fair access).
3. The owner's decision in the source catalog: approved, and for bulk files a bulk scope.
"""

import re

from multiverse_config import Settings
from multiverse_contracts.sources import DataSource, DecisionStatus, DownloadScope
from multiverse_pipelines.sec.errors import PermissionRefusedError

# "Name of the requester contact@domain.tld": a name first, the email last.
_USER_AGENT = re.compile(r"^\S.*\s[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def check_user_agent(value: str | None) -> str:
    if value is None or not _USER_AGENT.fullmatch(value.strip()):
        raise PermissionRefusedError(
            "MULTIVERSE_SEC_USER_AGENT must name the requester and end with a contact email, "
            'for example "MULTIVERSE research name@example.com"; put it into .env'
        )
    return value.strip()


def require_permission(settings: Settings, source: DataSource, scope: DownloadScope) -> str:
    """Return the User-Agent when every lock is open; otherwise say which one is closed."""
    if not settings.allow_network_downloads:
        raise PermissionRefusedError(
            "Network downloads are off. Set MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true for this "
            "command only; .env keeps it false."
        )
    user_agent = check_user_agent(settings.sec_user_agent)
    decision = source.download
    if decision.status is not DecisionStatus.APPROVED:
        raise PermissionRefusedError(
            f"{source.source_id}: the owner has not approved downloads ({decision.status})."
        )
    if scope is DownloadScope.BULK and decision.scope is not DownloadScope.BULK:
        raise PermissionRefusedError(
            f"{source.source_id} is approved for a sample only; bulk files need the owner's "
            "bulk approval in the source catalog (decision D-10)."
        )
    return user_agent
