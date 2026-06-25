# Módulo Global de Permisos / Observabilidad — Contrato Funcional

## Objetivo

Diseñar una capa centralizada de permisos y observabilidad para Suite Ultra sin reemplazar de golpe la lógica existente.

El módulo debe permitir responder:

- Qué módulos existen.
- Qué acciones sensibles existen.
- Qué usuario puede hacer qué.
- Por qué puede hacerlo.
- Qué rutas o acciones siguen usando permisos legacy.
- Qué decisiones futuras quedan pendientes.

## Principio rector

La migración debe ser progresiva.

El backend sigue siendo la fuente real de permisos.  
El frontend solo oculta, guía o mejora experiencia.

No se deben reemplazar guards existentes sin observabilidad previa.

## Alcance inicial

### Incluye

- Catálogo de módulos.
- Catálogo de acciones.
- Mapeo de rutas a módulo/acción.
- Observabilidad de permisos efectivos.
- Registro de decisiones pendientes.
- Base para futuras políticas granulares.

### No incluye todavía

- Reemplazar todos los decorators actuales.
- Cambiar permisos reales de producción.
- Crear UI administrativa final.
- Migrar todos los módulos a una sola tabla de permisos.
- Eliminar lógica legacy sin fase de transición.

## Fuente base

Este contrato parte de:

- `docs/security/permissions_observability_phase1.md`
- `docs/security/permissions_high_risk_routes_review.csv`
- `docs/security/permissions_high_risk_review_summary.md`

## Patrones encontrados

### Patrón robusto: Planning / Metas

Planning usa un operador dedicado:

- `PlanningOperatorORM`
- `is_active=True`
- flags separados:
  - `can_edit`
  - `can_submit`
  - `can_approve`
  - `can_publish`
  - `can_configure_model`

Este patrón es referencia positiva para futuros módulos.

### Patrón robusto parcial: Warehouse

Warehouse usa operador dedicado:

- `WarehouseOperatorORM`
- `can_view`
- `can_upload`
- `can_archive`

Decisión futura:

- agregar `is_active`
- formalizar baja temporal de operadores

### Patrón legacy aceptado: PM

PM separa acciones por helpers:

- `require_pm_execute`
- `require_pm_validate`
- `require_pm_configure`

Decisión futura:

- evolucionar hacia operador dedicado tipo Planning

### Patrón legacy aceptado: Tickets

Tickets centraliza alcance en:

- `filtrar_tickets_por_usuario`

Decisión futura:

- formalizar acciones de cierre, creación y validación como permisos observables

## Entidades conceptuales futuras

### PermissionModule

Representa un módulo funcional de Suite Ultra.

Ejemplos:

- tickets
- inventario
- pm
- warehouse
- internal_documents
- track
- planning
- aperturas
- catalogos
- usuarios

Campos conceptuales:

- `key`
- `name`
- `description`
- `is_active`

### PermissionAction

Representa una acción sensible dentro de un módulo.

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

Campos conceptuales:

- `module_key`
- `action_key`
- `risk_level`
- `description`
- `is_active`

### PermissionRouteMap

Relaciona rutas backend con acciones funcionales.

Campos conceptuales:

- `method`
- `route`
- `endpoint_function`
- `module_key`
- `action_key`
- `current_guard`
- `current_scope`
- `review_status`

### PermissionGrant

Representa permisos asignados a usuarios, roles o scopes.

Primera decisión pendiente:

- definir si el MVP soportará solo usuario directo,
- o usuario + rol + sucursal desde el inicio.

Recomendación inicial:

- empezar con observabilidad y grants directos por usuario en módulos nuevos,
- mantener roles legacy como fallback documentado.

### PermissionAuditEvent

Registra eventos de cambios de permisos.

Ejemplos:

- asignar permiso
- revocar permiso
- cambiar scope
- activar/desactivar operador
- publicar permiso global

Campos conceptuales:

- `actor_user_id`
- `target_user_id`
- `module_key`
- `action_key`
- `old_value_json`
- `new_value_json`
- `created_at`

## Estados de revisión

Estados aceptados para checklist:

- `ok_hardened`
- `needs_manual_decision`
- `decommissioned`
- `pending`

## Decisiones futuras ya detectadas

### Usuarios / Admin

Las rutas están protegidas por admin, pero falta política granular para:

- crear roles altos
- editar roles altos
- autoedición
- validación de sucursal/departamento existente

### Inventario

Algunas operaciones están protegidas, pero requieren decisión futura:

- hard delete de inventario maestro sin movimientos
- borrado físico de movimientos
- importación masiva con deduplicación/auditoría

### Warehouse

Warehouse requiere decisión futura sobre:

- `is_active` en `WarehouseOperatorORM`
- política formal de baja temporal

### Aperturas

`create_task_comment` escribe comentarios con guard de lectura.

Decisión futura:

- mantener como colaboración con lectura,
- o crear permiso específico `aperturas.comment`

### PM

PM funciona con roles legacy.

Decisión futura:

- operador dedicado tipo `PlanningOperatorORM`

## MVP recomendado

### Fase MVP 1 — Observabilidad

Crear endpoint o vista interna que responda:

- usuario
- rol
- sucursal
- sucursales asignadas
- módulos visibles
- acciones sensibles permitidas
- fuente del permiso:
  - rol legacy
  - operador dedicado
  - scope sucursal
  - permiso directo futuro

No cambia permisos reales.

### Fase MVP 2 — Catálogo

Crear catálogo interno de módulos/acciones basado en el CSV revisado.

No reemplaza guards.

### Fase MVP 3 — Grants controlados

Agregar permisos directos solo para un módulo piloto.

Candidato recomendado:

- Warehouse
- Planning
- Nube Corporativa

No empezar con Tickets porque tiene flujos operativos más complejos.

## Reglas de implementación

- Todo cambio DB debe usar migración Alembic.
- No usar claims JWT como fuente de permisos de rol/sucursal.
- Resolver usuario real desde DB.
- Mantener compatibilidad con permisos legacy.
- No cambiar frontend antes de tener backend estable.
- No ocultar rutas solo en menú; backend debe validar.
- No eliminar guards existentes hasta tener fase de transición probada.

## Criterio de éxito

El módulo será exitoso cuando Suite pueda responder:

> Este usuario puede ejecutar esta acción porque tiene este permiso, este rol o este scope.

Y cuando una ruta sensible pueda mapearse a:

> módulo + acción + guard actual + scope esperado + estado de revisión.
