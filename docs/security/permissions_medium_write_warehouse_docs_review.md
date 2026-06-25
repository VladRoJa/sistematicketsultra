# Permissions Review — Medium Write: Warehouse / Nube Corporativa

## Objetivo

Revisar rutas de escritura relacionadas con Warehouse y Nube Corporativa: uploads, archivado, catálogos, accesos y acciones documentales.

## Resultado

No se detectaron rutas abiertas. Las 13 rutas revisadas tienen `@jwt_required()` y guard interno.

Nube Corporativa resuelve contexto desde DB usando `UserORM.get_by_id()` y concentra escrituras documentales en `require_internal_document_manager()`.

Aperturas valida administración mediante rol DB-backed y `OPENINGS_ADMIN_ROLES`.

Warehouse usa operador dedicado (`WarehouseOperatorORM`) con flags separados para `can_upload` y `can_archive`. La observación principal es que `WarehouseOperatorORM` no tiene `is_active`, por lo que la baja temporal de un operador debe resolverse cambiando flags o eliminando el operador. Esto se documenta como decisión futura, no como hotfix inmediato.

## Modelo de acceso observado

### Nube Corporativa

- `get_current_internal_document_context()` usa `get_jwt_identity()` solo para resolver `user_id`.
- Luego consulta el usuario real con `UserORM.get_by_id(user_id)`.
- Construye contexto con:
  - `role`
  - `sucursal_id`
  - `sucursales_ids`
  - `department_id`
- Las escrituras usan `require_internal_document_manager()`.
- La regla actual de manager se concentra en `can_manage_internal_documents()` / `is_internal_document_admin()`.

### Aperturas

- `_current_role()` usa `get_jwt_identity()` para resolver `user_id`.
- Luego consulta rol real desde `UserORM.get_by_id(user_id)`.
- `_require_openings_admin()` permite únicamente:
  - `ADMIN`
  - `ADMINISTRADOR`
  - `SUPER_ADMIN`
  - `SISTEMAS`
  - `APERTURAS_ADMIN`

### Warehouse

- `get_current_warehouse_operator()` usa `get_jwt_identity()` para resolver `user_id`.
- Consulta `WarehouseOperatorORM` por `user_id`.
- `require_warehouse_upload()` valida `can_upload`.
- `require_warehouse_archive()` valida `can_archive`.
- Observación futura: `WarehouseOperatorORM` no tiene `is_active`.

## Rutas revisadas

| módulo | método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|---|
| Nube Corporativa | POST | `` | `create_internal_document` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Creación documental protegida por manager DB-backed. |
| Nube Corporativa | PATCH | `/<int:document_id>` | `update_internal_document_metadata` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Edición de metadata protegida por manager DB-backed. |
| Nube Corporativa | POST | `/<int:document_id>/publish` | `publish_internal_document` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Publicación protegida por manager DB-backed. |
| Nube Corporativa | POST | `/<int:document_id>/archive` | `archive_internal_document` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Archivado protegido por manager DB-backed. |
| Nube Corporativa | POST | `/<int:document_id>/versions` | `replace_internal_document_version` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Reemplazo de versión protegido por manager DB-backed. |
| Nube Corporativa | POST | `/<int:document_id>/links` | `create_internal_document_link` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Alta de link protegido por manager DB-backed. |
| Nube Corporativa | PATCH | `/<int:document_id>/links/<int:link_id>` | `update_internal_document_link` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Edición de link protegido por manager DB-backed. |
| Nube Corporativa | DELETE | `/<int:document_id>/links/<int:link_id>` | `deactivate_internal_document_link` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Desactivación de link protegida por manager DB-backed. |
| Nube Corporativa | POST | `/<int:document_id>/external-resources` | `create_internal_document_external_resource` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Alta de recurso externo protegida por manager DB-backed. |
| Nube Corporativa | PUT | `/<int:document_id>/visibility` | `update_internal_document_visibility` | `backend/app/routes/internal_documents_routes.py` | `jwt_required` + `require_internal_document_manager()` | Manager Nube Corporativa | ok_hardened | Visibilidad protegida por manager DB-backed. |
| Nube Corporativa | POST | `/<int:opening_id>/tasks/<int:task_id>/documents/upload` | `upload_task_document` | `backend/app/routes/openings_routes.py` | `jwt_required` + `_require_openings_admin()` | Admin Aperturas | ok_hardened | Upload documental en tareas de apertura protegido por rol DB-backed y allowlist de administración de Aperturas. |
| Warehouse | POST | `/uploads` | `warehouse_create_upload` | `backend/app/routes/warehouse_routes.py` | `jwt_required` + `require_warehouse_upload()` | Warehouse operator con `can_upload` | needs_manual_decision | Guard correcto con operador dedicado y flag `can_upload`. Futuro recomendado: agregar `is_active` al operador Warehouse o definir política formal de desactivación. |
| Warehouse | PATCH | `/uploads/<int:upload_id>/archive` | `warehouse_archive_upload` | `backend/app/routes/warehouse_routes.py` | `jwt_required` + `require_warehouse_archive()` | Warehouse operator con `can_archive` | needs_manual_decision | Guard correcto con operador dedicado y flag `can_archive`. Futuro recomendado: agregar `is_active` al operador Warehouse o definir política formal de desactivación. |

## Conclusión

- No hay hotfix urgente.
- No hay rutas de escritura abiertas.
- Nube Corporativa queda protegida por manager DB-backed.
- Aperturas queda protegida por rol DB-backed restrictivo.
- Warehouse queda protegido por operador dedicado y flags, pero requiere decisión futura sobre `is_active`.
- Recomendación futura: evolucionar Warehouse hacia el patrón de Planning, con operador activo y flags explícitos por acción.
