@echo off
cd /d "%~dp0"
python -c "import demoparser2, imageio_ffmpeg" 2>nul
if errorlevel 1 (
    echo Installing first-run dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
python prepare_runtime.py
if errorlevel 1 goto failed
echo Keep this window open while using the CS2 editor in your browser.
python web_app.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Could not start the CS2 editor. Check the message above.
pause
exit /b 1
