"""Lightweight secret scan of the working tree (CI also runs gitleaks).

Fails if something that looks like a credential is written into a tracked-looking
file, or if the ignore rules stop protecting local secret files.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "node_modules", "var", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
SKIP_FILES = {"uv.lock", "package-lock.json", Path(__file__).name}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".toml",
    ".yml", ".yaml", ".md", ".txt", ".example", ".cfg", ".ini",
}  # fmt: skip

PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "assigned secret": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b[^\n=:]{0,20}[=:]\s*['\"]?[A-Za-z0-9/+_\-]{20,}"
    ),
}


def _candidate_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        if (
            path.is_file()
            and path.name not in SKIP_FILES
            and (path.suffix in TEXT_SUFFIXES or path.name.startswith(".env"))
        ):
            files.append(path)
    return files


def test_no_credentials_in_repository_files() -> None:
    findings = []
    for path in _candidate_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(REPO_ROOT)}: {label}")

    assert not findings, "possible secrets found:\n" + "\n".join(findings)


def test_local_secret_files_are_ignored() -> None:
    ignore_rules = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignore_rules
    assert "!.env.example" in ignore_rules
    assert "var/" in ignore_rules
