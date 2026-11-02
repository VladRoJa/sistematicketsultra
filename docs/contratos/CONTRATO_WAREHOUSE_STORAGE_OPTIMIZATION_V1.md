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
8. Medir funcionamiento y espacio real recuperado. Los respaldos de seguridad temporales no equivalen a almacenamiento permanente.

Hallazgo: `corte_caja_repository.py::persist_corte_caja_snapshot` inserta un nuevo canónico antes de buscar otro canónico por ID descendente; puede dejar varios canónicos por fecha.

## WSO-02 — iVentas
Las filas representan snapshots inmutables por corrida. Los lectores del funnel pueden requerir cortes exactos diferentes a la canónica mensual. Compactar con paridad histórica antes de retirar versiones redundantes.

## WSO-03 — Venta Total
El reporte es acumulado del primer día del mes hasta la fecha solicitada; los snapshots pueden repetir ventas. Track y Contact Center consumen filas e IDs históricos. Validar identidad de operación, cambios retroactivos y resultados antes de usar deltas/checkpoints.

## Reglas
No modificar datos de producción sin autorización; no cambiar permisos, reglas de negocio ni cálculos. Trabajar paso a paso, probar cada cambio, usar rama aislada y migraciones Alembic para schema. No interpretar porcentajes de filas como porcentaje de GB recuperables.

## Gates pendientes
Inventario final de consumidores, estado de jobs productivos, dependencias externas, respaldo restaurable y aceptación de la migración irreversible.

## Evidencia de dependencias de uploads (2026-11-02)

Consulta de solo lectura sobre los 2,061 uploads Corte de Caja:

- 2,061 rutas únicas `(stored_path, stored_filename)` dentro de este tipo; verificar posibles colisiones con OTROS tipos y existencia física antes de borrar.
- 0 registros en `internal_document_versions`, 0 en `opening_task_document_links`, 0 en `routine_control_provider_runs`.
- 1,100 uploads tienen `track_daily_version_id IS NOT NULL`: es una **FK saliente** del upload hacia `track_daily_versions.id`. Su eliminación no borra versiones Track; no hay prueba de que Corte de Caja alimente cálculos vigentes. El pipeline Track actual consume `venta_total` en el tramo de reportes individuales.
- 2,084 registros en `warehouse_audit_logs` hacen referencia a estos IDs; **FK entrante**, deben tratarse expresamente. La decisión de retirar también auditoría histórica individual requiere una evidencia resumida de la baja, sin conservar todo el histórico obsoleto.
- La consulta anterior sobre FKs/vistas de `corte_caja_snapshots` y `corte_caja_snapshot_rows` regresó vacía, pero NO cubre las FKs entrantes de `warehouse_uploads`.
- El campo `source_file_deleted_at IS NULL` para todos ellos no verifica presencia física. El espacio real recuperable debe medirse en el volumen de archivos.

**Próxima puerta de salida:** la lista de claves foráneas entrantes quedó comprobada (23 restricciones; 2026-11-02). Ejecutar el diagnóstico de solo lectura `backend/scripts/ops/wso01_corte_caja_upload_fk_diagnostic.sql` y exigir cero referencias en las dependencias marcadas `BLOCKER`. El script incluye por separado auditoría (2,084 esperadas) y `corte_caja_snapshots` (1,037 esperadas antes de migración). No confundir el listado de FKs con recuentos de filas. Después comprobar rutas/archivos físicos, colisiones entre tipos, hash y respaldo/restore antes del borrado seguro de `corte_caja`.

## Gate C1 / referencias completas — verificado 2026-11-02

Resultado real de `backend/scripts/ops/wso01_corte_caja_upload_fk_diagnostic.sql`:
- **21 relaciones BLOCKER: 0 filas en todas** (incluidos Google Ads, metas comerciales, documentos, aperturas, rutina, snapshots ajenos).
- `corte_caja_snapshots.warehouse_upload_id`: 1,037 referencias esperadas.
- `warehouse_audit_logs.upload_id`: 2,084 referencias esperadas.
- Solo los 2,061 uploads del tipo `corte_caja` son candidatos de borrado; 1,100 tienen una FK **saliente** a versiones Track, lo que no elimina las versiones al borrar el upload.
- Los conteos de dependencias se tomaron antes de la migración; la migración debe preservar restricciones existentes y abortar ante dependencias nuevas.

## Procedimiento de retiro (aún no ejecutado)

1. Exigir respaldo PostgreSQL verificado mediante restauración y respaldo operativo temporal de archivos. Verificar disponibilidad real de archivos, permisos y espacio en el volumen; confirmar que `--root` apunte al directorio que realmente contiene `uploads/warehouse`. **No suponer que la ruta del contenedor coincide con la del host.**
2. Ejecutar `python -m scripts.ops.wso01_corte_caja_files inspect` desde el runtime backend con `--root`, `--manifest` y `--quarantine-dir` absolutos. El script coteja la identidad exacta del conjunto (2,061/5,961,032,253 bytes), paths exclusivos, tamaño y SHA-256; genera un manifiesto privado. Cualquier archivo ausente o distinto bloquea el procedimiento.
3. Tras autorizar la operación, ejecutar modo `quarantine --apply` desde el mismo root: tras verificar nuevamente todo, mueve los 2,061 archivos a una zona privada separada del directorio público de uploads. `restore --apply` los devuelve si se cancela.
4. Desplegar código de retiro y, en ventana controlada, aplicar la migración Alembic `wso01caja110226`. El `upgrade` borra en la misma transacción tablas propias, auditorías, metadatos y catálogo del reporte, sin cambiar otras fuentes; verifica nuevas referencias `ON DELETE SET NULL` y rutas compartidas. **No aplicar la migración antes de la cuarentena.**
5. Verificar rutas API, Track, catálogos, estado Alembic y conteos residuales. Únicamente después usar `purge --apply --ack-irreversible` para eliminar los archivos ya puestos en cuarentena. Este paso comprueba que no exista metadata restante antes de borrar los ficheros.
6. Medir tamaño liberado en PostgreSQL y disco. Si falla cualquier gate: NO avanzar y usar el mecanismo de recuperación correspondiente. El downgrade no recrea datos; requiere restaurar el respaldo.

**Estado al 2026-11-02:** contrato y cambios de código versionados en rama. Sin pruebas de pytest/CI ejecutadas, sin cuarentena, migración, purge ni cambios productivos.

### Ejecución operativa de la inspección (no autorizada aún)

El `Dockerfile` usa `/app`; los uploads físicos se montan en `/uploads`, según `docker-compose.yml`. Para que el chequeo y la cuarentena estén en **un mismo bind mount** (y puedan moverse archivos sin cruces de filesystem), ejecutar desde la raíz del repositorio en el host, una vez desplegada la rama, con un montaje adicional del propio repositorio a `/workspace`:

```bash
# Paso exclusivamente de inspección: nunca mueve ni elimina archivos RAW.
docker compose run --rm --no-deps \\
  -v "$PWD:/workspace" backend \\
  python -m scripts.ops.wso01_corte_caja_files inspect \\
    --root /workspace \\
    --manifest /workspace/private/wso01/manifest.json \\
    --quarantine-dir /workspace/private/wso01/quarantine
```

La ruta `private/wso01/` debe estar protegida del acceso público y excluida de Git. Revisar el resultado antes de usar `quarantine --apply`. Ejecutar preflight con root equivocado o archivos ausentes debe fallar; no cambiar el script para saltarse esa comprobación. La limpieza final `purge --apply --ack-irreversible` solo va **después** de la migración, las pruebas de recuperación y la aprobación explícita.
