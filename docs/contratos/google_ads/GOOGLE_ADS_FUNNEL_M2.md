# Google Ads → Funnel de Venta Nueva (M2)

## Objetivo
Integrar la evidencia diaria importada de Google Ads en Warehouse (M1) al Funnel de Venta Nueva **sin alterar los costos Meta existentes, su atribución por sucursal, las ventas ni los cortes canónicos**.

## Contrato
- Fuente Google: `google_ads_daily_metrics`, filtrada por `GOOGLE_ADS_OAUTH_CUSTOMER_ID` y fechas del mes solicitado hasta `selected_cutoff_date`, inclusive.
- Vista **GLOBAL**: expone importe de cuenta, clics, impresiones, conversiones Ads, fechas cubiertas y cantidad de días faltantes.
- Vista de sucursal o región: `scope_unavailable`, sin importe ni consulta SQL de gasto Google; campañas regionales no cuentan con asignación certificada a clubes.
- Meta `summary.investment`: no se toca. Sigue representando únicamente el gasto Meta **asignado** a sucursales incluidas en el alcance del usuario.
- Nuevo `investment_sources` top-level: `meta_assigned`, `google_ads`, `combined`, `combined_available`, `combined_definition`, `existing_cpl_cpt_cac_basis`.
- Suma combinada mostrada **solo** cuando Google contiene **cada fecha desde el primer día del mes al corte**, y existe importe Meta; se rotula 'Meta asignada + Google Ads cuenta', no 'inversión total de publicidad' (Meta sin asignar queda excluida).
- Datos parciales (septiembre 24–30 vs mes 1–30; octubre 1–8 frente a un corte posterior al día 8): mostrar cobertura real y gasto observado, pero `combined=null`.
- Se mantienen CPL/CPT/CAC preexistentes bajo base Meta asignada, sin atribuir Google al CRM ni confundir conversiones publicitarias con ventas pagadas.
- Google no participa en `_cutoff_source_dates`; falta de información Google no bloquea lectura de Funnel.

## Seguridad y desarrollo
Conservar restricciones backend de MarketingAccess, sin nuevas rutas públicas y sin tocar Warehouse, migraciones o APIs OAuth. Tipos Angular y mensaje de cobertura definidos en TypeScript; HTML solo muestra bindings. Sin cambios a los exportadores existentes, que permanecen Meta por sucursal.

## QA
Validar pruebas negativas sin consulta SQL para accesos no globales, cobertura completa (oct 1–8), parcial (oct 1–12), histórico parcial (sep 24–30), sin datos y sin configuración. CI con pytest y TypeScript.

## Operación
Deploy `backend frontend` únicamente tras merge y CI. Esta fase no añade migraciones. Para validación visual consultar Octubre con corte 8 (Google completo) y corte posterior (Google parcial), luego seleccionar una sucursal y comprobar que Google no muestra cifras de cuenta.
