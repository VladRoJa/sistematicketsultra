# Script de PowerShell para automatizar Git

param (
    [string]$commitMessage = "Actualización automática"
)

# Mostrar estado del repositorio
Write-Host "Estado del repositorio:"
git status

# Agregar todos los cambios
Write-Host "Agregando archivos..."
git add .

# Hacer commit con mensaje
Write-Host "Haciendo commit: '$commitMessage'"
git commit -m "$commitMessage"

# Subir cambios a GitHub
Write-Host "Subiendo cambios a GitHub..."
git push origin main

Write-Host "Cambios subidos correctamente."
