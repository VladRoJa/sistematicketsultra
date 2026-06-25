# Permissions Review — Medium Write: Tickets

## Objetivo

Revisar rutas de escritura relacionadas con tickets: creación, actualización, cierre, doble check, notificaciones y flujos especiales.

## Resultado

No se detectaron rutas abiertas.

Durante la revisión se identificaron 3 endpoints RRHH fuera del flujo actual de Tickets. Como no tenían referencias fuera de `ticket_routes.py`, fueron removidos para reducir superficie y deuda técnica.

El flujo activo de cierre/validación de Tickets no fue modificado.

## Rutas RRHH retiradas

| método | ruta | función | estado | notas |
|---|---|---|---|---|
| POST | `/rrhh/solicitar/<int:ticket_id>` | `rrhh_solicitar` | decommissioned | Ruta fuera del flujo actual. Removida de backend. |
| POST | `/rrhh/aprobar/<int:ticket_id>` | `rrhh_aprobar` | decommissioned | Ruta fuera del flujo actual. Removida de backend. |
| POST | `/rrhh/rechazar/<int:ticket_id>` | `rrhh_rechazar` | decommissioned | Ruta fuera del flujo actual. Removida de backend. |

## Modelo de acceso observado

- `update_ticket_status` valida visibilidad del ticket usando `filtrar_tickets_por_usuario(actor)`.
- `notify_ticket` valida visibilidad del ticket usando `filtrar_tickets_por_usuario(user)`.
- `migrar_historial_local` usa `_require_ticket_admin_action()`.
- `bloquea_lectores_globales` bloquea escrituras a `LECTOR_GLOBAL`.
- Cierre administrativo y validación usan helpers específicos:
  - `_puede_cerrar_ticket_desde_cero`
  - `_puede_validar_cierre_gerente`
- `filtrar_tickets_por_usuario` centraliza scope por:
  - admin roles,
  - gerente regional con `sucursales_ids`,
  - técnicos/soporte por departamento y scope,
  - gerentes por sucursal,
  - jefaturas por departamento,
  - usuarios operativos por sucursal.

## Rutas activas revisadas

| método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|
| POST | `/create` | `create_ticket` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Usuario autenticado | ok_hardened | Creación de tickets requiere sesión autenticada. Mantiene flujo activo de creación sin tocar cierre/validación. |
| PUT | `/update/<int:id>` | `update_ticket_status` | `backend/app/routes/ticket_routes.py` | `jwt_required` + `bloquea_lectores_globales` | Scope de visibilidad del ticket | ok_hardened | Valida acceso al ticket mediante `filtrar_tickets_por_usuario(actor)`. |
| POST | `/migrar-historial-local` | `migrar_historial_local` | `backend/app/routes/ticket_routes.py` | `jwt_required` + `bloquea_lectores_globales` | Admin Tickets | ok_hardened | Operación protegida por `_require_ticket_admin_action()`. |
| POST | `/notify/<int:ticket_id>` | `notify_ticket` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Scope de visibilidad del ticket | ok_hardened | Valida acceso al ticket mediante `filtrar_tickets_por_usuario(user)`. |
| PUT | `/compromiso/<int:ticket_id>` | `set_compromiso` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Usuario autenticado / flujo operativo ticket | ok_hardened | Ruta activa de compromiso de solución/refacción. Mantiene lógica funcional existente. |
| POST | `/cierre/gerente-desde-cero/<int:ticket_id>` | `cierre_gerente_desde_cero` | `backend/app/routes/ticket_routes.py` | `jwt_required` + `bloquea_lectores_globales` | Admin o gerente de sucursal destino | ok_hardened | Usa `_puede_cerrar_ticket_desde_cero()`: admin o gerente de la sucursal del ticket. |
| POST | `/cierre/solicitar/<int:ticket_id>` | `cierre_solicitar` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Flujo activo de cierre | ok_hardened | Solicitud de cierre del flujo actual. No fue modificada. |
| POST | `/cierre/rechazar-jefe/<int:ticket_id>` | `cierre_rechazar_jefe` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Jefe/departamento o rol autorizado por flujo | ok_hardened | Mantiene flujo activo de validación/rechazo por jefe. |
| POST | `/cierre/aceptar-creador/<int:ticket_id>` | `cierre_aceptar_creador` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Creador del ticket / flujo activo | ok_hardened | Mantiene flujo activo de aceptación por creador. |
| POST | `/cierre/rechazar-creador/<int:ticket_id>` | `cierre_rechazar_creador` | `backend/app/routes/ticket_routes.py` | `jwt_required` | Creador del ticket / flujo activo | ok_hardened | Mantiene flujo activo de rechazo por creador. |

## Conclusión

- No hay rutas de escritura abiertas.
- Se removieron 3 endpoints RRHH fuera del flujo actual.
- El flujo activo de cierre/validación de Tickets permanece intacto.
- Tickets queda revisado con un cambio funcional acotado: reducción de superficie al retirar endpoints sin uso.
