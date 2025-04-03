@echo off
:: GIT COMMIT ULTRA POWERED – .BAT Launcher 🚀
:: Autor: ChatGPT para VladRoJa

set script=git-commit-ultra.ps1

:: Verifica que el script existe
if not exist "%~dp0%script%" (
    echo ❌ No se encontró %script% en esta carpeta.
    pause
    exit /b
)

:: Ejecutar PowerShell con permisos sin restricciones (solo para este script)
powershell -ExecutionPolicy Bypass -NoLogo -NoProfile -File "%~dp0%script%"

pause
exit
