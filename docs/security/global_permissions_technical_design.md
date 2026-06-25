# Módulo Global de Permisos / Observabilidad — Diseño Técnico Inicial

## Objetivo

Diseñar la base técnica mínima para el catálogo global de permisos de Suite Ultra.

Esta fase sigue siendo documental.

No crea tablas, no cambia endpoints y no reemplaza guards actuales.

## Principios

- El backend sigue siendo la fuente real de permisos.
- No se reemplazan permisos legacy de golpe.
- El primer objetivo es observabilidad, no control total.
- Todo cambio DB futuro debe ir con Alembic.
- El diseño debe permitir explicar por qué un usuario puede ejecutar una acción.

## Problema actual

Suite Ultra tiene permisos distribuidos en:

- roles generales del usuario,
- helpers por módulo,
- operadores dedicados,
- scopes por sucursal,
- flags específicos,
- reglas legacy.

Esto funciona, pero dificulta responder de forma centralizada:

- qué puede hacer un usuario,
- en qué módulo,
- con qué alcance,
- por qué tiene ese permiso,
- qué rutas siguen pendientes de decisión.

## Fuente documental base

- `docs/security/global_permissions_contract.md`
- `docs/security/permissions_observability_phase1.md`
- `docs/security/permissions_high_risk_routes_review.csv`
- `docs/security/permissions_high_risk_review_summary.md`

## Modelo técnico propuesto

### 1. `permission_modules`

Catálogo de módulos funcionales.

Campos propuestos:

| campo | tipo | notas |
|---|---|---|
| `id` | integer | PK |
| `key` | string unique | Ej: `tickets`, `inventory`, `pm` |
| `name` | string | Nombre visible |
| `description` | text nullable | Descripción funcional |
| `is_active` | boolean | Activo/inactivo |
| `created_at` | datetime tz | Auditoría |
| `updated_at` | datetime tz | Auditoría |

Ejemplos iniciales:

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

### 2. `permission_actions`

Catálogo de acciones sensibles por módulo.

Campos propuestos:

| campo | tipo | notas |
|---|---|---|
| `id` | integer | PK |
| `module_id` | integer FK | FK a `permission_modules` |
| `key` | string | Ej: `create`, `publish`, `archive` |
| `full_key` | string unique | Ej: `planning.publish` |
| `name` | string | Nombre visible |
| `description` | text nullable | Descripción |
| `risk_level` | string | `low`, `medium`, `high`, `critical` |
| `is_active` | boolean | Activo/inactivo |
| `created_at` | datetime tz | Auditoría |
| `updated_at` | datetime tz | Auditoría |

Ejemplos:

- `tickets.create`
- `tickets.update_status`
- `tickets.close`
- `inventory.master_write`
- `inventory.movement_write`
- `pm.execute`
- `pm.validate`
- `pm.configure`
- `warehouse.upload`
- `warehouse.archive`
- `planning.publish`
- `users.manage`
- `openings.comment`

### 3. `permission_route_map`

Mapa entre rutas backend y acciones funcionales.

Campos propuestos:

