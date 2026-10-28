# Suite Ultra — Fase A P32: conciliación por **capacidades** de las 102 rutas restantes

**Base Git:** P31 fusionado, commit `4ba2bfc59013d3b3a8f99c4e211d8470fc28cbb7`. **Corte PostgreSQL original:** P30 2026-10-26T23:48:39Z; 11 módulos, 40 acciones, 69 rutas catalogadas, 112 no-GET fuera del mapa y 247 GET fuera del mapa. P31 revisó las primeras 10/112; aquí se conserva una proyección exactamente 1:1 de las **102 restantes**.

**Contrato rector:** "no catalogado" NO significa sin JWT ni inseguro; el catálogo **no ejecuta guards** ni sustituye autorización por servicio, asignado, sucursal, fecha, estado o hard stops. No se deben crear 102 acciones por simple similitud de endpoint.

## Cobertura y evidencia

[Matriz por ruta — 102 operaciones](permissions_phase_a_p32_102_capability_contract_20261027.csv): método, ruta y handler originales, grupo P28/P31, capacidad candidata **de diseño** (no permiso real), fuente de código, señal directa del guard en handler, protocolo JWT, posibles efectos y decisión pendiente.

| Familia | Rutas | Grupos funcionales para decidir | Profundidad actual |
|---|---:|---|---|
| Marketing | **42** | dispatch 18, freeze/creación 7, preview/preflight 7, provider 5, configuración 2, blacklist 1, atribución batch 1, QA 1 | Inspección del handler fuente de las 42 |
| Requisiciones | **19** | workflow 11, aprobación/configuración financiera 7, corrección administrativa 1 | Inspección del handler fuente de las 19; permisos finos delegados a servicios |
| Integraciones Google Ads | **11** | RAW/estructurado/correcciones 7, aprobación/publicación 3, OAuth 1 | Inspección del handler fuente de las 11; flujo OAuth y service guards pendientes de paridad integral |
| Contact Center | **10** | flujo caso/cita 7, identidad/importación 2, confirmación de compra 1 | Inspección del handler fuente de las 10 y helpers de actor/caso/cita |
| Otras familias | **20** | 13 grupos entre Auth, Inventario, Daily Check, Mantenimiento, Routine, RPA, Track, Alerts, Warehouse | Heredan inventario y señales de P28–P31; **no** se etiquetan falsamente como revisión de fuente P32 |
| **Total** | **102** | **29 grupos candidatos** en la matriz (no acciones definitivas) | 82 inspeccionadas por función y 20 clasificadas para investigación posterior |

**Precaución de evidencia:** `direct_guard_or_delegate_signals` representa símbolos **llamados por el handler** (p. ej. `_current_user` o `_resolve_campaign_v2_request`). Su presencia NO prueba que la comprobación de objetos, autorizaciones de servicio o ausencia de side effects sea correcta. `evidence_level` diferencia `handler_source_inspected` de `p31_inventory_only_pending_source`. Los nombres `marketing.dispatch_governance` y equivalentes son **etiquetas de diseño**; **NO existen como acciones del catálogo salvo verificación y decisión posterior**.

## Hallazgos sobre límites de autorización

### 1. Marketing — no confundir preflight con envío

- La mayoría de las mutaciones de Campaign V2 resuelven `_resolve_campaign_v2_request()`, que exige `can_manage_campaigns`. El paso de configuración/dispatch utiliza `_resolve_campaign_v2_dispatch_config_request()`, que exige `can_manage_dispatch_config` **y alcance global**. Operaciones de aprobación/ejecución invocan además `_require_campaign_v2_send()` (permiso distinto).
- `campaign_v2_governed_execute_endpoint` exige flags de envío gobernado, `operator_password` verificado contra **el propio actor JWT**, manifest/child esperado y límites de proveedor. No etiquetar ese POST como un simple `marketing.manage`.
- Un `POST` de vista previa o un batch de atribución puede ser **consulta**; no convierte por sí solo en escritura o envío. `campaign_v2_commercial_attribution_summary_endpoint` se define explícitamente como lectura batch con sucursales permitidas.
- Revisar especialmente `provider-history/lookup`, export/import y preview con datos personales: efectos secundarios y minimización no se pueden concluir solo por verbo, nombres o guard superficial.
- Política pendiente de aprobar: capacidades *management*, *preflight*, *global dispatch config*, *send/step-up*, *provider reconciliation* y *read/attribution*. **No un grant universal** para todos los POST.

### 2. Requisiciones — separación de funciones y estado

