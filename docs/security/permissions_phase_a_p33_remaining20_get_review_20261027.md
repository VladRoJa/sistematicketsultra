# Suite Ultra — Fase A P33: 20 operaciones pendientes y auditoría pasiva de GET

**Fecha documental:** 27-oct-2026. **Base:** P32 `98ed79796721eb769229ca55298a742f77ad19e7`. P30 PostgreSQL `2026-10-26T23:48:39Z` observó **247 GET sin catalogar** y 112 métodos mutantes sin catalogar; P31 cubrió 10 y P32 revisó la fuente de 82 de los 102 restantes. **P33 completa la revisión del handler de los 20 últimos**. Importante: estos son los recuentos del snapshot de P30; **no garantizan la cifra live de hoy**.

## 1. Cierre de inventario de fuente: 102/102 de P32, no 102 permisos autorizados

La [matriz extendida P33](permissions_phase_a_p33_102_source_closure_20261027.csv) preserva **exactamente** método, ruta, handler, familia y grupo de las 102 rutas P32; añade `p33_evidence`, archivo inspeccionado, guard o delegación observada y límite de efectos. **82** referencias P32 se conservan como `prior_p32_source_inspected` y los **20** restantes pasan a `handler_source_inspected`. `p33_effective_scope_certified` permanece **NO en los 102**, porque **revisar fuente y comprobar JWT no demuestra autorización completa de objetos y permisos efectivos en producción**.

| Bloque final | Rutas | Guard y distinción principal | Riesgo funcional pendiente |
|---|---:|---|---|
| Checklist diario BI/operador | **3** | `_require_bi_access` para rollout; servicios `postpone_today`/`submit_today` por actor y sucursal | Cambio de rollout, anexos de evidencia, rollback y limpieza de archivos |
| Inventarios V2 E2 | **1** | `_actor()` lee rol/sucursal **desde DB**, `_is_allowed` por sucursal; idempotency key | PENDING vs oficial, consistencia del baseline y rechazo de autoaprobación |
| Autenticación | **3** | Login password; logout/revoke y refresh con cookie, comprobación de Origin | Token/cookie, expiración/rotación, origen y revocación; no exigir JWT de acceso artificial |
| Planner / Mantenimiento Equipos | **2** | JWT + servicio `schedule_ticket`/`preparar_compromiso_estructurado` | Alcance de ticket, motivo, fechas, estado e historial; notificación después de commit |
| Control de Rutinas | **2** | `_authorized_decision_user`: roles escritores y sucursal del socio | Aprobación/revocación auditable, razón, confirmación y estado |
| SMS Gasca RPA | **1** | `_require_module_access` + `_require_sucursal_access` | Crea solicitud en cola, no envío síncrono; destinatario, PIN y límites de sucursal |
| Track histórico | **1** | JWT + `_require_track_admin_role` | Solicitud de cierre `pending`, fecha pasada, precondición de agregadoras; ejecución posterior en scheduler |
| Track Alerts | **5** | JWT + `_require_track_alert_access(write=True/False)` (P29) | **2 previews lectura**, **1 generación y 2 envíos/admin**; SMTP y persistencia NO deben confundirse |
| Warehouse consolidado | **1** | JWT + `require_warehouse_upload` | Posible creación de snapshot; canonicalidad y scope warehouse |
| Warehouse job interno | **1** | `_require_internal_job_token` usa HMAC fail-closed, **sin JWT de usuario** | Endpoint M2M, productor/orquestador, token secreto y jobs diferidos |
| **Total** | **20** | **16 JWT**, **3 protocolo Auth**, **1 token interno** | **Sin grants ni mapas automáticos** |

**No mapear por verbo:** `POST /track-alerts/test` y `/regional-test` son previews protegidos por roles de lectura; `/generate` y `/send-*-email` requieren roles admin. El cierre canónico de Track es una solicitud **asíncrona**, no la ejecución inmediata del mart. `/auth/login`, `/logout` y `/refresh` son un protocolo basado en credenciales/cookies/origen y tienen amenazas distintas a JWT Bearer.

## 2. Apertura del inventario GET (247 en snapshot previo)

