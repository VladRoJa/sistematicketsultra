# Google Ads M5 — carga histórica explícita y despliegue seguro

**Alcance:** solo `APPROVED_PROVISIONAL_XLSX`, cuenta `2739125201`, período `2026-09-24..2026-10-08`, Warehouse upload `21499`. **No activa atribución en el Funnel.**

## Regla de portabilidad

- `flask db upgrade` aplica **solo** la migración de esquema `c7e4a9b2d601`. No importa identidades históricas ni exige que exista el upload 21499.
- La carga aprobada **NO forma parte de Alembic**. En ambientes nuevos/desarrollo sin ese upload, se ejecutan las migraciones normalmente y la tabla queda vacía; no se simula ni fabrica un mapeo.
- La carga real se realiza solamente mediante `backend/scripts/apply_google_ads_m5_approved_identities.py`, que consulta el manifiesto versionado en `backend/migrations/data/google_ads_m5_identity_seed_20261012.json`. El botón/comando de escritura no está conectado a ninguna ruta web ni scheduler.

## Validación antes de escritura

El comando revisa:

1. Upload 21499 existente y `ACTIVE`, tipo, nombre, fechas, tamaño, SHA-256 almacenado y **SHA-256 recalculado sobre bytes físicos del XLSX**.
2. 26 triples cuenta+campaña+grupo únicos, hashes derivados correctos, 26 sucursales y catálogo M4 sin conflictos.
3. 645 registros grupo-día, una cuenta, 15 días completos, 43 identidades, 26 autorizadas, 15 sin actividad y `Marca/EGADE` sin distribuir.
4. Gasto cuenta 19,126.37 MXN; gasto local 17,624.73 MXN; pases Google Ads 64 y compras web Ads 16; clics e impresiones exactos; conciliación campaña-día con `google_ads_daily_metrics`.
5. Tabla vacía o con **exactamente** las 26 filas autorizadas, sin desviaciones de fechas, manifiesto, upload ni sucursal.

Si algo cambia, falla cerrado **antes de insertar**. `--apply` utiliza una sola transacción PostgreSQL y bloqueo asesor transaccional para impedir carreras entre ejecuciones. El modo por defecto hace únicamente consultas y no escribe. La reejecución con los mismos registros es idempotente; con registros distintos falla.

## Secuencia operativa (SOLO tras autorización de merge y despliegue)

1. Revisar que los PR apilados se integraron en orden: #858 documental → #860 esquema → #861 servicio/CLI. Verificar HEAD único de Alembic en el commit que se va a desplegar. No seguir si `main` avanzó sin revisión.
2. Flujo normal: repo local → merge autorizado → servidor `git pull` → reconstrucción del backend (si autorizada) → `flask db upgrade`. El upgrade debe poder completarse **sin** el upload en una BD nueva.
3. En la BD real con el histórico, ejecutar solo revisión:
   ```bash
   docker compose exec -T backend python -m scripts.apply_google_ads_m5_approved_identities
   ```
   Debe terminar con `ACTION = CHECK_ONLY`, `APPROVED_IDENTITIES = 26`, `SOURCE_UPLOAD_ID = 21499`, `M5_IDENTITY_PREFLIGHT_OK` y sin insertar.
4. Con **autorización explícita y separada** para aplicar esas 26 identidades, ejecutar:
   ```bash
   docker compose exec -T backend python -m scripts.apply_google_ads_m5_approved_identities --apply
   ```
   Debe terminar con `ACTION = APPLY`, `FINAL_IDENTITIES = 26` y `M5_IDENTITY_APPLY_OK`.
5. Confirmar por lectura SQL que hay exactamente 26 triples, un solo upload 21499, 26 sucursales distintas, fechas de vigencia 2026-09-24..2026-10-08 y el estado provisional; repetir preflight para demostrar idempotencia.

**Nunca ejecutar `--apply` antes de la aprobación del propietario.** El comando no envía campañas, no modifica Meta/CRM ni cambia ninguna métrica del Funnel.

## Validaciones de CI

- Pruebas PG16 aisladas del esquema y la carga, casos positivos, ejecución repetida, negativas por identidad/fuente/importe/clics y conflicto de mappings.
- Prueba de fallo si los bytes físicos no coinciden con SHA-256.
- Validar que no existe la antigua revisión Alembic `a63e9f21d48b`, y que `c7e4a9b2d601` queda en el único HEAD de Alembic.
- Las bases sin datos Google M3 **no** necesitan ningún seed para `flask db upgrade`.

## Restricción

Esto soluciona portabilidad del *seed*, no confiere permisos para atribución futura ni convierte hashes provisionales en IDs oficiales de Google Ads API. Cambios de campaña/cuenta/periodo requieren nuevo manifiesto y revisión independiente.
