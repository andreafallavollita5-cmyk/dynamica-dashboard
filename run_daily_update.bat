@echo off
setlocal
cd /d "%~dp0"

if not exist logs mkdir logs
echo [%date% %time%] Avvio aggiornamento dati Ads>>logs\daily_update.log

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" -m src.build_spend_daily >>logs\daily_update.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] Aggiornamento storico giornaliero fallito>>logs\daily_update.log
  exit /b 1
)

"%PYTHON%" -m src.build_report_data >>logs\daily_update.log 2>&1

if errorlevel 1 (
  echo [%date% %time%] Aggiornamento fallito>>logs\daily_update.log
  exit /b 1
)

"%PYTHON%" -m src.update_excel >>logs\daily_update.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] Export Excel fallito>>logs\daily_update.log
  exit /b 1
)

"%PYTHON%" -m src.archive_outputs >>logs\daily_update.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] Archivio locale fallito>>logs\daily_update.log
  exit /b 1
)

"%PYTHON%" -m src.publish_to_github >>logs\daily_update.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] Pubblicazione GitHub fallita>>logs\daily_update.log
  exit /b 1
)

echo [%date% %time%] Pipeline dashboard completata>>logs\daily_update.log
exit /b 0
