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

---

## Adenda vigente — separación de roles, permisos y alcance (2026-10-22)

Esta adenda formaliza la decisión funcional de mantener **perfiles de trabajo separados de las capacidades y del alcance**. Aclara los apartados históricos de este contrato sin activar nuevas reglas de autorización. El objetivo es reducir condiciones especiales y evitar perfiles combinados difíciles de mantener.

### Tres conceptos independientes

1. **Rol o perfil:** responsabilidad operativa estable del usuario (por ejemplo, `GERENTE`, `SISTEMAS` o `COORDINADOR_MANTENIMIENTO`). Responde *qué función desempeña*, no contiene por sí solo todas las excepciones de acceso.
2. **Permiso o acción:** capacidad concreta, nombrada por módulo y acción (por ejemplo, `pm.validate` o `warehouse.upload`). Responde *qué puede hacer*. Lectura, ejecución, validación, configuración y administración deben poder distinguirse.
3. **Alcance o scope:** conjunto de sucursales, departamento, registros o documentos sobre los que se permite la acción. Responde *dónde y sobre qué puede hacerlo*. No se debe confundir una capacidad global con la misma capacidad limitada a sucursales.

Los **grants explícitos** (`allow`/`deny`) se reservan para conceder o bloquear excepciones justificadas; **`inherit` significa retirar la excepción y volver a la política base**, no conceder un tercer permiso. Los límites inviolables (usuario inactivo, acción deshabilitada, bandera de seguridad apagada o restricciones de datos) no se omiten mediante un `allow`.

### Política para nuevos roles y excepciones

- **Sí se pueden crear roles nuevos** cuando representen una responsabilidad laboral real, estable y distinguible de las existentes.
- No crear combinaciones de roles como `GERENTE_SISTEMAS`, `COORDINADOR_LECTOR_TRACK` o roles específicos por usuario/sucursal únicamente para entregar una acción adicional.
- Si dos personas tienen el mismo puesto pero distinto alcance, conservar el rol y configurar las sucursales permitidas.
- Si una persona requiere una capacidad extraordinaria, preferir una excepción explícita, delimitada y auditable antes que cambiar su rol principal.
- No incorporar todavía multirrol automático o jerarquías heredadas sin una necesidad operativa demostrada: el modelo legacy actual usa un rol principal por usuario.
- Cada rol nuevo necesita nombre funcional, responsabilidades, permisos base y alcance esperado claramente documentados; no basta crear un valor de texto para evitar una validación.

### Resolución y trazabilidad exigidas

Para una operación protegida, el backend debe poder explicar: **usuario + rol + acción + alcance + fuente de decisión + resultado**. La UI no autoriza por sí misma. Al migrar un módulo, las reglas de grants y su precedencia seguirán el diseño técnico de `docs/security/global_permissions_grants_technical_design.md`, sin invalidar hard stops ni controles específicos de acceso a registros.

Las asignaciones y revocaciones deben registrar quién las hizo, sobre qué usuario o rol, qué acción y scope cambiaron, valor anterior/nuevo, motivo y fecha. Evitar excepciones escondidas por nombre de usuario, cadenas dispersas de roles o controles de acceso duplicados entre frontend y backend.

### Matriz bidireccional de accesos — requisito funcional obligatorio

La administración de permisos debe ofrecer **la misma decisión efectiva desde cualquier punto de entrada**, no listas de roles separadas que puedan contradecirse. Las vistas deben ser filtros sobre un único resolutor backend, no una nueva fuente de autorización.

1. **Usuario → módulos y acciones:** elegir o buscar usuario y mostrar una matriz tipo checklist agrupada por módulo, con visibilidad/entrada al módulo, acciones disponibles y denegadas, rol base, alcance (global/sucursales/otros), origen de la decisión (rol, grant por usuario/rol, operador o legacy) y razón. Distinguir `permitido`, `denegado` y `sin información suficiente`; `inherit` es la fuente o estado de excepción, no una autorización por sí mismo.
2. **Módulo → usuarios:** elegir módulo y listar quién puede **ver/entrar** al módulo y, separadamente, quién puede ejecutar cada acción del módulo. Incluir usuarios sin acceso como filtro opcional; distinguir acceso base al módulo de permisos operativos, para no interpretar `ver` como `administrar`.
3. **Acción → usuarios:** elegir acción concreta (por ejemplo `pm.validate`) y mostrar todos los usuarios activos a los que les corresponde acceso efectivo, además del alcance y la fuente de autorización. Permitir visualizar también denegados, excepciones y usuarios inactivos mediante filtros explícitos. Si el permiso depende de una sucursal, ofrecer filtro de sucursal: el mismo usuario puede estar permitido en una y no en otra.
4. **Rol → acciones y usuarios:** elegir rol, consultar permisos base correspondientes y usuarios que lo poseen; señalar grants individuales o excepciones que alteren el resultado. Un rol por sí solo no implica acceso irrestricto a sucursales ni registros.
5. **Navegación cruzada:** desde cada fila se podrá abrir la perspectiva contraria (usuario ↔ acción ↔ módulo), conservando filtros útiles, búsqueda y paginación. Exportación CSV de la vista filtrada cuando aporte valor operativo.

