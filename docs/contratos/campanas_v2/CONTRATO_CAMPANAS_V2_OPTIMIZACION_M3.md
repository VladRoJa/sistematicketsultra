# Campañas V2 — M3: efectividad repetible, saturación y experimentos
Estado: CONTRATO PREPARADO · NO IMPLEMENTADO. Depende de M1/M2. 2026-11-18.

## Objetivo
Aprender qué segmento, plantilla, sucursal y frecuencia maximiza **contribución incremental** por peso invertido, conservando experiencia de socios y límites de envíos actuales.

## Frecuencia y campañas repetibles
- Frecuencia sobre envíos exitosos por teléfono y ventana 7/14/30 días; distinguir solicitudes/intentados de resultados `SENT`, `DELIVERED`, `VIEWED`. Un mismo teléfono contactado en varias sucursales es una sola persona para saturación global.
- Métricas por 1/2/3/4+ contactos: alcanzados, conversión posterior, ingreso único, costo y CPA; comparar poblaciones equivalentes (tipo de socio, sucursal, antigüedad). No interpretar correlación como efecto causal.
- Evaluar plantillas homologadas, audiencia, motivo, día/hora, resultados de ventas y cohortes comparables; controlar estacionalidad y tamaño de muestra.

## Experimentos
- Piloto A/B con grupos control/sin envío elegidos antes del dispatch, reproducibles y excluidos de todos los envíos participantes mientras duren. Mantener cumplimiento de privacidad, no inventar observaciones.
- Estimar lift incremental de compradores e ingreso neto, incertidumbre/intervalos, costos y efectos adversos; diferenciar KPI observados y estimados.
- Iniciar en modo sugerencia y `compare_only`, con flags OFF. Ningún cap de frecuencia, supresión, redistribución ni autoenvío se activa sin aprobación separada y pruebas de no regresión de protecciones HELD/QA/consentimiento.

## Integración externa
- Si iVentas entrega lista de campañas ejecutadas vía panel, importar evidencia histórica RAW FIRST y diferenciar API/Panel/desconocido por `provider_campaign_id`. Nunca atribuir «externo» por simple resta entre exitosos y facturables; tasas/categorías/tiempos deben ser comparables.
- Para contacto individual/plantillas de servicio, mantener una familia independiente de campañas masivas.

## Criterios de aceptación
1. Efecto frecuencia medido con denominadores claros y sin contar doble una venta.
2. Comparador por segmento/plantilla/sucursal con muestras y ventanas explícitas.
3. Piloto A/B auditable y reversible, holdout real excluido del envío cuando se autorice.
4. Optimización informa y recomienda; no desbloquea dispatch ni sobrepasa permisos.
5. Evidencia y desglose exportable a Dirección con metodología y limitaciones, sin teléfonos en export ejecutivo.

## Riesgos y dependencias
La medición exacta de `billableQuantity`, costo real por campaña y timestamps por destinatario depende de iVentas; resultados con cobertura parcial se etiquetan, no se fabrican.
