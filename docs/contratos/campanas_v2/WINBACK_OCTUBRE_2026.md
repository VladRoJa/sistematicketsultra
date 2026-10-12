# Winback octubre 2026 — cohortes y control de disponibilidad iVentas

**Fuente:** `EXPIRED_MEMBERS`. Vencimiento inclusivo del 2020-01-01 al 2026-09-30.

**Confirmación comercial (12 de octubre de 2026):** solamente existen **3 plantillas** iVentas, pero se necesitan **4 cohortes** con congelamientos independientes. Las restricciones por sucursal se aplican a **este envío**, no a todas las campañas futuras.

## Plantillas y filtros exactos

| Cohorte | Plantilla iVentas | Adeudo mínimo | Adeudo máximo | Filtro comercial por sucursal |
| --- | --- | ---: | ---: | --- |
| BCN | `Bcn_low_ticket_octubre` | $3,000 | Sin límite | **EXCLUIR:** Villalta, Metepec, Insurgentes, Serranía y Papalote |
| Winback general | `winback_general_octubre` | $0 | $0 | **EXCLUIR:** Serranía |
| Atención personalizada — adeudo menor | `Adeudo_menor_a_3000` | $0.01 | $2,999.99 | **EXCLUIR:** San Isidro y Serranía |
| Atención personalizada — BCN no elegible | `Adeudo_menor_a_3000` | $3,000 | Sin límite | **INCLUIR SOLO:** Villalta, Metepec e Insurgentes |

**IMPORTANTE:** seleccionar los nombres reales en `branch_options` del catálogo Track; verificar equivalencias de San Isidro, Papalote y Serranía con el catálogo canónico antes del freeze. No asumir que estas etiquetas escritas son las claves de base de datos.

## Excepciones por canal confirmadas

- **San Isidro:** no se pudo cargar `Adeudo_menor_a_3000`; NO enviar esta plantilla allí. Los exsocios con deuda $0.01–$2,999.99 de San Isidro permanecen pendientes, sin sustitución automática.
- **Papalote:** no se pudo cargar `Bcn_low_ticket_octubre`; NO enviar BCN allí. Los exsocios con adeudo >= $3,000 de Papalote permanecen pendientes, sin usar una oferta no autorizada.
- **Serranía:** **NO participa en ninguna de las tres plantillas ni en ninguna de las cuatro cohortes** de este envío. Queda completamente excluida.
- En San Isidro y Papalote, otras plantillas solo se pueden usar si están cargadas, autorizadas y probadas para el canal correspondiente.
- Los elegibles >= $3,000 de Villalta, Metepec e Insurgentes reciben la invitación genérica de **atención personalizada**, no una promesa BCN.

## Gates obligatorios antes de SUBMIT

1. Comprobar en iVentas la aprobación real de cada plantilla y el **provider channel ID** de cada sucursal.
2. Configurar en Campañas V2 la lista **explícita, no vacía**, de `compatible_channel_ids` por plantilla con solo los canales donde realmente se cargó y aprobó. **ATENCIÓN: hoy `template_allows_channel()` interpreta una lista vacía como compatible con todos los canales**, de modo que el preflight por sí solo NO detecta huecos cuando está vacía. No dejar esa lista vacía para este envío.
3. Usar preflight por campaña y verificar `TEMPLATE_CHANNEL_MISMATCH`, `MISSING_CHANNEL`, `MISSING_REQUIRED_VARIABLE` y variable `sucursal`. Cualquier inconsistencia bloquea el envío.
4. Verificar corte canónico de cartera y socios activos, consentimiento comercial, blacklist global, duplicados y teléfonos inválidos. No considerar adeudo `NULL` equivalente a $0.
5. Congelar cuatro campañas independientes con fingerprint; exportar Excel por sucursal/segmento. Auditar que Serranía esté ausente de todas, Papalote esté ausente de BCN y San Isidro esté ausente de ambas cohortes que usan `Adeudo_menor_a_3000`.
6. Antes de SUBMIT, cruzar los cuatro exports por teléfono normalizado y bloquear cualquier solapamiento de personas entre campañas. La deduplicación actual es *intra-campaña*, no inter-campañas; resolver cada conflicto sin reemplazar automáticamente plantillas.
7. Conservar reportes de exclusiones y destinatarios pendientes por causa (plantilla no disponible, sucursal fuera de alcance o identidad canónica ambigua). No afirmar conteos antes de consultarlos.
8. Confirmación interna con destinatarios de prueba por canal y revisión expresa del propietario antes del envío.

## Validación técnica realizada en el PR inicial

- Backend: 183 pruebas PASS (audiencia, rutas y congelamiento).
- Frontend: 49 pruebas PASS de lógica, TypeScript PASS, `ng build --configuration production` PASS.
- Sin migración Alembic: filtros se almacenan en JSON de audiencia.

Este documento ajusta **las reglas operativas de este envío** sin cambiar retrospectivamente las pruebas técnicas del PR inicial ni autorizar envío, merge o despliegue.
