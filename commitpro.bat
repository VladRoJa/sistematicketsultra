@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo === Verificando entorno ===
where git >nul 2>&1 || (echo [ERROR] Git no esta en PATH. & pause & exit /b 1)
git --version

git rev-parse --is-inside-work-tree >nul 2>&1 || (
  echo [ERROR] No estas dentro de un repositorio git.
  pause & exit /b 1
)

git remote get-url origin >nul 2>&1 || (
  echo [ERROR] No hay remoto "origin" configurado.
  pause & exit /b 1
)

echo.
echo === Actualizando referencias de remoto (git fetch --prune) ===
git fetch --prune

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%b"
echo Rama actual: %CURRENT_BRANCH%

echo.
echo === Menu de ramas ===
echo 1) Crear nueva rama desde origin/main
echo 2) Cambiar a una rama existente
echo 3) Continuar en la rama actual: %CURRENT_BRANCH%
choice /C 123 /N /M "Elige 1, 2 o 3: "
set "opt=%errorlevel%"
echo Opcion elegida: %opt%

if "%opt%"=="1" goto CREATE_BRANCH
if "%opt%"=="2" goto SWITCH_BRANCH
if "%opt%"=="3" goto CHECK_CHANGES
echo [ERROR] Opcion invalida.
pause & exit /b 1

:CREATE_BRANCH
echo.
echo Prefijos sugeridos: feature/  bugfix/  hotfix/
set "BR_PREFIX=feature/"
set /p BR_PREFIX=Prefijo (enter = feature/): 
if "%BR_PREFIX%"=="" set "BR_PREFIX=feature/"

set /p BR_NAME=Nombre corto de la rama (ej. tickets-filtros): 
if "%BR_NAME%"=="" (
  echo [ERROR] Nombre invalido.
  pause
  exit /b 1
)

