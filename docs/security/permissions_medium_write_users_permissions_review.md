# Permissions Review — Medium Write: Usuarios/Admin + Permisos Legacy

## Objetivo

Revisar rutas de escritura relacionadas con usuarios, asignación de sucursales y permisos legacy.

## Resultado

No se detectaron rutas abiertas. Todas las rutas revisadas tienen `@jwt_required()` y guard interno.

La observación principal queda en gobierno de roles: las rutas de crear/editar usuario están protegidas por admin, pero permiten asignar o modificar `rol`, `sucursal_id` y `department_id` sin una política granular adicional. Esto se documenta como decisión futura para el módulo de permisos globales, no como hotfix inmediato.

## Rutas revisadas

| módulo | método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|---|
| Usuarios / Admin | PUT | `/<int:user_id>/sucursales` | `put_sucursales_usuario_admin` | `backend/app/routes/admin_usuarios_routes.py` | `jwt_required` + `_get_current_user_admin()` | Admin usuarios | ok_hardened | Actualiza sucursales asignadas con validación de payload y transacción DELETE + INSERT. Futuro: validar existencia de sucursales antes de insertar. |
| Usuarios / Admin | POST | `` | `crear_usuario` | `backend/app/routes/usuarios_routes.py` | `jwt_required` + `_require_admin()` | Admin usuarios | needs_manual_decision | Guard correcto. Permite crear usuarios con cualquier `rol`, `sucursal_id` y `department_id`. Futuro: catálogo de roles permitidos y política de quién puede crear roles altos. |
| Usuarios / Admin | PUT | `/<int:user_id>` | `editar_usuario` | `backend/app/routes/usuarios_routes.py` | `jwt_required` + `_require_admin()` | Admin usuarios | needs_manual_decision | Guard correcto. Permite modificar `rol`, `sucursal_id`, `department_id`, contraseña y email. Futuro: política granular para cambios sensibles y posible regla especial para autoedición. |
| General / Otro | POST | `/asignar` | `asignar_permiso` | `backend/app/routes/permisos_routes.py` | `jwt_required` + `_require_permisos_admin()` | Admin permisos legacy | ok_hardened | Asignación de permiso legacy protegida por admin DB-backed. |

## Conclusión

- No hay hotfix urgente por rutas abiertas.
- Permisos legacy queda correctamente protegido por admin.
- Administración de usuarios queda protegida, pero requiere diseño futuro de política granular:
  - catálogo de roles permitidos,
  - roles que puede crear/editar cada rol administrador,
  - reglas para cambios de rol,
  - reglas de autoedición,
  - validación de sucursal/departamento existente.
