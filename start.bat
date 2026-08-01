@echo off
title Philly Outreach CRM
echo ============================================================
echo   Starting Philly Outreach CRM
echo ============================================================
echo.

cd /d "%~dp0"

:: Kill any existing servers on our ports
echo Clearing old processes...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
timeout /t 2 /nobreak >nul

echo Starting API server on port 8000 (work mode)...
start "CRM API" cmd /k "cd /d %~dp0 && set DEMO_MODE=0&& set DEMO_STATS=0&& uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"

echo Starting frontend on port 5173...
start "CRM Frontend" cmd /k "cd /d %~dp0web && npm run dev"

echo Waiting for servers to start...
timeout /t 8 /nobreak >nul

echo.
echo   API:  http://127.0.0.1:8000/docs
echo   CRM:  http://127.0.0.1:5173
echo.
echo Opening CRM in browser...
start http://127.0.0.1:5173

echo.
echo Close this window anytime. The servers run in their own windows.
timeout /t 3 /nobreak >nul
