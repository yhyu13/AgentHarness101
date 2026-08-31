"""Meta-tests for the coverage gate configuration.

These tests assert that the coverage gate declared in ``pyproject.toml`` is
present and legal, so the red-green + ``fail_under`` discipline cannot be
silently dropped. They read the file with the standard-library ``tomllib``
(no coverage is actually run here).
"""

from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

SOURCE_PACKAGES = [
    "goal_persistence",
    "goal_loop",
    "context_compaction",
    "hippocampus",
    "tool_registry",
    "sandbox",
    "eval_harness",
    "observability",
    "safety",
    "cost_control",
    "faux_provider",
]


def _config() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def test_dev_deps_include_pytest_cov() -> None:
    dev = _config()["project"]["optional-dependencies"]["dev"]
    assert any(dep.strip().lower().startswith("pytest-cov") for dep in dev)


def test_coverage_run_has_source_branch_omit() -> None:
    run = _config()["tool"]["coverage"]["run"]
    # src-layout: measure everything under src/.
    assert "src" in run["source"]
    assert run["branch"] is True
    omit = run["omit"]
    assert any("tests" in entry for entry in omit)
    assert any("examples" in entry for entry in omit)


def test_all_source_packages_live_under_src() -> None:
    # Every harness package must sit under src/ (the coverage source root),
    # so a newly added package can't silently fall outside the gate.
    for pkg in SOURCE_PACKAGES:
        assert (ROOT / "src" / pkg).is_dir(), f"{pkg} missing under src/"


def test_coverage_report_has_fail_under_and_show_missing() -> None:
    report = _config()["tool"]["coverage"]["report"]
    assert isinstance(report["fail_under"], int)
    assert report["show_missing"] is True
