# Permissions Review — Medium Write: Inventario / PM

## Objetivo

Revisar rutas de escritura operativas relacionadas con Inventario y Mantenimiento Preventivo.

## Resultado

No se detectaron rutas abiertas. Las 8 rutas revisadas tienen `@jwt_required()` y guard interno.

Inventario separa escritura global de inventario maestro y escritura operativa de movimientos por sucursal.

PM separa permisos de ejecución, validación y configuración mediante helpers dedicados y roles específicos.

## Modelo de acceso observado

### Inventario

- `crear_inventario` y `editar_inventario` usan `_require_inventory_global_write()`.
- `registrar_movimiento` usa `_require_inventory_movement_write(sucursal_id)`.
- `_require_inventory_global_write()` permite:
  - `ADMIN`
  - `ADMINISTRADOR`
  - `SUPER_ADMIN`
  - `MANTENIMIENTO`
  - `SISTEMAS`
  - `TECNICO`
- `_require_inventory_movement_write()` permite:
  - roles globales de inventario,
  - `AUX_MANTENIMIENTO` solo para su `sucursal_id`,
  - roles con scope asignado según reglas internas.
- `registrar_movimiento` usa usuario actual real, no `usuario_id` confiado desde payload.

### PM

- PM resuelve usuario actual desde `UserORM`.
- PM valida permiso por acción:
  - `require_pm_execute`
  - `require_pm_validate`
  - `require_pm_configure`
- PM valida sucursal contra scope del usuario.
- PM valida relación inventario/sucursal en bitácoras.
- PM evita doble validación.
- PM evita auto-validación.
- PM mantiene roles legacy de scope global:
  - `ADMIN`
  - `ADMINISTRADOR`
  - `SUPER_ADMIN`
  - `MANTENIMIENTO`
  - `SISTEMAS`
  - `TECNICO`

## Rutas revisadas

| módulo | método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|---|
| Inventario | POST | `/` | `crear_inventario` | `backend/app/routes/inventarios.py` | `jwt_required` + `_require_inventory_global_write()` | Escritura global inventario | ok_hardened | Creación de inventario maestro protegida por roles globales de inventario. |
| Inventario | POST | `/movimientos` | `registrar_movimiento` | `backend/app/routes/inventarios.py` | `jwt_required` + `_require_inventory_movement_write(sucursal_id)` | Escritura operativa por sucursal | ok_hardened | Movimiento protegido por scope de sucursal/rol. Usa usuario actual real, no `usuario_id` del payload. |
| Inventario | PUT | `/<int:inventario_id>` | `editar_inventario` | `backend/app/routes/inventarios.py` | `jwt_required` + `_require_inventory_global_write()` | Escritura global inventario | ok_hardened | Edición de inventario maestro protegida por roles globales de inventario. |
| PM | POST | `/mobile/bitacoras` | `pm_mobile_crear_bitacora` | `backend/app/routes/pm_routes.py` | `jwt_required` + `require_pm_execute()` + scope sucursal | Ejecución PM | ok_hardened | Creación de bitácora protegida por permiso de ejecución y validación de sucursal. |
| PM | POST | `/preventivo/registrar` | `pm_preventivo_registrar` | `backend/app/routes/pm_routes.py` | `jwt_required` + `require_pm_execute()` + scope sucursal | Ejecución PM | ok_hardened | Registro preventivo protegido por permiso de ejecución y validación de sucursal. |
| PM | POST | `/validaciones` | `pm_crear_validacion` | `backend/app/routes/pm_routes.py` | `jwt_required` + `require_pm_validate()` | Validación PM | ok_hardened | Validación protegida por permiso de validación; evita doble validación y auto-validación. |
| PM | POST | `/configuraciones` | `pm_crear_configuracion` | `backend/app/routes/pm_routes.py` | `jwt_required` + `require_pm_configure()` + scope sucursal | Configuración PM | ok_hardened | Creación de configuración protegida por permiso de configuración y validación de sucursal. |
| PM | PUT | `/configuraciones/<int:config_id>` | `pm_actualizar_configuracion` | `backend/app/routes/pm_routes.py` | `jwt_required` + `require_pm_configure()` + scope sucursal | Configuración PM | ok_hardened | Actualización de configuración protegida por permiso de configuración y validación de sucursal. |

## Conclusión

- No hay hotfix urgente.
- No hay rutas de escritura abiertas.
- Inventario queda protegido por separación entre escritura global y escritura por sucursal.
- PM queda protegido por separación entre ejecución, validación y configuración.
- Recomendación futura: evolucionar PM hacia un operador dedicado tipo Planning para reducir dependencia de roles legacy globales.