- Las **19** rutas verifican JWT y resuelven `_current_user()` (actor real); el control de aprobación, compras, finanzas, logística, entrega y corrección se delega a los servicios `purchase_requisition_*`. Obtener el actor **no basta** para autorizar una transición.
- `approve_purchase_requisition_quote_by_finance` y `reject_purchase_requisition_quote_by_finance` son decisiones financieras distintas de crear requisiciones o administrar aprobadores. Los servicios usan una allowlist de finanzas y reglas de estado/actor (ver suites P23/P24).
- Importa la pertenencia del solicitante, sucursal, estado y trazabilidad; las notificaciones se despachan **después del commit**, no prueban autorización.
- Política pendiente: creación/edición del solicitante, selección de cotizaciones, autorización de finanzas, logística/recepción, corrección administrativa y configuración de aprobadores; conservar los checks de servicio.

### 3. Integraciones Google Ads — publicación no es ingesta

- `manual/ingest` y `manual/publish` requieren JWT, flag de entorno específico, `require_current_admicorp()` y `require_warehouse_upload()`. Validan par de uploads y confirmación.
- `continuity/approve` exige JWT, flag y confirmación precisa; la autorización de actor se ejecuta en `approve_authenticated()` **dentro del servicio**.
- `corrections/candidates/<id>/review` es una **revisión independiente** con `require_warehouse_view()` y autorización adicional en el servicio; no debe equipararse a publicación, y debe impedir autoaprobación.
- OAuth start necesita revisar CSRF/state, callback y manejo de secretos como contrato de autenticación externo, no como permiso genérico de publicación.
- No leer, imprimir ni reproducir XLSX/raw reales, tokens OAuth, IDs personales ni claves del proveedor para auditar.

### 4. Contact Center — caso/cita no son acceso global

- `_context()` resuelve el actor y su acceso. `_assert_case_access` valida sucursales permitidas de gerente y propietario del caso; la excepción no-show exige regla expresa. `_assert_appointment_access` mantiene sucursal y caso.
- `post_merge_contacts` rechaza perfiles de gerente vía `_assert_operator_access` y además requiere supervisor; **fusionar identidades** no es una acción genérica de crear contacto.
- `post_verify_purchase` requiere operador y cita accesible; no es equivalente a cualquier cierre o interacción de Contact Center.
- Crear contacto/caso, reasignar citas, importar CRM y corregir resultado requieren decisiones por workflow de negocio y scope real de sucursal. No deducirlas de `POST` ni de `_context` únicamente.

### 5. Excepciones intencionales y otras 20

- `POST /api/auth/login`, `/logout`, `/refresh` se consideran **protocolo de sesión**: no imponer JWT de acceso por analogía; revisar protección de credenciales/cookies/CSRF en auditoría específica.
- `POST /api/warehouse/internal/gasca-report-jobs` utiliza `X-Suite-Internal-Token` validado por HMAC/fail-closed (P29); no sustituirlo por JWT de usuario.
- Track Alerts, tras P29-S1, requiere JWT y rol de lectura/admin según acción; Track canonical-close, jobs Warehouse y scheduler se deben evaluar por side effect diferido.
- El resto se mantiene explícitamente en `pending_source` y **no se certifica**, aunque el test anónimo proteja el límite JWT.

## Regresiones y límites

`backend/tests/routes/test_permissions_phase_a_p32_capability_groups.py` (sin datos productivos):
1. Conserva las **102/102** identidades de P31 y verifica 82 fuentes/20 pendientes, sin nuevas acciones ni grants.
2. Ejerce **98** HTTP requests sin JWT en un `create_app()` Flask sintético; los **otros 4** son tres rutas del protocolo de sesión y un job con token interno. Para los 98 exige **401 antes de ejecutar servicios**.
3. Valida las tres puertas distintas de Marketing (dispatch config, alcance global y send) y un request `dispatch/execute` denegado antes de construir proveedor externo.
4. Comprueba sucursal/cartera de Contact Center, y que gerente no herede rol de operador.
5. Comprueba que publicación M6 rechaza actor sin autorización antes del servicio canónico, y que la revisión independiente requiere su propio guard.

CI P25–P32 ejecuta también suites existentes: reglas de Finance requisitions, Contact Center, Google Ads approval, Marketing scoped exclusions/dispatch config y Track Alerts. **No se llama proveedor, no se envía campaña, no se publican métricas, no se alteran grants, no se toca DB productiva**.

## Decisión operativa / cierre

**P32 establece la taxonomía y puertas de acceso, pero NO aprueba nuevas capacidades en catálogo.** Las 102 requieren confirmar políticas de negocio, scope y precedencia (deny primero) antes de introducir migraciones de `permission_actions` o `permission_route_map`. Las 247 GET también siguen pendientes, así como la comparación histórica 111→112.

**Cambios de P32:** solo documentos, tests y CI. **No requiere desplegar frontend/backend ni migraciones.** Fase A issue #1053 continúa OPEN. Un milestone posterior puede consolidar propuestas de políticas reales por bloque, con tests negativos/positivos y sin reemplazar los hard stops existentes.
