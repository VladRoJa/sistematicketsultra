# Suite Ultra — Global Permissions Observability V1

## Estado

**Estado:** cerrado como Observabilidad V1  
**Alcance:** diagnóstico / solo lectura  
**Fecha de cierre:** 2026-06  
**Módulo:** Permisos globales / observabilidad de accesos

Este documento cierra la primera versión operativa del módulo global de permisos de Suite Ultra.

El objetivo de esta fase fue construir visibilidad real sobre permisos, rutas y usuarios sin reemplazar todavía los guards actuales ni activar edición centralizada de permisos.

---

## Principio rector

La Observabilidad V1 no cambia la autorización real de Suite Ultra.

La autoridad real sigue estando en:

- decorators actuales,
- guards backend específicos,
- roles legacy,
- allowlists por módulo,
- scopes por sucursal,
- reglas internas de cada módulo.

El nuevo catálogo global documenta, cruza y visualiza el estado actual, pero no decide permisos reales todavía.

---

## Qué ya existe

### 1. Catálogo DB de permisos

Tablas creadas por migraciones Alembic:

- `permission_modules`
- `permission_actions`
- `permission_route_map`

Estas tablas permiten describir:

- módulos funcionales,
- acciones de negocio,
- rutas backend asociadas,
- guard actual,
- scope actual,
- estado de revisión,
- rutas activas/inactivas.

---

### 2. Seed de módulos y acciones

Estado validado:

- módulos: 11
- acciones: 35

Módulos base:

- `tickets`
- `inventory`
- `pm`
- `warehouse`
- `internal_documents`
- `track`
- `planning`
- `openings`
- `catalogs`
- `users`
- `reports`

Acción crítica agregada:

- `tickets.delete_all`

Esta acción representa la operación masiva protegida por rol admin y bandera de entorno.

---

### 3. Seed de rutas high-risk

Estado validado:

- rutas totales: 72
- rutas activas: 69
- rutas inactivas: 3
- rutas sin `action_id`: 3

Las rutas inactivas corresponden a endpoints RRHH decommissioned:

- `rrhh_solicitar`
- `rrhh_aprobar`
- `rrhh_rechazar`

Estas rutas se conservan en el catálogo como evidencia histórica, pero quedan marcadas como inactivas.

---

## API read-only del catálogo

Blueprint:

- `permissions_catalog_bp`

Prefijo:

- `/api/permissions/catalog`

Endpoints disponibles:

- `GET /api/permissions/catalog/modules`
- `GET /api/permissions/catalog/actions`
- `GET /api/permissions/catalog/routes`
- `GET /api/permissions/catalog/users/<id>/effective`
- `GET /api/permissions/catalog/users/search`

Todos los endpoints requieren:

- JWT válido
- rol administrativo

Roles permitidos:

- `ADMIN`
- `ADMINISTRADOR`
- `SUPER_ADMIN`

La autorización del consultor se valida contra DB mediante `UserORM.get_by_id(get_jwt_identity())`.

---

## Endpoint de permisos efectivos por usuario

Endpoint:

- `GET /api/permissions/catalog/users/<id>/effective`

Modo:

- `observability_v1`

Fuente:

- `legacy_rules_readonly`

Este endpoint cruza el catálogo global de acciones con reglas legacy actuales y devuelve, por acción:

- permitido / denegado,
- source,
- reason,
- scope_type,
- scope_values,
- riesgo,
- módulo,
- acción.

También devuelve contexto del usuario:

- id,
- username,
- email,
- rol,
- department_id,
- sucursal principal,
- sucursales asignadas.

Y contexto de operadores:

- Warehouse operator,
- Planning operator.

---

## Buscador de usuarios

Endpoint:

- `GET /api/permissions/catalog/users/search?q=`

Permite buscar usuarios por:

- username,
- rol,
- email,
- ID.

Es solo lectura y existe únicamente para facilitar la pantalla de observabilidad.

---

## Pantalla frontend

Ruta:

- `/admin/permisos-observabilidad`

Menú:

- `Permisos → Observabilidad de permisos`

Visibilidad frontend:

- `ADMIN`
- `ADMINISTRADOR`
- `SUPER_ADMIN`

Protección de ruta:

- `AdminGuard`

El backend sigue siendo la fuente real de autorización.

---

## Funcionalidad de pantalla

La pantalla permite consultar:

### Módulos

- lista de módulos,
- descripción,
- estado activo/inactivo,
- número de acciones.

### Acciones

- acciones del catálogo,
- módulo,
- `full_key`,
- descripción,
- riesgo,
- estado.

Filtros:

- módulo,
- riesgo.

Exportación:

- CSV de acciones filtradas.

### Rutas high-risk

Permite auditar visualmente:

- rutas activas,
- rutas inactivas,
- rutas sin acción,
- rutas por módulo,
- rutas por review_status,
- rutas por guard,
- rutas por scope,
- rutas por riesgo,
- búsqueda por texto.

