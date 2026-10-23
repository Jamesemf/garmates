@echo off
rem Start the dashboard without `conda activate` - works even when PowerShell's execution
rem policy blocks profile scripts. Extra arguments pass through, e.g.  start.cmd --port 9000
setlocal
cd /d "%~dp0"

if not exist "frontend\dist\index.html" (
    echo Building the web app first - this takes a minute the first time...
    pushd frontend
    call conda run -n garmin-dashboard --no-capture-output npm install || goto :failed
    call conda run -n garmin-dashboard --no-capture-output npm run build || goto :failed
    popd
)

call conda run -n garmin-dashboard --no-capture-output garmin-dashboard serve %*
exit /b %errorlevel%

:failed
echo Building the web app failed - see the messages above.
exit /b 1
