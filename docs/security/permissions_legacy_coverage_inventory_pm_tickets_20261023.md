# Suite Ultra — Milestone de cobertura legacy verificable: Inventario, PM y Tickets

Fecha: 2026-10-23. `main` de partida: `770a3f5d754541a05cc83a5abfe6f3427c39a681`.

## Objetivo y garantías

Ampliar la columna **Legacy (guard base)** de la matriz read-only sin modificar los guards operativos, permisos de usuarios, grants, JWT, catálogos, restricciones por sucursal, rutas productivas ni el resolvedor global. No hay migración. La regla fundamental es que la comprobación del **guard inicial** no constituye autorización para ejecutar una mutación o visualizar un registro específico; el permiso de recurso/sucursal/estado se sigue resolviendo en el endpoint real.

El backend `backend/app/routes/permissions_visual_audit_routes.py::_legacy_guard_result` usa únicamente señales que ya están precargadas: rol de BD, sucursales M:N de `usuario_sucursal`, permiso individual de lectura PM y bandera de entorno de Tickets. No ejecuta ninguna operación de creación, modificación, eliminación, validación ni cambio de estado. Se conserva `evaluate_pair()` como **función común en Usuario → Permisos, Módulo → Usuarios y Acción → Usuarios**.

## Matriz de cobertura del milestone

| Acción | Fuente del guard real | Condición verificable en auditoría | Límite estricto |
|---|---|---|---|
| `pm.read` | `pm_permissions.can_pm_view` y `pm_routes.pm_read_access` | Role gate o lectura individual de COMPRAS / COORDINADOR_MANTENIMIENTO con sucursales M:N asignadas | Si se consulta `branch_id`, **Sin comprobar** hasta validar reglas completas sobre la sucursal; la apertura de una bitácora/documento todavía requiere control operativo |
| `pm.execute` | `pm_permissions.can_pm_execute` | Gate de rol inicial | Con `branch_id`: **Sin comprobar**; no simula registro de bitácora ni transición |
| `pm.validate` | `pm_permissions.can_pm_validate` | Gate de rol inicial | Con `branch_id`: **Sin comprobar**; no certifica que sea validable una bitácora |
| `pm.configure` | `pm_permissions.can_pm_configure` | Gate de rol inicial | Con `branch_id`: **Sin comprobar**; no certifica actualización de configuración |
| `inventory.master_write` | `inventarios._require_inventory_global_write` | Rol presente en `INVENTORY_GLOBAL_WRITE_ROLES` | Solo guard de rol global; no verifica payload, existencia de artículo ni estado |
| `inventory.movement_write` | `inventarios._require_inventory_movement_write(sucursal_id)` | Con `branch_id`, administradores/roles globales, AUX en sucursal primaria, SR en sucursales **M:N** | Sin `branch_id`: **Sin comprobar**, incluso si el usuario tiene rol global; no se deduce autorización por sucursal primaria para SR |
| `tickets.delete_all` | `ticket_routes._require_ticket_admin_action` y bandera del endpoint `eliminar_todos_los_tickets` | Admin + `ALLOW_TICKET_DELETE_ALL` literalmente igual a `true` tras lowercase; default OFF | No llama DELETE, no lee ni elimina tickets. No concede control sobre tickets individuales |

La excepción individual PM requiere simultáneamente `departamento_id=1`, `es_admin=false`, rol elegible, permiso de usuario y lista M:N no vacía; no se añade automáticamente la sucursal principal corporativa. `inventory.master_write` y `tickets.delete_all` son checks de entrada, no comprobaciones sobre datos o acciones de UI.

## Acciones explícitamente incompletas

- **Inventario:** `inventory.read` cubre endpoints legacy heterogéneos y un piloto V2 con gate distinto. No se puede expresar como una única autorización sin identificar el endpoint y su contexto; permanece **Sin comprobar**. Reportes, entradas especiales y eliminaciones de movimientos pueden tener guards adicionales.
- **Tickets:** `tickets.view/create/update/update_status/close/notify`, `tickets.maintenance.coordinate` y `tickets.maintenance.read_assigned_only` dependen de filtros, identidad, grant vigente, asignación, departamento, sucursal, estado o tipo de ticket. Sin `ticket_id` ni evaluación específica, permanecen **Sin comprobar**. En particular, **un gerente no tiene permiso genérico de cierre sobre cualquier ticket**.
- **PM:** las cuatro comprobaciones nuevas verifican exclusivamente el gate inicial sin `branch_id`. No se declara acceso al equipo, bitácora o sucursal concreta. La cuenta de mantenimiento regional y las excepciones de sucursal permanecen sujetas al guard de producción.

El frontend distingue los nuevos scopes `guard_rol_base` y `sucursal` y explica el límite de la comprobación. Código técnico fuente/motivo sigue desplegable. Las estimaciones del catálogo pueden discrepar legítimamente porque tienen una semántica más general; **no corregimos la paridad falseando decisiones reales**.

## QA y regresiones

`backend/tests/routes/test_permissions_legacy_coverage_inventory_pm_tickets.py` comprueba paridad con las funciones reales para roles globales/denegados, scope AUX/SR, rama inexistente, COMPRAS/COORDINADOR sin sucursales, PM por guard/branch, y doble gate de borrado masivo (sin ejecutarlo). `test_permissions_visual_audit_matrix.py` continúa asegurando que PM con `branch_id`, Tickets por objeto e `inventory.read` se mantengan indeterminados. El workflow ejecuta las pruebas de ruta de permisos, Fase A y compilación Angular.

**Postmerge:** reconstrucción `backend` y `frontend`, sin migraciones ni rebuild de schedulers; QA manual con GERENTE, ADMINISTRADOR, AUX_MANTENIMIENTO, SR_MANTENIMIENTO, COORDINADOR_MANTENIMIENTO y cuenta regional MANTENIMIENTO ID 45, comprobando que las solicitudes de branch no se confundan con permisos de objeto.
