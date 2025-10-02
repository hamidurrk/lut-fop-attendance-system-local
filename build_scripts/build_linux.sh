#!/usr/bin/env bash
set -euo pipefail

MODE="onedir"
if [[ $# -ge 1 ]]; then
  MODE="$1"
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
PYTHON_BIN="$VENV_PATH/bin/python"

if [[ ! -d "$VENV_PATH" ]]; then
  python3 -m venv "$VENV_PATH"
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt"

ARGS=(
  "--clean"
  "--noconfirm"
  "--specpath" "$PROJECT_ROOT/build_scripts"
  "$PROJECT_ROOT/build_scripts/attendance_app.spec"
)

if [[ "$MODE" == "onefile" ]]; then
  ARGS+=("--onefile")
fi

"$PYTHON_BIN" -m PyInstaller "${ARGS[@]}"
