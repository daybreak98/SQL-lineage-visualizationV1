#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d backend ]; then
  echo "[C10] Running backend golden tests"
  (cd backend && pytest tests/golden/test_c10_golden_cases.py -q)
fi

if [ -d frontend ]; then
  echo "[C10] Running frontend tests"
  (cd frontend && npm test -- --run)
fi
