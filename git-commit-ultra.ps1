# ─────────────────────────────────────────────
# GIT COMMIT ULTRA POWERED – PowerShell Edition
# Autor: ChatGPT para VladRoJa 🚀
# ─────────────────────────────────────────────

Clear-Host
Write-Host "🔍 Verificando cambios..." -ForegroundColor Cyan

$hasChanges = git status --porcelain
if ($null -eq $hasChanges) {
    Write-Host "✅ No hay cambios para commitear." -ForegroundColor Green
    pause
    exit
}

# Mostrar resumen de cambios
Write-Host "`n📊 Resumen de cambios:" -ForegroundColor Yellow
git diff --stat

# Contar líneas modificadas
Write-Host "`n📈 Líneas modificadas:"
git diff --shortstat

# Confirmación para continuar
$confirm = Read-Host "`n¿Deseas continuar con el commit? (s/n)"
if ($confirm -ne 's') {
    Write-Host "❌ Commit cancelado." -ForegroundColor Red
    exit
}

# Menú de opciones para tipo de commit
$types = @{
    "1" = "🚀 Feature"
    "2" = "🐛 Bugfix"
    "3" = "🔧 Refactor"
    "4" = "🧪 Test"
    "5" = "📦 Chore"
    "6" = "📝 Docs"
}
Write-Host "`n📝 Selecciona el tipo de commit:"
$types.GetEnumerator() | ForEach-Object { Write-Host "$($_.Key). $($_.Value)" }

$typeKey = Read-Host "Elige una opción (1-6)"
if (-not $types.ContainsKey($typeKey)) {
    Write-Host "❌ Opción inválida. Cancelando..." -ForegroundColor Red
    exit
}
$commitType = $types[$typeKey]

# Mensaje personalizado
$msg = Read-Host "`nEscribe el mensaje del commit"
$fullMsg = "$commitType $msg"

# Confirmación final
Write-Host "`n✅ Mensaje final:"
Write-Host $fullMsg -ForegroundColor Green
$ok = Read-Host "¿Confirmar y hacer push? (s/n)"
if ($ok -ne 's') {
    Write-Host "❌ Cancelado por el usuario." -ForegroundColor Red
    exit
}

# Ejecutar git
git add .
git commit -m "$fullMsg"
git push

Write-Host "`n✅ Commit y push completados con éxito." -ForegroundColor Green
pause
exit