# Suite Ultra — Fase A: inventario y mapa de compatibilidad de permisos

**Estado:** INVESTIGACIÓN DE CÓDIGO / EN CURSO (issue #1053)  
**Fecha:** 2026-10-22  
**Tipo:** documento de diagnóstico; no cambia código, grants ni enforcement.  
**Contrato rector:** `docs/contratos/contrato de permisos globales.md` (roles, acciones, scopes y matriz bidireccional).

## 1. Objetivo y límites

Identificar el **guard real** de cada módulo, su fuente de autoridad y las condiciones que se perderían si se sustituyera por una casilla de `permission_grants`. No se propone activar grants de forma global, retirar controles de sucursal ni migrar todos los módulos simultáneamente.

**Alcance de esta entrega:** lectura del repositorio y de los contratos; las cantidades del catálogo provienen del corte visual de la pantalla administrativa recuperada el 22/oct/2026 (11 módulos, 40 acciones, 72 rutas y 3 rutas inactivas). **No se ejecutaron consultas a PostgreSQL productivo ni se verificaron las asignaciones individuales de usuarios.** Las 72 rutas corresponden al mapeo high-risk existente, **no a la totalidad de endpoints de Suite Ultra**.

La decisión final tiene que ser backend y explicar **usuario, acción, rol, scope, fuente, permiso o denegación y motivo**. El checklist es representación, nunca autoridad por sí solo.

## 2. Capas actuales comprobadas en código

| Capa | Fuente/archivo | Estado comprobado | Precaución |
| --- | --- | --- | --- |
| Identidad/rol principal | `backend/app/models/user_model.py::UserORM` | Un campo `rol` en `users`; `sucursal_id`, `department_id`, relación `usuario_sucursal` | No hay multirrol modelado ni columna `is_active` declarada en este ORM |
| JWT + sesión | `backend/app/routes/auth_routes.py::_claims_for` | JWT incluye rol/sucursales/departamento; guardias importantes vuelven a DB | No usar claims antiguos como autoridad de permisos |
| Roles genéricos | `backend/app/utils/auth_utils.py` | Decoradores `requiere_rol`, `requiere_admin`, `prohibe_roles` | Conservar hasta migrar consumidores concretos |
| ACL por departamento | `backend/app/models/permiso_model.py`, `backend/app/routes/permisos_routes.py` | Tabla `usuarios_permisos` con `es_admin`; API independiente `/api/permisos` | No asumir que equivale a `permission_grants` |
| Operadores dedicados | `backend/app/utils/warehouse_access.py`, `backend/app/utils/planning_access.py` | Warehouse usa flags; Planning usa `is_active` + flags | El comportamiento operativo actual es autoridad hasta migración |
| Grants globales | `backend/app/models/permissions.py` | `permission_grants` para `user`/`role`, `allow`/`deny`, scope, fechas y auditoría | **Ya se leen para decisiones reales** de Tickets Mantenimiento |
| Observabilidad | `backend/app/routes/permissions_catalog_routes.py` | Catálogo, rutas, permisos efectivos y `module-access`; administración restringida en backend | No tratar el valor diagnóstico como autorización real |
| Permisos UI legacy | `frontend/src/app/admin-permisos/admin-permisos.component.ts` | Checklist de departamentos y `guardarPermisos()` solo imprime en consola | No reutilizar como editor efectivo sin sustituir flujo |
| Menú Angular | `frontend/src/app/layout/layout.component.ts` | Mezcla gating por rol y consultas de contexto según módulos | El menú no concede autorización y no debe duplicar políticas |

## 3. Matriz inicial por módulos del catálogo

**Interpretación:** “fuente real” indica la autoridad identificada en código, no que estén revisadas todas las rutas de ese dominio. “Pendiente” requiere contraste ruta por ruta antes del enforcement.

| Módulo | Fuente real identificada | Alcance/hard stops a preservar | Estado de mapeo |
| --- | --- | --- | --- |
| `tickets` | `backend/app/utils/ticket_filters.py::filtrar_tickets_por_usuario`, `backend/app/routes/ticket_routes.py`, `backend/app/utils/tickets_maintenance_permissions.py` | creador/departamento/sucursal, estado, cierre/validación, coordinación/solo asignados, flags destructivos | **Alto riesgo:** lectura/edición/cierre distintos; grants individuales YA afectan coordinación |
| `inventory` | `backend/app/routes/inventarios.py::_resolve_inventory_read_sucursal_ids`, `_require_inventory_global_write`, `_require_inventory_movement_write` | lectura por sucursal, escritura global vs movimientos por scope, controles de transacciones | **Alto riesgo:** no equiparar `inventory.read` con movimientos o borrados |
| `pm` | `backend/app/utils/pm_permissions.py`, `backend/app/routes/pm_routes.py::_verificar_permiso_sucursal` | permisos view/execute/validate/configure más sucursales, ACL de departamento y excepción jefe regional | **Alto riesgo:** rol solo no basta |
| `warehouse` | `backend/app/utils/warehouse_access.py` | allowlist de operador, `can_view`, `can_upload`, `can_archive`; catálogos tienen política propia | Patrón explícito; falta `is_active` en el helper/modelo actual |
| `internal_documents` | `backend/app/utils/internal_documents_access.py::can_manage_internal_documents`, `require_internal_document_manager`, `can_view_internal_document` | administradores de documentos, estado publicado/borrador, documentos sensibles, visibilidad y descargas por registro | **Piloto preferente:** separar manage de view; preservar seguridad documental |
| `track` | `backend/app/routes/track_routes.py` y helpers/guards por ruta (pendiente inventario exacto) | lectura frente a ejecución de pipelines críticos; permisos de scheduler separados de web | No usar aproximación `track.read` como sustituto global |
| `planning` | `backend/app/utils/planning_access.py` | operador activo y flags separados: view/edit/submit/approve/publish/configure_model | Modelo positivo, mantener granularidad |
| `openings` | `backend/app/routes/openings_routes.py`, `openings_lifecycle_routes.py` | administración y lectura, comentario de tarea según guard vigente | Pendiente contraste completo, especialmente `openings.comment` |
| `catalogs` | `backend/app/routes/catalogos_routes.py::_validar_admin_catalogos` | protección de escrituras, importaciones, jerarquías y borrados | Pendiente matriz endpoint por endpoint |
| `users` | rutas administrativas y decoradores específicos, `backend/app/utils/auth_utils.py` | alta/edición de roles privilegiados, sucursal, depto; no autoborrado inseguro | **Alto riesgo**; no migrar como piloto |
| `reports` | handlers de reportes y permisos asociados; `_effective_action_decision` estima read y reportar error | lectura vs captura de errores; alcance real por tipo de reporte | Pendiente inventario fino |

**Fuera del catálogo base:** la Suite ya tiene áreas como Contact Center, Campañas V2, Automatización/Salud Sistemas y demás pantallas creadas después del seed inicial (`backend/migrations/versions/3d4f6a8b9c10_seed_global_permissions_catalog.py`). Se requiere inventario de cobertura real antes de afirmar que “todos los permisos” están representados. No crear acciones inventadas hasta mapear endpoints y guard vigente.

## 4. Diferencias y riesgos técnicos verificables

### A-01 — Nube Corporativa: observabilidad distinta del guard real (prioridad crítica antes del piloto)

- Diagnóstico: `backend/app/routes/permissions_catalog_routes.py::_effective_action_decision` evalúa `internal_documents.manage` mediante `is_admin` como **aproximación**.
- Enforcement actual: `backend/app/utils/internal_documents_access.py::is_internal_document_admin` reconoce **rol SISTEMAS** y **cuenta ADMICORP**.
- Consecuencia posible: falso permitido y falso denegado en una matriz inversa si se reutiliza la aproximación. **No usar el diagnóstico actual para activar grants**. `internal_documents.view` tampoco equivale a leer cualquier documento: tiene reglas de visibilidad y sensibilidad.

### Evidencia productiva y rutas del piloto — 2026-10-22

**Comparación agregada de 70 cuentas de `users`, sin datos personales:**

| Guard real de `internal_documents.manage` | Diagnóstico `_effective_action_decision` | Cuentas |
| --- | --- | ---: |
| No | No | 68 |
| Sí | No | **1** |
| Sí | Sí | 1 |
| No | Sí | 0 |

- **2 cuentas autorizadas realmente** a administrar Nube; **1 falso negativo** en observabilidad; **0 falsos positivos** en este corte. La cuenta con verdadero acceso y falso diagnóstico cumple la condición del rol `SISTEMAS`. La consulta compara predicados de los dos helpers, no llamadas HTTP; no confirma el estado de documentos particulares ni evalúa sesiones.
- **No cambiar el rol, no denegar permisos ni inferir que ADMINISTRADOR obtiene automáticamente acceso a documentos**: primero fijar la política real de Nube y reproducir esta matriz en tests.
- Los dos grants vigentes de producción corresponden a Tickets Mantenimiento, no a Nube: por tanto hoy el piloto carece de grants individuales actuales que deban conservarse para `internal_documents.*`.

**Inspección inicial del código de rutas de Nube** (`backend/app/routes/internal_documents_routes.py`, sin probar endpoints productivos):

- Se identificaron **21 handlers HTTP** protegidos con `@jwt_required()` en este blueprint, con controles adicionales según la operación.
- La creación, edición de metadata, publicación, archivo, reemplazo de versión, creación/edición/desactivación de vínculos, recursos externos y cambios de visibilidad usan `require_internal_document_manager()`: **10 handlers de escritura**. Antes de migrar deben verificarse también las validaciones de objeto y negocio dentro de cada handler.
- Detalle, lectura de versiones/vínculos, recursos externos, descarga actual y auditoría aplican comprobaciones por documento distintas; **descarga de versión histórica** usa `can_download_historical_internal_document_version()`, que remite al permiso de manager.
- La lista general `GET /internal-documents` no concede acceso uniforme: managers consultan borradores y estados adicionales; no managers reciben solo documentos publicados que pueden ver. **Además, a managers distintos de ADMICORP se les excluye el documento con título `Consolidado de agregadoras`** en la consulta de listado.
- `can_view_internal_document()` trata `Consolidado de agregadoras` como **caso especial**: exige publicación y reglas de visibilidad incluso para el manager; las descargas siguen una excepción equivalente. Otros controles distinguen `DRAFT`, `ARCHIVED`, sensibles, visibilidad `GLOBAL/CUSTOM/PRIVATE`, propietario y reglas específicas de cobranza recurrente.
- **Conclusión:** el piloto debe comparar por separado **capacidad de administrar** y **acceso a cada documento**. Sustituir `is_internal_document_admin()` por un `allow` global no puede eliminar estos filtros ni modificar quién visualiza el consolidado.

### A-02 — `module-access` puede aparentar enforcement que no existe

- `GET /users/<id>/module-access` usa `_get_latest_active_grants_by_action` y `_apply_module_access_override`; reporta `effective_allowed` con preferencia usuario/rol.
- `PUT /users/<id>/module-access` guarda grants y auditoría, pero declara que **no cambia enforcement legacy todavía**.
- La función de lectura revisa `is_active` y `deleted_at` pero **no filtra `starts_at`/`expires_at`, scope ni bloqueos innegociables**; prioriza el grant más reciente por usuario/rol, sin `deny` duplicado prevalente por capa.
- Tampoco combina automáticamente grants apuntados solo a `module_id`, porque recupera por `action_id` base.
- **Consecuencia:** su `effective_allowed` no debe mostrarse como permiso operativo vigente; usar “override configurado / previsualización” hasta resolverlo.

### A-03 — Grants con enforcement parcial en Tickets

- `backend/app/utils/tickets_maintenance_permissions.py::_has_active_user_grant` exige acción activa, user grant global, `is_active`, ausencia de borrado, tiempo actual entre `starts_at` y `expires_at`.
- `_effects_allow` hace prevalecer `deny` sobre `allow`; además `has_maintenance_coordination_permission` aplica exclusiones por rol/jefe y `can_pm_view`, y exige validaciones de alcance en el endpoint.
- **Consecuencia:** sustituirlo por el helper genérico sin paridad puede **otorgar o quitar acceso real**. Congelar como referencia hasta tests de regresión.

### A-04 — Sucursales no son intercambiables

- `pm_routes.py::_verificar_permiso_sucursal` aplica reglas distintas para jefe regional y lectores de mantenimiento.
- `inventarios.py::_resolve_inventory_read_sucursal_ids` y `_require_inventory_movement_write` distinguen `SR_MANTENIMIENTO`, `AUX_MANTENIMIENTO`, roles globales y sucursal principal.
- `tickets_maintenance_permissions.py` mantiene permisos de coordinación separados de ejecución/cierre; `ticket_filters.py` resuelve audiencias más complejas.
- **Consecuencia:** los grants por sucursal deben comprobar intersección con las autorizaciones del dominio, no sustituir el filtro de filas/documentos.

### A-05 — Excepciones duras por identidad o ubicación

- `backend/app/utils/maintenance_regional_lead.py` reconoce explícitamente a la cuenta de jefe regional de Mantenimiento y cruza sus sucursales asignadas con una lista permitida.
- `internal_documents_access.py` contiene excepción administrativa por `username`.
- `ticket_routes.py::_es_admin_o_corporativo` admite sucursales corporativas como señal de privilegio para ciertos flujos.
- **Consecuencia:** son candidatos a roles o grants específicos, **pero retirarlos sin captura previa de comportamiento sería riesgoso**.

### A-06 — Usuarios, auditoría y modos

- `UserORM` del código leído no declara `is_active`; `get_user_module_access` lo obtiene con `getattr(..., True)`. No diseñar un hard stop inexistente sin definir una migración y el proceso de desactivación.
- Ya existe `PermissionGrantAuditLogORM`; no duplicar tabla de auditoría por cada módulo.
- Reglas `allow`/`deny` y scopes de `PermissionGrantORM` existen como capacidad estructural; **no implican soporte completo en el resolutor**.
- El contrato técnico propone modos `observability_only`, `compare_only`, `grants_overlay`, `grants_enforced`; no se observó una configuración general de enforcement por módulo. No suponer implementado solo porque esté documentado.

### A-07 — Catálogo incompleto respecto a Suite actual

- El seed inicial fija 11 módulos, pero existen módulos operativos posteriores y endpoints no cubiertos necesariamente por el mapeo high-risk.
- **Consecuencia:** matriz bidireccional “todos los usuarios con acceso” será exacta solo para acciones verificadas; indicar cobertura parcial hasta mapear cada dominio.

### A-08 — Ruta documental transversal Aperturas → Nube; acción efectiva de Aperturas (mapeo observado en producción, 2026-10-22)

- Consulta `permission_route_map` agrupada por `permission_modules.key='internal_documents'`: **11 rutas activas**, 0 inactivas, de las cuales **10** están asociadas a `internal_documents.manage` y **1** a `openings.manage`.
- La migración `backend/migrations/versions/7b8c9d0e1f2a_seed_permission_route_map_high_risk.py` documenta explícitamente esa fila cruzada:
  - `POST /api/openings/<int:opening_id>/tasks/<int:task_id>/documents/upload`
  - `endpoint_function=upload_task_document`
  - `module_key=internal_documents` (etiqueta funcional documental / Nube)
  - `action_full_key=openings.manage` (autorización efectiva de Aperturas)
  - `current_guard=_require_openings_admin`
  - `source_file=backend/app/routes/openings_routes.py`
- Inspección de `backend/app/routes/openings_routes.py::upload_task_document`: efectivamente llama a `_require_openings_admin()` y después realiza la carga documental mediante `create_warehouse_document_upload`. **No usa `require_internal_document_manager()`**.
- **No es evidencia de IDs corruptos ni error de autorización:** esta asociación es explícita en el seed y representa un proceso transversal. **Sí es una ambigüedad para el diseño futuro** si se usa `route_map.module_id` como acción autorizante sin comprobar `action.module_id`.
- Requisito del resolvedor y de la matriz bidireccional: distinguir **módulo donde se agrupa/expone la funcionalidad** vs **acción y módulo de autorización**, y resolver el guard real de la ruta. Un `internal_documents.manage` no debe otorgar automáticamente subida documental de Aperturas. Tampoco un `openings.manage` debe equivaler a administrar toda Nube.
- Las **21 rutas HTTP** del blueprint `internal_documents_routes.py` no quedan automáticamente cubiertas por estas 11 filas, porque una es de Aperturas y el catálogo fue sembrado para rutas de riesgo revisadas, **no para cobertura exhaustiva de cada GET/acción**. Antes de activar permisos, verificar el mapa por `method+route+endpoint` y no inferir cobertura global por conteo.
- **Seguimiento:** censo global efectuado; se encontraron 2 asociaciones adicionales (`reports` → `users.manage`), descritas en A-09. No modificar mapeos históricos sin decidir su semántica ni cambiar el guard real.

### A-09 — Censo global de rutas transversales; legacy permisos mal agrupados bajo Reportes

**Consulta productiva de 2026-10-22:** solo **3 filas activas** de `permission_route_map` tienen `route_map.module_id != action.module_id`.

| Módulo de agrupación | Acción / módulo autorizante | Método | Ruta |
| --- | --- | --- | --- |
| `internal_documents` | `openings.manage` / `openings` | POST | `/api/openings/<int:opening_id>/tasks/<int:task_id>/documents/upload` |
| `reports` | `users.manage` / `users` | POST | `/api/permisos/asignar` |
| `reports` | `users.manage` / `users` | DELETE | `/api/permisos/eliminar` |

**Cotejo del código del repositorio (no se ejecutaron escrituras):**
- En `backend/migrations/versions/7b8c9d0e1f2a_seed_permission_route_map_high_risk.py`, el seed coloca expresamente ambas rutas `/api/permisos` bajo `module_key='reports'`, pero con `action_full_key='users.manage'` y `current_guard='_require_permisos_admin'`. El comentario original para ambas indica `module_label=General / Otro`, por lo que **Reportes es una clasificación de conveniencia heredada**, no su dominio funcional.
- En `backend/app/routes/permisos_routes.py`, `asignar_permiso` y `eliminar_permiso` efectivamente invocan `_require_permisos_admin()` (rol actual desde `UserORM`; roles `ADMIN`, `ADMINISTRADOR`, `SUPER_ADMIN`) y crean/eliminan filas de la tabla `usuarios_permisos`.
- Por ello, **no hay evidencia de bypass actual por esta divergencia del catálogo**. El riesgo futuro sería convertir `reports` en puerta de entrada a `users.manage` o decidir privilegios basándose solo en `permission_route_map.module_id`.
- **Política de compatibilidad:** `users.manage` representa ahora operaciones administrativas de permisos legacy; la etiqueta del catálogo debe corregirse semánticamente en una etapa posterior y separarse de la autorización de `reports`. Evaluar si conviene acción granular `users.permissions_manage` antes de migrar, sin crearla todavía ni reescribir migraciones históricas ya aplicadas.
- **Restricción:** no reasignar estas dos rutas mediante SQL manual ni cambiar guards durante Fase A. Cualquier cambio futuro de mapeo almacenado deberá contar con migración Alembic versionada y pruebas que preserven el acceso administrativo actual.
- **Límite de la comprobación:** el censo cubre las filas `is_active=true` presentes en `permission_route_map`; no demuestra que todo endpoint web tenga un mapeo. Faltan cobertura de lectura, scopes y paridad por registro del piloto.

### A-10 — Cobertura GET del piloto: 11 rutas sin mapeo (2026-10-22)

La prueba en producción comparó **todos los endpoints Flask** con prefijo `/api/internal-documents` frente a los registros `permission_route_map` activos del mismo prefijo, mediante pares `(method, route)`:

- `RUTAS_FLASK=21`; `RUTAS_MAPEADAS=10`; `SIN_MAPEO=11`.
- **Las 11 rutas sin mapear usan GET; los 10 métodos de escritura sí están mapeados** para este blueprint. No son 11 rutas abiertas: todas las rutas del blueprint usan `@jwt_required()` y varias revalidan permisos por documento.
- La fila transversal `POST /api/openings/.../documents/upload` (A-08) **no pertenece** al prefijo de este conteo: no confundir 11 asociaciones de `module_key=internal_documents` con 11 rutas efectivas del blueprint Nube.

| GET sin mapeo | Guard/filtro real en código | Clase recomendada para futura observabilidad |
| --- | --- | --- |
| `/api/internal-documents/access` | JWT; contexto actual; devuelve `can_manage` real | Acceso al módulo / capacidades de sesión |
| `/api/internal-documents/categories` | JWT; catálogo de categorías activas | Lectura de categorías; no administrar documentos |
| `/api/internal-documents` | JWT; managers y no managers filtran diferente; no managers requieren `can_view_internal_document` y solo publicados; managers distintos de ADMICORP excluyen consolidado en listado | Listado con alcance por objeto y filtro especial |
| `/api/internal-documents/by-link` | JWT; contexto y relación activa; visibilidad según `can_manage or can_view_internal_document` | Listado por vínculo; **riesgo de diferencia frente a lectura por documento**, revisar |
| `/api/internal-documents/<int:document_id>` | JWT + `require_internal_document_view_access` | Lectura de detalle, reglas por documento |
| `/api/internal-documents/<int:document_id>/versions` | JWT + view access; no manager ve solo versión vigente no oculta | Lectura de versiones restringida por contexto |
| `/api/internal-documents/<int:document_id>/links` | JWT + view access | Lectura de vínculos, scope documental |
| `/api/internal-documents/<int:document_id>/external-resources` | JWT + view access | Lectura de recursos, scope documental |
| `/api/internal-documents/<int:document_id>/download` | JWT + `require_internal_document_download_access` | **Descarga actual**, requiere `can_download`, no equivale a ver |
| `/api/internal-documents/<int:document_id>/versions/<int:version_id>/download` | JWT + `can_download_historical_internal_document_version` (manager) | **Descarga histórica**, permiso privilegiado específico |
| `/api/internal-documents/<int:document_id>/audit` | JWT + `require_internal_document_audit_access` (manager) | **Consultar auditoría**, permiso privilegiado específico |

**Hallazgo de paridad por investigar (no implica exposición productiva confirmada):** `list_internal_documents_by_link` incluye documentos cuando `can_manage_internal_documents(context)` es verdadero **sin ejecutar `can_view_internal_document(document, context)`**. Para el documento especial `Consolidado de agregadoras`, el helper de visualización exige reglas explícitas incluso al manager; el listado general lo oculta a managers distintos de ADMICORP. En consecuencia, **la misma metadata podría ser visible por `/by-link`** si el documento tiene un vínculo activo y un manager conoce sus parámetros. Las descargas y el detalle mantienen checks propios. Esto requiere una **prueba de regresión con mocks/fixtures en entorno de tests** y luego una decisión separada sobre una corrección, no intervención apresurada sobre producción.

**Tests encontrados:** `backend/tests/utils/test_internal_documents_agregadoras_access.py` cubre `can_view/can_download` de ADMICORP, SISTEMAS y otros. `backend/tests/routes/test_internal_documents_agregadoras_visibility.py` cubre que el listado raíz excluye el consolidado para manager no ADMICORP. **No se encontró una prueba equivalente del handler `/by-link` en los tests revisados.** Antes de migrar, probar que todas las rutas de metadatos del documento especial respetan el alcance explícito.

**Regresión aislada ejecutada — 2026-10-23:** PR draft [#1062](https://github.com/VladRoJa/sistematicketsultra/pull/1062), en rama independiente, agrega `test_by_link_does_not_expose_agregadoras_metadata_to_sistemas` a `backend/tests/routes/test_internal_documents_agregadoras_visibility.py` y un workflow CI específico (solo código de tests/CI). Simula un documento publicado, sensible y `CUSTOM` con vínculo general activo, visible solo para ADMICORP, y un contexto `SISTEMAS` autorizado a administrar Nube. El helper real `can_manage_internal_documents` devuelve **True**, mientras `can_view_internal_document` devuelve **False**. En [CI 39979436595](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39979436595) la prueba llegó a la aserción `items == []` y **falló** porque `/by-link` devolvió `{'id':900,'title':'Consolidado de agregadoras'}`. Es un documento ficticio y el query fue simulado: **confirma la divergencia lógica y potencial exposición de metadatos en el handler bajo las condiciones del test, no una filtración observada en registros de producción**. El primer intento [CI 39979259790](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39979259790) tuvo un error de mock `_FakeColumn.is_`; se corrigió solo el mock antes de repetir. **No se modificó la autorización productiva**. PR #1062 debe seguir en draft/Rojo hasta resolver el cambio por separado con revisión del alcance documental.

**Corrección propuesta y validada en rama, NO desplegada — 2026-10-23:** PR [#1062](https://github.com/VladRoJa/sistematicketsultra/pull/1062) permanece **draft**, sin merge. Se cambió exclusivamente la condición de `list_internal_documents_by_link` de `can_manage or can_view_internal_document(document, context)` a `can_view_internal_document(document, context)`. La regresión previamente ROJA ahora es **verde** en [CI #39980139059](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39980139059); el workflow ampliado ejecutó **4 tests PASS** (regresión `/by-link`, listado general y helpers de visibilidad/descarga) en [CI #39980308075](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39980308075). Es evidencia de regresión unitaria simulada, no QA de integración contra documentos productivos. Las restricciones de acceso existentes permanecen efectivas en producción hasta que el PR se fusione y despliegue por el proceso normal.

**Escenarios mínimos de comparación para Fase B:** (1) sesión válida vs inválida, (2) lectura de documento publicado permitido, (3) lectura denegada de documento sensible, (4) SISTEMAS / ADMICORP vs otro rol ante el consolidado, (5) `view=true/download=false`, (6) versiones históricas vs versión actual, (7) auditoría solo manager, (8) listado general vs `/by-link` para un mismo documento, (9) borradores/archivados/visibilidad custom. **Resultado esperado:** el resolvedor podrá describir el acceso sin alterar los guards y sin fusionar todos los GET en un solo booleano `internal_documents.view`.

## 5. Política de paridad antes de activar permisos

1. Para cada acción, documentar el guard real, alcance y restricciones adicionales. Si no puede mapearse con fidelidad, **no migrar**.
2. Mantener autorización productiva intacta mientras el resolutor nuevo corra en `compare_only`.
3. Comparar `user_id + action_key + branch_id/contexto`, registrando resultado legacy y nuevo. No tratar una operación autorizada globalmente como idéntica a la misma operación limitada a una sucursal.
4. Resolver discrepancias explícitamente; nunca convertir una simplificación en elevación de privilegios silenciosa.
5. Preparar regresiones automatizadas **permitido / denegado / fuera de alcance**, más fechas y precedencia para grants; conservar rutas de reversión.
6. Activar **una sola acción** de Nube Corporativa tras paridad aprobada. Retirar guard legacy equivalente **solo después** de comprobar cobertura sin perder restricciones por documento.
7. Reutilizar el mismo resolutor para pantalla por usuario, por módulo, por acción y por rol. Mostrar si es **diagnóstico**, **comparación** o **enforcement real**.

## 5.1. Censo agregado de roles reales — 2026-10-22

Consulta `SELECT UPPER(TRIM(COALESCE(rol,''))), COUNT(*) FROM users GROUP BY 1` ejecutada en producción; **70 usuarios distribuidos en 17 roles** (coincide con las 70 cuentas de la comparación de Nube Corporativa). La consulta no incluyó nombres de usuario ni asignaciones individuales.

| Rol | Cantidad |
| --- | ---: |
| `GERENTE` | 26 |
| `AUX_MANTENIMIENTO` | 11 |
| `LECTOR_GLOBAL` | 11 |
| `GERENTE_REGIONAL` | 5 |
| `RECURSOS HUMANOS` | 3 |
| `SR_MANTENIMIENTO` | 3 |
| `ADMINISTRADOR` | 1 |
| `COMPRAS` | 1 |
| `COMUNICACION Y SERVICIOS` | 1 |
| `COORDINADOR_MANTENIMIENTO` | 1 |
| `FINANZAS` | 1 |
| `GERENCIA DEPORTIVA` | 1 |
| `MANTENIMIENTO` | 1 |
| `MARKETING` | 1 |
| `SISTEMAS` | 1 |
| `TECNICO` | 1 |
| `TIENDA` | 1 |
| **Total** | **70** |

**Interpretación para la migración:**
- No eliminar ni fusionar roles por frecuencia. Un rol con un solo usuario puede representar una responsabilidad laboral válida.
- Diferenciar puestos (`GERENTE` / `GERENTE_REGIONAL`) de permisos puntuales y scopes; una coincidencia parcial de permisos no implica que sean el mismo rol.
- Este censo **no describe permisos efectivos**, solamente `users.rol`; tampoco acredita que las cuentas estén habilitadas o que representen personas diferentes.
- El catálogo actual de 11 módulos/40 acciones no equivale al censo de roles: son dimensiones diferentes.
- **ACL departamental verificada:** una sola asignación en `usuarios_permisos` a `departamento_id=1`, `es_admin=false`, cuyo titular tiene rol `COORDINADOR_MANTENIMIENTO` (consultas agregadas 2026-10-22). **Pendiente:** verificar migraciones/esquema. Los operadores están censados en la sección siguiente.

## 5.2. Censo agregado de operadores Warehouse y Planning — 2026-10-22

Consulta SQL de solo lectura sobre `warehouse_operators` y `planning_operators`; no se devolvieron identidades. La consulta acredita los valores de las flags, no que ambos operadores sean la misma persona ni que todos los endpoints compartan idénticos checks.

| Módulo | Operadores registrados | Estado | Capacidades habilitadas |
| --- | ---: | --- | --- |
| Warehouse | **1** | El modelo no declara `is_active` | `can_view=1`, `can_upload=1`, `can_archive=0` |
| Planning | **1** | **1 activo** | `can_view=1`, `can_edit=1`, `can_submit=1`, `can_approve=1`, `can_publish=1`, `can_configure_model=1` |

**Decisiones de compatibilidad:**
- Mantener ambas asignaciones y todas las flags sin alterarlas en la Fase A. `warehouse_access.py` distingue `require_warehouse_view`, `require_warehouse_upload` y `require_warehouse_archive`, y `planning_access.py` utiliza operador activo y flags independientes.
- No inferir acceso universal por el rol principal del operador, ni crear roles combinados para reflejar sus flags.
- **No eliminar `warehouse_operators` ni `planning_operators` al introducir el resolutor:** primero demostrar paridad con casos permitidos y denegados y comprobar todas las rutas consumidoras.
- **No interpretar el `can_archive=0` de Warehouse como permiso para archivar**, aunque cualquier futuro grant `allow` global exista; el hard stop y la política de precedencia requieren aprobación explícita al migrar esa acción.
- La consulta agregada de `usuarios_permisos` ya se recibió; ver sección 5.3. No se alterarán flags ni asignaciones existentes.

## 5.3. ACL departamental legacy — 2026-10-22

Consulta agrupada de `usuarios_permisos` en producción devolvió únicamente:

| departamento_id | es_admin | Asignaciones | Usuarios distintos |
| ---: | --- | ---: | ---: |
| 1 (Mantenimiento) | `False` | 1 | 1 |

- Esta entrada **no es un permiso de administrador**. La columna `es_admin=false` corresponde a esta ACL y no determina el conjunto completo de privilegios del usuario.
- `backend/app/utils/pm_permissions.py::has_scoped_maintenance_read_grant()` consulta expresamente `usuarios_permisos` con `departamento_id=1` y `es_admin=False` para habilitar lectura de PM a los roles `COMPRAS` o `COORDINADOR_MANTENIMIENTO`.
- Una segunda consulta agregada confirmó **`COORDINADOR_MANTENIMIENTO | 1`**. Esta combinación cumple las condiciones de rol + departamento + `es_admin=False` verificadas por `has_scoped_maintenance_read_grant()`, por lo que corresponde al permiso individual de **lectura de PM**, no al de ejecución, validación o configuración. Esto no acredita todavía la intersección precisa de sucursales ni la identidad de los titulares de los dos `permission_grants` de Tickets.
- Esta ACL debe conservarse y contrastarse con los accesos reales a PM durante la migración.

## 5.4. Estado Alembic de producción — 2026-10-22

- Reporte entregado: `docker compose exec -T backend flask db current` → **`j22c10202622 (head)`**.
- Verificación en `main`: existe `backend/migrations/versions/j22c10202622_inventario_movimientos_anulacion.py`, con `revision = "j22c10202622"` y `down_revision = "i22c10202622"`. La migración afecta la auditoría de anulación en `movimientos_inventario`; **no introduce ni cambia los permisos globales**.
- **Alcance de la prueba:** la base del contenedor reporta estar en el head conocido por su Alembic. No se ejecutó una comparación exhaustiva de tablas/constraints contra SQLAlchemy ni un `flask db upgrade`. Por tanto, no confundir `head` con auditoría integral de esquema.

## 6. Evidencia aún pendiente para cerrar Fase A

Estos puntos necesitan información del servidor o revisión de código adicional. **No constituyen autorización para consultar datos personales sin necesidad, modificar registros ni ejecutar SQL de escritura.**

- [x] Reconocer todas las familias de fuentes de autorización en código (`rol`, `usuarios_permisos`, `permission_grants`, operadores, filtros por sucursal, guardias por objeto).
- [x] Identificar y documentar riesgos prioritarios y el piloto.
- [x] Verificar que el catálogo/observabilidad y el endpoint de edición de módulos no constituyen enforcement universal.
- [x] **Grants vigentes identificados (consultas agregadas, 2026-10-22):** solo se devolvieron **2 grants** (`principal_type=user`, `effect=allow`, `scope_type=global`, estado `current`), uno para `tickets.maintenance.coordinate` y uno para `tickets.maintenance.read_assigned_only`. **Ningún grant vigente corresponde a Nube Corporativa**. Ambos deben conservarse intactos; su impacto operativo sigue subordinado a las condiciones del guard real. El scope `global` del grant no exime restricciones de sucursal ni concede por sí solo acceso de escritura. **Pendiente:** revisar operadores/ACL y confrontar esquema/migraciones aplicadas con producción. El censo agregado de 17 roles y 70 cuentas ya está documentado abajo.
- [x] Censados operadores Warehouse y Planning en producción: 1 operador de Warehouse con lectura/subida pero sin archivo, y 1 operador activo de Planning con las 6 capacidades habilitadas. Sus identidades no están identificadas por estos agregados.
- [x] Censo agregado `usuarios_permisos`: departamento 1 / `es_admin=false` / una asignación / un usuario.
- [x] Confirmado por consulta agregada que la única ACL departamental pertenece al rol `COORDINADOR_MANTENIMIENTO` y satisface la condición legacy de lectura de PM.
- [x] **Revisión Alembic cotejada:** `flask db current` en producción reportó `j22c10202622 (head)` el 2026-10-22; el mismo identificador aparece en `main` del repositorio (`backend/migrations/versions/j22c10202622_inventario_movimientos_anulacion.py`, `down_revision=i22c10202622`). Esto coteja revisión y código, **no** prueba paridad física total del esquema, unicidad de heads en todos los entornos ni accesos por sucursal.
- [ ] Revisar escenarios de alcance por sucursal y documentar las diferencias conocidas del piloto antes de enforcement.
- [~] Inventariadas por código las **21 rutas HTTP** de Nube y los controles de escritura/lectura/descarga/auditoría, con excepción especial de agregadoras. **Pendiente:** matriz exhaustiva ruta → decisión por contexto y tests de paridad; esta inspección no sustituye QA.
- [ ] Producir conjunto de escenarios de paridad de Nube Corporativa (rol SISTEMAS, ADMICORP, admin con otro usuario, usuario ordinario, documento sensible).
- [ ] Decidir con responsable operativo únicamente los accesos legacy contradictorios que supongan un cambio de política, no pedir autorización para cada refactor.
- [x] Censadas las **3 asociaciones transversales activas** del catálogo: 1 upload documental de Aperturas agrupado bajo Nube, y 2 altas/bajas de permisos departamentales (`users.manage`) agrupadas históricamente bajo Reportes. Guards efectivos cotejados en código, sin indicios de bypass y sin cambios de autorización.
- [x] **Cobertura Flask vs catálogo del blueprint Nube** cotejada: 21 rutas (10 mapeadas, 11 GET sin mapeo); se categorizó el guard real de cada GET y se documentó una potencial divergencia de metadata en `/by-link`, pendiente de prueba de regresión.
- [x] Ejecutar regresión aislada de `/by-link` con rol SISTEMAS y documento sensible CUSTOM: **ROJO confirmado en la aserción de metadatos**, CI #39979436595, PR draft #1062.
- [x] Corrección puntual de `/by-link` preparada en PR draft #1062: 4 tests PASS en CI #39980308075 (sin merge, sin despliegue ni cambios productivos).
- [ ] Obtener revisión/merge/deploy del PR #1062 por flujo normal y comprobar paridad para escenarios adicionales de rutas/documentos antes de activar resolver global.
- [ ] Marcar expresamente el alcance incompleto de módulos fuera del catálogo y plan de expansión.

### Consulta posterior de producción

El siguiente paso adecuado es **una única consulta agregada SELECT de solo lectura**, revisada de antemano, sobre distribución de permisos y grants actuales. No hacer dumps de usuarios, contraseñas, JWT ni payloads sensibles. Los resultados deben orientar los tests de paridad, no crear reglas productivas automáticamente.

## 7. Criterio de cierre de milestone A

Documento de compatibilidad completado con evidencia de código y agregados productivos, primer piloto delimitado, riesgos priorizados y diferencias conocidas aprobadas o clasificadas como bloqueos. **Esta versión abre Fase A pero no la cierra:** todavía falta el contraste con PostgreSQL y los escenarios de paridad de la Nube.

### Referencias del repositorio

- `docs/contratos/contrato de permisos globales.md`
- `docs/security/global_permissions_grants_technical_design.md`
- `docs/security/global_permissions_observability_v1_closure.md`
- `docs/security/permissions_high_risk_review_summary.md`
- `backend/app/models/permissions.py`
- `backend/app/models/user_model.py`
- `backend/app/models/permiso_model.py`
- `backend/app/routes/permissions_catalog_routes.py`
- `backend/app/routes/permisos_routes.py`
- `backend/app/utils/internal_documents_access.py`
- `backend/app/utils/pm_permissions.py`
- `backend/app/utils/tickets_maintenance_permissions.py`
- `backend/app/utils/maintenance_regional_lead.py`
- `backend/app/utils/planning_access.py`
- `backend/app/utils/warehouse_access.py`
- `backend/app/routes/inventarios.py`
- `backend/app/routes/pm_routes.py`
- `backend/app/routes/ticket_routes.py`
