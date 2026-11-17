@echo off
rem Starts the dashboard: backend (:8000), frontend (:5173) and, if ngrok-policy.yml exists,
rem a password-protected ngrok tunnel. Each runs in its own window; close a window to stop it.

rem --- settings ------------------------------------------------------------
set "NGROK=%USERPROFILE%\Downloads\ngrok-v3-stable-windows-amd64\ngrok.exe"
rem Optional fixed domain claimed at dashboard.ngrok.com, e.g. https://name.ngrok-free.app
set "NGROK_URL="
rem --------------------------------------------------------------------------

cd /d "%~dp0"

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if errorlevel 1 (
    start "Markets backend" /d backend cmd /k ".venv\Scripts\markets serve"
) else (
    echo Backend already running on :8000
)

netstat -ano | findstr /r /c:":5173 .*LISTENING" >nul
if errorlevel 1 (
    start "Markets frontend" /d frontend cmd /k "npm run dev"
) else (
    echo Frontend already running on :5173
)

if not exist ngrok-policy.yml (
    echo No ngrok-policy.yml: skipping the public link. Copy ngrok-policy.example.yml and set a password.
    goto browser
)
if not exist "%NGROK%" (
    echo ngrok not found at %NGROK%: skipping the public link. Fix the path at the top of this file.
    goto browser
)
tasklist /fi "imagename eq ngrok.exe" | findstr /i ngrok.exe >nul
if not errorlevel 1 (
    echo ngrok already running
    goto browser
)
if defined NGROK_URL (
    start "Markets ngrok" "%NGROK%" http 5173 --traffic-policy-file ngrok-policy.yml --url %NGROK_URL%
) else (
    start "Markets ngrok" "%NGROK%" http 5173 --traffic-policy-file ngrok-policy.yml
)
echo The public link is shown in the "Markets ngrok" window (Forwarding line).

:browser
timeout /t 5 /nobreak >nul
start "" http://localhost:5173