Nuevo lector `python -m app.utils.permission_get_surface_audit`:
- Construye Flask `url_map` sin llamar handlers.
- Consulta **solo** `permission_route_map` en PostgreSQL por `read_current_route_map(db.engine)`, reutilizando `SET TRANSACTION READ ONLY` y `ROLLBACK`.
- Incluye exclusivamente `GET` en estado `not_cataloged`, `handler_mismatch` o `catalog_inactive`, y conserva método, ruta, endpoint y familia.
- Señala **prioridades de revisión**, no permisos y no descubrimiento de vulnerabilidades:

| Prioridad | Etiqueta del analizador | Qué comprobar |
|---|---|---|
| P1 | `oauth_callback_protocol` | Contrato OAuth `state`, redirección, callback y CSRF |
| P1 | `internal_or_machine_protocol` | HMAC, origen del job, token/allowlist, no JWT de usuario por defecto |
| P1 | `download_export_or_document` | Autorización por documento/recurso, descargas, anexos, scopes y PII |
| P1 | `identity_or_personal_records` | Usuarios, contactos, CRM, datos de socios y minimización |
| P2 | `operational_and_financial_data` | Scope de sucursal/rol y BI financiero, Warehouse, Inventario |
| P3 | `general_read_review` | Revisión manual sin asumir que la ruta es pública/inocua |

**Muy importante:** esta heurística de nombres y rutas NO comprueba decorador `jwt_required`, `@before_request`, ni el permiso de objeto. Un documento puede tener protección adicional o faltante; la categoría no lo decide. `GET` no significa libre de efectos secundarios, tampoco. La herramienta emite JSON **sin** usuarios, JWT, grants, correos, nombres personales, cuerpos de respuesta ni payload de DB. La salida es un inventario útil para QA por familias y revisión posterior.

**Cifra viva pendiente:** no se ejecutó la nueva herramienta contra producción en este PR; el número real puede haber cambiado por commits simultáneos. La referencia **247 GET** procede del corte P30, no de una corrida inventada de P33. P33 inicia su clasificación y conserva esa diferencia histórica explícita.

## 3. Regresiones sin efectos en producción

`backend/tests/routes/test_permissions_phase_a_p33_read_surfaces.py` prueba:
- **102 identidades preservadas**, 82 + 20, 16+3+1 rutas por contrato; 0 grants creados.
- **16 peticiones anónimas** a las rutas restantes que requieren JWT: deben obtener 401 antes de leer/escribir servicios.
- M2M `/api/warehouse/internal/gasca-report-jobs` sin token obtiene 403; no se ejecutan productores.
- Los tres handlers Auth preservan modelo distinto: JWT no obligatorio en login/logout/refresh, refresh rota cookie si el origen y token son válidos.
- Prioridades GET P1/P2/P3 con fixtures sintéticos y conservación de identidades no catalogadas; sin ejecutar handlers, ni divulgar datos.
- Lectura del registro Flask para comprobar que el scanner puede consumir métodos GET reales y nunca los ejecuta.

Se ejecutan también las suites P25–P32, Contact Center, compras/finanzas, Track Alerts y otros contratos que ya son CI. No se hicieron requests mutantes autenticados reales, envíos SMTP/SMS, publishes, login de usuarios de prod, ni cambios a DB.

## 4. Qué falta para cerrar Fase A

1. **GET P34:** ejecutar manualmente lector sobre backend actualizado tras merge, guardar sólo agregados y metadatos seguros; evaluar uno a uno los GET P1 (sobre todo descargas, PII, OAuth e internos) con pruebas de 401/403/404 y scope por documento/sucursal. Evitar leer/exportar datos personales.
2. **Operaciones P35:** para las 102/112 rutas, verificar además delegación de servicios, casos de roles positivos/negativos, scope/objeto/estado y si deben recibir una acción de catálogo específica; los 29 grupos de P32 son propuestas de capacidades, **no** permisos nuevos aprobados.
3. **Snapshot histórico:** recuperar ambos cortes completos para explicar 111→112 sin suposiciones.
4. Solo entonces decidir en un bloque funcional migraciones Alembic para mapear acciones sin sustituir guards ni otorgar grants automáticos.

**Cambios P33:** lector GET manual, CSV de 102, informe, tests y CI. **Sin cambio funcional en endpoints, roles, grants o esquema**, sin migraciones, sin despliegue inmediato. La issue global #1053 sigue abierta.
