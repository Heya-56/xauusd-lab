@echo off
REM XAUUSD Lab - mise a jour en un double-clic : arret, telechargement GitHub, copie, redemarrage.
REM Le script se recopie d'abord dans %TEMP% pour pouvoir se remplacer lui-meme sans planter.
if /i not "%~1"=="--run" (
  copy /y "%~f0" "%TEMP%\hinova-maj.bat" >nul
  "%TEMP%\hinova-maj.bat" --run "%~dp0"
  exit /b
)
set "BOT=%~2"
if "%BOT:~-1%"=="\" set "BOT=%BOT:~0,-1%"
title Mise a jour du bot
echo.
echo  [1/4] Arret du bot...
call "%BOT%\ARRETER.bat" <nul >nul 2>&1
echo  [2/4] Telechargement de la derniere version...
curl -sL --retry 5 -o "%TEMP%\hinova-bot.zip" https://github.com/Heya-56/xauusd-lab/archive/refs/heads/feat/bot-v1.zip
if errorlevel 1 ( echo  ECHEC du telechargement : verifie Internet puis relance. & pause & exit /b 1 )
echo  [3/4] Copie des fichiers modifies (tes positions papier et ton jeton sont conserves)...
if exist "%TEMP%\xauusd-lab-feat-bot-v1" rmdir /s /q "%TEMP%\xauusd-lab-feat-bot-v1"
tar -xf "%TEMP%\hinova-bot.zip" -C "%TEMP%"
robocopy "%TEMP%\xauusd-lab-feat-bot-v1" "%BOT%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 ( echo  ECHEC de la copie. & pause & exit /b 1 )
echo  [4/4] Redemarrage...
start "" /d "%BOT%" "%BOT%\DEMARRER.bat"
echo.
echo  Termine. Dans le cockpit, fais Ctrl + F5.
timeout /t 8
