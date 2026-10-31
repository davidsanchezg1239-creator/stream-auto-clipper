@echo off
title Stream Auto Clipper AI - Bot Automático
color 0b
cd /d "C:\Users\TUF\.gemini\antigravity-ide\scratch\stream-auto-clipper"
echo ======================================================================
echo          STREAM AUTO CLIPPER AI - BOT DE MONITOREO Y EDICION
echo ======================================================================
echo.
echo [1/2] Abriendo panel de control en tu navegador...
timeout /t 2 >nul
start http://localhost:8050
echo.
echo [2/2] Iniciando servidor de monitoreo y edicion con IA...
echo (Manten esta ventana abierta mientras quieras que el bot funcione)
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8050
pause
