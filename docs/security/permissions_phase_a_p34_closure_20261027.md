# Suite Ultra — P34 / Acta de cierre de Fase A (inventario y compatibilidad)

**Fecha del acta:** 27 de octubre de 2026. **Issue:** [#1053](https://github.com/VladRoJa/sistematicketsultra/issues/1053). **Contrato:** [Contrato global de permisos](../contratos/contrato%20de%20permisos%20globales.md). **Clase de entrega:** diagnóstico consolidado, decisiones y alcance de la primera migración; **sin activar enforcement**.

**Estado del documento:** propuesta de aceptación de cierre de **Fase A de descubrimiento** con riesgos explícitos trasladados a Fase B. **NO significa** que toda la Suite ya aplique grants centralizados, que los GET estén certificados ni que sea seguro habilitar edición de cualquier acción.

## I. Lo que exigía #1053 y la evidencia disponible

| Condición de #1053 | Resultado respaldado | Límite / decisión residual |
|---|---|---|
| Inventariar roles, ACL de departamentos, operadores, grants, excepciones y scopes | [Matriz maestra de 11 módulos](permissions_phase_a_p34_compatibility_master_20261027.csv); roles legacy y ACL `usuarios_permisos`; operadores Warehouse/Planning; tablas `permission_grants` + log; control `usuario_sucursal` y documentos | Las identidades de grants no se exportaron. La inspección de estructuras no prueba todos los usuarios de producción |
| Módulo → acción → ruta → guard real → fuente → alcance y hard stops | Matriz maestra; [P31 (112 métodos)](permissions_phase_a_p31_effective_guards_20261027.csv) y [P33 (102/102 restantes)](permissions_phase_a_p33_102_source_closure_20261027.csv); [nueve lecturas sensibles Nube](permissions_phase_a_p34_nube_pilot_p1_reads_20261027.csv); P25–P33 | 112 mutaciones con revisión de fuente no son 112 autorizaciones dinámicamente certificadas; 247 GET fuera del catálogo en corte anterior |
| Separar diagnóstico de enforcement y marcar incertidumbre | [Contrato de auditoría visual](permissions_visual_audit_milestone_20261023.md) usa `legacy_allowed`, `catalog_allowed` y `no_concluyente`; matriz P34 explicita desfases | `module-access.effective_allowed` es proyección/override, **no** la respuesta efectiva universal del backend |
| Diferencias lectura/edición vs operaciones HTTP | Hallazgos Nube `internal_documents.manage`, Aperturas P31, Mantenimiento/Tapizado P31, grupos P32 | No convertir automáticamente un `allow` del catálogo en permiso de archivo, sucursal, financiamiento o envío |
| Riesgos y secuencia empezando por Nube | Esta acta define prioridades y un **primer piloto Nube Corporativa en compare_only** | Sin cambios de acceso productivo, sin grant nuevo, sin Alembic, sin despliegue |

### Fotografías verificadas; prohibido mezclar cortes

- **PostgreSQL P30 (26-oct-2026 23:48:39 UTC)**, backend host SHA reportado `8abfb04e23a4f99a881b8aa63515fd5da855fa80`: **11 módulos**, **40 acciones activas**, **69 mapeos activos** (**68 exactos + 1 alias**), **359 sin mapa** (**112 no-GET + 247 GET**). No se reportaron handler_mismatch ni catalog_inactive. Son datos de ese corte, **no se afirma que sean actuales en cualquier deploy posterior**.
- **Grants P30:** únicamente conteo agregado de **2 filas `allow/user/global` con `is_active=True`**. No se exportaron action_id, identificadores de personas, ventanas temporales ni hard stops; por tanto no afirmar sobre esa evidencia que sean grants efectivos hoy, de Nube o de Mantenimiento. La atribución a Mantenimiento en el PR histórico #1058 requiere corroboración independiente.
- **P31**: 10 candidatas clasificadas como 3 guards especializados, 3 etiquetas genéricas no equivalentes, 3 candidatas acotadas y 1 proyección de Aperturas corregida. Ninguna sustituye guard real.
- **P32/P33**: 102 restantes examinadas a nivel de handler (**82+20**). Entre las 102, **98** rutas de usuario rechazaron petición anónima en P32 (P33 volvió a probar 16 del subgrupo); otras 4 usan protocolos especiales: Auth login/logout/refresh y token interno Warehouse. JWT **no equivale** a permiso de sucursal, documento ni objeto.
- **P33 GET:** lector manual `python -m app.utils.permission_get_surface_audit` creado, aún **sin corte nuevo de producción**. Los **247 GET** son una **cola de revisión priorizada**, no 247 incidentes ni necesariamente 247 nuevas acciones; su ejecución exhaustiva **no** es requisito de cierre de *inventario* Fase A.

## II. Fuente de verdad: 11 módulos y decisiones explícitas

La matriz [P34 por módulo](permissions_phase_a_p34_compatibility_master_20261027.csv) indica acciones representativas, autoridad efectiva actual, hard stops, brecha diagnóstica, decisión de conservación y puerta de paso. Se conserva deliberadamente:
- **Roles** estables para responsabilidad; **capacidades** para operaciones; **alcance** por sucursal/objeto/documento; excepciones `allow/deny/inherit` auditables, sin inventar roles combinados.
- **Operadores especializados** Warehouse/Planning; **PM/Tickets/Inventario** con helpers de sucursal, asignación, estado, trazabilidad y, en mantenimiento, grants que sí pueden participar en enforcement legado.
- **Hard stops por dominio** antes de resolver nuevos grants; `is_active` de catálogo o casilla frontend NO es autorización.
- **Identidad real desde DB**, JWT para autenticar (salvo protocolos explícitos), y resolutores internos solo como base de comparación mientras no exista enforcement por módulo.

### Discrepancias aceptadas **solo temporalmente**, sin ocultarlas

**D1 — Nube, crítica para primera migración.** `internal_documents.manage` en `permissions_catalog_routes.py::_effective_action_decision` usa `is_admin` (roles `ADMIN/ADMINISTRADOR/SUPER_ADMIN`), pero `internal_documents_access.py::can_manage_internal_documents` usa **rol SISTEMAS o usuario ADMICORP**. Así, un usuario SISTEMAS puede aparecer negado en la proyección aunque el guard lo permita; un ADMINISTRADOR genérico puede aparecer permitido sin tener manager real de Nube. Es una discordancia **diagnóstica**: no se modifica el guard real y **NO se permite migrar Nube a enforcement** hasta eliminar el falso estado con paridad probada. `internal_documents.view` devuelve `allowed=True` como indicación abstracta, **no acceso a todos los documentos**.

**D2 — Módulo vs grants.** El `module-access` de catálogo puede mostrar `effective_allowed` a partir del último grant user/role sin contemplar completamente fechas, scope, precedencia `deny`, acción base ni hard stops. Se conserva como proyección de configuración; **no** usar como único criterio para asignar un acceso operativo. Compare la semántica final con `docs/security/global_permissions_grants_technical_design.md` y la aplicación real de `tickets_maintenance_permissions.py`, antes de habilitar grants en cualquier módulo migrado.

**D3 — Documentos especiales.** Nube protege visibilidad `GLOBAL/CUSTOM/PRIVATE`, estados `DRAFT/PUBLISHED/ARCHIVED`, sensibilidad y propiedad. La gestión o el grant de lectura abstracto no eliminan esas reglas. `Consolidado de agregadoras` tiene exclusiones adicionales A-12/A-13: manager + visibilidad efectiva para auditoría; en listado manager SISTEMAS ≠ ADMICORP se excluye el consolidado **antes** de paginar. Las pruebas HTTP/JWT A12/A13 usan dobles de DB, no documentos productivos. No confiar en identificación por título como política definitiva de clasificación duradera.

**D4 — Otras mutaciones.** Requisiciones (finanzas vs solicitante), Marketing (preflight/configurar/enviar/step-up), Contact Center (propiedad del caso/sucursal), Integraciones (RAW/estructurado/revisión independiente/publicación), Tickets (coordinación vs completar trabajo/tapizado), Inventario (stock/branch) y Track (admin/canonical async) permanecen bajo sus guards. Sus propuestas de grupos P32 **no son nuevos permisos aprobados**.

## III. Primer piloto acordado: Nube Corporativa, pero en comparación segura

**Fase B — primera entrega permitida:** solo `internal_documents.manage` y `internal_documents.view` como **acciones de observabilidad** y comparación con el guard actual. Consulta por documento/sucursal para `view` solo cuando hay documento real y acceso administrativo a diagnósticos; ausencia de ID o fuente incompleta => **no concluyente**, nunca “permitido” universal.

**Qué se conserva intacto durante B1:** `require_internal_document_manager`, `require_internal_document_view_access`, `require_internal_document_download_access`, `can_download_historical_internal_document_version`, `require_internal_document_audit_access`, comprobaciones de publicación/visibilidad/especiales, JWT+usuario desde DB, guardias de manager SISTEMAS/ADMICORP, lista paginada y sus exclusiones.

**Primera migración controlada, solo después de B1:**
1. Corregir la **proyección**, no la política, para reproducir exactamente `can_manage_internal_documents` con identidad real de DB, y fijar `allowed/denied/unknown` por documento (no convertir todos los admin en managers).
2. Pruebas 401/403/200 + IDOR con actores manager/lector, mismos y distintos documentos/sucursales, `CUSTOM`, `PRIVATE`, borrador/publicado, consolidado A12/A13, histórico, auditoría y descargas; no leer contenido de archivos productivos.
3. Paralelismo de resoluciones legacy vs catálogo sobre contexto idéntico; coincidencia o `no_concluyente` con evidencia guardada. Prohibir `grants_enforced` y `grants_overlay` sin aprobación explícita, backout probado y migración Alembic para cualquier tabla/action/map nuevos.
4. Una vez probado compare_only, decidir por separado las capacidades de *administrar*, *ver*, *descargar*, *auditar* y *publicar*. **No inventar ni activar** estas nuevas acciones en Fase A.
5. UI bidireccional usa un único resolutor; mostrar claramente `diagnóstico legacy`, `comparación` o `enforcement activo`, con fuente, alcance y motivo; editar solo capacidades que hayan migrado realmente y que preserven hard stops.

[Nueve rutas GET de Nube prioritarias](permissions_phase_a_p34_nube_pilot_p1_reads_20261027.csv) incluyen listado, detalle, versiones, vínculos, recursos externos, búsquedas por vínculo, descargas vigente/histórica y auditoría. Su lista **no certifica** a las otras GET del sistema ni obliga a catalogarlas ahora. Los demás GET P1 de P33 continúan en backlog posterior.

## IV. Decisiones de compatibilidad con aceptación de riesgo

| Prioridad | Estado al cerrar A | Decisión / siguiente dueño |
|---|---|---|
| **Bloqueante B1** | D1 Nube `manage` y `view` muestran diagnóstico incompleto | B1 backend + QA objeto; jamás activar enforcement antes de paridad |
| **Bloqueante ante grants efectivos** | D2 scope/tiempo/deny/hard stops y no probar a quién pertenecen las 2 filas agregadas | B posterior de resolutor central, validaciones DB y auditoría |
| **Alta B1** | D3 visibilidad de Nube, descargas, audit, consolidado | conservar guard; matriz P1 9 y regresión HTTP/JWT/objeto |
| **Alta fuera de B1** | Requisiciones Finance; Marketing envío; Integraciones publicar; Contact Center CRM | no transferir acceso: regresiones por servicios y pruebas por rama/estado |
| **Alta fuera de B1** | Tickets/PM/Inventario con permisos legacy y excepciones especializadas | no migrar sin paridad de actor/objeto/sucursal y no editar roles en masa |
| **Media, aceptada como deuda inventariada** | 247 GET no catalogados en P30 y 112 no-GET sin mapeo | no son rutas públicas por definición; lector P33 y revisiones por riesgo P1/P2/P3 |
| **Media, trazabilidad** | Diferencia histórica entre 111 y 112 mutaciones en cortes distintos | no atribuir sin snapshots completos de ambas versiones |

**Regla de cierre:** Fase A termina al entregar **inventario + matriz + discrepancias + decisiones de conservación + piloto B1 y gates**. No termina al mapear todas las rutas, modificar permisos reales, instalar un menú nuevo ni agotar pruebas end-to-end de todos los dominios. Las excepciones se trasladan **visibles y obligatorias** a B1 o a un backlog específico; no quedan “aprobadas” para enforcement por el cierre administrativo.

## V. Reproducibilidad y despliegue

- Leer solo catálogo/Flask en instancia versionada: `python -m app.utils.permission_route_inventory` y `python -m app.utils.permission_get_surface_audit` (P25/P33); transacción `SET TRANSACTION READ ONLY` y `ROLLBACK`; no ejecutar handlers.
- Confirmar **commit del contenedor desplegado**, no inferir de `git rev-parse HEAD` del host. No ejecutar tests de escritura reales sobre documentos, SMS o campañas productivas.
- Suites existentes P25–P33, A12/A13, matriz visual; la nueva regresión P34 prueba invariante de discrepancia Nube y casos JWT pasivos. Los tests de CI con fixtures **no certifican** el estado temporal ni la pertenencia de grants actuales.
- No es necesario reconstruir Docker por documentación/tests P34. La herramienta P33 requiere que el contenedor esté actualizado a una imagen que la contenga, cuando se quiera ejecutar. **Sin migración Alembic en P34**.
- PR documental original [#1058](https://github.com/VladRoJa/sistematicketsultra/pull/1058) conserva afirmaciones históricas no verificadas por el corte agregado P30 y estaba abierto/no fusionado; **esta acta sustituye su función**, sin importar contenido obsoleto automáticamente. Conciliar/cerrar #1058 como superseded para dejar un único documento rector.

**Criterio final de aceptación para #1053:** enlace al CSV de 11, al anexo de Nube, a la matriz P33 y a este documento; CI verde; revisión explícita de D1–D4; riesgo diferido registrado. Después, #1053 puede cerrarse como **discovery/compatibility complete**, no como autorización centralizada implementada.
