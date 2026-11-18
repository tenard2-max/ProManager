@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PORT=18766
set URL=http://127.0.0.1:%PORT%/

echo [FS 뷰어] Central-Agent Orchestration (아들 프로젝트)
echo [FS 뷰어] 정적 UI + File System Access API
echo [FS 뷰어] 부모 관제 서버(18765)는 별도입니다. 이 bat는 UI만 제공합니다.
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo   - 기존 PID %%a 종료
  taskkill /F /PID %%a >nul 2>&1
)

echo [FS 뷰어] %URL%
echo        Chrome/Edge에서 data 폴더(monitor_agent\data)를 선택하세요.
echo 종료: Ctrl+C
start "" cmd /c "timeout /t 2 /nobreak >nul & start %URL%"
python -m http.server %PORT% --bind 127.0.0.1
pause