#### Checklist de consulta versus edición

- **Consulta primero:** casillas o indicadores muestran el permiso efectivo y su origen. No confundir una casilla marcada con un grant explícito; un permiso puede ser heredado o condicionado.
- **Edición futura y por módulo migrado:** al cambiar un acceso, el administrador elige `allow`, `deny` o `inherit`, alcance y motivo; el backend aplica la política, registra auditoría y actualiza ambas perspectivas. No habilitar una casilla que parezca conceder acceso real cuando el módulo sigue únicamente en observabilidad.
- No crear roles combinados para hacer coincidir el checklist con una excepción. Preferir los grants existentes, con alcance y razón.
- El historial de cambios debe permitir reconstruir quién cambió qué, para quién, cuándo y por qué; un grant denegado o desactivado debe seguir siendo auditable.

#### Consistencia, límites y criterio de aceptación

- **Una sola fuente de verdad:** los resultados por usuario, módulo y acción deben derivarse del mismo resolvedor backend, con la misma precedencia, las mismas restricciones por sucursal y los mismos hard stops.
- **Mostrar modo real:** identificar claramente si el resultado es `diagnóstico legacy`, `comparación` o `enforcement activo`; una inferencia de observabilidad no debe mostrarse como garantía de acceso operativo.
- **Seguridad:** consultas transversales solo para administradores autorizados en backend; no divulgar la matriz completa a usuarios ordinarios.
- **Simplicidad:** filtros por nombre/rol/sucursal/módulo/acción y paginación; evitar calcular toda la matriz global en cada carga o introducir motores genéricos de políticas solo para construir la pantalla.
- **Prueba de aceptación cruzada:** dado el mismo usuario, acción y sucursal, la vista Usuario → Acción y la vista Acción → Usuarios deben devolver igual decisión y procedencia. El acceso a módulo debe verificarse por separado del permiso para escribir o aprobar.

**Estado de implementación al agregar esta adenda:** ya existe consulta de usuario efectivo y catálogo de módulos/acciones; la búsqueda inversa por módulo/acción a todos los usuarios **queda como requerimiento pendiente**, no como una funcionalidad ya desplegada.

### Estado comprobado y alcance inmediato

- Observabilidad V1 volvió a cargar después de corregir el JOIN ambiguo en PR #1049 (2026-10-22).
- Corte visual de ese día: 11 módulos, 40 acciones y 72 rutas mapeadas, de las cuales 3 aparecen inactivas. Son métricas del catálogo, no una afirmación de cobertura total.
- Ya existen modelos y API de consulta para `permission_grants` y auditoría. El endpoint `PUT /api/permissions/catalog/users/<id>/module-access` guarda overrides por módulo, **pero expresamente no reemplaza aún el enforcement legacy**.
- **Primer piloto propuesto:** Nube Corporativa / `internal_documents`. Separar capacidades de consulta y administración sin debilitar la visibilidad por documento, sus restricciones de sensibilidad ni los controles de escritura existentes.
- Tickets, Inventario, PM y Track no se migran en bloque. Cada módulo se incorpora con un cambio pequeño, reversible y comprobación de permitido, denegado y alcance aplicable.

**Criterio de aceptación funcional:** un operador puede comprender por qué alguien tiene acceso sin leer condiciones especiales esparcidas por el repositorio, y el backend aplica exactamente ese resultado a la operación real.


## Adenda 2026-10-23 — Auditoría visual read-only

Se incorpora como propuesta en rama de milestone la pestaña **Matriz visual · Auditoría** en la pantalla actual de Observabilidad. Tres perspectivas usan el mismo evaluador trivalente (permitido / denegado / no concluyente), y la comparación solo considera coincidencia o diferencia cuando legacy real y catálogo son comprobables. La UI NO edita grants ni sustituye guards. La fuente de autoridad es el guard legacy y el catálogo sigue siendo diagnóstico.

La cobertura probada se limita a predicados seguros de Track, Warehouse, Planning y Nube Corporativa; los scopes de sucursal y objeto restantes quedan pendientes, igual que el catálogo histórico parcial. Se documentan límites, API, QA y seguimiento en `docs/security/permissions_visual_audit_milestone_20261023.md`. El issue #1053 y PR documental #1058 siguen independientes. La aprobación de merge/despliegue corresponde al responsable del proyecto.
