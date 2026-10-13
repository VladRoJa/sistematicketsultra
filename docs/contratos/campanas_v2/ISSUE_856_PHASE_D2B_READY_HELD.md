# Issue #856 — D2b / Manifiesto READY–HELD gobernado

**Estado:** subfase técnica sin envío. Rama dependiente de D2a (PR #873) y D1 (PR #870). No incluye deploy, habilitación de kill switch, llamadas a Meta/iVentas ni autorización de submit de campañas.

## Contrato operativo

1. Un operador con **alcance global, can_manage_dispatch_config y can_send_campaigns** realiza preflight y obtiene `dispatch_fingerprint`, `budget.quote_fingerprint`, `total_estimated_mxn` y total de destinatarios.
2. `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/approval`: indica `template_id`, `expected_dispatch_fingerprint`, `expected_quote_fingerprint`, `expected_recipients`, `expected_total_mxn` como cadena `"123.45"`, opcionalmente `held_sucursal_canons` (lista exacta) y `held_source_references` (mapa exacto de sucursal a referencia). No se aceptan sucursales repetidas, desconocidas ni una campaña completamente retenida.
3. El costo confirmado cubre **todo el preflight**, incluidas las sucursales retenidas. El cupo reservado abarca **solo las READY**. Se aplican bloqueos transaccionales PostgreSQL por canal y portafolio compartido; las atestaciones son declaraciones de operador, no cupo verificado automáticamente en Meta.
4. Se persiste una aprobación por campaña, con manifest `D2B_READY_HELD_V1`. Cada HELD conserva referencia y actor, sin deducir que se envió. El manifiesto dura hasta el menor de 15 minutos y la vigencia de las atestaciones.
5. `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/materialize` con body `{}` valida nuevamente plan, tarifas/versiones, cuota, vigencias y reservas. Persiste todos los provider children `READY`/`HELD` en una transacción, sin realizar HTTP al proveedor. Repetirlo solo se admite si los children permanecen exactamente idénticos, sin intentos. Cualquier alteración se rechaza.
6. `GET /api/marketing/campaigns-v2/{campaign_id}/dispatch/approval` consulta la aprobación sin autorización de envío.

## Aislamiento de envíos

- El submit heredado `submit_campaign_v2()` rechaza campañas con aprobación gobernada, incluso si el kill switch global está habilitado. Las campañas históricas sin esa aprobación mantienen su contrato anterior.
- Un child `HELD` no representa un intento ni consume por sí mismo capacidad Meta.
- La persistencia de `READY` **no autoriza el envío**; no existe en D2b un endpoint para procesar estos READY.
- Reservas y aprobaciones vencidas no se extienden ni liberan automáticamente para envío. D2c deberá diseñar una autorización de despacho nueva, con revalidación transaccional de evidencia/cupo, reconciliación y freno ante resultados inciertos. D3 cubrirá liberación de HELD y seguimiento.
- Ninguna operación de este corte debe usarse para enviar campañas reales.

## Validaciones requeridas

- PostgreSQL 16 real: migración D2a, constraints, locks por portafolio y reservas concurrentes.
- Manifest íntegro: mismos canales, sucursales, template, destinatarios, revisiones de tarifa, fingerprint y montos.
- Retenciones: fuentes explícitas por sucursal, al menos un READY, no modificar children HELD.
- Permisos 403, campos extra 400, cuota/vigencia/estado incompatibles 409.
- Idempotencia: children ya persistidos coincidentes se informan, nunca se reescriben; child alterado o con intento bloquea.
- Regresión de submit histórico y Winback. No API al proveedor durante pruebas D2b.
