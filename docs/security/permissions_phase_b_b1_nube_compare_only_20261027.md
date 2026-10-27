# Suite Ultra — Fase B / B1: Nube Corporativa en comparación segura

**Fecha:** 27 de octubre de 2026. **Origen:** Fase A cerrada, issue [#1053](https://github.com/VladRoJa/sistematicketsultra/issues/1053), acta [P34](permissions_phase_a_p34_closure_20261027.md). **Seguimiento:** [#1161](https://github.com/VladRoJa/sistematicketsultra/issues/1161).

## Objetivo y decisión

Corregir la **inconsistencia diagnóstica D1**: la proyección previa de `internal_documents.manage` utilizaba `is_admin` (ADMIN, ADMINISTRADOR, SUPER_ADMIN) aunque **el guard operativo real** `internal_documents_access.can_manage_internal_documents` reconoce el rol `SISTEMAS` o el usuario `ADMICORP`. Antes, SISTEMAS podía aparecer denegado pese a poder gestionar; un ADMINISTRADOR genérico podía aparecer permitido pese a no cumplir el guard.

**B1 utiliza exactamente el predicado existente en ambas pantallas de consulta**, sin convertir la proyección en una fuente de autorización. La identidad del usuario consultado se resuelve desde DB en los endpoints administrativos; el helper puro compara el contexto, no utiliza ni claims ni token del consultor.

| Actor sintético | Guard manager | Catálogo antes | Catálogo B1 |
|---|---:|---:|---:|
| `SISTEMAS` / cualquier cuenta de ese rol | Sí | No | **Sí** |
| `ADMINISTRADOR` / `ADMICORP` | Sí | Sí | **Sí** |
| `LECTOR_GLOBAL` / `ADMICORP` | Sí | No | **Sí** |
| `ADMINISTRADOR` / otra cuenta | No | Sí | **No** |
| `SUPER_ADMIN` / otra cuenta | No | Sí | **No** |
| `GERENTE` / otra cuenta | No | No | **No** |

La condición basada en username (ADMICORP) se mantiene por compatibilidad con el guard legacy, **no se recomienda promoverla** como diseño definitivo de grants por cuenta; eso requiere decisión operativa independiente. La comparación con identidad ausente no declara manager autorizado.

## Archivos y métodos cambiados

- `backend/app/routes/permissions_catalog_routes.py::_effective_action_decision`: sustituye la heurística `is_admin` para **solo** `internal_documents.manage` por `can_manage_internal_documents(InternalDocumentUserContext(...))` del usuario objetivo; incluye `details.mode=compare_only`. La rama `internal_documents.view` conserva su indicador abstracto de entrada, pero explicita `object_access_certified=False` y `requires_document_id=True`.
- `backend/app/routes/permissions_visual_audit_routes.py::evaluate_pair`: `internal_documents.view` no reporta `catalog_allowed=True` para permiso de **objeto**, ni con documento ni sin él. Sin documento: `legacy_allowed=None`, `catalog_allowed=None`, estado `no_concluyente`; con documento, el legacy llama a `can_view_internal_document(document, actor)`, pero catálogo sigue `None` porque no modela visibilidad, versiones, estado ni reglas CUSTOM de ese objeto. Nunca falsificar una coincidencia entre dos evaluadores que no hacen lo mismo.
- Tests históricos P19/P20/P34, matriz visual y regresión nueva B1: las discrepancias del 22-oct/27-oct quedan **en la documentación**, ya no como expectativas de CI del código actual.

## Contratos que NO se tocan

- Sin modificaciones a `backend/app/utils/internal_documents_access.py`, `backend/app/routes/internal_documents_routes.py`, `require_internal_document_manager`, guards de view/download/audit, visibilidad `GLOBAL/CUSTOM/PRIVATE`, estados `DRAFT/PUBLISHED/ARCHIVED`, consolidado A-12/A-13, auditoría ni permisos de documento.
- Sin nuevos endpoints ni habilitación de `grants_overlay`/`grants_enforced`; no muta `permission_grants`, módulos, acciones o route-map.
- La API `GET /api/permissions/catalog/users/<id>/effective` continúa **solo diagnóstico**. Para `internal_documents.view`, su campo booleano `allowed=True` es entrada abstracta y **NO significa que ese usuario pueda abrir todos los documentos**; el `details` nuevo lo advierte. En la **matriz visual**, el trivalor es explícito.
- `module-access.effective_allowed` aún necesita revisión de fechas, deny/allow, scope y hard stops (D2). No se utiliza para enforcement.
- Los resultados con `document_id` de la matriz administrativa no reemplazan checks de descarga histórica, auditoría, links ni contenido de archivos.

## Validaciones

- Tabla sintética de roles y cuenta ADMICORP, cotejo directo con el guard puro y con `_serialize_effective_action` más las tres perspectivas de `evaluate_pair`.
- `internal_documents.view` sin documento devuelve *no concluyente* en la matriz, y con documento deja decidir únicamente al guard legacy; ningún grant de catálogo hace la lectura universal.
- Suites heredadas P19, P20, P34, visual y A12/A13 conservan el comportamiento HTTP real; CI ejecuta tests sin DB de producción, SMTP o descarga de contenidos.

## Gate de entrega y continuación B2

**B1 se puede fusionar con CI verde** y QA de estructura, sin migración Alembic. El único cambio operacional es de **diagnóstico administrativo**; para verlo en producción debe reconstruirse backend con el flujo Git/Docker habitual **previa autorización de despliegue**.

**B2 está pendiente (no cubierto por B1)**: paridad efectiva de las **9 GET P1 de Nube** por actor+documento+visibilidad/estado, revisando 401/403/404/200 con dobles de DB y sin exportar archivos reales, incluido IDOR de descarga de versiones y auditoría. Solo después decidir capacidades granulares y posible migración Alembic. Issue #1161 permanece abierto. No se habilitan checkboxes que aparenten conceder permisos reales.
