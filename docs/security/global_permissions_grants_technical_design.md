# Suite Ultra — Diseño Técnico de permission_grants

## Estado

**Fase:** 4A
**Tipo:** diseño técnico
**Estado:** propuesta inicial
**Alcance:** documentación
**No implementa:** tablas, endpoints, frontend, guards ni cambios reales de permisos.

Este documento define la frontera técnica recomendada para evolucionar desde Global Permissions Observability V1 hacia un sistema controlado de permisos editables.

La intención no es reemplazar de golpe los guards actuales. La intención es crear una capa progresiva, auditable y segura que permita migrar permisos módulo por módulo.

---

## Contexto actual

Suite Ultra ya cuenta con Observabilidad V1:

- catálogo de módulos
- catálogo de acciones
- route map high-risk
- API read-only
- pantalla admin
- permisos efectivos por usuario
- filtros
- auditoría visual
- exportación CSV

Pero todavía no existe una fuente editable centralizada de permisos.

La autorización real sigue viviendo en roles legacy, decorators, helpers backend, allowlists por módulo, operadores dedicados, scopes por sucursal, banderas de entorno y reglas internas de cada módulo.

---

## Objetivo de permission_grants

permission_grants debe permitir registrar excepciones explícitas de acceso sin romper el modelo actual.

Debe responder preguntas como:

- ¿este usuario puede ejecutar esta acción?
- ¿este rol puede ejecutar esta acción?
- ¿este permiso aplica globalmente o solo por sucursal?
- ¿este permiso fue concedido o denegado explícitamente?
- ¿quién lo modificó?
- ¿cuándo?
- ¿por qué?
- ¿está activo?
- ¿está en modo beta o productivo?

---

## Principios de diseño

### 1. Migración gradual

No se debe reemplazar toda la autorización de Suite Ultra en un solo cambio.

La migración debe ser módulo por módulo: observar, comparar, activar beta, activar enforcement y retirar lógica legacy solo cuando sea seguro.

### 2. Backend como fuente real

El frontend puede mostrar u ocultar botones, pero nunca debe ser la fuente de autorización. Todo permiso efectivo debe resolverse en backend.

### 3. Deny explícito debe existir

El sistema debe soportar dos efectos: allow y deny.

Un deny explícito permite bloquear una acción aunque el rol legacy pudiera permitirla.

### 4. Todo cambio debe auditarse

Cualquier grant o deny debe registrar usuario que hizo el cambio, usuario o rol afectado, acción afectada, scope, efecto, motivo, fecha y estado anterior/nuevo.

### 5. Scopes desde el inicio

Suite Ultra depende mucho de sucursales. Un grant no debe ser únicamente global.

Debe permitir scopes como global, sucursal, conjunto de sucursales, departamento, módulo completo y acción específica.

---

## Modelo propuesto

Tabla principal futura:

- permission_grants

Campos sugeridos:

- id
- principal_type
- principal_user_id
- principal_role_key
- module_id
- action_id
- effect
- scope_type
- scope_branch_id
- scope_branch_ids
- scope_department_id
- scope_payload
- reason
- is_active
- starts_at
- expires_at
- created_by_user_id
- updated_by_user_id
- created_at
- updated_at
- deleted_at

---

## principal_type

Define a quién aplica el grant.

Valores sugeridos:

- user
- role

Futuro posible:

- group
- department
- branch_position

### user

Aplica a un usuario específico usando principal_user_id.

### role

Aplica a un rol completo usando principal_role_key.

Ejemplos: GERENTE, GERENTE_REGIONAL, LECTOR_GLOBAL, SISTEMAS, ADMINISTRADOR.

---

## effect

Define el resultado explícito del grant.

Valores permitidos:

- allow
- deny

allow concede una acción.

deny niega una acción aunque otra regla pudiera permitirla.

---

## scope_type

Define el alcance del grant.

Valores sugeridos:

- global
- branch
- branch_list
- department
- module
- custom

global aplica a toda la Suite y debe usarse poco.

branch aplica a una sola sucursal usando scope_branch_id.

branch_list aplica a varias sucursales usando scope_branch_ids.

department aplica a un departamento usando scope_department_id.

module aplica al módulo completo y debe usarse con cuidado.

custom permite reglas especiales mediante scope_payload y debe evitarse al inicio salvo necesidad real.

---

## Reglas de integridad recomendadas

Si principal_type es user, principal_user_id debe existir y principal_role_key debe ser null.

Si principal_type es role, principal_role_key debe existir y principal_user_id debe ser null.

effect debe limitarse a allow o deny.

scope_type debe limitarse a global, branch, branch_list, department, module o custom.

Un grant debe apuntar a una acción específica o a un módulo completo.

Si action_id y module_id existen al mismo tiempo, action_id debe tener prioridad.

No se deben borrar grants físicamente. Usar deleted_at e is_active.

---

## Precedencia propuesta

La precedencia debe ser explícita y estable.

Orden recomendado:

1. Hard stops del sistema.
2. Deny explícito por usuario.
3. Allow explícito por usuario.
4. Deny explícito por rol.
5. Allow explícito por rol.
6. Operadores dedicados.
7. Reglas legacy.
8. Default deny solo en módulos migrados a enforcement.

Hard stops siempre ganan. Ejemplos: endpoint decommissioned, bandera de entorno apagada, módulo deshabilitado, usuario inactivo, JWT inválido o acción crítica bloqueada por configuración.

Ejemplo: si ALLOW_TICKET_DELETE_ALL=false, ningún grant debe permitir tickets.delete_all.

---

## Modos de operación por módulo

Se recomienda agregar en el futuro una configuración por módulo.

