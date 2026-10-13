# Issue #856 — Fase D1: evidencia de capacidad y evaluación preventiva

## Estado y límites

Implementa exclusivamente administración manual de política/capacidad y evaluación **de solo lectura** en preflight. **No** habilita envío parcial desde la web, no crea provider children, no reserva cupo ni activa el kill switch. D2 tendrá reserva transaccional, confirmación de costo/volumen, manifest y submit parcial; D3 seguimiento por canal y liberación controlada.

## Evidencia registrada

- `marketing_campaign_v2_quota_policy_revisions`: asociación versionada de canal exacto iVentas → portafolio / cuenta WhatsApp / alias de número, límite nominal opcional, zona IANA y fuente. Un límite nominal no es cuota restante.
- `marketing_campaign_v2_quota_capacity_attestations`: evidencia manual de remanente para canal y para portafolio compartido; fuente, actor, fecha observada, caducidad y fin de ventana. Este registro es una **declaración de operador** y no implica lectura automática/confirmación de Meta.
- Todas las revisiones se insertan y no se sobrescriben; el rollback Alembic rehúsa borrar evidencia real. Revisiones con zonas/fechas inválidas, referencias ausentes o capacidad negativa se rechazan.

## Preflight

- Para cada lote, elegir la política más reciente de ese canal y las últimas observaciones vigentes tanto del canal como del portafolio. Si falta alguna, el lote requiere revisión.
- Sumar demanda total del plan por portafolio. Si la demanda supera remanente compartido, bloquear la recomendación de todos los lotes del mismo portafolio. Así nunca se muestra cada sucursal como disponible independientemente.
- Para prevenir evidencia caducada por actividad posterior, revisar provider children de todos los canales del portafolio, incluso los que no son parte de este plan; intentos o aceptaciones posteriores requieren nueva observación. Un `HELD` sin intento no se cuenta como consumo.
- `quota.status` es `INCOMPLETE` o `REVIEWABLE`, nunca autoridad de envío. El resultado tiene `send_authorized=false` siempre. No existe reserva transaccional todavía, por tanto `REVIEWABLE` **no autoriza submit**.
- No se inventan números 100k/250, ni hora de reinicio, ni fuentes Meta, ni se asume `SUBMITTED` como entregado.

## Seguridad

GET/POST de configuración de cuota requieren JWT, `can_manage_dispatch_config` y alcance global. En las rutas se rechazan campos adicionales (incluido `send_enabled`) y se obtiene actor del token, nunca del navegador. El preflight permanece de solo lectura. Los endpoints de envío, reconciliación, jobs y estadísticas existentes no se modifican en D1.

## Alembic

Revisión `f4d856a1b20c` derivada de `e4b856c9170d`; crear ambas tablas antes de desplegar backend. Migración aislada, sin modificar tablas/campañas existentes.

## Pendiente antes de autorizar envío

Reserva atómica por portafolio y ventana, actor/costo/volumen confirmados y ligados a fingerprint, manifest exacto READY/HELD, cuota consumida desde la observación y sesiones concurrentes; integración controlada con helpers de submit duradero/reconciliación. No ejecutar envíos para probar estas piezas.