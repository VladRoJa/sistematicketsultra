# Suite Ultra — B3: checks globales sin elevar grants limitados

**Origen:** issue [#1161](https://github.com/VladRoJa/sistematicketsultra/issues/1161), Fase B, después de B1/B2. **Entrega:** endurecimiento puntual de lectura/configuración en `GET/PUT /api/permissions/catalog/users/<id>/module-access`. **No crea enforcement ni cambia guards HTTP de módulos.**

## Hallazgo antes del cambio

1. El GET seleccionaba grants por `is_active=True` y `deleted_at IS NULL`, sin distinguir **global vs sucursal** ni `starts_at/expires_at`: podía mostrar un override ya vencido, futuro o acotado como si fuera una casilla global aplicable.
2. El PUT buscaba cualquier grant activo del usuario para la acción base; después reescribía `scope_type="global"`, quitaba sucursales, departamento y `scope_payload` y conservaba fechas si existían. Esto podía **ampliar silenciosamente** una excepción limitada o hacer que una casilla global continuara ligada a fechas heredadas.
3. Dos grants del mismo principal/acción con efectos distintos se reducían al registro más recientemente actualizado: un `allow` posterior podía ocultar un `deny` anterior. El contrato técnico recomienda `deny` prioritario dentro del mismo nivel.
4. `effective_allowed` se serializaba con nombre de permiso efectivo, aunque la interfaz solo ofrece una **proyección de configuración** y no reemplaza `require_internal_document_*`, roles, sucursal, estado ni flags. El PUT sí modifica la tabla de grants; todavía no habilita enforcement general.

## Decisión B3 — una sola capacidad de edición: GLOBAL sin vencimiento

En `backend/app/routes/permissions_catalog_routes.py`:

- `_get_latest_active_grants_by_action`: solo considera grants *globales sin fechas*, `is_active=True`, no borrados y cuyos campos de sucursal/departamento/payload estén vacíos; `_best_module_grants_by_action` da prioridad a `deny` sobre `allow` duplicado **dentro de cada nivel** de principal (usuario o rol). El orden entre niveles continúa **usuario primero y rol después**, conforme al contrato. Un grant temporal *actualmente válido* tampoco puede reducirse a un check global indefinido: debe administrarse por su alcance real en una interfaz posterior.
- `update_user_module_access`: valida todo el lote antes de escribir, rechaza `module_key` duplicado (HTTP 400) y devuelve **409 Conflict** si el usuario ya tiene algún grant activo para la acción que lleve fecha, sucursal, departamento, payload, scope distinto a `global` o efecto desconocido. Eso aplica a `allow`, `deny` e `inherit`. **No modifica, amplía ni desactiva** esos registros; un editor de scopes específico tendrá que resolverlos. Conserva el modelo previo de override para grants simples globales.
- `get_user_module_access`: incluye `grants_enforced=false`, `hard_stops_evaluated=false` y un aviso de que `effective_allowed` **no es autorización HTTP**. La salida de la tabla base no pretende describir grants temporales ni scoped.

## Prohibiciones de esta entrega

- No cambia el comportamiento de `backend/app/utils/tickets_maintenance_permissions.py`: ese guard **sí** consulta un allow global vigente por tiempo, con `deny` preferente, hard stops y alcance por sucursal de ticket. B3 es exclusivamente la representación/editor de permisos por módulo, no el resolver de Tickets.
- No cambia `internal_documents_access.py` ni ninguna ruta documental, Marketing, Finanzas, Track, Inventario o PM. Los dos grants agregados observados en P30 no tienen identidad ni destino certificado; **no consultar ni reescribir** usuarios de producción en B3.
- No crea migraciones, nuevos grants, acciones, mapeos, cambios Angular ni habilita `grants_overlay/grants_enforced`. No desplegar automáticamente: el único cambio productivo tras deploy es que la pantalla de checks ya no puede sobrescribir grants complejos y la lectura es más conservadora.

## QA requerido

1. Casos sintéticos por alcance `branch`, `branch_list`, `department`, `custom payload`, fechas future/current/expired: ninguno se interpreta como global indefinido.
2. Deny > allow del mismo nivel pese al orden temporal; usuario > rol en el preview actual y hard stops siguen externos.
3. PUT rechazo 409 antes de `db.session.add`, `flush` o `commit` para grants limitados y rechazo 400 por módulo repetido. Sin escrituras/usuarios reales.
4. CI de permisos P25–P34 y regresiones B1/B2 intactas, además de suite B3. Verificar que el PR no haya incluido Alembic/frontend ni cambiado el guard operativo.

**Pendiente posterior de #1161:** definir editor específico de scopes/vigencia con justificación y auditoría, fijar regla de `deny` entre principals/scope por recurso, añadir resolución real `resolve_permission(user, action, resource)` solo con aprobación independiente y pruebas de paridad. No activar enforcement por el mero cierre de B3.
