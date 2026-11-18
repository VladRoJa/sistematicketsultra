# Campañas V2 — M2: conversión y rentabilidad comercial
Estado: CONTRATO PREPARADO · NO IMPLEMENTADO. Depende de evidencia M1. 2026-11-18.

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
