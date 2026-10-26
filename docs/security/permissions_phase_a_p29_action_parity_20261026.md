# Suite Ultra — Fase A P29: acciones existentes frente a 112 rutas sin mapeo

**Corte del catálogo:** 26-oct-2026 22:30 UTC, recogido con `permission_route_inventory.py` en modo PostgreSQL READ ONLY. **Base de este trabajo:** P28 ya fusionado en `main`. El SHA del backend que ejecutó el corte PostgreSQL no se incluyó; esta matriz no certifica paridad de despliegue ni reconstruye la tabla `permission_actions` productiva.

## Decisión central

**No debe confundirse `permission_route_map` (observabilidad) con un control efectivo, ni reutilizar una acción legacy solo porque su nombre se parece a la operación.**

El nuevo anexo [P29: matriz por operación](permissions_phase_a_p29_action_reconciliation_20261026.csv) conserva **las 112 identidades P28** con cinco campos adicionales de decisión: `historical_seed_action_candidate`, `proposal_state`, `backend_gate_to_verify`, `boundary_to_verify` y `runtime_permission_proven`.

| Estado diagnóstico | Rutas | Decisión |
|---|---:|---|
| `candidate_requires_guard_parity` | **10** | Hay una acción **semánticamente plausible** en migraciones históricas; aún se debe demostrar paridad de guard, rol, sucursal, objeto, estado y hard stops |
| `requires_operational_action_decision` | **102** | No se asigna una acción antigua por aproximación; antes de proponer una nueva, evaluar reutilización segura con una decisión funcional |
| `runtime_permission_proven=YES` | **0** | No se simuló una autorización final de los 112 actores/objetos ni se inspeccionaron grants actuales |

Las **10 asociaciones provisionales** son:
- `tickets.update` (4): coordinación, reasignación de mantenimiento y dos recepciones de Tapizado. **No dar por hecho** que recepción o reasignación equivale a editar libremente un ticket.
- `tickets.update_status` (2): devolver trabajo al técnico y marcar trabajo terminado. Deben respetarse asignación, rol y estado.
- `inventory.master_write` (1): corregir código interno; validar unicidad/autoría/auditoría.
- `inventory.movement_write` (1): anular movimiento; conservar validaciones de existencias y concurrencia.
- `openings.manage` (1): marcar apertura; validar rol y estado.
- `users.manage` (1): actualizar el acceso modular de un usuario; requerir admin DB, hard stops y auditoría. **No autoriza editar permisos por sí sola**.

Estos nombres se encuentran en **migraciones semilla históricas**; no se corroboró que cada acción exista, esté activa o sea asignable en el catálogo productivo vigente. Ninguna de las 10 asociaciones se incorpora automáticamente a `permission_route_map`.

## 17 familias — decisión de tratamiento

| Familia | Total | Candidatos semilla | Pendientes de decisión |
|---|---:|---:|---:|
| Marketing | 42 | 0 | 42 |
| Requisiciones | 19 | 0 | 19 |
| Integraciones (Google Ads) | 11 | 0 | 11 |
| Contact Center | 10 | 0 | 10 |
| Tickets | 6 | 6 | 0 |
| Track Alerts | 5 | 0 | 5 |
| Auth | 3 | 0 | 3 |
| Inventario | 3 | 2 | 1 |
| Chequeo Diario | 3 | 0 | 3 |
| Routine Control | 2 | 0 | 2 |
| Warehouse | 2 | 0 | 2 |
| Planner | 1 | 0 | 1 |
| Mantenimiento de equipos | 1 | 0 | 1 |
| Aperturas | 1 | 1 | 0 |
| Permisos | 1 | 1 | 0 |
| RPA SMS | 1 | 0 | 1 |
| Track | 1 | 0 | 1 |
| **Total** | **112** | **10** | **102** |

`requires_operational_action_decision` **no significa automáticamente que deban crearse 102 permisos**. Varias rutas pueden utilizar una misma capacidad bajo condiciones distintas, y algunos métodos POST son consultas o vistas previas. El fichero conserva los **35 grupos funcionales** de P28 para discutir políticas por bloques.

