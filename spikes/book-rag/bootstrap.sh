#!/usr/bin/env bash
# Create / refresh the shared LAB venv for the book-rag spike.
# Idempotent. Run from the MAIN checkout once; workers reference it by ABSOLUTE
# path (a venv can't be copied into a worktree — its paths are baked in):
#
#     /Users/charbelelhachem/projects/public/math-app/spikes/book-rag/.venv/bin/python
#
# If you'd rather have a per-worktree venv, just run this script from inside the
# worktree — it builds .venv next to itself either way.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"

if [ ! -d "$VENV" ]; then
  echo "creating venv at $VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$HERE/requirements.txt"
echo "venv ready: $VENV"
"$VENV/bin/python" "$HERE/_shared/db.py" || true
