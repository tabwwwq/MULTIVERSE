"""Smoke test of the worker composition root."""

from pathlib import Path

import pytest

from multiverse_worker.main import main


def test_worker_starts_with_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "test")

    assert main() == 0


def test_worker_refuses_invalid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIVERSE_ENV", "staging")

    with pytest.raises(ValueError, match="env"):
        main()


def test_a_backup_goes_out_is_checked_and_comes_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    monkeypatch.setenv("MULTIVERSE_DATA_DIR", str(data))
    folder = tmp_path / "copy"
    fresh = tmp_path / "fresh"
    assert main(["backup", str(folder)]) == 0
    assert main(["verify", str(folder)]) == 0
    assert main(["restore", str(folder), str(fresh)]) == 0
    assert (fresh / "jobs" / "jobs.sqlite").exists()
    assert main(["restore", str(folder), str(fresh)]) == 1
    assert "refused" in capsys.readouterr().out
