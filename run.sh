#!/usr/bin/env bash
# macOS / Linux GUI launcher. Equivalent to run.bat on Windows.
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[run] .venv 가 없습니다. 먼저 ./setup.sh 를 실행하세요."
    exit 1
fi

exec .venv/bin/python chromapeel_gui.py
