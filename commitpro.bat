@echo off
setlocal enabledelayedexpansion

:: Detectar rama actual
for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set branch=%%i

echo 🔍 Rama actual detectada: %branch%

:: Verificar si hay cambios
git diff --shortstat > temp_git_diff.txt
set /p changes=<temp_git_diff.txt
del temp_git_diff.txt

if "%changes%"=="" (
    echo ✅ No hay cambios para hacer commit.
    pause
    exit /b
)

echo 📊 Cambios detectados: %changes%

:: Pedir mensaje de commit
set /p msg=📝 Escribe el mensaje del commit: 

:: Hacer pull para estar actualizado
echo 🔄 Haciendo pull de la rama actual antes de commit...
git pull origin %branch%

:: Commit + push
git add .
git commit -m "!msg!"
git push origin %branch%

echo ✅ Commit y push realizados exitosamente.

:: Preguntar si quiere mergear a main
set /p merge=🔀 ¿Quieres mergear esta rama a main? (S/N): 

if /i "%merge%"=="S" (
    echo 🔄 Cambiando a rama main...
    git checkout main

    echo 🔄 Haciendo pull de main...
    git pull origin main

    echo 🔀 Realizando merge de %branch% en main...
    git merge %branch%

    :: Validar si el merge tuvo conflictos
    if errorlevel 1 (
        echo ❌ Conflictos detectados durante el merge. Revísalos manualmente.
        pause
        exit /b
    )

    echo 🚀 Haciendo push de main actualizado...
    git push origin main

    echo ✅ Merge y push completados exitosamente en main.
) else (
    echo ⏭ Merge omitido. Puedes hacerlo más tarde.
)

pause