| campo | tipo | notas |
|---|---|---|
| `id` | integer | PK |
| `method` | string | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` |
| `route` | string | Ruta Flask declarada |
| `endpoint_function` | string | Nombre de función |
| `source_file` | string | Archivo donde vive |
| `module_id` | integer FK nullable | Módulo asociado |
| `action_id` | integer FK nullable | Acción asociada |
| `current_guard` | text nullable | Guard actual documentado |
| `current_scope` | text nullable | Scope actual documentado |
| `review_status` | string | Estado de revisión |
| `notes` | text nullable | Observaciones |
| `is_active` | boolean | Si la ruta sigue vigente |
| `created_at` | datetime tz | Auditoría |
| `updated_at` | datetime tz | Auditoría |

Uso inicial:

- importar desde `permissions_high_risk_routes_review.csv`,
- completar manualmente rutas no high-risk en fases posteriores,
- no usar todavía para bloquear permisos.

### 4. `permission_grants`

Permisos directos futuros.

Campos propuestos:

| campo | tipo | notas |
|---|---|---|
| `id` | integer | PK |
| `user_id` | integer FK nullable | Usuario directo |
| `role_key` | string nullable | Rol legacy opcional |
| `module_id` | integer FK | Módulo |
| `action_id` | integer FK | Acción |
| `scope_type` | string | `global`, `branch`, `department`, `custom` |
| `scope_value` | string nullable | Ej: sucursal_id/departamento |
| `is_allowed` | boolean | Allow/deny |
| `is_active` | boolean | Activo/inactivo |
| `starts_at` | datetime tz nullable | Vigencia opcional |
| `ends_at` | datetime tz nullable | Vigencia opcional |
| `created_by_user_id` | integer FK nullable | Auditoría |
| `created_at` | datetime tz | Auditoría |
| `updated_at` | datetime tz | Auditoría |

Nota:

Para MVP, no activar `permission_grants` como fuente real de permisos hasta tener endpoint de observabilidad estable.

### 5. `permission_audit_events`

Auditoría de cambios de permisos.

Campos propuestos:

| campo | tipo | notas |
|---|---|---|
| `id` | integer | PK |
| `actor_user_id` | integer FK nullable | Quién hizo el cambio |
| `target_user_id` | integer FK nullable | Usuario afectado |
| `event_type` | string | Ej: `grant_created`, `grant_disabled` |
| `module_key` | string nullable | Snapshot del módulo |
| `action_key` | string nullable | Snapshot de acción |
| `old_value_json` | json nullable | Valor anterior |
| `new_value_json` | json nullable | Valor nuevo |
| `metadata_json` | json nullable | Contexto adicional |
| `created_at` | datetime tz | Auditoría |

## Relaciones conceptuales

- `permission_modules` 1 a N `permission_actions`
- `permission_modules` 1 a N `permission_route_map`
- `permission_actions` 1 a N `permission_route_map`
- `permission_actions` 1 a N `permission_grants`
- `users` 1 a N `permission_grants`
- `users` 1 a N `permission_audit_events`

## MVP técnico recomendado

### MVP 1 — Catálogo read-only

Crear tablas:

- `permission_modules`
- `permission_actions`
- `permission_route_map`

Cargar datos iniciales desde el inventario revisado.

No usar estas tablas para autorizar todavía.

### MVP 2 — Endpoint de observabilidad

Endpoints candidatos:

| método | ruta | objetivo |
|---|---|---|
| GET | `/api/permissions/modules` | listar módulos |
| GET | `/api/permissions/actions` | listar acciones |
| GET | `/api/permissions/routes` | listar rutas mapeadas |
| GET | `/api/permissions/users/<id>/effective` | explicar permisos efectivos de usuario |

### MVP 3 — Comparador legacy vs catálogo

Objetivo:

Mostrar si una ruta tiene:

- guard actual,
- scope esperado,
- acción mapeada,
- estado de revisión,
- decisión pendiente.

No bloquea tráfico.

### MVP 4 — Grants controlados

Activar grants directos solo en un módulo piloto.

Candidatos:

1. Warehouse
2. Planning
3. Nube Corporativa

No iniciar con Tickets.

## Módulo piloto recomendado

### Opción recomendada: Warehouse

Motivo:

- ya tiene operador dedicado,
- tiene flags simples,
- tiene decisión futura clara: `is_active`,
- menor riesgo operativo que Tickets.

Acciones piloto:

- `warehouse.view`
- `warehouse.upload`
- `warehouse.archive`
- `warehouse.catalogs`

### Opción alternativa: Nube Corporativa

Motivo:

- ya usa contexto DB-backed,
- escrituras concentradas en manager,
- podría separarse en permisos granulares.

Acciones futuras:

- `internal_documents.create`
- `internal_documents.update_metadata`
- `internal_documents.publish`
- `internal_documents.archive`
- `internal_documents.manage_visibility`

## Reglas para migración futura

- Nunca quitar un guard legacy sin endpoint de observabilidad equivalente.
- Primero mapear, luego observar, luego activar permisos nuevos.
- Mantener rollback sencillo.
- Todo permiso nuevo debe poder auditarse.
- Todo permiso nuevo debe poder explicarse.
- Si hay conflicto entre legacy y nuevo permiso, legacy gana durante transición.
- El frontend no debe ser la fuente real de autorización.

## Decisiones pendientes antes de Alembic

1. Confirmar nombres finales de tablas.
2. Confirmar si `permission_grants` entra desde primera migración o se deja para MVP 2.
3. Confirmar si `permission_route_map` se precarga por migración o por seed script.
4. Confirmar si módulos/acciones se administrarán por UI o por seed versionado.
5. Confirmar módulo piloto para grants reales.
6. Confirmar si se agregará `is_active` a `WarehouseOperatorORM` como cambio separado.

## Recomendación

Primera migración real debería limitarse a:

- `permission_modules`
- `permission_actions`
- `permission_route_map`

Y dejar `permission_grants` + `permission_audit_events` para una fase posterior, salvo que se decida arrancar directamente con grants read-only.

## Criterio de éxito técnico

Suite Ultra podrá mostrar algo como:

Ruta: POST /api/track/run-daily-pipeline

Módulo: Track

Acción: track.run_daily_pipeline

Guard actual: _require_track_admin_role

Estado: ok_hardened

Fuente actual: legacy guard

Fuente futura: permission action mapped
