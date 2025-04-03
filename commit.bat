@echo off
setlocal enabledelayedexpansion

echo 🔍 Revisando cambios...
git diff --shortstat > temp_git_diff.txt
set /p changes=<temp_git_diff.txt
del temp_git_diff.txt

if "%changes%"=="" (
    echo ✅ No hay cambios para hacer commit.
    pause
    exit /b
)

echo 📊 Cambios detectados: %changes%

set /p msg=📝 Escribe el mensaje del commit: 

echo.
echo 🌿 Ramas locales disponibles:
for /f "tokens=*" %%i in ('git branch --format="%%(refname:short)"') do (
    echo   - %%i
)

set /p branch=📍 Escribe el nombre de la rama a la que quieres hacer push: 

echo 📦 Haciendo push a la rama "%branch%"...

git add .
git commit -m "%msg%"
git push origin %branch%

pause
