# Suite Ultra — P31 / Fase A: autorización efectiva de 10 rutas candidatas

**Referencia**: P30 fusionado, 112 rutas sin mapeo de catálogo; PostgreSQL read-only 2026-10-26T23:48:39Z (11 módulos, 40 acciones, 69 route maps activos). **Fuente de comportamiento**: guards, servicios backend y pruebas sintéticas sobre `main` al abrir este PR. **NO se certificaron decisiones por usuarios de producción, grants individuales ni endpoints mutantes en vivo.**

## Dictamen

Una acción `full_key` es una **etiqueta del catálogo**, no la prueba de autorización efectiva. Se validaron el límite JWT y los checks por rol/alcance para 10 operaciones, conservando las restantes **102/112 sin inferir permisos**. Detalle por método/handler en [matriz P31](permissions_phase_a_p31_effective_guards_20261027.csv), que conserva P30 en columnas separadas.

| Clase P31 | Rutas | Resultado |
|---|---:|---|
| `specialized_guard_aligned` | **3** | Coordinar, reasignar y devolver trabajo al técnico dependen de `has_maintenance_coordination_permission`; al evaluar el ticket se respetan sucursal, estado, modalidad, motivo y trazabilidad. La **devolución** cambia su *candidato diagnóstico* de `tickets.update_status` a `tickets.maintenance.coordinate`. No crea ni consume grants nuevos. |
| `generic_action_not_equivalent` | **3** | Marcar trabajo terminado es exclusivo de técnico asignado; los dos PATCH de Tapizado exigen scope de tickets y política específica de recepción. **Retiramos de la propuesta** `tickets.update_status` para terminar trabajo y `tickets.update` para ambos PATCH: reutilizarlos sin condiciones podría sobrestimar acceso. El backend actual queda intacto. |
| `candidate_guard_scoped` | **3** | Corregir código: escritores globales de inventario + unicidad/auditoría; anular movimiento: escritor autorizado **para sucursal del movimiento** + stock/concurrencia/auditoría; acceso modular: administrador de la base de usuarios + asignabilidad, cambios y rastro. Son candidatos compatibles solo si el catálogo no omite hard stops. |
| `observability_projection_corrected` | **1** | `openings.manage`: la proyección anterior admitía solo roles genéricos ADMIN/ADMINISTRADOR/SUPER_ADMIN; el guard real permite también SISTEMAS y APERTURAS_ADMIN. Corregimos **solo la proyección** `_effective_action_decision` para consumir `OPENINGS_ADMIN_ROLES` del guard (fuente única). El endpoint `mark-opened` no cambia. |
| `out_of_scope_p31` | **102** | Sin cambio: decisión de capacidad y prueba por grupo pendiente. |
| **Total** | **112** | Ninguna ruta se agregó al route map ni se concedió acceso por catálogo. |

## Evidencia por dominio y limitaciones

### Tickets / Mantenimiento (4 rutas)

- `PUT /api/tickets/maintenance/<id>/coordinate` y `/reassign`: guard individual de coordinación; los servicios `prepare_maintenance_coordination` y `prepare_maintenance_reassignment` evalúan sucursal y estados. La reasignación no permite modificar compromiso ni refacción.
- `POST /api/tickets/maintenance/<id>/return-to-technician`: **guard de coordinador**, distinto a un simple cambio de estado. Solo atención INTERNA/en progreso/pendiente de revisión; requiere motivo.
- `POST /api/tickets/maintenance/<id>/work-completed`: actor con rol técnico de Mantenimiento, departamento correcto, **coincidencia de usuario asignado**, atención interna y en progreso; no solicita cierre, no permite un administrador o gerente arbitrario por el mero hecho de `tickets.update_status`.
- La acción `tickets.maintenance.read_assigned_only` **reduce** visibilidad; no se usa como permiso de escritura. La validez temporal y reglas de grants de coordinación quedan en `tickets_maintenance_permissions.py`.

### Tapizado (2 rutas)

`PATCH /api/tickets/tapizado/<id>/aparatos/<id>/recepcion` y `.../recepciones-lote`: JWT, exclusión de lector global, feature flag, row-lock, tipo TAPIZADO, `filtrar_tickets_por_usuario`, estado diferente de abierto y `puede_editar_recepcion_tapizado` (gerente **de sucursal destino**, coordinador de mantenimiento, jefe regional o **técnico asignado**). Reversión exige motivo; validación de avance se calcula por aparato, y el lote se confirma junto o ninguno. El permiso de editar ticket genérico **no** es equivalente.

