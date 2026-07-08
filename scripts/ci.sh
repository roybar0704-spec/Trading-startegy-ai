#!/usr/bin/env bash
# Local CI: what every commit must pass. Mirrors the Quality Gates in docs/QUALITY_GATES.md.
set -euo pipefail
cd "$(dirname "$0")/.."
RUN="uv run"
command -v uv >/dev/null 2>&1 || RUN=""  # fall back to an already-activated venv

echo "== ruff check (Code Quality Gate) =="
$RUN ruff check src tests scripts

echo "== pylint duplicate-code (Code Quality Gate) =="
$RUN pylint --disable=all --enable=duplicate-code src

echo "== lint-imports (Architecture Gate) =="
$RUN lint-imports

echo "== pytest -q (Functional Gate) =="
$RUN pytest -q

echo "== frozen-config integrity =="
$RUN python3 -c "from src.config.frozen_guard import verify_frozen_rules; print('rules_v1.yaml OK:', verify_frozen_rules())"

echo "All checks passed."
