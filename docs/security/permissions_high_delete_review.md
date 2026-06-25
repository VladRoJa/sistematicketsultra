# Permissions Review — High Delete Routes

## Objetivo

Revisar rutas de eliminación antes de hacer cambios funcionales.

## Resultado

No se detectaron rutas high_delete abiertas. Las 7 rutas revisadas tienen `@jwt_required()` y guard interno.

La observación principal queda en Inventario: las rutas están protegidas, pero conservan borrado físico en ciertos escenarios. Esto se documenta como decisión futura de producto/auditoría, no como hotfix de seguridad inmediato.

## Rutas revisadas

| módulo | método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|---|
| Catálogos | DELETE | `/<string:catalogo>/<int:elemento_id>` | `eliminar_catalogo` | `backend/app/routes/catalogos_routes.py` | `jwt_required` + `_validar_admin_catalogos()` | Admin catálogo global | ok_hardened | Clasificaciones no permiten hard delete; catálogos con `activo` usan soft delete; hard delete requiere `ALLOW_CATALOG_HARD_DELETE=true`. |
| Inventario | DELETE | `/<int:inventario_id>` | `eliminar_inventario` | `backend/app/routes/inventarios.py` | `jwt_required` + `_require_inventory_global_write()` | Escritura global de inventario | needs_manual_decision | Guard correcto. Permite hard delete solo si no hay movimientos. Futuro recomendado: evaluar soft delete/env gate/auditoría para catálogo maestro. |
| Inventario | DELETE | `/movimientos/<int:id>` | `eliminar_movimiento` | `backend/app/routes/inventarios.py` | `jwt_required` + `_require_inventory_movement_write(mov.sucursal_id)` | Escritura por scope de sucursal/movimiento | needs_manual_decision | Guard correcto. Revierte stock y borra movimiento físico. Futuro recomendado: cancelación/reverso con auditoría en vez de delete físico. |
| Aperturas | DELETE | `/<int:opening_id>/task-dependencies/<int:dependency_id>` | `delete_task_dependency` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin de aperturas | ok_hardened | Incluye validación de pertenencia a apertura y auditoría `TASK_DEPENDENCY_DELETED`. |
| General / Otro | DELETE | `/eliminar` | `eliminar_permiso` | `backend/app/routes/permisos_routes.py` | `jwt_required` + `_require_permisos_admin()` | Admin permisos legacy | ok_hardened | Borra relación de permiso legacy con guard admin DB-backed. |
| Tickets | DELETE | `/eliminar-todos` | `eliminar_todos_los_tickets` | `backend/app/routes/ticket_routes.py` | `jwt_required` + `_require_ticket_admin_action()` + env gate | Admin tickets + bandera explícita | ok_hardened | Operación masiva bloqueada salvo `ALLOW_TICKET_DELETE_ALL=true`. |
| Usuarios / Admin | DELETE | `/<int:user_id>` | `eliminar_usuario` | `backend/app/routes/usuarios_routes.py` | `jwt_required` + `_require_admin()` + env gate | Admin usuarios + bandera explícita | ok_hardened | Hard delete bloqueado salvo `ALLOW_USER_HARD_DELETE=true`; bloquea self-delete. |

## Conclusión

- No hay cambios funcionales urgentes derivados de la revisión high_delete.
- Las rutas destructivas críticas ya tienen guard interno.
- Inventario queda como decisión futura de diseño: migrar de delete físico hacia soft delete/cancelación/reverso auditado.
