# Campañas V2 — M2: conversión y rentabilidad comercial
Estado: EN IMPLEMENTACIÓN EN RAMA M2. M1 mergeado (PR #1254). 2026-11-18.

## Objetivo
Relacionar campañas de Suite con conversiones de membresía de Gasca y medir ingreso observado, costo por comprador y ROAS sin atribuir varias veces una venta. Reusar los servicios existentes de materialización comercial, Venta Total canónico, `marketing_campaign_v2_commercial_attribution_service.py` y resolver alias de `gasca_family`.

## Regla temporal y de identidad
- Identidad por teléfono MX10 normalizado; confirmar que pertenece al destinatario realmente enviado en el child, no solo a toda la cohorte.
- El proveedor confirma `SUCCESSFUL`; `FAILED` no es venta relacionada. Tomar la hora real de `submitted_at` y hora local de venta de Gasca. Sin timestamp de entrega por teléfono, etiquetar explícitamente «venta posterior al envío», NO «venta posterior a la recepción».
- Coincidencia de sucursal real, salvo escenario cross-branch identificado aparte. Respetar estatus válido, clase NUEVO/REACTIVACION, membresía y exclusions existentes de pass/penalización/recargo/inscripción.
- Filtrar ventas por ventana desde el envío (7, 14 y 30 días) y no limitar incorrectamente al fin del mismo mes; exigir snapshots canónicos completos para cada ventana y mostrar PENDING cuando falten cortes.
- Utilizar `id_orden`/folio con identidad estable; sumar componentes válidos de la misma operación una sola vez. Excluir devoluciones/cancelaciones según evidencia de Gasca.

## Atribución única y trazabilidad
- En el total del periodo, una venta puede asignarse a **una sola campaña elegible**, preferentemente el último contacto exitoso previo a la operación, con desempate determinista por tiempo, lote e ID. Las campañas precedentes se registran como asistencia, nunca como ingreso duplicado.
- Registrar versión de regla, corte Venta Total, IDs provider/child y evidencia de alcance; poder reconstruir la decisión sin guardar PII adicional innecesaria.
- «Venta posterior al envío» es correlación operativa; no usar palabra «causada por» sin control experimental.
- Referidos, activos, cobranza y propósitos distintos se muestran NO_ATRIBUIBLE o como métricas secundarias; no reinterpretar silenciosamente como venta nueva.

## Costos y KPI
- Mostrar tres estados separados: máximo preflight, estimado con estado confirmado y facturado proveedor; facturado puede permanecer unavailable.
- ROAS observado = ingreso de operaciones únicas / costo real compatible, con moneda, periodo, facturabilidad y tasa FX auditable; si solo hay estimación, etiquetar «ROAS estimado» y no mezclar USD con MXN.
- Mostrar compradores únicos, transacciones, ingreso, tasa de conversión sobre éxito verificable, CPA, ROAS, margen de contribución y estado de cobertura.
- Reportes por campaña, lote, sucursal, segmento y periodo con Excel sin datos personales salvo permiso explícito.

## Seguridad y pruebas
- Realizar cruces pesados en worker/materialización, no al atender GET; ALLOW de permisos nunca supera ACL sucursal/objeto. Nuevas tablas requieren Alembic.
- Pruebas: compras antes/después, cross-month, multi-child, recontacto de dos campañas, folios duplicados, cambio de sucursal, venta inválida, snapshot tardío, cobertura parcial y no filtración de PII.

## Puerta de salida
M2 se acepta solo cuando ingresos consolidados no duplican operaciones, reportes explican su causalidad limitada, y los importes se reconcilian con un corte Gasca reproducible. No autoriza envío ni cambios productivos.

## Avance de implementación M2 — primer corte funcional
- `marketing_campaign_v2_unique_sales_service.py`: selector determinista, sin DB, de última campaña con envío probado, ventana 7/14/30 días, una venta por clave canónica y asistencias sin ingreso duplicado.
- Pruebas de cruces multisucursal, recontactos, compras previas, corte de mes, diferencias entre snapshots, importes inválidos y no exposición de teléfonos.
- **NO conectar al endpoint ni sumar con los resultados legacy hasta que el scheduler genere candidatos validados de Venta Total y contactos con SUCCESSFUL probado.** Los agregados legacy siguen siendo por campaña y NO son un total de ingresos únicos.
- Pendiente implementar construcción materializada de candidatos, ventas realmente elegibles, control de cortes completos, persistencia/auditoría con Alembic si requiere esquema, conversión de moneda validada y vista ROAS/CPA; no hay atribución automática real todavía.

## Implementación de conciliación por mes de venta (segundo corte)
- `marketing_campaign_v2_sales_month_source_service.py`: adaptador exclusivamente de worker que cruza `SUBMITTED` + último snapshot `SUCCESSFUL` con destinatarios incluidos realmente en el child, validados contra la cohorte congelada. Consulta Venta Total canónico diario con fecha de negocio que cubra toda la ventana de ventas y captura **posterior al cierre del último día**, con rango de envío hacia atrás de 7/14/30 días. La salida falla cerrada si faltan snapshots, fechas, correspondencia de destinatarios o alias. Una venta solo pertenece al mes de **compra**, evitando duplicación entre cortes mensuales.
- `marketing_campaign_v2_sales_month_materialization_service.py`: persiste únicamente agregados por `(sale_from, sale_to, window_days)` en tabla nueva, con migración `m1234m2sales111826`, y consulta cacheada protegida por la visibilidad de campaña y sucursal existentes. Para alcance parcial no reporta un falso global de compradores únicos.
- `GET /api/marketing/campaigns-v2/commercial-performance`: endpoint GET con JWT, guard de Marketing y visibilidad por recurso; nunca escanea Warehouse ni llama a iVentas.
- Nueva sección en `Resultados`: ingresos relacionados, operaciones, compradores, asistencias y estados de evidencia. Costo real y ROAS quedan explícitamente en pendiente, no se divide USD contra MXN.
- Comandos manuales: `python -m scripts.campaign_v2_m2_sales_month_readonly --from-date 2026-10-01 --to-date 2026-10-31 --window-days 14` para diagnóstico no persistente; después de migración y autorización de ejecución, `python -m scripts.campaign_v2_m2_materialize_sales_month --from-date 2026-10-01 --to-date 2026-10-31 --window-days 14 --write-materialized-cache` para actualizar solo agregados. **No programado automáticamente**, ni activado en producción.
- Pruebas sintéticas de joins, fallas cerradas, alias, ACL, no exponer PII, migración/ORM y compatibilidad HTTP. Faltan conciliación real en PostgreSQL y facturación desglosada iVentas antes de declarar rentabilidad.

## Riesgos/resguardos explícitos para la activación
1. No habilitar el worker automáticamente. La primera ejecución será diagnóstico de solo lectura fuera del backend web, con revisión de duración, índices y cardinalidades; luego autorizar materialización específica.
2. El reporte actual cubre `NEW_SALE/FUNNEL_PORTFOLIO` y `REACTIVATION/EXPIRED_MEMBERS` únicamente; no sumar renovaciones, cobranza, referidos ni contactos de panel externo. Fecha de envío no equivale a fecha de lectura.
3. La fila materializada se sobrescribe al recalcular el mismo rango y ventana. Una política de revisiones históricas y snapshot lineage refinado queda pendiente antes de usarlo para conciliaciones financieras cerradas.
4. `SENT` se interpreta solo como estado exitoso reportado por iVentas, no comprobante de entrega individual. Para ROAS verificable, exigir costo facturado, FX trazable y deducción de margen; hasta entonces mostrar únicamente correlación de ingresos.
5. La retención RAW/STRUCTURED/CANONICAL y los alias Gasca se mantienen intactos. Ninguna tabla original de Warehouse se modifica.
