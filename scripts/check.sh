#!/usr/bin/env sh
# Single-command gate: format + lint + test + coverage. All four must pass.
set -e

echo "== format =="
python3 -m ruff format --check .

echo "== lint =="
python3 -m ruff check .

echo "== test + coverage =="
python3 -m pytest --cov --cov-report=term-missing "$@"
