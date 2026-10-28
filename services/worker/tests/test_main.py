"""Smoke test of the worker composition root."""

import pytest

from multiverse_worker.main import main


def test_worker_starts_with_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "test")

    assert main() == 0


def test_worker_refuses_invalid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "staging")

    with pytest.raises(ValueError, match="env"):
        main()
