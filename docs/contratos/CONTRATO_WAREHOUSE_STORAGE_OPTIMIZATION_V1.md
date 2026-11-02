# Contrato — Warehouse Storage Optimization V1

Fecha: 2026-11-02. Estado: autorizado para trabajo en rama, sin despliegue ni migraciones productivas.

## Objetivo
Reducir crecimiento histórico de Warehouse sin afectar Track, Funnel, Contact Center o auditoría. Mantener PostgreSQL y Alembic.

## Evidencia en producción
- Venta Total: 31 GB; 236 snapshots canónicos (16,014,599 filas reportadas) y 142 no canónicos (14,096,579).
- iVentas: 12 GB; 5 corridas canónicas (414,104 contactos) y 359 no canónicas (16,676,371).
- Corte de Caja: 7.4 GB; 1,037 snapshots canónicos, 1,033 en fechas con varios canónicos; 33,797,716 filas reportadas.
- Archivos originales Corte de Caja: 2,061 registros en `warehouse_uploads`, suma de `file_size_bytes` = 5,961,032,253 bytes (~5.96 GB decimales); primer upload 2026-05-08, último 2026-09-05. Los 2,061 presentan `source_file_deleted_at IS NULL` (no equivale a verificar existencia física). La cantidad de bytes puede sumar referencias repetidas al mismo archivo; comprobar rutas únicas antes de estimar liberación.
- **Alcance ampliado WSO-01:** además de eliminar las tablas estructuradas, retirar los archivos físicos, los metadatos `warehouse_uploads` y su tipo de reporte una vez demostrada ausencia de referencias relevantes. Los `warehouse_audit_logs` que dependan de esos uploads requieren decisión explícita y migración consistente. Eliminar únicamente IDs comprobados de `corte_caja`, nunca datos generales de Warehouse.

## WSO-01 — Retiro de Corte de Caja
Decisión: si no existen consumidores actuales, retirar por completo esta fuente obsoleta, sin mantener una base histórica innecesaria.
1. Investigar referencias en repo, tareas automatizadas y consumidores externos de DB.
2. Desconectar generación y persistencia, manteniendo intactas otras fuentes.
3. Validar dependencias y respaldo recuperable de producción antes de retirar tablas.
4. Preparar migración Alembic controlada con comprobaciones previas.
5. Antes de limpiar archivos físicos: consultar todas las referencias a `warehouse_uploads.id`, confirmar archivos reales y rutas únicas, generar manifiesto exacto de los 2,061 candidatos, verificar rutas restringidas a `uploads/warehouse/*/corte_caja/` y verificar SHA-256. No borrar rutas compartidas ni referencias activas.
6. Ejecutar eliminación de archivos y metadatos exclusivamente mediante procedimiento controlado y reversible hasta el punto de confirmación, con respaldos probados; no efectuar `rm -rf` ni `DELETE` sin filtro.
7. Ejecutar únicamente tras revisión, CI, autorización de migración y respaldo probado.
6. Medir funcionamiento y espacio real recuperado. Los respaldos de seguridad temporales no equivalen a almacenamiento permanente.

Hallazgo: `corte_caja_repository.py::persist_corte_caja_snapshot` inserta un nuevo canónico antes de buscar otro canónico por ID descendente; puede dejar varios canónicos por fecha.

## WSO-02 — iVentas
Las filas representan snapshots inmutables por corrida. Los lectores del funnel pueden requerir cortes exactos diferentes a la canónica mensual. Compactar con paridad histórica antes de retirar versiones redundantes.

## WSO-03 — Venta Total
El reporte es acumulado del primer día del mes hasta la fecha solicitada; los snapshots pueden repetir ventas. Track y Contact Center consumen filas e IDs históricos. Validar identidad de operación, cambios retroactivos y resultados antes de usar deltas/checkpoints.

## Reglas
No modificar datos de producción sin autorización; no cambiar permisos, reglas de negocio ni cálculos. Trabajar paso a paso, probar cada cambio, usar rama aislada y migraciones Alembic para schema. No interpretar porcentajes de filas como porcentaje de GB recuperables.

## Gates pendientes
Inventario final de consumidores, estado de jobs productivos, dependencias externas, respaldo restaurable y aceptación de la migración irreversible.
