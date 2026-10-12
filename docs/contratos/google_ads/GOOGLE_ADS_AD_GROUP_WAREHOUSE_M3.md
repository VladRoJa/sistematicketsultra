# Google Ads Warehouse M3 — grupos de anuncios por día

## Alcance
Fuente raw-first independiente `google_ads_ad_group_daily`:
- Un XLSX diario por grupo exportado con Segmento → Tiempo → Día, columnas personalizadas **Pase gratis Ads** (`UG Lead Pase Gratis`) y **Compras web Ads** (`UG Compra web`).
- Clave provisional `(customer_id, campaign_key, ad_group_key, report_date)` derivada del texto normalizado de campaña+grupo; los IDs oficiales de Google Ads no aparecen en el XLSX y no se inventan.
- `google_ads_ad_group_daily_metrics` es un **detalle**, no un segundo ledger de inversión. No modificar `google_ads_daily_metrics`, `summary.investment`, CPL/CPT/CAC, metas, ni los resultados de ventas.
- Pases gratis y compras web son **conversiones atribuidas por Google Ads** (pueden ser fraccionarias), NO pases efectivamente emitidos ni ventas pagadas en GASCA.
- NINGUNA atribución automática grupo→sucursal. El grupo nacional **Marca** queda sin distribuir. El mapeo a sucursales necesita catálogo de alias aprobado, criterios de alcance y pruebas negativas.
- La cuenta Google Ads se resuelve exclusivamente desde `GOOGLE_ADS_OAUTH_CUSTOMER_ID`.

## Validaciones
- Una hoja, título/periodo legítimos, columna `Día`, campañas y grupos no vacíos, encabezados exactos incluidos los dos KPI personalizados, moneda MXN, días cerrados America/Tijuana.
- 645 grupo-día / 43 grupos / 15 días para el histórico 2026-09-24 → 2026-10-08; números de validación: inversión 19,126.37 MXN, clics 7,887, impresiones 79,198, pases Ads 64 y compras Ads 16.
- Todos los grupos deben aparecer por día; conciliación de coste/clics/impresiones estrictamente exacta con `Total: Grupos de anuncios` y `Total: Cuenta`. Se permite <=0.01 por subtotal para diferencias de redondeo atribuible a Google en conversiones/valor de conversión.
- Si hay campaña-día en Warehouse, conciliar exhaustivamente las métricas de coste/clics/impresiones por campaña-día. Las campañas sin grupo deben tener todos esos valores en cero; bloquear campañas nuevas no conciliadas con gasto o tráfico.
- Una reimportación idéntica produce registros sin cambios. Cualquier alteración, renombre o variación histórica bloquea **la transacción completa**: no se sustituyen hechos previos ni se silencian conversiones tardías.
- Sin cambios en autenticación/permisos Warehouse. Auditoría `GOOGLE_ADS_AD_GROUP_IMPORT`.

## Operación
Tras merge y CI, despliegue correcto: `git pull --ff-only origin main`, reconstruir backend+frontend y ejecutar `docker compose exec -T backend flask db upgrade`. Subir el XLSX como tipo **Google Ads - grupos por día (pases y compras)** con fechas 2026-09-24 a 2026-10-08. Confirmar que ingesta estructurada reporta 645 filas nuevas, inversión 19,126.37, pases 64, compras 16. En caso de fallo, raw queda guardado, estructurado queda intacto.

## Fuera de alcance M3
Asignación de grupos a sucursales, integración con Funnel por club, reconciliación de compras reales, automatización de correos/reportes, refresh/correcciones tardías, API/OAuth. Requieren contratos y QA propios después de verificar esta ingesta en producción.
