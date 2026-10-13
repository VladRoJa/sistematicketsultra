# Google Ads M5 — verificación de integridad de Warehouse

**Fecha:** 2026-10-12 (America/Tijuana).  
**Estado:** PASS en la prueba ejecutada por el operador sobre el backend de producción.  
**Alcance:** solo lectura, histórico Google Ads M3 del 2026-09-24 al 2026-10-08.

## Procedencia documental

- Warehouse upload: `21499`.
- Report type: `google_ads_ad_group_daily`.
- Archivo: `Informe de grupo de anuncios (7).xlsx`.
- Fecha inicial: `2026-09-24`; fecha final: `2026-10-08`.
- Metadata de upload: `ACTIVE`, `source_file_deleted_at IS NULL`.
- Tamaño registrado: `79836` bytes.
- SHA-256 registrado en PostgreSQL: `90a33628541f28d90799aa1195975d785484fdda50a61b80c9e945431543dd44`.

## Trazabilidad del detalle M3

Consulta agrupada sobre `google_ads_ad_group_daily_metrics`: 645 filas, 15 días, 43 identidades campaña-grupo, una sola cuenta, 19,126.37 MXN, `source_kind = WAREHOUSE_XLSX`, `source_upload_id = 21499`.

## Comprobación del archivo físico

El operador ejecutó desde `docker compose exec -T backend python` el lector existente `app.warehouse.services.google_ads_daily_ingestion_service._upload_content`, pasando `warehouse_upload_id = 21499` y `report_type_key = google_ads_ad_group_daily`; calculó `hashlib.sha256(content).hexdigest()` y comparó también `len(content)` contra la metadata.

Resultado reportado:

```text
ARCHIVO_DISPONIBLE = TRUE
SIZE_OK = True
SHA256_OK = True
```

**Interpretación:** presencia e integridad física respecto al hash guardado: PASS, según ejecución de producción del operador. Esto no demuestra independientemente el contenido de Google Ads API, ni convierte claves basadas en nombres en IDs oficiales.

## Restricciones que permanecen

- La identidad `APPROVED_PROVISIONAL_XLSX` sigue restringida al histórico `2026-09-24..2026-10-08`.
- La autoridad del gasto de cuenta sigue siendo `google_ads_daily_metrics`; el detalle grupo-día no es un segundo ledger.
- No se asignan `Marca`, `EGADE` ni los 15 grupos sin alias.
- El manifiesto de 26 triples aprobado permanece en `GOOGLE_ADS_M5_IDENTITY_APPROVED_20261012.json`.
- Sin escritura en PostgreSQL, sin implementación funcional, sin merge ni despliegue por esta evidencia.

## Siguiente gate

Revisión del diseño de migración Alembic para mappings auditables, periodos de vigencia, integridad de los 26 triples y el servicio de solo lectura con autorización por sucursal y conciliación estricta. Mantener M5-CORE separado de cambios en Meta, ventas y cortes.
