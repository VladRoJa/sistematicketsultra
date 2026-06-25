# Permissions Review — Medium Write: Remaining Routes

## Objetivo

Revisar las rutas `medium_write` que seguían pendientes después de los bloques anteriores.

## Resultado

No se detectaron rutas abiertas.

Se revisaron 15 rutas pendientes:
- 4 de Catálogos
- 10 de Aperturas
- 1 de Reportes

Catálogos queda protegido por guard administrativo de catálogos.

Aperturas queda mayormente protegido por `_require_openings_admin()`. La única observación es `create_task_comment`, que escribe comentarios pero usa `_require_openings_read()`. Esto puede ser correcto como colaboración del módulo, pero queda como decisión futura de producto/permisos.

Reportes permite que cualquier usuario autenticado reporte un error, creando un ticket de bug asociado al usuario actual. Esto se considera comportamiento esperado.

## Rutas revisadas

| módulo | método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|---|
| Catálogos | POST | `/<string:catalogo>` | `crear_catalogo` | `backend/app/routes/catalogos_routes.py` | `jwt_required` + `_validar_admin_catalogos()` | Admin catálogos | ok_hardened | Creación protegida por admin de catálogos; detecta duplicados y valida clasificaciones con flujo dedicado. |
| Catálogos | PUT | `/<string:catalogo>/<int:elemento_id>` | `editar_catalogo` | `backend/app/routes/catalogos_routes.py` | `jwt_required` + `_validar_admin_catalogos()` | Admin catálogos | ok_hardened | Edición protegida por admin de catálogos; clasificaciones usan flujo dedicado. |
| Catálogos | POST | `/clasificaciones/<int:elemento_id>/desactivar` | `desactivar_clasificacion` | `backend/app/routes/catalogos_routes.py` | `jwt_required` + `_validar_admin_catalogos()` | Admin catálogos | ok_hardened | Desactivación protegida por admin; bloquea desactivar clasificaciones con hijos activos. |
| Catálogos | POST | `/clasificaciones/<int:elemento_id>/reactivar` | `reactivar_clasificacion` | `backend/app/routes/catalogos_routes.py` | `jwt_required` + `_validar_admin_catalogos()` | Admin catálogos | ok_hardened | Reactivación protegida por admin; valida padre activo y duplicados equivalentes. |
| Aperturas | POST | `` | `create_opening` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Creación de apertura protegida por admin; valida sucursal, estado y audita creación. |
| Aperturas | PATCH | `/<int:opening_id>` | `update_opening` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Edición de apertura protegida por admin; audita cambios. |
| Aperturas | POST | `/<int:opening_id>/phases` | `create_opening_phase` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Creación de fase protegida por admin; valida estado y audita creación. |
| Aperturas | PATCH | `/<int:opening_id>/phases/<int:phase_id>` | `update_opening_phase` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Edición de fase protegida por admin; valida pertenencia a apertura y audita cambios. |
| Aperturas | POST | `/<int:opening_id>/tasks` | `create_opening_task` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Creación de tarea protegida por admin; valida fase/tarea padre, estado, prioridad y audita creación. |
| Aperturas | PATCH | `/<int:opening_id>/tasks/<int:task_id>` | `update_opening_task` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Edición de tarea protegida por admin; valida pertenencia, estado, progreso y audita cambios. |
| Aperturas | POST | `/<int:opening_id>/tasks/<int:task_id>/dependencies` | `create_task_dependency` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Creación de dependencia protegida por admin; valida pertenencia a apertura y evita autodependencia. |
| Aperturas | POST | `/<int:opening_id>/tasks/<int:task_id>/blockers` | `create_task_blocker` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Creación de bloqueo protegida por admin; valida tarea, tipo, impacto, duplicados y audita creación. |
| Aperturas | PATCH | `/<int:opening_id>/task-blockers/<int:blocker_id>/resolve` | `resolve_task_blocker` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Resolución de bloqueo protegida por admin; valida pertenencia y audita resolución. |
| Aperturas | POST | `/<int:opening_id>/tasks/<int:task_id>/comments` | `create_task_comment` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_read()` | Lectura Aperturas con permiso para comentar | needs_manual_decision | Es write real, pero usa guard de lectura. Puede ser correcto como colaboración, pero conviene decidir si comentar debe requerir permiso específico. |
| Reportes | POST | `/reportar-error` | `reportar_error` | `backend/app/routes/reportes.py` | `jwt_required` | Usuario autenticado | ok_hardened | Reporte de bug permitido a usuarios autenticados; crea ticket asociado al usuario real. |

## Conclusión

- No hay hotfix urgente.
- No hay rutas abiertas.
- Catálogos queda protegido por admin de catálogos.
- Aperturas queda protegido por admin en rutas administrativas.
- `create_task_comment` queda como decisión futura por usar guard de lectura para una escritura colaborativa.
- Reportes queda como flujo esperado para usuarios autenticados.
