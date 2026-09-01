#!/usr/bin/env python3
"""F5: per-directory coverage gate.

The aggregate ``fail_under`` in ``pyproject.toml`` is a *tree-wide* lower bound; a
single hot package at 100% can mask a sibling sitting at 60%. This script recomputes
coverage one package at a time and fails when any package drops below its floor.

Usage (from repo root, after a ``pytest --cov`` run produced ``.coverage``):

    python scripts/coverage_gate.py [coverage_file]

Floors come from ``[tool.coverage.coverage_gate]`` (``default_floor``, plus optional
per-package overrides in ``floors``). Exit code is 0 when every package clears its
floor, 1 when any does not, 2 on a usage/data error.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYPROJECT = ROOT / "pyproject.toml"


def _load_floors() -> tuple[float, dict[str, float]]:
    with PYPROJECT.open("rb") as fh:
        cfg = tomllib.load(fh)
    gate = cfg["tool"]["coverage"].get("coverage_gate", {})
    default_floor = float(gate.get("default_floor", 0.0))
    floors = {k: float(v) for k, v in gate.get("floors", {}).items()}
    return default_floor, floors


def _packages() -> list[str]:
    return sorted(
        p.name
        for p in SRC.iterdir()
        if p.is_dir() and p != SRC / "__pycache__" and (p / "__init__.py").exists()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "coverage_file",
        nargs="?",
        default=".coverage",
        help="path to the coverage data file (default: .coverage)",
    )
    args = parser.parse_args(argv)

    try:
        import coverage  # noqa: PLC0415 - lazy import so usage errors are clear
    except ImportError:
        print("coverage_gate: coverage is not installed (pip install coverage)", file=sys.stderr)
        return 2

    default_floor, floors = _load_floors()
    data_file = Path(args.coverage_file)
    if not data_file.exists():
        print(f"coverage_gate: no data file at {args.coverage_file!r}", file=sys.stderr)
        return 2

    cov = coverage.Coverage(data_file=str(data_file))
    cov.load()

    # Parse the text report it produces (Name Stmts Miss … Cover) and group the
    # statement/miss totals by top-level package. Parsing the canonical table is more
    # robust than reimplementing statement counting against CoverageData's internal API.
    import io  # noqa: PLC0415

    report_buf = io.StringIO()
    cov.report(file=report_buf)
    acc: dict[str, list[int]] = {p: [0, 0] for p in _packages()}  # [stmts, miss]
    for line in report_buf.getvalue().splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].endswith(".py"):
            continue  # skip header / separator / TOTAL + non-module lines
        segments = parts[0].replace("\\", "/").split("/")
        # Report names are relative to the coverage source root: "src/pkg/mod.py".
        top = segments[1] if segments[0] == "src" else segments[0]
        if top not in acc:
            continue  # only track packages that live under src/
        acc[top][0] += int(parts[1])  # Stmts
        acc[top][1] += int(parts[2])  # Miss

    failures: list[str] = []
    for pkg in _packages():
        stmts, miss = acc[pkg]
        pct = (stmts - miss) / stmts * 100.0 if stmts else float("inf")
        floor = floors.get(pkg, default_floor)
        mark = "ok " if pct >= floor else "LOW"
        if pct < floor:
            failures.append(pkg)
        print(f"{mark} {pkg}: {pct:5.1f}% (floor {floor:.0f}%)")

    if failures:
        print(f"coverage_gate: packages below floor: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("coverage_gate: all packages at/above floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
