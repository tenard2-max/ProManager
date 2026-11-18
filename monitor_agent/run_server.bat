@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 관제 전용 포트 (8765는 XFS 등 다른 로컬 서비스와 충돌 가능)
set PORT=18765
set URL=http://127.0.0.1:%PORT%/

echo [관제] Central-Agent Orchestration
echo [관제] 의존성 확인 중...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo pip 설치 실패. Python PATH를 확인하세요.
  pause
  exit /b 1
)

echo [관제] 포트 %PORT% 사용 중이면 기존 관제 프로세스를 종료합니다...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo   - PID %%a 종료
  taskkill /F /PID %%a >nul 2>&1
)

echo [관제] %URL%
echo        서버 기동 후 브라우저가 자동으로 열립니다.
echo        (참고: 8765는 다른 앱이 쓸 수 있음 → 관제는 %PORT%)
echo 종료: Ctrl+C
start "" cmd /c "timeout /t 2 /nobreak >nul & start %URL%"
python -m app.main
pause
