"""Smoke tests: every analysis module imports, and every command-line entry point answers --help."""

import importlib
import pkgutil
import subprocess
import sys

import pytest
from _support import REPO_ROOT

import analysis

ANALYSIS_MODULES = sorted(m.name for m in pkgutil.iter_modules(analysis.__path__))


def test_module_list_is_complete():
    assert {"batch_match", "classify", "fields", "get4", "kpi_single", "kpis", "reports"} <= set(ANALYSIS_MODULES)


@pytest.mark.parametrize("name", ANALYSIS_MODULES)
def test_analysis_module_imports(name):
    module = importlib.import_module(f"analysis.{name}")
    assert module.__doc__, f"analysis.{name} has no module docstring"
    assert callable(getattr(module, "main", None)), f"analysis.{name} has no main()"


def _help(cmd: list[str], cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *cmd, "--help"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


@pytest.mark.slow
@pytest.mark.parametrize("name", ANALYSIS_MODULES)
def test_analysis_cli_help(name):
    done = _help(["-m", f"analysis.{name}"], REPO_ROOT)
    assert done.returncode == 0, done.stderr[-3000:]
    assert "usage:" in done.stdout


@pytest.mark.slow
@pytest.mark.parametrize(
    ("cmd", "cwd"),
    [
        (["get4.py"], "batch_match"),
        (["batch_classifier.py"], "batch_match"),
        (["-m", "src.get4"], "sem_pipeline"),
    ],
    ids=["batch_match/get4.py", "batch_match/batch_classifier.py", "sem_pipeline src.get4"],
)
def test_other_cli_help(cmd, cwd):
    done = _help(cmd, REPO_ROOT / cwd)
    assert done.returncode == 0, done.stderr[-3000:]
    assert "usage:" in done.stdout


def test_backend_app_imports():
    from app.main import app

    routes = set(app.openapi()["paths"])
    assert {"/health", "/batches/{batch_id}/images", "/batches/{batch_id}/uncertainty"} <= routes
