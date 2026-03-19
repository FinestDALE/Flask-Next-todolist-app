@echo off
setlocal

set "ROOT=%~dp0"
set "SERVER_DIR=%ROOT%server"
set "CLIENT_DIR=%ROOT%client"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY_CMD=python"
  ) else (
    echo Python was not found on PATH.
    echo Install Python 3, then reopen your terminal and run this file again.
    echo After installing Python, this launcher will start both Flask and Next.js.
    exit /b 1
  )
)

where npm >nul 2>nul
if not %errorlevel%==0 (
  echo npm was not found on PATH.
  echo Install Node.js, then reopen your terminal and run this file again.
  exit /b 1
)

start "Flask Server" cmd /k cd /d "%SERVER_DIR%" ^&^& %PY_CMD% -m flask --app server.py run
start "Next Client" cmd /k cd /d "%CLIENT_DIR%" ^&^& cmd /c npm run dev

echo Started Flask and Next.js in separate windows.
echo Flask API:  http://127.0.0.1:5000
echo Next app:   http://localhost:3000

endlocal
