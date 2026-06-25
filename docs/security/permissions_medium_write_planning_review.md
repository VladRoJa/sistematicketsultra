# Permissions Review — Medium Write: Planning / Metas

## Objetivo

Revisar rutas de escritura relacionadas con metas, aprobaciones, rechazos, publicación y sincronización hacia Track.

## Resultado

No se detectaron rutas abiertas. Las 8 rutas revisadas tienen `@jwt_required()` y guard interno.

Planning / Metas presenta un patrón robusto de permisos: usa un operador dedicado (`PlanningOperatorORM`) con flags separados por acción y `is_active=True`.

## Modelo de acceso observado

El acceso se resuelve mediante:

- `get_jwt_identity()` para obtener el `user_id` actual.
- Normalización de `user_id` a entero válido.
- Consulta de `PlanningOperatorORM` por `user_id` e `is_active=True`.
- Validación granular por acción:
  - `can_edit`
  - `can_submit`
  - `can_approve`
  - `can_publish`
  - `can_configure_model`

Este patrón es compatible con el futuro módulo global de permisos porque no depende únicamente del rol general del usuario.

## Rutas revisadas

| método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|
| POST | `/model-configs` | `create_model_config_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_model_config()` | Planning operator con `can_configure_model` | ok_hardened | Configuración de modelos protegida por permiso granular dedicado. |
| POST | `/batches/<int:batch_id>/approve` | `approve_target_batch_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_approve()` | Planning operator con `can_approve` | ok_hardened | Aprobación protegida por permiso granular dedicado. |
| POST | `/batches/<int:batch_id>/reject` | `reject_target_batch_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_approve()` | Planning operator con `can_approve` | ok_hardened | Rechazo protegido por el mismo permiso granular de aprobación/rechazo. |
| POST | `/batches/<int:batch_id>/publish` | `publish_approved_batch_to_track_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_publish()` | Planning operator con `can_publish` | ok_hardened | Publicación hacia Track protegida por permiso granular dedicado. |
| POST | `/batches` | `create_target_batch_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_edit()` | Planning operator con `can_edit` | ok_hardened | Creación de batch protegida por permiso de edición. |
| POST | `/batches/<int:batch_id>/branch-rows` | `add_branch_row_to_batch_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_edit()` | Planning operator con `can_edit` | ok_hardened | Alta de filas por sucursal protegida por permiso de edición. |
| PUT | `/batches/<int:batch_id>/branch-rows/<int:branch_row_id>` | `update_branch_row_in_batch_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_edit()` | Planning operator con `can_edit` | ok_hardened | Edición de filas por sucursal protegida por permiso de edición. |
| POST | `/batches/<int:batch_id>/submit` | `submit_target_batch_route` | `backend/app/routes/planning_targets_routes.py` | `jwt_required` + `require_planning_submit()` | Planning operator con `can_submit` | ok_hardened | Envío a revisión protegido por permiso granular dedicado. |

## Conclusión

- No hay hotfix urgente.
- No hay rutas de escritura abiertas.
- Planning / Metas queda como uno de los módulos mejor alineados al futuro modelo de permisos globales.
- Recomendación futura: reutilizar este patrón como referencia para otros módulos críticos.
