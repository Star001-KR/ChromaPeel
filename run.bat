@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run] .venv 가 없습니다. 먼저 setup.bat 을 실행하세요.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import chromapeel_gui" 2> "%TEMP%\chromapeel_import_err.log"
if errorlevel 1 (
    echo [run] chromapeel_gui import 실패. 의존성이 누락됐거나 패키지가 손상됐을 수 있습니다.
    type "%TEMP%\chromapeel_import_err.log"
    echo.
    echo setup.bat 을 다시 실행하거나 문제를 해결한 뒤 재시도하세요.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m chromapeel_gui
