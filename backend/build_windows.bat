@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt -r requirements-dev.txt pyinstaller
if errorlevel 1 exit /b 1
py -3 -m PyInstaller --noconfirm --clean --onefile --name VendoraBackend --hidden-import flashing --hidden-import repair_planner --collect-all fastapi --collect-all uvicorn --collect-all pydantic app.py
if errorlevel 1 exit /b 1
echo Backend executable created at dist\VendoraBackend.exe
