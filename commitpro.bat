@echo off
setlocal enabledelayedexpansion

:: =========================
::  Git workflow con ramas
:: =========================

git rev-parse --is-inside-work-tree >nul 2>&1 || (
  echo ❌ No estas dentro de un repositorio git.
  pause & exit /b 1
)

git remote get-url origin >nul 2>&1 || (
  echo ❌ No hay remoto "origin" configurado.
  pause & exit /b 1
)

echo 🔄 Actualizando remoto...
git fetch --prune

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set CURRENT_BRANCH=%%b
echo 🟢 Rama actual: %CURRENT_BRANCH%

:: =========================
::  Evitar commits a main
:: =========================
if /i "%CURRENT_BRANCH%"=="main" (
  echo 🚫 Estas en "main". No se permite commitear/pushear directo a produccion.
  echo.
  echo 🌱 ¿Que deseas hacer?
  echo   1^) Crear nueva rama desde origin/main
  echo   2^) Cambiar a una rama existente
  set /p opt=Elige 1 o 2: 

  if "%opt%"=="1" (
    echo.
    echo Prefijos sugeridos: feature/, bugfix/, hotfix/
    set /p BR_PREFIX=Prefijo [feature/]: 
    if "%BR_PREFIX%"=="" set BR_PREFIX=feature/
    set /p BR_NAME=Nombre corto (ej. tickets-filtros): 
    if "%BR_NAME%"=="" (
      echo ❌ Nombre invalido.
      pause & exit /b 1
    )
    for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
    set NEW_BRANCH=%BR_PREFIX%%BR_NAME%/%TODAY%

    echo 🔁 Preparando base limpia: origin/main
    git switch main || git checkout main
    git pull --ff-only origin main || (
      echo ❌ No se pudo actualizar main (merge requerido). Resuelve primero.
      pause & exit /b 1
    )
    echo 🌿 Creando y cambiando a "%NEW_BRANCH%"
    git switch -c "%NEW_BRANCH%" || (
      echo ❌ No se pudo crear la rama.
      pause & exit /b 1
    )
    set CURRENT_BRANCH=%NEW_BRANCH%
  ) else if "%opt%"=="2" (
    echo.
    echo 📜 Ramas locales:
    git branch --format="  - %(refname:short)"
    echo.
    set /p TARGET=Escribe el nombre exacto de la rama: 
    if "%TARGET%"=="" (
      echo ❌ Nombre invalido.
      pause & exit /b 1
    )
    git switch "%TARGET%" || (
      echo ❌ No se pudo cambiar a la rama.
      pause & exit /b 1
    )
    set CURRENT_BRANCH=%TARGET%
  ) else (
    echo ❌ Opcion invalida.
    pause & exit /b 1
  )
)

:: =========================
::  Detectar cambios
:: =========================
echo.
echo 🔍 Revisando cambios sin commitear...
git diff --shortstat > temp_git_diff.txt
set /p changes=<temp_git_diff.txt
del temp_git_diff.txt

if "%changes%"=="" (
  echo ✅ No hay cambios para commit en "%CURRENT_BRANCH%".
  echo (Si solo querias crear/cambiar de rama, ya quedo.)
  pause & exit /b 0
)

echo 📊 Cambios: %changes%
set /p msg=📝 Mensaje del commit: 
if "%msg%"=="" set msg=Actualizacion

echo ➕ Agregando...
git add -A

echo 💬 Commit...
git commit -m "%msg%" || (
  echo ❌ Fallo el commit.
  pause & exit /b 1
)

:: =========================
::  Push (crea upstream si no existe)
:: =========================
git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
if errorlevel 1 (
  echo 🚀 Push inicial con upstream...
  git push -u origin "%CURRENT_BRANCH%" || (
    echo ❌ Fallo el push.
    pause & exit /b 1
  )
) else (
  echo 🚀 Push...
  git push || (
    echo ❌ Fallo el push.
    pause & exit /b 1
  )
)

:: =========================
::  Abrir PR automaticamente
:: =========================
for /f "delims=" %%u in ('git remote get-url origin') do set REMOTE_URL=%%u

:: Usamos PowerShell para parsear https/ssh y construir URL de PR
for /f "delims=" %%p in ('powershell -NoProfile -Command ^
  "$u='%REMOTE_URL%';" ^
  "if($u -match '^git@([^:]+):([^/]+)/([^\.]+)(\.git)?$'){ $host=$matches[1]; $owner=$matches[2]; $repo=$matches[3]; }" ^
  "elseif($u -match '^https?://([^/]+)/([^/]+)/([^\.]+)(\.git)?$'){ $host=$matches[1]; $owner=$matches[2]; $repo=$matches[3]; }" ^
  "else{ $host=''; $owner=''; $repo=''; }" ^
  "$branch='%CURRENT_BRANCH%';" ^
  "$target='main';" ^
  "if($host -eq 'github.com'){"
  "  $url = 'https://github.com/'+$owner+'/'+$repo+'/compare/'+$target+'...'+$branch+'?expand=1';"
  "} elseif($host -eq 'gitlab.com'){"
  "  $url = 'https://gitlab.com/'+$owner+'/'+$repo+'/-/merge_requests/new?merge_request%5Bsource_branch%5D='+$branch+'&merge_request%5Btarget_branch%5D='+$target;"
  "} elseif($host -eq 'bitbucket.org'){"
  "  $url = 'https://bitbucket.org/'+$owner+'/'+$repo+'/pull-requests/new?source='+$branch+'&dest='+$target;"
  "} else { $url=''; }"
  "Write-Output $url"
') do set PR_URL=%%p

if not "%PR_URL%"=="" (
  echo 🌐 Abriendo PR: %PR_URL%
  start "" "%PR_URL%"
) else (
  echo ℹ️ Remoto no reconocido para abrir PR automaticamente. Crea el PR manualmente.
)

echo ✅ Listo. Rama: %CURRENT_BRANCH%
echo 💡 Revisa y crea el PR antes de mergear a main.
pause
