@echo off
setlocal

set "ROOT=%~dp0"
set "SERVER_DIR=%ROOT%server"
set "CLIENT_DIR=%ROOT%client"
set "MONGODB_URI=mongodb://127.0.0.1:27017"
set "MONGODB_DB=todo_app"
set "MONGODB_COLLECTION=tasks"
set "PY_EXE="
set "PY_ARGS="

if not defined PY_EXE if exist "%SERVER_DIR%\venv\Scripts\python.exe" (
  set "PY_EXE=%SERVER_DIR%\venv\Scripts\python.exe"
)

if not defined PY_EXE if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" (
  set "PY_EXE=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
)

if not defined PY_EXE (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3"
  )
)

if not defined PY_EXE (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=python"
  )
)

if not defined PY_EXE (
  echo Python was not found on PATH.
  echo Install Python 3, then reopen your terminal and run this file again.
  echo After installing Python, this launcher will start both Flask and Next.js.
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found on PATH.
  echo Install Node.js, then reopen your terminal and run this file again.
  exit /b 1
)

start "Flask Server" /D "%SERVER_DIR%" cmd /k "set MONGODB_URI=%MONGODB_URI% && set MONGODB_DB=%MONGODB_DB% && set MONGODB_COLLECTION=%MONGODB_COLLECTION% && %PY_EXE% %PY_ARGS% -m flask --app server.py run"
start "Next Client" cmd /k "cd /d ""%CLIENT_DIR%"" && npm run dev"

echo Started Flask and Next.js in separate windows.
echo Flask API:  http://localhost:5000
echo Next app:   http://localhost:3000
echo MongoDB:    %MONGODB_URI%  ^(%MONGODB_DB%.%MONGODB_COLLECTION%^)

endlocal
