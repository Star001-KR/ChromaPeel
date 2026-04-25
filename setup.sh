#!/usr/bin/env bash
# macOS / Linux setup script. Equivalent to setup.bat on Windows.
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
    echo "[setup] .venv 폴더가 없어 새로 생성합니다..."
    "$PYTHON" -m venv .venv
fi

mkdir -p base alpha

echo "[setup] 의존성 설치 중..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo
echo "[setup] 완료되었습니다. GUI 실행:"
echo "    ./run.sh"
echo "또는 CLI 모드:"
echo "    .venv/bin/python imageAlpha.py"

if [ "$(uname)" = "Linux" ]; then
    if ! command -v xclip >/dev/null 2>&1 && ! command -v wl-copy >/dev/null 2>&1; then
        echo
        echo "[setup] 참고: 이미지 클립보드 복사를 사용하려면 'xclip'(X11) 또는"
        echo "        'wl-clipboard'(Wayland) 패키지를 설치하세요."
    fi
fi
