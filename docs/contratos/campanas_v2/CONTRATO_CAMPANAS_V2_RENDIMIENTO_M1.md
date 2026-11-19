# Campañas V2 — M1: medición confiable de envíos, costo estimado y frecuencia
Estado: IMPLEMENTACIÓN EN RAMA · 2026-11-18. Complementa `CONTRATO_CAMPANAS_V2_GLOBAL.md`, no sustituye sus ACL ni reglas de despacho.

## Objetivo y límites
Dar visibilidad verificable a los resultados de los lotes realmente enviados por Suite Ultra (incluidos 1:N multisucursal), sin confundir cohortes congeladas, solicitudes aceptadas, resultados de iVentas o facturación. Reutilizar modelos y observaciones actuales; este paquete es **solo lectura** y no cambia dispatch, límites ni flags.

## Unidad de conteo
- Campaña padre: `marketing_campaign_v2_campaigns`; lote real: `marketing_campaign_v2_provider_campaigns` con `status=SUBMITTED`, `submitted_at` y `provider_campaign_id`.
- Cada lote obtiene solo su snapshot más reciente según `fetched_at DESC, id DESC` para la identidad `(campaign_v2_id, provider, provider_campaign_id)`. Nunca sumar snapshots sucesivos.
- `raw_successful` es total de estados exitosos: `SENT + DELIVERED + VIEWED`; `raw_failed` es disjunto. La lectura no presupone que `SUCCESSFUL` sea `billable`.
- Para frecuencia, contar apariciones `SUCCESSFUL` de un teléfono normalizado a través de lotes; deduplicar observaciones/snapshots. Un destinatario no equivale a un teléfono único mensual.
- Desglosar por sucursal del **lote efectivo**, no asumir que toda la cohorte congelada fue enviada. Mostrar lotes sin snapshot, inconsistencias de cobertura y excluidos del denominador; nunca traducirlos a cero medido.
- El periodo se define por `submitted_at` convertido a `America/Tijuana`, no por `fetched_at`. Mostrar corte, zona y evidencia.

## Costos
- La tarifa de referencia vigente en código (`IVENTAS_MX_DELIVERED_USD_V1`, US$0.0542) es solo estimación. Costo estimado = entregados + vistos * tarifa **cuando exista snapshot**. No se marca como facturado ni se infiere `billableQuantity` desde `successful`.
- Una fila con lote sin estadísticas deja el total en estado INCOMPLETE y solo muestra el subtotal observable; no confundirlo con costo final.
- Monedas USD y MXN separadas; no calcular ROAS con tipos de cambio inventados. Costo facturado por campaña queda pendiente de evidencia verificable de iVentas; su API de costos mensual no permite atribuir el total a lotes individuales.

## UX / seguridad / rendimiento
- Incorporar sección legible en `Resultados` (por envío efectivo y no por snapshot observado) con totales, frecuencia 1/2/3/4+, costo estimado y tabla por sucursal.
- Backend aplica ACL de Marketing **y** visibilidad de campaña/sucursal antes del agregado. No retornar teléfonos en la respuesta agregada; no filtrar datos de otras sucursales.
- Consultas agregadas, sin N+1 por lote, sin llamadas HTTP a iVentas desde el request y sin mutaciones.
- Evitar que las consultas de analítica pesada bloqueen Gunicorn; si el volumen real excede el presupuesto, materializar mediante worker en una extensión acotada, no aumentar timeout.

## Criterios de aceptación
1. Dos lotes de una misma campaña en diferentes sucursales suman ambos, cada uno usando su último snapshot.
2. Dos snapshots del mismo lote no duplican éxito ni frecuencia; con un lote sin snapshot se informa cobertura INCOMPLETE.
3. La distribución 1/2/3/4+ suma exactamente los teléfonos exitosos distintos; los mensajes exitosos suman frecuencia ponderada.
4. Lotes preparados, QA no enviados y campañas fuera de scope no aparecen; solicitudes no autorizadas devuelven 403.
5. Costo se etiqueta estimado USD y nunca se presenta como cobro real; falta evidencia se muestra.
6. Pruebas focales y compatibilidad del reporting y exports previos.

## No incluye
Atribución comercial cross-campaign (M2), política automática de recontacto, datos históricos del panel iVentas ni pruebas de incrementalidad (M3). No crear migraciones sin cambiar esquema.
