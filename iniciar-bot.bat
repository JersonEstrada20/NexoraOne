@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno .venv. Ejecuta: python -m venv .venv
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m app.main
pause
