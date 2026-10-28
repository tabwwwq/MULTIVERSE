"""Every module imports, declares its responsibility and has one consistent version."""

import importlib
from importlib.metadata import version

import pytest

MODULES = {
    "multiverse_contracts": "multiverse-contracts",
    "multiverse_config": "multiverse-config",
    "multiverse_finance": "multiverse-finance",
    "multiverse_causal": "multiverse-causal",
    "multiverse_forecast": "multiverse-forecast",
    "multiverse_pipelines": "multiverse-pipelines",
    "multiverse_api": "multiverse-api",
    "multiverse_worker": "multiverse-worker",
}


@pytest.mark.parametrize(("module_name", "distribution"), MODULES.items())
def test_module_imports_with_matching_version(module_name: str, distribution: str) -> None:
    module = importlib.import_module(module_name)

    assert module.__doc__, f"{module_name} must document its responsibility"
    assert module.__version__ == version(distribution)


def test_forecast_does_not_pull_heavy_ml_libraries_on_import() -> None:
    import sys

    importlib.import_module("multiverse_forecast")

    assert "torch" not in sys.modules
    assert "lightgbm" not in sys.modules
