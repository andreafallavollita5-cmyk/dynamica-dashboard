@echo off
setlocal
cd /d "%~dp0"

if not exist logs mkdir logs
echo [%date% %time%] Avvio aggiornamento dati Ads>>logs\daily_update.log

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m src.build_report_data >>logs\daily_update.log 2>&1
) else (
  python -m src.build_report_data >>logs\daily_update.log 2>&1
)

if errorlevel 1 (
  echo [%date% %time%] Aggiornamento fallito>>logs\daily_update.log
  exit /b 1
)

echo [%date% %time%] CSV dashboard aggiornato>>logs\daily_update.log
exit /b 0
