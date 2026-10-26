@echo off
REM ============================================================
REM  XAUUSD Lab - demarrage en un double-clic (Windows)
REM  Pre-requis : QuestDB (service Windows) et MT5 ouvert et connecte.
REM ============================================================
cd /d "%~dp0"

REM Recherche du bus compile. On le lance directement depuis "deps" si besoin :
REM l'antivirus (Avast) bloque parfois la copie finale vers "release", pas le fichier compile.
call :findbus
if not defined BUS (
  echo Bus introuvable : compilation automatique, 1 a 5 minutes...
  pushd bus
  cargo build --release --target-dir target-rebuild
  popd
  call :findbus
)
if not defined BUS (
  echo [ERREUR] Le bus n'a pas pu etre compile. Verifie l'exception Avast sur le dossier bus.
  pause
  exit /b 1
)

if not exist admin_token.txt (
  echo Choisis le mot de passe qui permettra de RELACHER le bouton STOP.
  set /p "TOKEN=Mot de passe : "
  call echo %%TOKEN%%> admin_token.txt
)
set /p ADMIN_TOKEN=<admin_token.txt

echo [1/4] Bus d'evenements : %BUS%
start "1-BUS (ne pas fermer)" /min cmd /k "set "QUESTDB_ILP=127.0.0.1:9009"&& "%BUS%""
timeout /t 3 /nobreak >nul

echo [2/4] Agents de strategie...
start "2-AGENTS (ne pas fermer)" /min cmd /k "py -m src.agents.runner all"

echo [3/4] API et interface...
start "3-API (ne pas fermer)" /min cmd /k "set "ADMIN_TOKEN=%ADMIN_TOKEN%"&& py -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --no-access-log"
timeout /t 6 /nobreak >nul

echo [4/4] Pont MT5 (MT5 doit etre ouvert)...
start "4-MT5 (ne pas fermer)" /min cmd /k "py -m src.feeders.mt5 --symbol GOLD"
start "5-HISTORIQUE" cmd /k "py -m src.feeders.mt5 --symbol GOLD --backfill-only"
timeout /t 2 /nobreak >nul

start "" http://127.0.0.1:8000/ui/
echo.
echo Tout est lance. Les 4 fenetres sont reduites dans la barre des taches : ne les ferme pas.
echo Pour tout arreter : double-clic sur ARRETER.bat
timeout /t 10
exit /b 0

:findbus
set "BUS="
for %%F in (bus\target-rebuild\release\hinova-bus.exe bus\target-rebuild\release\deps\hinova_bus.exe bus\target\release\hinova-bus.exe bus\target\release\deps\hinova_bus.exe bus\target-rebuild\release\bus.exe bus\target\release\bus.exe bus\target\release\deps\bus.exe) do (
  if not defined BUS if exist "%%F" set "BUS=%%F"
)
exit /b 0
