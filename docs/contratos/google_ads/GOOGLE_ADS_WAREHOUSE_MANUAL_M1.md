# Google Ads — Warehouse manual M1

## Alcance

Carga de un XLSX exportado desde Google Ads, sin OAuth activo, mediante el flujo existente de **Warehouse → Subir archivo**. El archivo original se almacena como raw, y solo si su estructura se valida se crean filas estructuradas en `google_ads_daily_metrics`.

- Tipo nuevo de reporte: `google_ads_campaign_daily`.
- Fuente Warehouse: `manual`; periodo: `rango`.
- Permiso: operador Warehouse con `can_upload` y JWT; el backend conserva los guards existentes.
- Cuenta fija a `GOOGLE_ADS_OAUTH_CUSTOMER_ID` configurada en el servidor, nunca tomada del Excel ni del formulario.
- No existe llamada a Google Ads, modificación del Funnel, scheduler, ni mutación de campañas.
- La migración Alembic crea catálogo y tabla; aplicar antes de subir archivos.

## Formato aceptado

Exportar **Campañas**, con **Segmento → Tiempo → Día**, del 24/09/2026 al 08/10/2026 para el histórico inicial. El Excel debe tener exactamente una hoja, dos filas de título/periodo en español, encabezados en fila 3, y columnas `Día`, `Campaña`, `Código de moneda`, `Coste`, `Conversiones`, `Valor de conv.`, `Clics`, `Impr.`. Puede incluir columnas adicionales.

El parser descarta filas `Total: ...` para evitar duplicados y **concilia el coste, clics e impresiones de cada día contra `Total: Cuenta`**. Rechaza fechas ausentes, campañas duplicadas en un día, moneda distinta de MXN, datos negativos, cambios de escala y periodos de más de 31 días.

El formulario Warehouse debe declarar exactamente el rango del Excel. Se rechaza el día actual (zona `America/Tijuana`) o posterior: solo días cerrados.

**Archivo validado en diseño:** Informe de campaña (2).xlsx: 405 filas de campaña-día, 15 días, importe MXN $19,126.37. Hay 90 filas de las seis campañas con actividad; 315 filas restantes corresponden a campañas sin gasto. Los subtotales de cuenta y tipo de campaña no se importan.

## Identidad, auditabilidad y API posterior

- Unicidad: `(customer_id, campaign_key, report_date)`.
- Este Excel **no incluye ID de campaña**. El campo `campaign_id` queda `NULL` y `campaign_key` es un hash del nombre normalizado con prefijo `name:`. No se asignan IDs inventados.
- La integración API futura **necesita reconciliación explícita** entre ID real de campaña y nombre histórico antes de reemplazar registros. Los cambios de nombre no se deduplican automáticamente.
- `source_upload_id`, `source_kind` y auditoría `GOOGLE_ADS_IMPORT` conservan trazabilidad.
- Reimportación de cifras idénticas: sin filas nuevas. Si hay diferencias, se **rechaza la carga estructurada completa** hasta revisión; no se sobreescribe gasto automáticamente.
- El archivo raw puede quedar registrado aunque falle el paso estructurado, siguiendo el principio raw first.
- Se exige `GOOGLE_ADS_OAUTH_CUSTOMER_ID` válido, pero **no** hace falta consentimiento OAuth vigente para carga manual.

## Uso cuando esté desplegado

1. Ejecutar `flask db upgrade` durante el despliegue controlado del backend.
2. En Warehouse elegir `Google Ads - campañas por día`, periodo del 24/09/2026 al 08/10/2026 y el XLSX exportado.
3. Verificar en la respuesta `manual_structured_result.structured_result` los 405 registros y el total de $19,126.37; ante `failed`, consultar la validación sin volver a cargar a ciegas.
4. Reimportar el mismo fichero: debe indicar `created_rows=0`, `unchanged_rows=405`.

## Límites

Esta etapa deja el histórico listo en PostgreSQL y Warehouse. **No aparecen todavía Google Ads ni inversión total en el Funnel**: ese cruce será un hito distinto. Tampoco se mezclan las conversiones de Google Ads con ventas pagadas de GASCA/iVentas.
