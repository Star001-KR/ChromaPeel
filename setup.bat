@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv" (
    echo [setup] .venv 폴더가 없어 새로 생성합니다...
    python -m venv .venv
    if errorlevel 1 (
        echo [setup] 가상환경 생성 실패. Python 설치 여부를 확인하세요.
        pause
        exit /b 1
    )
)

if not exist "base" (
    echo [setup] base 폴더 생성
    mkdir base
)
if not exist "alpha" (
    echo [setup] alpha 폴더 생성
    mkdir alpha
)

echo [setup] .venv 활성화 및 의존성 설치 중...
call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo [setup] 의존성 설치 실패.
    pause
    exit /b 1
)

echo.
echo [setup] 완료되었습니다. GUI 실행:
echo     run.bat  (더블클릭)
echo 또는 CLI 모드:
echo     .venv\Scripts\python.exe imageAlpha.py
pause
