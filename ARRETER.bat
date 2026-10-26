@echo off
REM XAUUSD Lab - arret propre de toutes les fenetres du bot (QuestDB et MT5 restent ouverts)
taskkill /fi "WINDOWTITLE eq 1-BUS*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq 2-AGENTS*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq 3-API*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq 4-MT5*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq 5-HISTORIQUE*" /t /f >nul 2>&1
taskkill /im bus.exe /f >nul 2>&1
taskkill /im hinova-bus.exe /f >nul 2>&1
echo Bot arrete.
timeout /t 3