REM --- Slugify: minusculas, permite guion, espacios->guiones ---
for /f "delims=" %%s in ('powershell -NoProfile -Command ^
  "$n='%BR_NAME%'.ToLower();" ^
  "$n=$n -replace 'á|à|ä','a' -replace 'é|è|ë','e' -replace 'í|ì|ï','i' -replace 'ó|ò|ö','o' -replace 'ú|ù|ü','u' -replace 'ñ','n';" ^
  "$n=$n -replace '[^a-z0-9 \-]','';" ^
  "$n=$n -replace '\s+','-';" ^
  "Write-Output $n"') do set "SLUG=%%s"

if "%SLUG%"=="" (
  echo [ERROR] El nombre quedo vacio tras sanitizar.
  pause
  exit /b 1
)

for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "NEW_BRANCH=%BR_PREFIX%%SLUG%/%TODAY%"

echo.
echo [INFO] Cambiando a main...
git switch main >nul 2>&1
if errorlevel 1 git checkout main
if errorlevel 1 (
  echo [ERROR] No se pudo cambiar a main.
  pause
  exit /b 1
)

echo [INFO] Actualizando main con origin/main ff-only...
git pull --ff-only origin main
if errorlevel 1 (
  echo [ERROR] Pull ff-only fallo. Puede haber merges pendientes o falta de red.
  pause
  exit /b 1
)

echo [INFO] Creando y cambiando a "%NEW_BRANCH%"
git switch -c "%NEW_BRANCH%" >nul 2>&1
if errorlevel 1 git checkout -b "%NEW_BRANCH%"
if errorlevel 1 (
  echo [ERROR] No se pudo crear la rama.
  pause
  exit /b 1
)
set "CURRENT_BRANCH=%NEW_BRANCH%"
goto CHECK_CHANGES

:SWITCH_BRANCH
echo.
echo Ramas locales:
git branch --format="  - %(refname:short)"
echo.
set /p TARGET=Escribe el nombre exacto de la rama: 
if "%TARGET%"=="" (
  echo [ERROR] Nombre invalido.
  pause
  exit /b 1
)

echo [INFO] Cambiando a "%TARGET%"
git switch "%TARGET%" >nul 2>&1
if errorlevel 1 git checkout "%TARGET%"
if errorlevel 1 (
  echo [ERROR] No se pudo cambiar a la rama indicada.
  pause
  exit /b 1
)
set "CURRENT_BRANCH=%TARGET%"

:CHECK_CHANGES
echo.
echo === Revisando cambios sin commitear ===
git diff --shortstat > temp_git_diff.txt
set /p changes=<temp_git_diff.txt
del temp_git_diff.txt 2>nul

if "%changes%"=="" (
  echo No hay cambios para commit en "%CURRENT_BRANCH%".
  echo Quieres publicar la rama vacia en origin para abrir PR?
  choice /C SN /N /M "  [S]i / [N]o: "
  if "%errorlevel%"=="1" (
    echo Subiendo rama vacia con upstream...
    git push -u origin "%CURRENT_BRANCH%"
    if errorlevel 1 (
      echo [ERROR] Fallo el push de la rama vacia.
      pause
      exit /b 1
    )
    goto OPEN_PR
  ) else (
    echo Ok, no se publico la rama. Trabaja cambios y vuelve a correr el script.
    pause
    exit /b 0
  )
)

echo Cambios detectados: %changes%
set /p msg=Mensaje del commit: 
if "%msg%"=="" set "msg=Actualizacion"

echo.
echo Agregando archivos (git add -A)...
git add -A

echo Haciendo commit...
git commit -m "%msg%"
if errorlevel 1 (
  echo [ERROR] Fallo el commit.
  pause
  exit /b 1
)

echo.
echo === Push (crea upstream si no existe) ===
git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
if errorlevel 1 (
  echo Push inicial con upstream...
  git push -u origin "%CURRENT_BRANCH%"
  if errorlevel 1 (
    echo [ERROR] Fallo el push inicial.
    pause
    exit /b 1
  )
) else (
  echo Push normal...
  git push
  if errorlevel 1 (
    echo [ERROR] Fallo el push.
    pause
    exit /b 1
  )
)

:OPEN_PR
echo.
echo === Intentando abrir PR automaticamente ===
for /f "delims=" %%u in ('git remote get-url origin') do set "REMOTE_URL=%%u"

for /f "delims=" %%p in ('powershell -NoProfile -Command ^
  "$u='%REMOTE_URL%';" ^
  "if($u -match '^git@([^:]+):([^/]+)/([^\.]+)(\.git)?$'){ $host=$matches[1]; $owner=$matches[2]; $repo=$matches[3]; }" ^
  "elseif($u -match '^https?://([^/]+)/([^/]+)/([^\.]+)(\.git)?$'){ $host=$matches[1]; $owner=$matches[2]; $repo=$matches[3]; }" ^
  "else{ $host=''; $owner=''; $repo=''; }" ^
  "$branch='%CURRENT_BRANCH%';" ^
  "$remoteHead = (git symbolic-ref refs/remotes/origin/HEAD 2>$null);" ^
  "if ($remoteHead -and $remoteHead -match 'refs/remotes/origin/(.+)$') { $target = $Matches[1] } else { $target = 'main' }" ^
  "if($host -eq 'github.com'){"
  "  $url = 'https://github.com/'+$owner+'/'+$repo+'/compare/'+$target+'...'+$branch+'?expand=1';"
  "} elseif($host -eq 'gitlab.com'){"
  "  $url = 'https://gitlab.com/'+$owner+'/'+$repo+'/-/merge_requests/new?merge_request%5Bsource_branch%5D='+$branch+'&merge_request%5Btarget_branch%5D='+$target;"
  "} elseif($host -eq 'bitbucket.org'){"
  "  $url = 'https://bitbucket.org/'+$owner+'/'+$repo+'/pull-requests/new?source='+$branch+'&dest='+$target;"
  "} else { $url=''; }" ^
  "Write-Output $url"
') do set "PR_URL=%%p"

if not "%PR_URL%"=="" (
  echo Abriendo PR: %PR_URL%
  start "" "%PR_URL%"
) else (
  echo Remoto no reconocido para abrir PR automaticamente.
)

echo.
echo === FIN ===
echo Rama actual: %CURRENT_BRANCH%
pause