Modos sugeridos:

- observability_only
- compare_only
- grants_overlay
- grants_enforced

observability_only solo muestra permisos efectivos y no cambia comportamiento.

compare_only calcula resultado legacy y resultado grants, pero no aplica grants.

grants_overlay permite grants y denies explícitos, pero conserva fallback legacy.

grants_enforced usa grants como fuente principal y solo debe activarse cuando esté probado.

---

## Resolución de permisos propuesta

Función conceptual futura: resolve_permission(user, action_key, context).

Entrada sugerida:

- user
- action_key
- module_key
- branch_id opcional
- department_id opcional
- request_context

Salida sugerida:

- allowed
- source
- reason
- scope_type
- scope_values
- mode
- matched_grant_id
- legacy_result
- grant_result

---

## Auditoría

Tabla futura sugerida:

- permission_grant_audit_log

Campos sugeridos:

- id
- grant_id
- event_type
- before_payload
- after_payload
- changed_by_user_id
- reason
- created_at
- request_ip
- user_agent

Eventos posibles: created, updated, disabled, enabled, deleted_soft, expired.

---

## Endpoints futuros sugeridos

Todos admin-only al inicio.

Read-only:

- GET /api/permissions/grants
- GET /api/permissions/grants/<id>
- GET /api/permissions/grants/effective/users/<id>

Write beta:

- POST /api/permissions/grants
- PUT /api/permissions/grants/<id>
- DELETE /api/permissions/grants/<id>

DELETE debe ser soft delete.

---

## UI futura sugerida

La pantalla actual /admin/permisos-observabilidad puede evolucionar con una nueva pestaña llamada Grants beta.

Funciones iniciales:

- listar grants
- filtrar por usuario
- filtrar por rol
- filtrar por módulo
- filtrar por acción
- filtrar por effect
- ver historial
- crear grant
- desactivar grant

No se recomienda permitir edición masiva en la primera versión.

---

## Flujo seguro para crear un grant

1. Admin busca usuario o rol.
2. Admin selecciona módulo.
3. Admin selecciona acción.
4. Admin selecciona effect: allow o deny.
5. Admin selecciona scope.
6. Admin escribe motivo obligatorio.
7. Sistema muestra preview con resultado legacy, resultado con grant, rutas afectadas y riesgo.
8. Admin confirma.
9. Backend guarda grant.
10. Backend guarda auditoría.
11. Pantalla muestra nuevo permiso efectivo.

---

## Reglas especiales

Acciones con riesgo critical deben requerir confirmación extra.

Ejemplos: tickets.delete_all, jobs manuales de Track, archives de Warehouse, cambios masivos de inventario y administración de usuarios.

Para acciones críticas se recomienda motivo obligatorio, confirmación textual, auditoría completa y quizá doble autorización futura.

Los grants deberían poder expirar mediante starts_at y expires_at.

Los permisos temporales son útiles para soporte, auditoría, cobertura temporal, onboarding y pruebas beta.

---

## Estrategia de migración recomendada

Paso 1: diseño.

Paso 2: migración DB para crear permission_grants, permission_grant_audit_log y quizá permission_module_modes, sin usarlas todavía para autorizar.

Paso 3: API read-only para listar grants y calcular preview efectivo.

Paso 4: UI read-only de grants.

Paso 5: crear grants beta solo para módulos en grants_overlay.

Paso 6: primer módulo candidato.

Paso 7: enforcement parcial solo cuando compare_only y overlay sean estables.

---

## Módulos que NO deben ser los primeros

Tickets no debe ser el primer módulo migrado porque tiene creación, cierre, doble check, RRHH decommissioned, filtros por usuario y visibilidad por rol/sucursal.

Inventario no debe ser el primer módulo migrado porque afecta movimientos, existencias, import/export y relación con tickets/PM.

PM no debe ser el primer módulo migrado porque afecta ejecución, validación, historial, programación y trazabilidad por sucursal.

Warehouse puede migrarse después de internal documents o reports porque tiene operadores dedicados y acciones sensibles como upload/archive.

---

## Primer candidato recomendado

Internal Documents es el primer candidato recomendado.

Motivo: módulo más acotado, permisos principalmente de lectura/subida, menor riesgo operativo, lógica de acceso dedicada y buen caso para probar grants con bajo impacto.

Segundo candidato posible: Reports read-only.

---

## Riesgos

1. Dar acceso indebido.
Mitigación: preview obligatorio, auditoría, confirmación extra en acciones critical y beta por módulo.

2. Bloquear usuarios operativos.
Mitigación: grants_overlay antes de grants_enforced, exportación de auditoría y rollback rápido desactivando grant.

3. Divergencia con legacy.
Mitigación: compare_only, reportes de diferencia y no enforcement hasta resolver discrepancias.

4. Complejidad de scopes.
Mitigación: empezar con global y branch, dejar custom para fases posteriores y documentar cada decisión.

---

## Criterios para pasar a implementación

Antes de crear migración, deben estar definidos:

- campos finales de permission_grants
- campos finales de auditoría
- precedencia aprobada
- primer módulo candidato
- modo inicial
- reglas para critical actions
- estrategia de rollback
- quién podrá administrar grants

---

## Decisión recomendada

No activar grants como autoridad todavía.

Siguiente paso después de este documento: Fase 4B — Migración DB read-only para permission_grants y audit log.

Esa fase debe crear tablas, pero no usarlas todavía para autorizar.

---

## Estado final de este diseño

- permission_grants: diseñado
- enforcement: no activo
- edición: no activa
- guards legacy: sin cambios
- módulo candidato inicial: internal_documents
- modo recomendado inicial: compare_only / grants_overlay
