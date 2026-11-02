# Contrato — Warehouse Storage Optimization V1

**Fecha:** 2026-11-02 · **Estado:** WSO-01 en PR DRAFT, sin merge ni eliminación productiva.
**PR:** https://github.com/VladRoJa/sistematicketsultra/pull/1195

## 1. Objetivo y alcance

Eliminar almacenamiento innecesario en Warehouse sin modificar los cálculos de Track, Funnel ni Contact Center.

- **WSO-01: retiro total de Corte de Caja** (código, ORM, tablas, uploads, auditoría vinculada, archivos XLSX y tipo de reporte). Decisión del propietario: **sin cuarentena y sin respaldo nuevo**. Gasca conserva la fuente de información; esto **no garantiza** la restauración exacta del histórico de Suite Ultra.
- **WSO-02: optimización de contactos iVentas.** Preservar cortes de Funnel y la semántica histórica de corridas, tags y canonicalidad.
- **WSO-03: optimización de Venta Total.** Los reportes mes-a-fecha repiten ventas, pero Track y Contact Center consumen filas/IDs; demostrar identidad, cambios retroactivos y paridad antes de compactar.

No alterar permisos ni otros reportes; cambios de esquema siempre con Alembic.

## 2. Datos observados en producción

| Fuente | Espacio aproximado | Evidencia |
|---|---:|---|
| Corte de Caja estructurado | 7.4 GB | 1,037 snapshots, 33,797,716 filas reportadas |
| Corte de Caja RAW | 5.96 GB | **2,061 archivos**; **5,961,032,253 bytes** |
| Contactos iVentas | 12 GB | 5 corridas canónicas y 359 no canónicas |
| Venta Total | 31 GB | 236 snapshots canónicos, 142 no canónicos |

**Integridad Corte de Caja:** `REGISTROS=2061`, `HASHES_CORRECTOS=2061`, `ERRORES=0` comprobados en servidor; 2,061 rutas únicas y exactamente 5,961,032,253 bytes físicos.

**Dependencias:** 23 FKs entrantes a `warehouse_uploads`; las 21 ajenas a Corte de Caja arrojaron **cero referencias**. Las dos restantes tienen 1,037 snapshots propios y 2,084 eventos de auditoría. Otros 1,100 uploads tienen FK **saliente** hacia versiones Track; al borrar el upload no se borra la versión Track. El pipeline actual consume Venta Total, no Corte de Caja, en el tramo de reportes individuales.

**Canon:** el repositorio antiguo de Corte de Caja insertaba el canónico nuevo antes de buscar el previo con ID descendente; puede explicar la multiplicidad de canónicos. Se retira en vez de corregir una fuente obsoleta.

## 3. Decisión de riesgo irreversible

El propietario **rechaza cuarentena y respaldo completo nuevo**, y ordena eliminación permanente de Corte de Caja. No se crearán copias extra de los RAW. El inventario JSON es pequeño, no un respaldo de archivos.

El respaldo PostgreSQL existente falla por espacio: registros más recientes locales 2026-09-24/23/22; ejecuciones 2026-11-01 y 2026-11-02 detenidas porque el script exige 122 GB libres y había aproximadamente 70 GB (tamaño lógico PostgreSQL ~56 GB). **No hay restauración reciente verificada**. La eliminación de 7.4 GB estructurados, 2,061 uploads, 2,084 auditorías y 2,061 archivos RAW es irreversible en Suite Ultra; no se presenta Gasca como respaldo técnicamente probado.

La decisión autoriza **preparar el procedimiento sin backup ni cuarentena**, pero no significa que ya se haya ejecutado contra el servidor. El propietario ejecuta el despliegue y la migración según el flujo Git.

## 4. Implementación

- Extracción, ingesta, despacho, configuración y carga directa/manual de Corte de Caja retiradas. Otros reportes Gasca permanecen habilitados.
- Migración Alembic `wso01caja110226`: borra solo `corte_caja_snapshot_rows`, `corte_caja_snapshots`, la auditoría asociada, los metadatos `warehouse_uploads` de ese tipo y el catálogo `corte_caja`; no usa `CASCADE` sobre otras tablas y aborta con dependencias nuevas.
- `backend/scripts/ops/wso01_corte_caja_files.py`: únicamente `inspect` y `delete`, sin cuarentena. El manifiesto privado asocia cada ID/ruta/tamaño/SHA-256. `delete` exige comprobar primero que la migración retiró los objetos en BD; verifica otra vez los archivos y solamente elimina los listados en manifiesto con `--apply --ack-irreversible`. El script nunca modifica PostgreSQL.
- Diagnóstico de 23 FKs: `backend/scripts/ops/wso01_corte_caja_upload_fk_diagnostic.sql`.
- Pruebas sintéticas de migración sobre PostgreSQL 16 y regresiones Warehouse/Gasca.

## 5. Orden de operación — sin cuarentena

1. Revisión y CI de PR #1195. Merge y despliegue mediante Git, no edición manual del código en producción.
2. Antes de aplicar Alembic: ejecutar `inspect` dentro del runtime backend con `--root` apuntando a los uploads físicos y `--manifest` fuera de `uploads`. Comprobar 2,061 archivos, 5,961,032,253 bytes y SHA-256 sin errores. Se genera solo un JSON privado con nombres/hashes.
3. Ejecutar **una sola vez** la migración Alembic en una ventana controlada. Verificar que Corte de Caja ya no exista en catálogos/tablas/metadata y que Track y Venta Total sigan funcionando.
4. Ejecutar `delete --apply --ack-irreversible` utilizando el mismo root/manifiesto: revalida cada archivo y comprueba que la migración se haya aplicado. Borrado directo mediante `unlink`; sin movimientos ni duplicaciones.
5. Medir almacenamiento realmente recuperado, validar que no queden archivos de `corte_caja`, y que Warehouse/Track/Marketing mantengan sus endpoints.

**Regla de corte:** si `inspect` encuentra rutas, archivos o hashes distintos, NO ejecutar migración. Si la migración falla, NO ejecutar eliminación física. Si la eliminación de archivos es parcial, el modo `delete` permite reintentar con el mismo manifiesto, sin tocar archivos ajenos. El `downgrade` no recupera datos eliminados.

### Comando de inspección (cuando la rama haya sido fusionada y desplegada)

```bash
cd ~/sistematicketsultra
docker compose run --rm --no-deps -v "$PWD:/workspace" backend \
  python -m scripts.ops.wso01_corte_caja_files inspect \
  --root /workspace \
  --manifest /workspace/private/wso01/manifest.json
```

**No ejecutar aún la migración ni el borrado físico sin haber revisado el resultado de `inspect`.** El manifiesto está en `private/wso01/`, ignorado por Git, y no es una copia de los XLSX.

## 6. Validación y estado

- Datos y SHA-256 en producción: **PASS**.
- Primer CI de la implementación anterior: **11/11 workflows SUCCESS**.
- Nuevo procedimiento de borrado directo: pendiente de CI sobre el HEAD actualizado.
- **NOT_RUN:** migración productiva, borrado físico, liberación de almacenamiento, recuperación de datos.
