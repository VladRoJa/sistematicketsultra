# Suite Ultra — Google Ads M6: sincronización diaria automática y certificación por sucursal

**Fecha:** 2026-10-13  
**Estado:** PROPUESTA CONTRACTUAL / GATE A PENDIENTE. Ningún scheduler ni escritura automática autorizado.  
**Dependencias:** OAuth M1, Google Ads API M2 (solo lectura), Warehouse M1/M3, alias M4, asociaciones históricas M5, Funnel M5 y Contrato Control de Automatizaciones V1.

## 1. Resultado funcional buscado

Actualizar Google Ads **sin exportar Excel manualmente** para que el Funnel muestre campañas, inversión y desglose de grupos por sucursal, con fecha efectiva, evidencia de corrida, conciliación y semáforo de frescura. Respetar permisos por sucursal del backend. No sumarlo a Meta ni alterar `summary.investment`, `branches[].investment`, CPL, CPT, CAC, ventas CRM o snapshots Track.

La fuente Google Ads histórica fue validada al 2026-10-08 y no autoriza automáticamente fechas posteriores:
- Cuenta `2739125201`; XLSX físico Warehouse `21499`; 645 filas grupo-día, 43 triples y 15 días (24-sep–08-oct).
- 26 asociaciones **`APPROVED_PROVISIONAL_XLSX`** para dicho período: 17,624.73 MXN atribuidos, 1,501.64 MXN sin asignación; cuenta 19,126.37 MXN.
- **Identidades oficiales de campañas/grupos aún NO verificadas.** No extender `valid_to` de M5 ni sobreescribir sus hechos manuales.

## 2. Auditoría verificada en el repo

| Capa | Existe | Brecha antes de automatizar |
|---|---|---|
| OAuth | `backend/app/routes/google_ads_oauth_routes.py` cifra refresh token y lo asocia a cuenta fija | Confirmar estado y permiso Google de producción sin divulgar secretos |
| API REST | `backend/app/services/google_ads_readonly_service.py` y rutas `/account-check`, `/campaign-daily`; API version `v25`; 1–31 días, límites de filas/lotes | Solo campañas por día, **sin persistencia**, sin ad groups, sin conversion action IDs, sin job |
| Ledger manual | `google_ads_daily_metrics` y `google_ads_daily_ingestion_service.py` | Claves `name:hash` derivadas del Excel, `source_upload_id` obligatorio, conflicto ante correcciones |
| Detalle manual | `google_ads_ad_group_daily_metrics` y servicio M3 | Fuente XLSX, `campaign_id` y `ad_group_id` `NULL`; no constituye fuente aditiva |
| Mapping M5 | `google_ads_branch_identity_mappings` y lector M5 | Solo upload 21499, período fijo 24-sep..08-oct, aprobación provisional, **no admite extensión automática** |
| Scheduler | `backend/app/services/marketing_scheduler_worker.py` ejecuta iVentas/Meta y estadística Campaign V2 opcional, con prioridad Track | No hay tarea Google Ads; no integrar al éxito/fallo de iVentas/Meta hasta definir aislamiento |
| Observabilidad | `backend/app/services/automation_control/job_catalog.py` y contrato transversal | No registrar Google Ads como job real/activo hasta tener ejecución persistida verificable |

La configuración privada y la autorización OAuth **en producción** no se infieren de archivos del repositorio. Lo primero es confirmar `account-check` real para la cuenta objetivo.

## 3. Reglas de origen, identidad y cálculo

1. **Raw first.** Guardar respuesta inmutable (contenido JSON normalizado + hash SHA-256, metadatos de cuenta, versión API, GAQL, rango, moneda y zona horaria), con identidad de `sync_run`; jamás persistir access/refresh tokens ni respuestas de error sin sanear. Diseñar relación con Warehouse y retención antes de publicar.
2. **Lecturas separadas:** campaña-día es autoridad de gasto de cuenta; grupo-día detalla la misma inversión y NO se suma como fuente adicional. Tomar `cost_micros` enteros de Google y comparar en micros; convertir a MXN usando `Decimal` solamente para presentación/columnas monetarias. No permitir doble conteo por join con conversion actions.
3. **IDs oficiales:** fijar cliente `2739125201`, consultar `campaign.id` / `ad_group.id` en ad groups por fecha. Reconciliar explícitamente las 26 identidades históricas nombre-hash con las oficiales usando período coincidente, importes, clics, impresiones y campaña. Prohibido autorizar por homonimia/fuzzy, por grupo aislado o por inferencia del nombre de sucursal.
4. **Mappings futuros:** entidad/versión nueva con `customer_id + campaign_id + ad_group_id + valid_from/to + sucursal_id + evidence + approved_by + approved_at` y reglas contra superposiciones. IDs desconocidos, renombrados, desactivados o nuevos `ad_group_id` con gasto: **PENDING_REVIEW / sin asignar**. `Marca` y `EGADE` permanecen excluidos hasta aprobación explícita.
5. **Conversiones:** Google Ads API **no expone columnas personalizadas** del XLSX. Identificar y aprobar por ID las `conversion_action` reales de **Pase gratis Ads** y **Compra web Ads**; consultar las métricas segmentadas por `segments.conversion_action` sin sumar gasto ni tráfico repetidos por segmento. No equiparar estas conversiones a compras confirmadas CRM.
6. **Conciliación:** por cuenta/día, `SUM(campaign.cost_micros) = SUM(ad_group.cost_micros)`; comprobar además clics/impresiones, unicidad, moneda, zona horaria, cobertura de grupos y ausencia de truncamiento. Frente a diferencias o ajustes tardíos, usar versión/revisión nueva del snapshot y bloquear publicación automática; no mutar histórico XLSX.
7. **Calendario:** usar día de negocio en la zona horaria real de la cuenta (verificarla en `account-check`), mostrar corte en `America/Tijuana`. No publicar hoy como completo antes de cerrar el día de Google. Revisión de hasta varios días recientes por conversiones tardías mediante snapshots versionados; **sin sobreescritura silenciosa**.
8. **Alcance:** el backend filtra consultas de atribución por `MarketingAccess`; no globales jamás consultan ni reciben ledger completo, cuenta global ni `unassigned`. Estado `partial/requires_review/unavailable` nunca equivale a cero.