Incluye conteos:

- total,
- activas,
- inactivas,
- sin acción,
- critical,
- high,
- filtradas.

Exportación:

- CSV de rutas filtradas.

### Usuario efectivo

Permite:

- buscar usuario,
- seleccionar usuario,
- consultar permisos efectivos,
- filtrar por texto,
- filtrar por decisión: todas, permitidas, denegadas,
- filtrar por módulo,
- ver conteos filtrados,
- exportar CSV.

Exportación:

- CSV de permisos efectivos filtrados.

---

## Qué NO hace Observabilidad V1

Esta versión no hace lo siguiente:

- no edita permisos,
- no crea grants,
- no revoca permisos,
- no reemplaza guards legacy,
- no modifica roles de usuarios,
- no modifica sucursales asignadas,
- no decide autorización real,
- no permite cambios desde frontend,
- no sustituye validaciones específicas de módulos.

---

## Fuente real de permisos actual

La autoridad real sigue distribuida en:

- roles legacy,
- helpers backend específicos,
- decorators,
- allowlists,
- operadores dedicados,
- scopes por sucursal,
- banderas de entorno.

Ejemplos relevantes:

### Warehouse

Usa operador dedicado:

- `WarehouseOperatorORM`
- `can_view`
- `can_upload`
- `can_archive`

### Planning

Usa operador dedicado:

- `PlanningOperatorORM`
- `can_view`
- `can_edit`
- `can_submit`
- `can_approve`
- `can_publish`
- `can_configure_model`

### PM

Usa sets de roles legacy por acción:

- view,
- execute,
- validate,
- configure,
- admin.

### Inventario

Usa roles globales y roles scoped por sucursal.

### Tickets

Usa reglas legacy y filtros específicos de tickets.

La acción `tickets.delete_all` además depende de bandera de entorno:

- `ALLOW_TICKET_DELETE_ALL=true`

---

## Validaciones realizadas

Validaciones de DB:

- modules: 11
- actions: 35
- routes: 72
- active routes: 69
- inactive routes: 3
- null action routes: 3

Validaciones API:

- `GET /api/permissions/catalog/modules`
- `GET /api/permissions/catalog/actions`
- `GET /api/permissions/catalog/routes?active=all`
- `GET /api/permissions/catalog/users/<id>/effective`
- `GET /api/permissions/catalog/users/search?q=`

Validaciones frontend:

- pantalla carga correctamente,
- usuario efectivo carga correctamente,
- buscador de usuarios funciona,
- filtros funcionan,
- auditoría de rutas funciona,
- CSV se descarga correctamente,
- no hay botones de edición.

---

## Riesgos pendientes

### 1. Permisos todavía distribuidos

La autorización real sigue distribuida entre módulos.

Esto es correcto por ahora, pero debe considerarse antes de activar edición centralizada.

### 2. Catálogo no cubre todavía el 100% de rutas

La primera carga se enfocó en rutas high-risk revisadas.

Falta eventualmente mapear rutas medium/low o rutas nuevas que se agreguen.

### 3. Riesgo de divergencia futura

Si se agregan rutas nuevas sin actualizar `permission_route_map`, la pantalla puede quedar incompleta.

Recomendación futura:

- agregar revisión de route_map a PR checklist,
- generar auditoría automática de rutas no mapeadas.

### 4. Frontend solo oculta

Aunque el menú esté limitado a admin, el backend debe seguir siendo la fuente de verdad.

### 5. Grants aún no existen

Todavía no hay tabla ni flujo para `permission_grants`.

Esto es intencional.

---

## Siguiente frontera

Antes de activar edición real:

1. Crear diseño técnico de `permission_grants`.
2. Definir precedencia:
   - rol legacy,
   - grant explícito,
   - deny explícito,
   - scope por sucursal,
   - operador dedicado.
3. Crear migración.
4. Crear API read-only de grants.
5. Crear pantalla de comparación.
6. Activar edición solo en modo beta.
7. Migrar módulo por módulo.

No se recomienda reemplazar todos los guards actuales de golpe.

Riesgo:

- romper Tickets,
- romper PM,
- romper Warehouse,
- romper Track,
- romper Inventario,
- dar accesos indebidos,
- bloquear usuarios operativos.

---

## Criterio de cierre

Observabilidad V1 se considera cerrada porque ya permite responder:

- qué módulos existen,
- qué acciones existen,
- qué rutas high-risk están mapeadas,
- qué rutas están activas/inactivas,
- qué rutas no tienen acción,
- qué usuario tiene permisos observables,
- por qué una acción aparece permitida o denegada,
- qué guard/scope protege cada ruta,
- exportar evidencia a CSV.

---

## Estado final

- Global Permissions Observability V1: COMPLETADO
- Modo: read-only
- Producción: desplegado
- Grants: no activos
- Edición: no activa
- Guards reales: sin cambios
