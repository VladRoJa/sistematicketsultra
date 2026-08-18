# Track Inteligencia Regional V2

## Alcance

Esta vista es un centro de seguimiento operativo diario por región y sucursal.
No sustituye la pantalla legacy de Inteligencia Regional y no crea escrituras ni
eventos en `track_alert_events`.

La vista Angular nueva usa la ruta:

`/#/warehouse/track-intelligence/regional-operational`

La pantalla legacy conserva:

`/#/warehouse/track-intelligence/regional`

Ambas consumen `GET /api/track-alerts/regional-detail`. La representación nueva
se solicita con `view=operational`; omitir el parámetro conserva el contrato
legacy.

## Versión efectiva del Track

La autoridad de resolución es
`backend/app/warehouse/services/track_daily_query_version_service.py`.

- Día actual con `manual_preview`: `preview_operativo`.
- Históricos: `cierre_canonico`.
- Fallback histórico: `base_nocturna_canonica`.
- Una versión solo es utilizable si contiene filas del Mart.
- Todas las filas regionales se consultan por
  `TrackDailyMartORM.track_daily_version_id == resolved_version.id`.

No se combinan filas por `track_date + generation_mode`.

## Universo regional

La consulta reutiliza:

- `suite_regions` con `is_active = true`;
- `suite_sucursal_region_assignments` con `is_current = true`;
- `track_branch_catalog` con `is_track_active = true`.

Una sucursal con más de una asignación regional current produce un error de
integridad explícito; no se selecciona una región de forma silenciosa.

## Reglas de métricas

### Clientes nuevos

Pesos weekday aprobados:

| Día | Peso |
| --- | ---: |
| Lunes | 39.353 |
| Martes | 20.504 |
| Miércoles | 15.574 |
| Jueves | 11.104 |
| Viernes | 7.613 |
| Sábado | 2.721 |
| Domingo | 3.130 |

Los pesos se aplican a todos los días naturales del mes y después se
normalizan para sumar exactamente 1.

`expected_mtd = monthly_target * expected_progress_ratio`

`gap_units = actual_mtd - expected_mtd`

`gap_pct_points = actual_progress_pct - expected_progress_pct`

### Reactivaciones

Utiliza la misma normalización mensual, con su perfil propio:

| Día | Peso |
| --- | ---: |
| Lunes | 41.609 |
| Martes | 20.866 |
| Miércoles | 14.319 |
| Jueves | 9.365 |
| Viernes | 5.290 |
| Sábado | 3.967 |
| Domingo | 4.584 |

### Bajas

No utiliza curva weekday ni deltas diarios.

`limit_usage_pct = bajas_reales_mtd / meta_bajas_mes * 100`

`remaining_margin = meta_bajas_mes - bajas_reales_mtd`

Solo existe `LIMITE_EXCEDIDO` cuando
`bajas_reales_mtd > meta_bajas_mes`.

### Domiciliados, Ingreso y Tienda

Muestran avance simple contra meta, sin curva weekday:

`compliance_pct = actual_mtd / monthly_target * 100`

`remaining_to_target = max(monthly_target - actual_mtd, 0)`

Ingreso utiliza `ingreso_real_total_mtd`. Solamente cuando ese campo es nulo
usa el fallback transitorio `ingreso_real_mtd`.

### Proyección de Ingreso

Reutiliza la curva histórica estable y los controles de calidad existentes en
`track_forecast_service.py`. Si la historia comparable no pasa esos controles,
la respuesta es `insufficient_history` y `projected_close` permanece nulo. No
existe fallback lineal.

### Usuarios

La única operación es:

`users_gap = usuarios_activos_actual - proyeccion_usuarios_cierre_mes`

Se presenta como Brecha de usuarios. No usa `m2_sin_circulaciones` ni genera
alerta de ocupación.

## Estados y prioridades

Para Clientes nuevos y Reactivaciones:

- `gap > 0`: `ADELANTADO`.
- `gap = 0`: `EN_RITMO`.
- `gap < 0`: `DEBAJO_RITMO`.
- Meta nula o no positiva: `SIN_META`.
- Actual nulo: `DATOS_INSUFICIENTES`.

No existe tolerancia implícita ni threshold porcentual.

Las prioridades se devuelven en listas separadas para Clientes nuevos,
Reactivaciones y Bajas. Las dos primeras se ordenan por
`gap_pct_points` ascendente; Bajas se ordena por exceso sobre el límite. No se
calcula un score común entre KPIs incompatibles.

El detalle por sucursal siempre se conserva aunque el agregado regional esté
adelantado.

## Permisos y rollout

`regional-detail` exige JWT y el permiso de lectura Track existente. El backend
es la autoridad de acceso.

El rollout visual inicial se limita al username `ADMICORP` en:

`frontend/src/app/warehouse/track-intelligence-regional-operational/track-regional-operational-access.guard.ts`

Los roles previstos están comentados en `ENABLED_ROLES`. Para ampliar el
rollout, se habilitan ahí; no se cambia el permiso backend ni se duplica la
lógica en el dashboard.