## 4. Ejecución y seguridad

- Proceso aislado **fuera del request Flask**; candidato: job separado en `marketing-scheduler` si su ventana de prioridad y duración lo permite. No bloquear iVentas, Meta ni Track; si el trabajo crece, worker dedicado bajo profile `scheduler`.
- Tres flags separados: lectura API existente, preparación/preview nuevo y **publicación automática**, siendo el último **false por defecto**. Revocación/errores detienen el job; no afectar el resto de Suite.
- Un solo `run_id` por cuenta, fecha, source revision y disparador; bloqueo transaccional, idempotencia, reintentos con límites, backoff 429 y observancia de cuotas Google. Una repetición no crea filas duplicadas.
- Estados: `REQUESTED → RUNNING → VERIFIED → PUBLISHED` o `PARTIAL/REQUIRES_REVIEW/FAILED`; `PUBLISHED` solo si source, identidad, montos, coverage y permisos cumplen todos los gates.
- Guardar run, intento, error sanitario, fechas cubiertas, contador de filas, hash de fuente y revisión publicada. Vincular `marketing.google_ads_sync` al **Control de Automatizaciones** solo cuando exista job y evidencia real. «Ejecutar ahora» requerirá contrato, autorización y cola; no disparar sincronización desde el HTTP.
- Semáforo del bloque Google Ads independiente del semáforo general del Funnel: esperado vs último corte exigible, SLA definido y estado `NOT_DUE/UP_TO_DATE/LAGGING/LATE/UNKNOWN/DISABLED`. Éxito de worker no significa datos completos.

## 5. Fases y gates de ejecución (una validación cada vez)

**M6-A — API preflight, solamente lectura.** Desde UI admin Google Ads: `/oauth/status`, `/account-check`, y `/campaign-daily` para un día cerrado acotado (p.ej. 2026-10-08). Confirmar `account_access_verified=true`, ID 2739125201, moneda MXN, zona horaria, `snapshot_persisted=false` y equivalencia contra Warehouse. No revelar secretos. Si falla, detenerse.

**M6-B — ID y conversion-action discovery.** Ampliar el servicio read-only con consultas GAQL estrictas para grupos y acciones, límites y errores sanitizados. Sin escribir DB, sin scheduler. Validar triples históricos y documentar conflictos/no-matches. No publicar nuevas asociaciones automáticamente.

**M6-C — Raw/snapshots/ledger versionado.** Nuevas tablas mediante **Alembic** para sync_runs, raw manifest+hash, campaign/group diario por IDs y aprobaciones explícitas. Mantener XLSX y sus asociaciones M5 intactos. Probar PG16 real, deduplicación, concurrencia, correcciones y conciliación. Guardas de transacción.

**M6-D — Operación manual controlada.** Preview `CHECK_ONLY`, dry run y corrida administrativa aislada (no desde Gunicorn), con autorización separada para guardar y después publicar. Demostrar mismos números que Google/Excel y scopes global/gerente/regional. Ventas y Meta sin diferencias.

**M6-E — Scheduler apagado por defecto.** Job opt-in por fecha cerrada, tiempo negociado con schedulers existentes, reintentos, recuperación, log seguro y semáforo Control de Automatizaciones. Probar fallos, bloqueo, restart, duplicados y caída OAuth. Habilitar solo con orden explícita y evidencia de M6-D.

**M6-F — Funnel.** Resolver fuente aprobada por corte y sucursal, indicando provisional/certificada y cobertura; no duplicar campaña-día con grupo-día. Vigencia M5 y fuente nueva no se mezclan silenciosamente. Revalidar Angular, backend, datos e inventario de métricas.

## 6. Criterios de aceptación innegociables

- Sin secretos en repo, salidas, capturas, logs ni auditorías; permiso backend ADMINISTRADOR/ADMICORP según contrato aprobado para controles.
- Al menos un día cerrado confirmado contra Google Ads UI/Excel antes de cualquier escritura automática.
- Pruebas negativas de token revocado, cliente equivocado, moneda/fecha, respuesta parcial, cuotas, ID desconocido, conversion action ambigua, revisiones tardías, duplicidad, fallo de fuente, cuenta MCC y permisos restringidos.
- Misma inversión de cuenta con o sin desglose. `summary.investment`, `branches[].investment`, Meta, CPL/CPT/CAC, ventas CRM, iVentas y Warehouse histórico sin mutaciones.
- CLI/PR/CI por fase; migración previa al uso. Deployment por git pull + Docker Compose del servicio pertinente, **nunca editar código manualmente en el servidor**.

## 7. Primer gate operativo

Abrir `/#/marketing/google-ads` con usuario administrador y comprobar el estado de OAuth y el botón de verificación de cuenta. Necesitamos **solo** resultado seguro: `enabled`, `authorized`, `account_access_verified`, `customer_id`, `currency_code`, `timezone` y código de error si aplica. No recopilar refresh token, client secret, clave Fernet, access token ni capturas de URLs de consentimiento.

Referencias API: https://developers.google.com/google-ads/api/docs/api-policy/developer-token ; https://developers.google.com/google-ads/api/docs/conversions/reporting ; https://developers.google.com/google-ads/api/rest/common/search .
