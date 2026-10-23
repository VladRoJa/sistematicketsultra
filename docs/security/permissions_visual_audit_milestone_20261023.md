# Suite Ultra — Matriz visual de auditoría de permisos (2026-10-23)

## Alcance

Milestone único, solo lectura. Pantalla existente `/#/admin/permisos-observabilidad` → pestaña **Matriz visual · Auditoría**. No edita `permission_grants`, no altera decorators/guards, no activa el resolvedor global y no requiere migración de datos.

Fuente de autoridad: guard operativo legacy. La estimación del catálogo **nunca** se convierte en enforcement. El endpoint `/api/permissions/catalog/audit/matrix` es solo `GET`, JWT y rol administrador obtenido nuevamente desde la BD (helper `_current_admin_user_or_error`).

## Tres perspectivas y criterio compartido

- Usuario → Acciones: usuario identificado, acciones activas paginadas, agrupación por módulo, marca de acción base de entrada cuando existe.
- Módulo → Usuarios: por omisión compara la acción base que configura visibilidad/entrada; seleccionar otra acción muestra su permiso de ejecución específico.
- Acción → Usuarios: acción concreta y usuarios paginados con búsqueda y rol. Se conserva filtro de módulo/sucursal/documento al navegar.

Las tres usan `evaluate_pair()`, misma tupla usuario + acción + contexto. El resultado contiene `legacy_allowed: true|false|null`, `catalog_allowed: true|false|null`, fuentes, motivos y `comparison: coincide|diferencia|no_concluyente`.

**Los contadores reflejan solo los elementos efectivamente evaluados de la página**, nunca estimaciones de toda la plantilla. `unknown` no se suma a `allowed` ni a `denied`. La paginación y los filtros de usuario/rol/módulo/acción son server-side; el filtro visual de estado se aplica exclusivamente a la página actual y se etiqueta así. La exportación CSV abarca solo la página filtrada, no una descarga silenciosa de todos los usuarios.

## Cobertura efectiva comprobable en V1

| Acción | Evidencia safe read-only | Alcance de afirmación |
| --- | --- | --- |
| `track.read` | Conjunto de roles en `_require_track_read_role()` | Guard de entrada/lectura Track; no objeto ni sucursal |
| `track.run_daily_pipeline`, `track.run_agregadoras` | `_require_track_admin_role()` | Guard de rol; el hard stop del job y los parámetros quedan fuera |
| `warehouse.view/upload/archive/catalogs` | Operador + flag exactos de `warehouse_access` | Base del guard, no autorización de objeto/documento específico |
| `planning.read/edit/submit/approve/publish/configure_model` | Operador activo + flag exacto de `planning_access` | Base de guard, no estado de batch ni transición específica |
| `internal_documents.manage` | `can_manage_internal_documents` | Manager legado por rol/usuario |
| `internal_documents.view` | `can_view_internal_document` | Solo con ID de documento existente y visibilidad evaluable. El catálogo no modela visibilidad por objeto: comparación no concluyente incluso cuando el legacy puede evaluarse |

Los demás módulos/acciones (Tickets, Inventario, PM, usuarios, catálogos, aperturas, reportes, permisos de detalle) **no se proclaman legacy verificables**. Sus checks reales muestran `Sin comprobar`, aunque exista estimación diagnóstica. `branch_id` no convierte una comprobación de rol global en permiso de sucursal. La comparación se computa exclusivamente cuando **ambas decisiones** son booleanas y sustentadas; un seed ausente, acción inactiva, grant temporal o scoped sin semántica completa produce `no_concluyente`.

La proyección del catálogo usa los predicados V1 del mismo módulo y las reglas diagnósticas `permission_grants` en lotes por página. El orden de precedencia mostrado es solo preliminar (usuario sobre rol). Los grants con scope o vigencia no evaluada quedan `null` y nunca se interpretan como permisos en producción. Para consultas con `document_id`, los controles internos del documento y sus relaciones de visibilidad se consultan bajo JWT administrativo; el ID no se utiliza para conceder acceso adicional.

**Cobertura incompleta:** el catálogo histórico no representa los 419 métodos HTTP Flask identificados en P21/P22 (350 ausentes del seed antiguo). Sin mapeo no significa ruta vulnerable o desprotegida. La pantalla usa cobertura explícitamente parcial.

## Consultas, rendimiento y seguridad

- `view=user`: pagina acciones y consulta solo un usuario.
- `view=module`: pagina usuarios y evalúa la acción base, o una acción elegida en el mismo módulo.
- `view=action`: pagina usuarios y evalúa una acción concreta.
- Límite duro: 50 filas de origen por solicitud. No se calcula usuarios × acciones en la consulta inversa.
- Las sucursales M:N, operadores Warehouse, Planning y ACL específica PM se precargan por lote. Los grants de acciones seleccionadas se precargan con una consulta.
- `q` + `role` son filtros acumulables para consultas inversas; `branch_id` es contexto de evaluación, **no** prueba de pertenencia.
- Las comprobaciones por documento pueden requerir lecturas de visibilidad sobre la relación; se mantiene el límite duro de página.
- Sin PUT/POST/DELETE nuevos, sin mutación `db.session`, sin cambios a tablas, migraciones o enforcement legacy.
- Pendiente: permitir `document_id` en acciones de descarga solo después de mapear esa acción en catálogo y sus hard stops; actualmente el ID solo prueba `internal_documents.view`.
- Pendiente: agregar evaluación real de sucursal/objeto para PM, Inventario y Tickets mediante helpers puros, y validación end-to-end de los predicados a nivel HTTP.

## QA / CI

Workflow `.github/workflows/permissions-visual-audit-ci.yml`:
1. Compilación Python y pytest de matriz, clasificación bidireccional P20, paridad Track e Inventario.
2. Compilación Angular `npm run build -- --configuration production`.

Se validan roles permitidos/denegados, inconclusos, comparación de Nube/Track, filtros y paginación, prohibición de escritura en el endpoint, alcance de documento en fixture, y origen de decisión. Los fixtures no prueban la paridad total ni todos los guards HTTP.

## Fase A y dependencia documental

El issue [#1053](https://github.com/VladRoJa/sistematicketsultra/issues/1053) permanece abierto. La bitácora de compatibilidad `docs/security/permissions_phase_a_compatibility_inventory_20261022.md` **aún no figura en main** porque pertenece al [PR documental #1058](https://github.com/VladRoJa/sistematicketsultra/pull/1058) (sin fusionar). Este documento independiente evita conflictos de ruta con #1058; integrar una referencia desde aquella bitácora después de su merge será un paso separado.

**Estado:** Fase A: observabilidad visual implementada como capa consultiva, con paridad parcial verificada en los guardias seguros. Global resolver OFF. Auditoría de cobertura del catálogo abierta, falta piloto con datos reales, guards de objeto y QA posmerge. Ningún despliegue autorizado.

## Después de merge (bajo aprobación)

Reconstruir `backend` y `frontend` por Docker Compose a partir del repo actualizado. Sin migraciones Alembic. Comprobar acceso administrativo, 403 para usuarios ordinarios, tres vistas en `/#/admin/permisos-observabilidad` y comparación de casos de prueba; no desplegar ni fusionar desde este PR.