### Inventario (2 rutas)

- `POST /api/inventario/<id>/corregir-codigo`: `_require_inventory_global_write` actúa antes del bloqueo de código, consulta del objeto o escritura. Conflictos de código y auditoría se validan aparte.
- `POST /api/inventario/movimientos/<id>/anular`: tras localizar el movimiento, el guard `_require_inventory_movement_write(mov.sucursal_id)` decide según usuario y sucursal. Los roles AUX/SR se restringen a sucursales asignadas; los escritores globales conservan su propio guard. El endpoint hace rollback ante denegación y rechazo de doble anulación/stock insuficiente.

### Aperturas (1 ruta) — diferencia encontrada y corregida

`POST /api/openings/<id>/mark-opened`: `_require_openings_admin` permite la allowlist `OPENINGS_ADMIN_ROLES` definida en `backend/app/routes/openings_routes.py`, que incluye `SISTEMAS` y `APERTURAS_ADMIN` además de los tres administradores generales. La **vista diagnóstica** de `openings.manage` antes marcaba incorrectamente estos perfiles como denegados. Se corrige `backend/app/routes/permissions_catalog_routes.py::_effective_action_decision` sin tocar `_require_openings_admin`, y se prueban 403/404 sin ejecución de escrituras.

### Usuarios y permisos (1 ruta)

`PUT /api/permissions/catalog/users/<id>/module-access`: `_current_admin_user_or_error()` comprueba el rol desde UserORM antes de cargar el objetivo y los grants. Solo módulos `active`/`assignable` con `base_action` aceptan operaciones `allow/deny/inherit`; límites de lote y logs de auditoría se conservan. Los grants editados pueden tener efectos diagnósticos en Permisos V1, **pero no deben confundirse con levantar los hard stops de otros módulos**.

## Pruebas / garantías

`backend/tests/routes/test_permissions_phase_a_p31_effective_guard_parity.py` comprueba:
1. 112/112 identidades P30/P31 y decisiones 3+3+3+1+102, sin marcarlas falsamente como autorizaciones productivas.
2. **10/10** métodos HTTP rechazan peticiones anónimas con 401 antes de tocar servicios.
3. Cinco roles en Aperturas contrastan proyección y guard HTTP (403 o 404 por objeto ficticio, sin commits): incluido SISTEMAS y APERTURAS_ADMIN.
4. Usuario no administrador no puede cambiar acceso modular (403 antes de escritura).
5. GERENTE no puede corregir códigos (403, sin bloqueo/escritura).
6. Anulación inventario mantiene el scope AUX/SR por sucursal y rechaza gerente.
7. Matriz negativa/positiva de editor Tapizado por sucursal/asignación/estado.
8. Técnico que no corresponda y gerente no pueden ejecutar las acciones cruzadas de terminado/devolución antes de localizar tickets.

El workflow P25–P31 también incluye regresiones preexistentes especializadas (coordinación, tapizado, inventario, aperturas) para validar negocio y trazabilidad, sin necesidad de repetir fixtures con datos reales.

**Límite explícito:** no hay prueba de side effects reales, flujo admin de grants completo en PostgreSQL ni comparación dinámica por usuarios/sucursales de producción. Por eso las columnas `effective_permission_proven_by_runtime` siguen en `NO`.

## Cambio y siguientes etapas

- **Único cambio de respuesta del sistema:** proyección de `openings.manage` en observabilidad. Deja de mostrar falsas denegaciones para SISTEMAS/APERTURAS_ADMIN; **no amplía el guard HTTP ni grants**.
- Cero cambios a `permission_route_map`, DB, modelos, Alembic, tokens, schedulers, frontend o acceso operativo.
- Para mostrar la proyección corregida en producción sí habrá que actualizar backend por el flujo Git/Docker **después del merge y validación**; no es un parche de urgencia.
- Fase A #1053 permanece **OPEN**. Las 102 rutas restantes deben auditarse por grupo, con especial atención Marketing 42, Requisiciones 19, Integraciones 11, Contact Center 10; quedan además 247 GET sin catálogo.