## Guard real, alcance y side effects: evidencia disponible

La matriz distingue **qué mecanismo se debe auditar** de **autorización comprobada**. Se revisaron señales estructurales en handlers concretos y se añadieron regresiones de su presencia; eso no valida todos los caminos de servicio.

- **Marketing:** `campaign_v2_governed_execute_endpoint` utiliza `_resolve_campaign_v2_dispatch_config_request`, requiere envío y contiene step-up ligado al actor. `campaign_v2_preview_endpoint` usa `_resolve_campaign_v2_request`. `commercial-attribution/summary` usa POST para una lectura batch, de modo que no es apropiado crear permiso de mutación solo por el verbo. Preservar la diferencia entre management regional, dispatch global, estados y banderas.
- **Requisiciones:** las rutas de aprobación/rechazo financiero resuelven `_current_user` y delegan la decisión a `approve_purchase_requisition_quote_by_finance` / `reject_purchase_requisition_quote_by_finance`. Mantener estados, aprobadores autorizados y separación de la configuración de aprobadores; `_current_user` **no es un permiso de aprobación**.
- **Contact Center:** `post_verify_purchase` usa `_context`, `_assert_operator_access` y `_assert_appointment_access`; `post_contact` pasa `allowed_branch_ids` para gerentes al servicio. Verificar caso, cita, sucursal, titularidad y fusión/importación.
- **Chequeo Diario:** `today_submit` y `today_postpone` pasan `_requested_branch_id` a servicios; rollout BI tiene `_require_bi_access`. Revisar restricciones del servicio, evidencias, rollback y cambios globales.
- **Integraciones:** en Google Ads M6, `publish_google_ads_m6_manual_day` requiere bandera, `require_current_admicorp` y `require_warehouse_upload`. **Ingesta no es publicación**, y OAuth tiene un contrato diferente.
- **Tickets/Inventario:** las acciones candidatas exigen validar asignado, sucursal, estado, códigos únicos, movimiento reversible y registro de auditoría. No cambiar su enforcement por simple mapeo.
- **Auth:** `login`, `refresh` y `logout` son **excepciones intencionales** al `@jwt_required()` porque verifican contraseña o sesión/cookie. Añadirles JWT por homogeneidad bloquearía el login.
- **Permisos:** `update_user_module_access` llama `_current_admin_user_or_error`; no convertir `users.manage` en una autorización de editar cualquier grant ni omitir hard stops.
- **Track:** `request_track_canonical_close_endpoint` llama `_require_track_admin_role` y crea una solicitud para el scheduler; **no es equivalente sin más** a `track.run_daily_pipeline`.
- **RPA SMS:** `create_gasca_sms_request_route` usa `_require_module_access`; evaluar sucursal y envío diferido.
- **Warehouse / Track Alerts / Routine Control / aperturas / mantenimiento:** revisión de actor, sucursal, estado, canal de side effects y trazabilidad pendiente antes de tomar decisiones finales.


## Hallazgo de seguridad P29-S1 — Track Alerts (remediación de backend)

La suite estructural P29 detectó una **ausencia real de `@jwt_required()` en cinco POST** de `backend/app/track_alerts/routes/track_alert_routes.py`: `/test`, `/generate`, `/regional-test`, `/send-email` y `/send-regional-email`. Al revisar el Blueprint también aparecieron **dos GET de preview de correo** sin JWT: `/preview-email` y `/regional-preview-email`. En esos handlers originales no había un check alternativo de rol; `app.before_request` solo atiende preflight OPTIONS. **Por lectura de código eran rutas con riesgo de ejecución anónima**, incluidas generación de eventos y envíos SMTP. No se hicieron solicitudes a producción ni se enviaron correos reales para demostrar una explotación.

