@echo off
REM ============================================================
REM  XAUUSD Lab - demarrage en un double-clic (Windows)
REM  Pre-requis : QuestDB (service Windows) et MT5 ouvert et connecte.
REM ============================================================
cd /d "%~dp0"

set "BUS=bus\target\release\bus.exe"
if not exist "%BUS%" set "BUS=bus\target\release\deps\bus.exe"
if not exist "%BUS%" (
  echo [ERREUR] Bus introuvable. Compile-le d'abord : cd bus puis cargo build --release
  pause
  exit /b 1
)

if not exist admin_token.txt (
  echo Choisis le mot de passe qui permettra de RELACHER le bouton STOP.
  set /p "TOKEN=Mot de passe : "
  call echo %%TOKEN%%> admin_token.txt
)
set /p ADMIN_TOKEN=<admin_token.txt

echo [1/4] Bus d'evenements...
start "1-BUS (ne pas fermer)" /min cmd /k "set "QUESTDB_ILP=127.0.0.1:9009"&& "%BUS%""
timeout /t 3 /nobreak >nul

echo [2/4] Agents de strategie...
start "2-AGENTS (ne pas fermer)" /min cmd /k "py -m src.agents.runner all"

echo [3/4] API et interface...
start "3-API (ne pas fermer)" /min cmd /k "set "ADMIN_TOKEN=%ADMIN_TOKEN%"&& py -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --no-access-log"
timeout /t 6 /nobreak >nul

echo [4/4] Pont MT5 (MT5 doit etre ouvert)...
start "4-MT5 (ne pas fermer)" /min cmd /k "py -m src.feeders.mt5 --symbol GOLD"
timeout /t 2 /nobreak >nul

start "" http://127.0.0.1:8000/ui/
echo.
echo Tout est lance. Les 4 fenetres sont reduites dans la barre des taches : ne les ferme pas.
echo Pour tout arreter : double-clic sur ARRETER.bat
timeout /t 10
