#!/usr/bin/env bash
# macOS / Linux GUI launcher. Equivalent to run.bat on Windows.
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[run] .venv 가 없습니다. 먼저 ./setup.sh 를 실행하세요."
    exit 1
fi

# Import precheck — run.bat 과 동일하게, 의존성 누락이나 패키지 손상을
# silent fail 시키지 않고 사용자에게 traceback + 가이드를 노출한다.
err_log=$(mktemp -t chromapeel_import_err.XXXXXX)
trap 'rm -f "$err_log"' EXIT
if ! .venv/bin/python -c "import chromapeel_gui" 2>"$err_log"; then
    echo "[run] chromapeel_gui import 실패. 의존성이 누락됐거나 패키지가 손상됐을 수 있습니다."
    cat "$err_log"
    echo
    echo "./setup.sh 를 다시 실행하거나 문제를 해결한 뒤 재시도하세요."
    exit 1
fi

exec .venv/bin/python -m chromapeel_gui
