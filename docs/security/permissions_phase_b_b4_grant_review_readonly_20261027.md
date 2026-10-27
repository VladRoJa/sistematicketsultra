# Suite Ultra — Fase B / B4: revisión integral de grants (solo lectura)

**Issue:** #1161 · **Estado:** milestone en PR, pendiente CI/merge/QA de producción.
**Modo:** observación / `compare_only`. No habilitar `grants_overlay` ni `grants_enforced`.

## Problema comprobado en código

La pestaña `Grants beta` de observabilidad mostraba `grants.length` como total
y cargaba siempre `limit=200,offset=0`; el GET proporciona `summary.total`,
pero no estaba usado. La auditoría solicitaba `limit=100,offset=0`, sin página
siguiente. Asimismo, `is_active` aparecía como si garantizara vigencia
del permiso y el scope solo exhibía una sucursal/departamento, ocultando
`branch_list` y ventanas temporales.

## Alcance B4 implementado

- `permissions-observability.component.ts::loadGrants()`: usa `summary.total` y
  paginación backend de 50 registros. Previene respuestas desordenadas mediante
  `grantRequestVersion`. `applyGrantFilters()` reinicia al primer lote.
- `loadGrantAudit()/fetchGrantAudit()`: usa paginación backend de 50 eventos,
  impide mostrar una respuesta obsoleta al cambiar de grant y permite inspeccionar
  los cambios estructurados anteriores/posteriores.
- `getGrantScopeSummary()`: distingue `global`, `branch`, `branch_list`,
  `department`, `module`, `custom` y valores no reconocidos. `module/custom`
  no se traducen a autorización.
- `getGrantRecordStatus()`: distingue inactivo, borrado lógico y activo con/sin
  ventana, sin declarar fechas como efectivas según reloj del cliente.
- `getGrantAuditSafeSummary()`: presenta campos de auditoría estructurados;
  no vuelca `scope_payload` ni campos libres en pantalla.
- En HTML se expone alcance completo, timestamps `starts_at/expires_at`,
  lista de eventos, totales de backend, filtros exactos y navegación anterior/siguiente.
  La búsqueda textual conserva el alcance **solo página actual** y lo declara.
- Todos los cambios son de **presentación y lectura**; la autoridad sigue en los
  guards HTTP.

## Archivos y límites

- `frontend/src/app/permissions-observability/permissions-observability.component.ts`
- `frontend/src/app/permissions-observability/permissions-observability.component.html`
- `frontend/src/app/permissions-observability/permissions-observability.component.css`

No se modificaron `PermissionGrantORM`, API, `update_user_module_access()`,
`internal_documents_access.py`, evaluador legacy, mapeos, JWT, migraciones,
datos ni grants. El servicio actual ya soporta limit/offset y total.

## Matriz de aceptación

1. **Seguridad:** API de grants e historial siguen admin-only (sin JWT 401,
   con JWT no admin 403); no se crean nuevas rutas ni botones de mutación.
2. **Paginación:** el total representa `summary.total` y los controles permiten
   navegar la página 2+ sin pérdida/duplicidad; 0 registros muestra 0–0.
3. **Auditoría:** historial de 51+ eventos permite segunda página; al cambiar
   grant, respuestas antiguas no sustituyen datos nuevos; before/after muestra
   solo campos estructurados.
4. **Scope:** `branch_list=[1,7]` muestra ambos; `department` muestra
   departamento; `custom` permanece no certificado; `global` no se muestra
   como autorización efectiva.
5. **Fechas:** `starts_at` o `expires_at` se ven, pero un grant activo con
   fechas no se certifica como vigente ni como autorización.
6. **UX:** filtros backend user/role/module/action/effect/scope y búsqueda de
   texto solo en página visible. Sin edición ni cambio de grant al hacer clic.
7. **CI:** permisos visual audit backend + Angular production build exitosos
   sobre el HEAD del PR, inspección de diff y rollback de frontend por deploy
   de commit previo. Validación de producción solo por responsable.

## Fuera de B4

No se resuelve precedencia de denies entre principal/scope/ventana/recurso.
No hay `resolve_permission()` general, editor de grants por scope, evaluación de
hard stops ni autorización sobre un objeto. La matriz de Nube conserva
`catalog_allowed=null` para `internal_documents.view`; QA-B.5 verificó
positivos y negativos mediante el guard legacy.

La continuación para edición segura requiere contrato de precedencia aprobado,
QA de cambios atómicos (allow/deny/inherit) y gate independiente para cualquier
enforcement real.
