#!/usr/bin/env sh
set -e
python3 -m pytest --cov --cov-report=term-missing "$@"