**Corrección en este mismo PR:** se añade `@jwt_required()` y la comprobación de rol basada en usuario BD a esas siete rutas. Se reutilizan los guards existentes `_require_track_read_role()` para las 4 vistas/consultas y `_require_track_admin_role()` para los 3 efectos (generar eventos, enviar correo nacional, enviar correo regional). Se devuelve 403 ante rol insuficiente, antes de invocar servicios, y JWT ausente devuelve 401. Quedan intactas las otras dos rutas GET de detalle que ya estaban protegidas. Los roles de lectura del Track pueden consultar vistas previas, pero no generar ni enviar.

**Otra excepción descubierta:** `POST /api/warehouse/internal/gasca-report-jobs` tampoco lleva JWT **porque es un endpoint máquina→máquina**, protegido por `X-Suite-Internal-Token` con comparación `hmac.compare_digest`, y rechaza si el secreto no está configurado. Exigir JWT de usuario allí rompería el contrato interno. Test sintético comprueba 403 antes del orquestador si falta el token o es incorrecto. No imprimir ni persistir el secreto en reportes.

Las regresiones HTTP sintéticas de `backend/tests/test_track_alert_routes_p29_auth.py` validan siete respuestas 401 sin JWT, 403 por rol, cero invocaciones de servicios de envío/generación en rechazados y éxitos simulados por rol permitido. No se usó SMTP, proveedor externo ni base productiva. **Este hallazgo sí altera enforcement de Track Alerts** y exige desplegar backend tras revisión/merge por el flujo de producción. No hay cambios SQL ni migraciones. El alcance funcional necesita aceptación de política: solo roles administradores de Track pueden generar/enviar alertas.

## Qué garantizan las pruebas de P29 (y qué no)

`backend/tests/routes/test_permissions_phase_a_p29_action_reconciliation.py`:
1. Exige relación 1:1 de **112** filas con P28, sin alterar IDs de método/ruta/handler/familia/riesgo.
2. Verifica que solo las **10 asociaciones provisionales explícitas** apunten a claves encontradas en los seeds históricos; las otras **102** no se rellenan por inferencia.
3. Revisa la presencia estructural de `@jwt_required` en rutas de usuario, y reconoce **auth (credenciales/cookies)** y **Warehouse internal jobs (token compartido)** como excepciones con controles propios.
4. Verifica señales puntuales en handlers sensibles de permisos, Track, SMS, Marketing dispatch, finanzas, Contact Center, Chequeo Diario y publicación de Google Ads.

No se ejecutan endpoints ni servicios, no se consultan datos productivos, no se modifica ningún guard o grant y no se resuelve la precedencia de excepciones. Las pruebas estructurales pueden fallar por refactors seguros y deberán ajustarse solo tras revisar el nuevo contrato real.

## Siguiente cierre de Fase A

1. Obtener un corte read-only de `permission_actions` y `permission_route_map` en **el mismo backend/DB**, incluyendo activación de módulo/acción y SHA ejecutado; contrastar candidatos y roles/grants vigentes antes de proponer una migración.
2. Consolidar decisiones de acción por **grupo funcional**. Especial atención a 42 Marketing, 19 Requisiciones, 11 Integraciones y 10 Contact Center, con step-up, propietario, sucursal y hard stops.
3. Para cada grupo, verificar 401/403/200/409 por actor, sucursal/objeto, ausencia de side effects en denegaciones y auditoría de excepciones. Priorizar cambios de permisos administrables solo después de esa equivalencia comprobada.
4. Inventariar los **247 GET sin catálogo**, particularmente exportaciones y datos sensibles. Determinar variación histórica 111→112 a partir de snapshots históricos completos; no atribuir a Tapizado u otra causa sin diff.
5. Si procede incorporar mapeos o acciones, escribir **migración Alembic** explícita y revisable que **no active grants ni sustituya guards legacy**. Revalidar paridad después del despliegue autorizado.

**P29-S1 sí corrige enforcement en siete rutas Track Alerts.** Fuera de esa remediación no se modifican los 112 mapeos del catálogo, los grants, las acciones, otros guards ni BD. La Fase A #1053 sigue OPEN. Ni 112 ni 102 son permisos nuevos que haya que otorgar.
