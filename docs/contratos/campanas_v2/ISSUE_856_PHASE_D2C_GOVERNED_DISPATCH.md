# Suite Ultra — Issue #856 / Fase D2c

## Despacho gobernado: autorización independiente

**Estado:** implementación en PR DRAFT, sin despliegue ni envíos reales. Depende de D1 (#870), D2a (#873) y D2b (#875).

### Alcance

1. D2a confirma costo MXN/versiones de tarifas, volumen y cuota declarada por el operador; D2b persiste los child `READY/HELD` sin contacto con iVentas.
2. El operador autorizado consulta `GET /api/marketing/campaigns-v2/{campaign_id}/dispatch/execution`, que muestra el manifiesto y `manifest_digest`.
3. `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/authorize` exige `approval_id`, `expected_manifest_digest`, `expected_ready_recipients` y `confirm_dispatch: true`. Revalida plan, cotización, quota y reservas antes de crear **una sola** autorización por aprobación. No crea campañas iVentas.
4. Cada envío es deliberadamente individual: `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/execute` exige `execution_id`, `child_id` y `expected_manifest_digest`. Solo procesa el siguiente child `READY` en orden y con snapshots inalterados.
5. Para ejecutar se requieren simultáneamente `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=true` y `CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=true`. El segundo es nuevo y está **apagado por defecto** en `backend/app/config.py`. El frontend no puede establecerlos por payload.
6. Las rutas requieren JWT, permiso `can_manage_dispatch_config`, `can_send_campaigns` y alcance `is_global`, comprobados en backend. Los gerentes sin estos permisos reciben 403.
7. El claim de ejecución `IN_FLIGHT` y el cambio del child a `SUBMITTING` ocurren en una única transacción durable antes de HTTP. Una caída entre claim y respuesta no permite retry automático. Una aceptación `SUBMITTED` habilita únicamente el siguiente child tras otra validación; un fallo o resultado ambiguo deja la ejecución `REVIEW_REQUIRED`.
8. El servicio de retry heredado rechaza cualquier child cuya campaña tenga aprobación gobernada. El submit heredado ya estaba bloqueado desde D2b; no se cambian campañas históricas sin aprobación.
9. Antes de enviar se revalidan vigencia de aprobación/reserva, plan y tarifa, evidencia de canal/portafolio y actividad externa. Los intentos previos de **la misma campaña** se excluyen exclusivamente del chequeo de nueva actividad externa, no del control de historial de children.

### Restricciones y pendientes

- Evidencias de Meta/iVentas son declaraciones manuales del operador, no cupos garantizados por Meta; no inventar remanentes ni saldos.
- No activar flags ni probar contra cuentas reales sin revisión explícita de seguridad y decisión de operación.
- No reactivar automáticamente `IN_FLIGHT` o `REVIEW_REQUIRED`; requieren reconciliación manual. D3 definirá trazabilidad, renovación de evidencia y liberación de lotes HELD.
- La autorización vence junto con la aprobación, hasta 15 minutos desde la reserva, o antes si caduca la evidencia.
- Reglas de despliegue: merge por orden de dependencias y migración Alembic antes de habilitar rutas; no editar servidor manualmente.

### Pruebas y gates

- Unitarias: ambos interruptores apagados, ausencia de provider durante autorización, un solo child, orden estricto, doble ejecución, errores ambiguos, retry legado bloqueado y permisos.
- PostgreSQL 16 sintético: creación, unicidad, estados válidos, historial conservado ante downgrade.
- Regresiones HELD, Winback, presupuesto, campañas anteriores y build de frontend.
- Estado requerido para merge: todos los workflows del HEAD vigente PASS y revisión de seguridad de claim de autorización.
