#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null
command -v tesseract >/dev/null
tesseract --list-langs 2>/dev/null | rg -x eng >/dev/null
uv sync --frozen
bash scripts/postgres.sh start
.venv/bin/python -m wain.ingest init
echo 'Dependencies and database ready. See README.md for importing the supplied catalog.'
