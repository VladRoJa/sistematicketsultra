# Contrato — Warehouse Storage Optimization V1

Fecha: 2026-11-02. Estado: autorizado para trabajo en rama, sin despliegue ni migraciones productivas.

## Objetivo
Reducir crecimiento histórico de Warehouse sin afectar Track, Funnel, Contact Center o auditoría. Mantener PostgreSQL y Alembic.

## Evidencia en producción
- Venta Total: 31 GB; 236 snapshots canónicos (16,014,599 filas reportadas) y 142 no canónicos (14,096,579).
- iVentas: 12 GB; 5 corridas canónicas (414,104 contactos) y 359 no canónicas (16,676,371).
- Corte de Caja: 7.4 GB; 1,037 snapshots canónicos, 1,033 en fechas con varios canónicos; 33,797,716 filas reportadas.

## WSO-01 — Retiro de Corte de Caja
Decisión: si no existen consumidores actuales, retirar por completo esta fuente obsoleta, sin mantener una base histórica innecesaria.
1. Investigar referencias en repo, tareas automatizadas y consumidores externos de DB.
2. Desconectar generación y persistencia, manteniendo intactas otras fuentes.
3. Validar dependencias y respaldo recuperable de producción antes de retirar tablas.
4. Preparar migración Alembic controlada con comprobaciones previas.
5. Ejecutar únicamente tras revisión, CI, autorización de migración y respaldo probado.
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
