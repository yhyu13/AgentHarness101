"""Meta-tests for packaging: import smoke (F3), metadata contract (F4), demo smoke (F6).

These guard the "installable + CLI + typed" contract so a src-layout regression
cannot silently ship a package that only imports under pytest's ``pythonpath`` hack.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYPROJECT = ROOT / "pyproject.toml"


def _packages() -> list[str]:
    return [
        p.name
        for p in sorted(SRC.iterdir())
        if p.is_dir() and p != SRC / "__pycache__" and (p / "__init__.py").exists()
    ]


def _config() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


# --- F3: every package under src/ imports cleanly (no pytest pythonpath aid) ---
def test_every_src_package_imports_standalone() -> None:
    for name in _packages():
        try:
            importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - only on failure
            raise AssertionError(f"package {name!r} failed to import: {exc}") from exc


# --- F4: the installable contract is declared (subset, not exact-list) ---
def test_build_system_declared() -> None:
    build_system = _config().get("build-system", {})
    assert build_system.get("build-backend"), "build-system is missing build-backend"
    requires = build_system.get("requires", [])
    assert any("setuptools" in r.lower() for r in requires)


def test_package_discovery_under_src() -> None:
    find = _config()["tool"]["setuptools"]["packages"]["find"]
    assert "src" in find.get("where", [])


def test_console_script_exposes_ah() -> None:
    scripts = _config().get("project", {}).get("scripts", {})
    assert scripts.get("ah") == "agent_harness.cli:main"


def test_cli_package_ships_py_typed() -> None:
    assert (SRC / "agent_harness" / "py.typed").is_file()


def test_cli_main_imports_every_layer(capsys) -> None:
    from agent_harness.cli import LAYERS, main

    assert main() == 0
    out = capsys.readouterr().out
    assert "all layers importable" in out
    # every harness layer printed an "ok" line (the CLI package itself is not a layer)
    assert out.count("ok  ") == len(LAYERS)


# --- F6: a real demo runs under a clean cwd (imports must not depend on cwd) ---
def test_harness_layers_demo_runs_from_clean_cwd(tmp_path: Path) -> None:
    demo = ROOT / "examples" / "harness_layers_demo.py"
    proc = subprocess.run(
        [sys.executable, str(demo)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"demo failed:\n{proc.stdout}\n{proc.stderr}"
    assert "Done." in proc.stdout
