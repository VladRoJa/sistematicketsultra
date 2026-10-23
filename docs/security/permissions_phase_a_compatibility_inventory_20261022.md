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

**Regresión aislada ejecutada — 2026-10-23 (antes de la corrección):** PR [#1062](https://github.com/VladRoJa/sistematicketsultra/pull/1062), en rama independiente, agrega `test_by_link_does_not_expose_agregadoras_metadata_to_sistemas` a `backend/tests/routes/test_internal_documents_agregadoras_visibility.py` y un workflow CI específico (solo código de tests/CI). Simula un documento publicado, sensible y `CUSTOM` con vínculo general activo, visible solo para ADMICORP, y un contexto `SISTEMAS` autorizado a administrar Nube. El helper real `can_manage_internal_documents` devuelve **True**, mientras `can_view_internal_document` devuelve **False**. En [CI 39979436595](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39979436595) la prueba llegó a la aserción `items == []` y **falló** porque `/by-link` devolvió `{'id':900,'title':'Consolidado de agregadoras'}`. Es un documento ficticio y el query fue simulado: **confirma la divergencia lógica y potencial exposición de metadatos en el handler bajo las condiciones del test, no una filtración observada en registros de producción**. El primer intento [CI 39979259790](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39979259790) tuvo un error de mock `_FakeColumn.is_`; se corrigió solo el mock antes de repetir. **En esta etapa RED no se modificó la autorización productiva**. Posteriormente, PR #1062 incorporó la corrección y se fusionó a `main` (véase siguiente párrafo).

**Corrección validada, fusionada y presente en el backend desplegado — 2026-10-23:** PR [#1062](https://github.com/VladRoJa/sistematicketsultra/pull/1062) fue integrado con squash commit `e27e63b77a8ce1f3afaefa079902c9e247ce31e9`. Se cambió exclusivamente la condición de `list_internal_documents_by_link` de `can_manage or can_view_internal_document(document, context)` a `can_view_internal_document(document, context)`. La regresión previamente ROJA ahora es **verde** en [CI #39980139059](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39980139059); el workflow ampliado ejecutó **4 tests PASS** (regresión `/by-link`, listado general y helpers de visibilidad/descarga) en [CI #39980308075](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39980308075). Es evidencia de regresión unitaria simulada, no QA de integración contra documentos productivos. El operador confirmó `git pull` y reconstrucción de `backend` en producción. Comprobación de código cargado dentro del contenedor con `inspect.getsource(list_internal_documents_by_link)` devolvió `NUEVA_VALIDACION = True`, `VALIDACION_ANTERIOR = False`, `QA_BY_LINK = PASS`: **verificado el código importado en una ejecución del contenedor**. Esto no sustituye pruebas HTTP de visibilidad con perfiles reales ni garantiza por sí solo que todos los workers activos respondan igual. No requirió migración Alembic.

**QA HTTP anónimo en producción — 2026-10-23:** se ejecutó `curl` sin JWT a `http://127.0.0.1:5000/api/internal-documents/by-link?entity_type=GENERAL` y el operador confirmó **HTTP 401**. Esto comprueba que la ruta rechaza una solicitud sin autenticación (junto con el código correcto cargado y las pruebas unitarias verdes). **No demuestra** el acceso/denegación real por visibilidad documental con sesión autenticada. Próximo chequeo de bajo riesgo: JWT válido + `entity_type` deliberadamente inválido debe devolver `400`, sin leer documentos.

**QA HTTP autenticado sin lectura documental — 2026-10-23:** desde sesión legítima de Suite Ultra se llamó a `GET /api/internal-documents/by-link?entity_type=INVALIDO` con el JWT de sesión sin imprimir el token. Resultado comunicado por operador: **HTTP 400**, esperado por `entity_type` inválido. Como el handler verifica `entity_type` antes de consultar `InternalDocumentORM`, demuestra que el request autenticado alcanzó validación de parámetros **sin ejecutar consulta de documentos**. No implica haber comprobado permisos de lectura por usuario ni por documento. Siguiente prueba acotada: ruta válida con `entity_key` de QA deliberadamente imposible, validando solo HTTP e inventario vacío, sin registrar contenido ni token.

**QA HTTP autenticado con filtro válido sin coincidencias — 2026-10-23:** el operador ejecutó desde Suite Ultra `GET /api/internal-documents/by-link?entity_type=GENERAL&entity_key=SUITE_ULTRA_QA_SIN_VINCULOS_20261023` usando el JWT de su sesión. Resultado reportado: **HTTP 200, `DOCUMENTOS=0`**. Confirma que el endpoint procesa parámetros válidos y devuelve lista vacía para este filtro; no prueba controles de visibilidad sobre documentos existentes, ni demuestra que la clave sea permanentemente inexistente. Con ello se completaron tres comprobaciones básicas HTTP: sin JWT → 401, JWT + tipo inválido → 400, JWT + filtro válido sin coincidencias → 200/0.

**QA paridad por perfil / documento privado ficticio — 2026-10-23:** el operador ejecutó dentro de `backend` un script que invoca `can_view_internal_document` sobre un `SimpleNamespace` publicado, no sensible y `PRIVATE` (id ficticio negativo, sin DB) con contextos ficticios de rol `SISTEMAS` y `GERENTE`. Obtuvo `SISTEMAS | CAN_VIEW=True`, `GERENTE | CAN_VIEW=False`. **PASS**: corrobora la política legacy de administrador documental para un documento ordinario privado y la denegación del gerente no propietario; **no** prueba HTTP ni permisos reales de otros perfiles/documentos. Pendiente comprobar la excepción de documento sensible `Consolidado de agregadoras` bajo visibilidad explícita simulada.

**QA de excepción de visibilidad sensible con fixture — 2026-10-23:** ejecutado por el operador dentro del backend sin acceso documental real: documento `PUBLISHED`, `CUSTOM`, `is_sensitive=True`, título `Consolidado de agregadoras`; helper de reglas CUSTOM simulado para permitir únicamente username `ADMICORP`. `can_view_internal_document` devolvió `ADMICORP=True`, `SISTEMAS_QA=False`, `GERENTE_QA=False` (**PASS**). Confirma que un manager `SISTEMAS` no salta la restricción especial de lectura en este helper, bajo la regla simulada. Quedan fuera de este caso la descarga actual y la descarga histórica (riesgo A-11).

**Escenarios mínimos de comparación para Fase B:** (1) sesión válida vs inválida, (2) lectura de documento publicado permitido, (3) lectura denegada de documento sensible, (4) SISTEMAS / ADMICORP vs otro rol ante el consolidado, (5) `view=true/download=false`, (6) versiones históricas vs versión actual, (7) auditoría solo manager, (8) listado general vs `/by-link` para un mismo documento, (9) borradores/archivados/visibilidad custom. **Resultado esperado:** el resolvedor podrá describir el acceso sin alterar los guards y sin fusionar todos los GET en un solo booleano `internal_documents.view`.

### A-11 — Riesgo de alcance en descarga de versiones históricas de documento sensible (revisión de código 2026-10-23)

- Tras el QA **PASS** de `can_view_internal_document` para `Consolidado de agregadoras` con visibilidad `CUSTOM` simulada (ADMICORP=True, SISTEMAS=False, GERENTE=False), se revisó el helper de descarga de versiones.
- `backend/app/utils/internal_documents_access.py::can_download_historical_internal_document_version(document, context)` **devuelve únicamente** `can_manage_internal_documents(context)`; ignora su parámetro `document` y no llama a `can_view_internal_document` ni a `has_document_visibility_access`.
- `backend/app/routes/internal_documents_routes.py::download_internal_document_version` verifica el documento y llama a ese helper; si devuelve True, busca la versión del documento y pasa al envío del archivo. No se observó en ese handler otra comprobación de visibilidad explícita del documento.
- **Inconsistencia confirmada a nivel de helpers mediante fixture (2026-10-23):** documento ficticio `PUBLISHED/CUSTOM/is_sensitive=True`, título `Consolidado de agregadoras`, visibilidad CUSTOM simulada para permitir exclusivamente a `ADMICORP`. Resultados en columnas `VIEW/DOWNLOAD/HISTORICAL`: `ADMICORP=True/True/True`, `SISTEMAS_QA=False/False/True`, `GERENTE_QA=False/False/False`. **PASS como reproducción del fallo de política de autorización**: `SISTEMAS` es admitido por el helper de descarga histórica aunque no puede ver ni descargar la versión actual. No hubo requests HTTP, documentos ni ficheros reales; el alcance en producción depende de documentos y versiones existentes e identificadores conocidos.
- **Superficies relacionadas:** este helper también alimenta `list_internal_document_versions` (visibilidad y detalle de versiones) y `build_internal_document_capabilities` (flag `can_download_historical_versions` enviado a la UI), además del endpoint `download_internal_document_version` (descarga del archivo). Corregir un solo guard de ruta sin revisar esos usos dejaría discrepancias funcionales.
- **Política de seguridad para corrección aislada:** conservar el requisito de `can_manage_internal_documents` para históricos, pero exigir la regla explícita de **descarga** del consolidado mediante `can_download_internal_document(document, context)`; mantener el comportamiento actual de managers sobre documentos ordinarios. Antes de cambiar el helper, crear un test de regresión RED en PR separado; después un cambio mínimo y CI GREEN, sin migraciones. Revisar asimismo que no se autorice descarga histórica solo por permiso de lectura.

**Seguimiento de la corrección A-11 — 2026-10-23:** PR [#1067](https://github.com/VladRoJa/sistematicketsultra/pull/1067) contiene exclusivamente `backend/app/utils/internal_documents_access.py` (helper de históricos), fixture de regresión y workflow. Confirmado **RED** por aserciones de autorización: [CI #39999421770](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39999421770), **2 fallos esperados / 5 PASS**; confirmado **GREEN** tras cambio mínimo: [CI #39999587923](https://github.com/VladRoJa/sistematicketsultra/actions/runs/39999587923), **7/7 PASS**. Nueva condición: sigue siendo obligatorio ser manager documental; para el consolidado especial publicado también exige `has_document_visibility_access(..., action="download")`. No depende de `current_version_id` y conserva gestión de versiones históricas de otros documentos. **Estado: PR #1067 fusionado a `main` con squash commit `df035eb02f4833dc77a4e67236472b5f5948b963` el 2026-10-23; backend posteriormente reconstruido y QA de código importado `QA_A11=PASS` reportado por el operador.** La corrección y las pruebas no son evidencia de descarga real o incidente de explotación. Bloque A-11 finalizado: próxima etapa de Fase A es completar la matriz de paridad de permisos restante, evitando reabrir la corrección salvo nueva evidencia.

**QA de despliegue A-11 — 2026-10-23:** usuario reportó `A11_CODIGO_DESPLEGADO = True` y `QA_A11 = PASS` tras reconstruir backend. El chequeo inspeccionó el código importado dentro del contenedor para confirmar presencia de `can_manage_internal_documents(context)` y `action="download"` en `can_download_historical_internal_document_version`. Combinado con CI #39999587923 (**7/7 PASS**) y merge #1067 (`df035eb02f4833dc77a4e67236472b5f5948b963`), se da **por cerrado el bloque correctivo A-11**. Esta evidencia **no** implica haber verificado acceso HTTP real por documento, explotación histórica, ni cobertura completa del sistema de permisos. **Fase A NO se cierra**, y no se ha activado ningún resolvedor global.


### A-12 — Auditoría del consolidado: corrección fusionada y QA productivo PASS

**Revisión estática del código en main — 2026-10-23.** `backend/app/utils/internal_documents_access.py::can_view_internal_document_audit(document, context)` devuelve exclusivamente `can_manage_internal_documents(context)`, sin revisar `document` ni `can_view_internal_document`. `require_internal_document_audit_access` llama a ese helper; `GET /api/internal-documents/<int:document_id>/audit` lo ejecuta después de resolver el documento, sin un `require_internal_document_view_access` adicional.

La respuesta de auditoría serializa `old_value_json`, `new_value_json`, `metadata_json`, `actor_user_id`, `ip_address` y `user_agent` (`_serialize_audit_log`). Por tanto, **bajo la regla CUSTOM simulada del caso A-11**, un contexto administrador `SISTEMAS` puede quedar denegado para lectura del consolidado pero autorizado por el helper de auditoría del mismo documento. Es una **divergencia lógica verificable por inspección**, no prueba de petición HTTP ni de lectura real de auditoría. No conocemos el contenido de logs productivos ni se consultaron.

**Política aprobada por el responsable operativo, 2026-10-23:** la auditoría del consolidado exige privilegio de administrador **y** visibilidad explícita (`view`) de ese documento; `SISTEMAS` sin `view` no debe leer su auditoría. Los administradores conservan la lectura de auditoría sobre documentos ordinarios. Los fixtures simulan log y perfiles, nunca acceden a datos reales.

**Implementación aislada en PR [#1074](https://github.com/VladRoJa/sistematicketsultra/pull/1074), FUSIONADO A `main` con squash commit `38dadf38e49f1a2f68b8a1cd321086f365bbb192` el 2026-10-23; PENDIENTE DE DESPLIEGUE:** solo cambia `backend/app/utils/internal_documents_access.py::can_view_internal_document_audit()`: exige primero `can_manage_internal_documents(context)`; si el documento es el consolidado especial, además `can_view_internal_document(document, context)`; en otros documentos mantiene retorno manager. Endpoint `/audit`, serializador y capacidades ya invocan el helper.

**RED→GREEN verificado con GitHub Actions:** [RED #40005867664](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40005867664) obtuvo **3 fallos esperados y 9 PASS**, incluyendo test de handler audit (simulado: HTTP 200 indebido frente a 403 esperado); [último GREEN A-12 #40006216745](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40006216745) **12/12 PASS**; [regresión A-11 #40006216811](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40006216811) **7/7 PASS**. Es evidencia de tests aislados, no inspección de auditoría en producción. **Despliegue confirmado por el operador y QA funcional de helper en contenedor (2026-10-23):** tras `git pull` y reconstrucción de backend se evaluó el helper con contextos simulados `ADMICORP`, `SISTEMAS_QA`, `GERENTE_QA` y visibilidad CUSTOM ficticia. Resultado `A12_RESULTADOS=[True, False, False]`, `QA_A12=PASS`. Con CI A-12 12/12 PASS y A-11 7/7 PASS, **el bloque A-12 queda cerrado**. El QA no consultó logs o documentos reales ni verifica todas las rutas HTTP productivas. No se requieren migraciones. A-13 permanece como tema independiente.

### A-13 — Listado general: PR #1077 fusionado, validación operativa afirmativa (2026-10-23)

En `backend/app/routes/internal_documents_routes.py::list_internal_documents`, para administradores que no son `ADMICORP`, el filtro preventivo es `InternalDocumentORM.title != "Consolidado de agregadoras"`. En cambio, `_document_is_agregadoras_consolidado` normaliza el título (`strip().upper()`) antes de aplicar la política especial.

**Riesgo condicional:** si existiese un registro cuyo título difiera en mayúsculas, espacios u otra variación que el helper sí reconoce, el listado general de un administrador podría omitir la exclusión exacta y serializar metadatos sin llamar a `can_view_internal_document`. No se ha comprobado que existan variantes en producción ni se ha consultado la tabla. La ruta `/by-link` sí usa `can_view_internal_document` por elemento después del PR #1062.

**Prueba RED→GREEN completada en PR [#1077](https://github.com/VladRoJa/sistematicketsultra/pull/1077), fusionado por squash a `main` el 2026-10-23 (commit `ebb9e9080fb76d98696b451c429610701f43a779`), con validación operativa afirmativa posterior: ** se añadió test de listado manager con títulos canónico, MAYÚSCULAS y espacios periféricos y cálculo de `total`/paginación en un fake ORM evaluando SQLAlchemy sobre SQLite **en memoria**, sin BD ni documentos productivos. [RED limpio CI #40008420077](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40008420077): 4 aserciones fallaron por documentos indebidamente incluidos y total incorrecto, 14 tests previos pasaron. Cambio único funcional en `list_internal_documents`: filtro SQL `upper(trim(title)) != AGREGADORAS_CONSOLIDADO_TITLE`, antes de count/offset/limit; se actualizó test previo que asumía formato literal del SQL. [Último GREEN A-13 CI #40009002764](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40009002764): **18/18 PASS**; [A-12 #40009002774](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40009002774) 12/12, [A-11 #40009002738](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40009002738) 7/7, [A-10 `/by-link` #40009002814](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40009002814) 7/7, todos GREEN. `ADMICORP` y documentos ordinarios conservan su listado. **Límite explícito:** comprobadas variantes de mayúsculas y espacios ordinarios; TRIM en SQL no implica equivalencia perfecta para todos los caracteres Unicode que pueda eliminar Python `.strip()`. No se comprobó presencia de variantes en registros reales ni se afirma exposición productiva.


**Diagnóstico automatizado A-12/A-13 — 2026-10-23:** PR DRAFT [#1072](https://github.com/VladRoJa/sistematicketsultra/pull/1072), exclusivo de fixtures y workflow, ejecutó [GitHub Actions #40004028928](https://github.com/VladRoJa/sistematicketsultra/actions/runs/40004028928): **3 fallos de aserción deliberados y 7 tests previos PASS** (no fallos de instalación ni de mock).
- **A-12 helper:** SISTEMAS con documento de consolidado `CUSTOM` ficticio ⇒ `VIEW=False`, pero `AUDIT=True` cuando el contrato propuesto esperaría `False`.
- **A-12 handler:** con Flask `test_request_context` y log falso, endpoint de auditoría de consolidado restringido respondió **200** donde el contrato propuesto esperaría **403**.
- **A-13 listado:** título ficticio `CONSOLIDADO DE AGREGADORAS` (mayúsculas), que el helper especial reconoce pero el SQL `title != "Consolidado de agregadoras"` no excluye, produjo **total=1**, donde el contrato propuesto esperaba **0**.
**Alcance:** resultado de simulación; sin afirmar que exista título variante, contenido de auditoría expuesto o acceso no autorizado en producción. **PR #1072 permanece DRAFT y ROJO, NO fusionar**, como evidencia original. A-12 fue aprobado, fusionado y desplegado vía PR #1074; A-13 se corrigió en PR #1077 con CI GREEN y ya se fusionó a `main` (validación operativa afirmativa posterior).

**Cierre operativo A-13 — 2026-10-23:** el operador respondió «sí bien» al bloque propuesto de `git pull --ff-only`, reconstrucción backend e inspección de fuente del filtro A-13. Se considera **confirmación operativa afirmativa** del bloque; la salida de terminal específica no se compartió. No se inventan valores de `A13_CODIGO_DESPLEGADO` / `QA_A13`, ni se afirma verificación HTTP de documento sensible existente. Se mantiene evidencia CI GREEN del PR #1077 (18/18 A-13, 12/12 A-12, 7/7 A-11, 7/7 by-link). No se vuelve a intervenir este bloque salvo nueva evidencia.

### A-14 — Matriz de los 21 handlers Flask frente a autorización legacy (revisión de código 2026-10-23)

Esta matriz **no es el catálogo `permission_route_map`** ni afirma cobertura del resolvedor global. Es una extracción de `@internal_documents_bp.route` y de sus guards reales de `backend/app/routes/internal_documents_routes.py` en `main`. Prefijo común: `/api/internal-documents`. **Todos los 21 handlers usan `@jwt_required()`.** Se mantienen los 10 métodos de escritura mapeados y los 11 GET sin mapeo observados en producción el 2026-10-22 (A-10); **no se recontó `permission_route_map` en producción hoy**.

| # | Método y ruta (sufijo del prefijo) | Función Flask | Guard / política de autorización real |
| ---: | --- | --- | --- |
| 1 | GET `/access` | `internal_documents_access` | JWT + contexto; devuelve capacidad de manager |
| 2 | GET `/categories` | `list_internal_document_categories` | JWT; catálogo activo sin guard adicional por rol |
| 3 | GET `/` | `list_internal_documents` | JWT; administradores y otros tienen ramas separadas; no administradores con filtro por `can_view_internal_document`; ver A-13 para exclusión de consolidado por título |
| 4 | GET `/<document_id>` | `get_internal_document_detail` | JWT + `require_internal_document_view_access`; incluye datos administrativos solo cuando `can_view_internal_document_audit` |
| 5 | POST `/` | `create_internal_document` | JWT + `require_internal_document_manager` |
| 6 | PATCH `/<document_id>` | `update_internal_document_metadata` | JWT + `require_internal_document_manager` |
| 7 | POST `/<document_id>/publish` | `publish_internal_document` | JWT + `require_internal_document_manager` y precondiciones de estado |
| 8 | POST `/<document_id>/archive` | `archive_internal_document` | JWT + `require_internal_document_manager` y precondiciones de estado |
| 9 | POST `/<document_id>/versions` | `replace_internal_document_version` | JWT + `require_internal_document_manager` y controles de estado/upload |
| 10 | GET `/<document_id>/versions` | `list_internal_document_versions` | JWT + `require_internal_document_view_access`; helper de histórico controla versiones visibles y datos de upload |
| 11 | GET `/<document_id>/links` | `list_internal_document_links` | JWT + `require_internal_document_view_access` |
| 12 | POST `/<document_id>/links` | `create_internal_document_link` | JWT + `require_internal_document_manager` |
| 13 | PATCH `/<document_id>/links/<link_id>` | `update_internal_document_link` | JWT + `require_internal_document_manager` |
| 14 | DELETE `/<document_id>/links/<link_id>` | `deactivate_internal_document_link` | JWT + `require_internal_document_manager` |
| 15 | GET `/<document_id>/external-resources` | `list_internal_document_external_resources` | JWT + `require_internal_document_view_access` |
| 16 | POST `/<document_id>/external-resources` | `create_internal_document_external_resource` | JWT + `require_internal_document_manager` |
| 17 | GET `/by-link` | `list_internal_documents_by_link` | JWT + contexto + vínculo activo; `can_view_internal_document` por elemento (fix #1062) |
| 18 | PUT `/<document_id>/visibility` | `update_internal_document_visibility` | JWT + `require_internal_document_manager` |
| 19 | GET `/<document_id>/download` | `download_current_internal_document` | JWT + `require_internal_document_download_access` |
| 20 | GET `/<document_id>/versions/<version_id>/download` | `download_internal_document_version` | JWT + `can_download_historical_internal_document_version` (fix #1067/A-11) |
| 21 | GET `/<document_id>/audit` | `get_internal_document_audit` | JWT + `require_internal_document_audit_access`; guard de manager, sin regla de `view` por objeto (A-12) |

**Balance:** 11 GET y 10 mutaciones (6 POST, 2 PATCH, 1 PUT, 1 DELETE). Las diez mutaciones se protegen con `require_internal_document_manager`; esto **no** significa que todas apliquen las restricciones especiales de visualización por documento. Antes de trasladar guards al resolvedor, decidir explícitamente si un administrador de Nube que no puede leer el consolidado debe poder cambiar metadata, vínculos, visibilidad, versiones o estado de ese registro. No suponer equivalencia entre `manage`, `view`, `download`, `historical` y `audit`.

**Situación del bloque:** inventario de guards de las 21 rutas **completo en código**; paridad de ejecución por rol/objeto, alcance de mutaciones específicas y correspondencia con permisos nuevos **todavía parciales**. A-12 tiene política aprobada, PR #1074 validado/fusionado y QA de helper de backend desplegado `QA_A12=PASS`; A-13 tiene fix aislado PR #1077 con CI GREEN, merge y confirmación operativa positiva; el draft #1072 es solo evidencia RED. El resolvedor global no ha sido activado.

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

## 5.5. Matriz transversal de paridad por contexto — revisión de código 2026-10-23

**Tipo de evidencia:** comparación **estática** del código de \`main\` de \`_effective_action_decision\` (observabilidad), \`get_user_module_access\` y helpers/guards legacy. **No se ejecutaron fixtures nuevos, SQL ni requests de producción en esta revisión**. Las expectativas que siguen son hipótesis directamente deducidas del código para construir fixtures reproducibles, **no resultados empíricos por usuario real**. El criterio de paridad es: misma identidad, misma acción, misma sucursal y, cuando aplique, **mismo documento/ticket/registro**. No se confunde una acción visible del catálogo con autorización HTTP.

### 5.5.1. Diferencias verificadas entre predicados (sin tocar enforcement)

| Caso / contexto de prueba ficticio | Decisión del guard legacy y límite | Aproximación actual del catálogo / diferencia | Estado de paridad |
| --- | --- | --- | --- |
| **P01 — Nube: rol SISTEMAS, administrar** | \`is_internal_document_admin\` acepta \`SISTEMAS\` | \`internal_documents.manage\` estima acceso por \`ADMIN/ADMINISTRADOR/SUPER_ADMIN\` exclusivamente; **falso negativo** | **NO equivalente**, A-01 |
| **P02 — Nube: ADMINISTRADOR distinto de ADMICORP, administrar** | \`is_internal_document_admin\` NO concede por ese rol únicamente | Observabilidad \`internal_documents.manage=True\` por \`is_admin\`; **falso positivo posible** a nivel predicado (censo previo: ninguno en las 70 cuentas analizadas) | **NO equivalente**, A-01 |
| **P03 — Nube: gerente, documento publicado/privado no propio vs consolidado CUSTOM** | \`can_view_internal_document\` y \`can_download_internal_document\` dependen de documento, publicación, visibilidad, propiedad y acción; histórico/auditoría requieren manager y reglas especiales A-11/A-12 | \`internal_documents.view=True\` para cualquier autenticado; no recibe \`document_id\` ni \`action=view/download/audit\` por registro | **NO representable** como un único booleano |
| **P04 — Tickets: LECTOR_GLOBAL, listar tickets** | \`ticket_filters.ADMIN_ROLES\` incluye \`LECTOR_GLOBAL\`: filtro de lectura retorna query completa | \`_effective_action_decision\` para \`tickets.*\` deniega acciones salvo \`tickets.notify\`. No distinguir listado de acciones de escritura puede mostrar un falso denegado en acciones de lectura | **NO equivalente / separar acciones** |
| **P05 — Tickets: rol ADMIN y rol EDITOR_CORPORATIVO** | \`ticket_filters.ADMIN_ROLES\` incluye \`EDITOR_CORPORATIVO\`, no \`ADMIN\`; el catálogo \`LEGACY_ADMIN_ROLES\` sí incluye \`ADMIN\`, no \`EDITOR_CORPORATIVO\` | El rol por sí solo produce comparaciones diferentes de alcance para \`tickets.*\` | **NO equivalente**, evaluar cada endpoint |
| **P06 — Tickets: SR/AUX/MANTENIMIENTO con grant \`read_assigned_only\` activo** | \`has_assigned_only_maintenance_scope\` exige rol elegible y grant individual; \`filtrar_tickets_por_usuario\` restringe a \`departamento_id=1\` y \`asignado_a=username\`, **sin fallback por autor/sucursal** | Acción genérica \`tickets.*\` informa scope de sucursales, no condición de asignación por registro | **NO equivalente**, hard stop de asignación |
| **P07 — Tickets: coordinación de Mantenimiento con grant de usuario** | \`has_maintenance_coordination_permission\` requiere rol compatible, \`can_pm_view\` y grant vigente \`allow\` individual, con \`deny\` prioritario; excluye jefe regional y SR/AUX/TECNICO aun con grant incidental; la ruta además valida alcance/estado de ticket | \`_effective_action_decision\` para tickets no reproduce esa combinación; \`module-access\` por acción base no equivale al guard de coordinación | **NO equivalente**, grant ya operativo |
| **P08 — PM: cuenta regional MANTENIMIENTO identificada por ID + usuario + depto** | \`_verificar_permiso_sucursal\` limita a intersección \`usuario_sucursal ∩ MAINTENANCE_LEAD_BRANCH_IDS\`; \`ticket_filters\` le aplica además \`departamento_id=1\`; sede corporativa 100 no suma alcance | \`pm.read/execute/validate/configure\` en observabilidad usa rol global o lista genérica de sucursales; no identifica excepción ni su intersección | **NO equivalente**, excepción por identidad |
| **P09 — PM: COORDINADOR_MANTENIMIENTO con ACL departamento 1, \`es_admin=False\`** | \`has_scoped_maintenance_read_grant\` habilita **solo lectura** cuando existe la ACL; \`_verificar_permiso_sucursal\` usa sucursales asignadas sin sumar sucursal principal corporativa | \`pm.read\` conoce esta ACL, pero no valida individualmente la sucursal solicitada; \`pm.execute/validate/configure\` no se heredan de ella | **Parcial**, verificar sucursal por sucursal |
| **P10 — PM: GERENTE/GERENTE_REGIONAL, misma sucursal y otra fuera de alcance** | \`can_pm_view\` por rol + \`_verificar_permiso_sucursal\` por asignaciones/principal; ver no concede ejecutar ni validar | \`pm.read\` informa un conjunto agregado, sin \`requested_sucursal_id\` y sin verificar registro objetivo | **Parcial**, permiso y alcance separados |
| **P11 — Inventario: SR_MANTENIMIENTO, lectura/movimiento en sucursal principal no asignada** | \`_resolve_inventory_read_sucursal_ids\` y \`_require_inventory_movement_write\` usan sucursales M:N, con fallback explícito a \`usuario_sucursal\` si la lista está vacía; no añaden siempre sucursal principal | \`_get_user_assigned_sucursal_ids\` para diagnóstico **siempre añade la sucursal principal**, por lo que el scope puede sobrerrepresentar el real | **NO equivalente**, falsos positivos de scope |
| **P12 — Inventario: AUX_MANTENIMIENTO con múltiples sucursales asignadas** | Lectura/movimientos se limitan a \`sucursal_id\` principal; permisos maestros requieren rol global diferente | \`inventory.read\` y \`inventory.movement_write\` toman el conjunto \`sucursales_ids ∪ principal\`, ampliando lo representado | **NO equivalente**, sucursales extra |
| **P13 — Inventario: MANTENIMIENTO/TECNICO/SISTEMAS, edición maestra vs movimiento** | \`_require_inventory_global_write\` y \`_require_inventory_movement_write\` permiten global a la lista \`INVENTORY_GLOBAL_WRITE_ROLES\` (incluidos estos roles). Esto NO implica alcance global en Tickets o PM de la misma cuenta | \`inventory.master_write/movement_write\` es razonable como diagnóstico del **rol**, pero debe validarse por acción y por módulo; excepción regional de PM no se propaga automáticamente a Inventario | **Paridad de rol parcial**, no reutilizar scopes |
| **P14 — Warehouse: operador con view/upload/archive independientes** | \`warehouse_access.require_warehouse_*()\` consulta \`warehouse_operators\`; catálogos admiten \`can_view OR can_upload\`, upload/archive son flags separados | Las decisiones \`warehouse.view/upload/archive/catalogs\` replican este patrón al nivel de flags; no sustituyen validación del endpoint ni futura política de \`is_active\` | **Candidato a fixture de paridad** |
| **P15 — Planning: operador inactivo vs activo, edit sin view** | \`get_current_planning_operator\` exige \`is_active=True\`; \`require_planning_operator\` exige también \`can_view\`, pero los guardias de acciones específicas miran sus flags independientes | \`_get_target_context\` filtra activo y el catálogo informa flags, pero \`planning.read\` y \`planning.edit\` son acciones **distintas**, no implicación automática una de otra | **Candidato a fixture de paridad** |
| **P16 — Track: GERENTE, GERENTE_REGIONAL, SISTEMAS, MARKETING, TIENDA (lectura)** | \`_require_track_read_role\` **sí permite** esos roles, además de los administrativos/LECTOR_GLOBAL | \`track.read\` solo permite admin o LECTOR_GLOBAL; **falso negativo** de observabilidad para esos otros roles | **NO equivalente**, alta prioridad |
| **P17 — Track: ejecutar pipeline vs leer daily mart** | \`_require_track_admin_role\` solo admite \`ADMIN/ADMINISTRADOR/SUPER_ADMIN\`; lectura tiene lista más amplia | El catálogo distingue \`track.run_daily_pipeline\` / \`track.run_agregadoras\` de \`track.read\`, pero debe conservarse la autorización por ruta y la separación con scheduler | **Roles de ejecución alineados; lectura NO** |
| **P18 — \`module-access\`: allow/deny expirado o scope de sucursal** | En Tickets hay guard de grant **vigente** con fechas y deny prioritario; las rutas del resto de módulos no adoptan por defecto grants del menú | \`_get_latest_active_grants_by_action\` filtra \`is_active/deleted_at\` pero **no** fechas ni scope; \`_apply_module_access_override\` elige primer grant user, luego role; \`effective_allowed\` puede diferir del derecho operativo | **NO usar como enforcement** (A-02/A-03) |

**Lectura correcta de la matriz:** «NO equivalente» significa *diferencia verificable entre predicados de código*, no una explotación o permiso incorrecto efectivamente concedido en producción. Los ejemplos de identidades, documentos y sucursales de las pruebas aún **no se ejecutaron como suite**, salvo los casos previamente documentados de A-10–A-13. Un \`allow\` de catálogo nunca debe reemplazar automáticamente \`filtrar_tickets_por_usuario\`, \`_verificar_permiso_sucursal\`, una validación de documento ni el estado del registro.

### 5.5.2. Esquema mínimo de comparación para la futura matriz bidireccional

| Campo | Significado / condición |
| --- | --- |
| \`user_id\`, \`role\` | Identidad real resuelta desde DB, rol principal legacy; no publicar identificadores personales en reportes agregados |
| \`module_key\`, \`action_key\`, \`http_method\`, \`route\` | Capacidad y entrada funcional; **no** inferir permiso de todas las rutas con un \`view\` de módulo |
| \`requested_branch_id\`, \`object_type\`, \`object_id\` | Sucursal y recurso sobre el cual se decide; \`null\` solo si la acción verdaderamente no tiene scope específico |
| \`legacy_allowed\`, \`legacy_scope\`, \`legacy_reason\` | Resultado del guard real y hard stops para esa operación; puede ser «no evaluado» sin datos de registro |
| \`catalog_observed_allowed\`, \`catalog_source\`, \`catalog_scope\` | Proyección de observabilidad; conservar advertencia \`diagnostic\` / \`compare_only\` |
| \`grant_effect\`, \`principal_type\`, \`starts_at\`, \`expires_at\` | Excepciones vigentes y caducadas, sujeto y precedencia; preservar la función operativa especial de Tickets |
| \`comparison\` | \`match\`, \`legacy_allow_catalog_deny\`, \`legacy_deny_catalog_allow\`, \`incomplete_context\` o \`not_evaluated\`; no fingir decisión binaria donde faltan datos |
| \`effective_mode\` | \`legacy_enforced\` / \`diagnostic_only\` / futuro \`compare_only\`; prohibido mostrar el modo observabilidad como enforcement |

**Contrato de consistencia:** un mismo \`(user, action, branch, object)\` debe producir **igual resultado y procedencia** tanto en Usuario→Acción como en Acción→Usuarios y Módulo→Usuarios. El filtro por rol o sucursal solo recorta la misma consulta, no reinterpreta autorizaciones. Un permiso «global» de coordinación o lectura **no** cancela la restricción del ticket, documento o sucursal. El modelo de acciones por módulo no sustituye esta llave completa.

### 5.5.3. Criterio para avanzar y prioridades del siguiente bloque

1. **P0 — Bloquear sustitución de guardias por el catálogo** para Nube (A-01), Track lectura (P16), Tickets lectura/asignados/coordinación (P04–P07), PM regional/ACL (P08–P10) e Inventario SR/AUX (P11–P12). Documentar que el diagnóstico no es autorización efectiva.
2. **P1 — Suite de fixtures de paridad, sin DB real:** pares de roles (SISTEMAS/ADMICORP/ADMINISTRADOR; GERENTE/GERENTE_REGIONAL/LECTOR_GLOBAL; SR/AUX/COORDINADOR/MANTENIMIENTO), sucursal dentro/fuera, documento \`PUBLISHED/CUSTOM\` y ordinario, ticket asignado/no asignado, grant allow/deny/expirado; resultado de ambos predicados y razón, sin cambiar todavía su comportamiento.
3. **P1 — Revisión de cobertura del catálogo y el mapping:** diferenciar ruta mapeada vs no mapeada, y fuente de autorización real. El censo de 11 módulos, 40 acciones y 72 asociaciones de rutas del 22/oct es un **corte histórico**, no cobertura exhaustiva actual.
4. **P2 — Paridad positiva de operadores Warehouse y Planning:** usar las flags de operador activas como oráculo, probar independencia \`read\` / \`write\` / \`publish\`, y validación de \`is_active\` para Planning. Mantener el patrón actual sin desactivar accesos productivos.
5. **Pendiente de decisión de producto:** si la matriz debe mostrar \`effective_allowed\` como simple previsualización en las acciones no migradas, o renombrarlo a \`catalog_preview_allowed\`; la regla de fondo **ya está definida por contrato**: no etiquetar observabilidad como enforcement.

**Conclusión de este bloque:** matriz de escenarios y diferencias **clasificadas**, no «paridad comprobada». No hubo nueva ejecución de fixtures, petición HTTP ni SELECT en producción y no se activó ningún resolvedor global. Para cerrar Fase A sigue faltando ejecutar la comparación por casos, resolver únicamente contradicciones de política, documentar scopes por registro y cubrir módulos fuera del catálogo.

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
- [x] **Matriz comparativa por código P01–P18 (5.5):** roles, acciones, sucursal, registro/objeto y fuente de autorización real vs estimación del catálogo; se identificaron discrepancias de Track, Tickets, PM y Inventario y candidatos Warehouse/Planning. **No equivalen a tests de paridad ejecutados**.
- [ ] Ejecutar fixtures aislados de paridad por sucursal/documento/ticket con estados `match`, `legacy_allow_catalog_deny`, `legacy_deny_catalog_allow`, `incomplete_context`, preservando todos los guards vigentes.
- [x] **Inventario de los 21 handlers Nube completo por código** (A-14): 11 GET y 10 mutaciones, todos con JWT; se registró el guard legacy de cada ruta. **Pendiente:** pruebas de paridad por contexto y correspondencia 1:1 con el resolvedor; no confundir inventario estático con cobertura QA.
- [ ] Producir conjunto de escenarios de paridad de Nube Corporativa (rol SISTEMAS, ADMICORP, admin con otro usuario, usuario ordinario, documento sensible).
- [ ] Decidir con responsable operativo únicamente los accesos legacy contradictorios que supongan un cambio de política, no pedir autorización para cada refactor.
- [x] Censadas las **3 asociaciones transversales activas** del catálogo: 1 upload documental de Aperturas agrupado bajo Nube, y 2 altas/bajas de permisos departamentales (`users.manage`) agrupadas históricamente bajo Reportes. Guards efectivos cotejados en código, sin indicios de bypass y sin cambios de autorización.
- [x] **Cobertura Flask vs catálogo del blueprint Nube** cotejada: 21 rutas (10 mapeadas, 11 GET sin mapeo); se categorizó el guard real de cada GET y se documentó una potencial divergencia de metadata en `/by-link`, pendiente de prueba de regresión.
- [x] Ejecutar regresión aislada de `/by-link` con rol SISTEMAS y documento sensible CUSTOM: **ROJO confirmado antes de la corrección**, CI #39979436595, PR #1062.
- [x] Corrección puntual de `/by-link` validada (4 tests PASS en CI #39980308075) y fusionada a `main` con PR #1062, commit `e27e63b77a8ce1f3afaefa079902c9e247ce31e9`.
- [x] Deploy del fix #1062 confirmado por el operador: `git pull` y reconstrucción de `backend`. QA interno de código importado en el contenedor: `NUEVA_VALIDACION=True`, `VALIDACION_ANTERIOR=False`, `QA_BY_LINK=PASS`.
- [x] **Prueba HTTP sin JWT en backend productivo (2026-10-23):** `GET /api/internal-documents/by-link?entity_type=GENERAL` respondió `401` sin cabecera Authorization. Confirma el rechazo de una solicitud anónima al endpoint, no la corrección de las restricciones entre roles/documentos autenticados.
- [x] **HTTP autenticado sin leer documentos:** JWT de sesión legítimo + `entity_type=INVALIDO` devolvió HTTP 400; alcanzó validación previa a consulta de documentos.
- [x] **Camino HTTP autenticado con parámetros válidos y vínculo ficticio inexistente:** `GET /api/internal-documents/by-link?entity_type=GENERAL&entity_key=SUITE_ULTRA_QA_SIN_VINCULOS_20261023` devolvió **HTTP 200, `items` vacío** (`DOCUMENTOS=0`), sin exponer metadatos de documentos.
- [x] QA aislado con documento privado ordinario ficticio: rol `SISTEMAS` → `CAN_VIEW=True`; rol `GERENTE` sin propiedad → `CAN_VIEW=False`.
- [x] **QA de lectura sensible CUSTOM** con fixture: `ADMICORP=True`, `SISTEMAS_QA=False`, `GERENTE_QA=False` para `Consolidado de agregadoras` simulado.
- [x] **A-11 CONFIRMADO por fixture:** para consolidado CUSTOM, `SISTEMAS_QA` obtuvo `VIEW=False`, `DOWNLOAD=False`, `HISTORICAL=True`, frente a ADMICORP `True/True/True` y GERENTE `False/False/False`.
- [x] **A-11 fix preparado sin desplegar:** PR #1067 con test RED (2 fallos esperados, CI #39999421770) → helper corregido → GREEN (7/7 PASS, CI #39999587923), sin migraciones.
- [x] PR #1067 revisado, CI 7/7 PASS y squash merge a `main`: `df035eb02f4833dc77a4e67236472b5f5948b963`.
- [x] **A-11 desplegado y verificado:** el operador confirmó ejecución del bloque Git pull + reconstrucción de `backend`, y la inspección `inspect.getsource(can_download_historical_internal_document_version)` devolvió `A11_CODIGO_DESPLEGADO = True`, `QA_A11 = PASS` (2026-10-23). Verificación estática del código importado en el contenedor; las **7/7 pruebas funcionales** corresponden a CI, no a un ensayo HTTP con archivo real. Sin migraciones.
- [x] **A-12/A-13 diagnosticados con fixtures y GitHub Actions:** PR draft #1072 RED controlado (**3 fallos de aserción / 7 PASS**, CI #40004028928), sin cambiar reglas ni consultar BD productiva.
- [x] **Política A-12 aprobada:** auditoría del consolidado requiere rol manager documental **y** `view` explícito; lectura ordinaria de auditoría manager no cambia.
- [x] **A-12 RED→GREEN y merge:** PR #1074 fusionado a `main` como `38dadf38e49f1a2f68b8a1cd321086f365bbb192`; 12/12 A-12 PASS y 7/7 A-11 PASS en el último commit.
- [x] **A-12 desplegado y QA PASS:** operador confirmó reconstrucción del backend y fixture en contenedor: `A12_RESULTADOS=[True, False, False]`, `QA_A12=PASS`; sin migraciones ni lectura de auditorías reales.
- [x] **A-13 preparada RED→GREEN:** PR [#1077](https://github.com/VladRoJa/sistematicketsultra/pull/1077) corrige en SQL el filtro de título antes de contar y paginar. RED limpio CI #40008420077 = 4 fallos esperados / 14 PASS; GREEN última CI #40009002764 = **18/18 PASS** y suites A-12 12/12, A-11 7/7, `/by-link` 7/7 PASS. **Fusionado a main; operador indicó que el bloque de despliegue y QA A-13 quedó bien, sin pegar valores de consola.**
- [x] **Merge A-13 autorizado y completado:** PR #1077 fusionado por squash como `ebb9e9080fb76d98696b451c429610701f43a779`, con 4 workflows verdes en último commit.
- [x] **Validación operativa A-13 confirmada verbalmente por el operador (2026-10-23):** ante el bloque de despliegue y QA para filtro normalizado, respondió «si bien». Se registra como confirmación positiva del bloque, pero **no se recibieron impresos** `A13_CODIGO_DESPLEGADO` ni `QA_A13`; no atribuirles valores textuales ni tratarlo como prueba HTTP end-to-end. CI previo 18/18 PASS, sin migraciones.
- [ ] **Fase A sigue abierta:** la matriz transversal está documentada a nivel predicados de código; faltan fixtures por contexto, paridad HTTP/inversa y módulos fuera del catálogo. No activar el resolvedor global.
- [ ] Ampliar fixtures a descarga actual e histórica y controles por registro de las demás rutas del piloto.
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
