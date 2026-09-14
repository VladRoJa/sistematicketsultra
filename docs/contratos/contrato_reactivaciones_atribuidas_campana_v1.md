# Contrato — Reactivaciones atribuidas a campaña V1

## Objetivo

Cerrar el ciclo operativo de Marketing > Reactivación para poder demostrar, con evidencia auditable, qué destinatarios de una campaña enviada regresaron posteriormente a estado activo y qué campaña recibe el crédito.

Esta métrica se denomina **Reactivación atribuida a campaña**. No sustituye ni modifica el KPI corporativo `Reactivaciones` de KPI Desempeño/Track.

## Flujo

`Vencido -> elegible -> campaña -> destinatario congelado -> SENT -> seguimiento -> reactivación atribuida -> resultado`

El destinatario congelado conserva la fotografía de quién fue incluido. El resultado posterior vive en una tabla 1:1 separada.

## Campañas atribuibles

Generan seguimiento:

- `WINBACK`
- `VENCIDOS_RECIENTES`
- `COBRANZA_LIGERA`
- `BORRON_CUENTA_NUEVA`
- `PERSONALIZADA` con `universo=VENCIDOS`

No generan atribución:

- `PROXIMOS_VENCER`
- `BASCULA_RETENCION`
- `INVITA_GANA`
- `PERSONALIZADA` con `universo=ACTIVOS`

Solo campañas con estado `SENT` participan. `DRAFT` y `EXPORTED` nunca cuentan como contacto realizado.

## Inicio y ventana de atribución

El seguimiento inicia en `campaign.sent_at`.

V1 utiliza una ventana fija de **14 días calendario**, persistida en cada campaña como `attribution_window_days=14`.

La comparación se realiza en `America/Tijuana`:

`sent_at_local < fecha_ultimo_pago_local <= sent_at_local + 14 días`

Un pago anterior o igual al envío no es atribuible. Un pago posterior al cierre tampoco.

## Fuente de verdad

La evidencia primaria es un snapshot **canónico** de Socios Activos.

Para cada destinatario se conserva el `socios_vencidos_cartera_id` original y se reutiliza el resolver vigente de identidad entre Socios Vencidos y Socios Activos.

No se implementa un matcher paralelo y nunca se declara una reactivación únicamente por coincidencia de teléfono.

## Regla REACTIVATED

Un destinatario se marca `REACTIVATED` únicamente cuando:

1. pertenece a una campaña atribuible `SENT`;
2. posee identidad vencida auditable;
3. el resolver vigente produce `ACTIVE_CONFIRMED` contra un snapshot canónico;
4. la fila activa tiene `fecha_ultimo_pago_local`;
5. el pago ocurre después del envío y dentro de la ventana;
6. la campaña gana la atribución last-touch.

La fecha de reactivación es `fecha_ultimo_pago_local`, no la fecha en que Suite detectó el cambio.

La evidencia persistida incluye snapshot, fila exacta, `active_id_socio` y sucursal observada.

## Identidad dudosa

Mapeo del resolver:

| Estado resolver | Resultado |
| --- | --- |
| `ACTIVE_CONFIRMED` | candidato a `REACTIVATED` |
| `ACTIVE_REVIEW` | `REVIEW` |
| `AMBIGUOUS` | `REVIEW` |
| `IDENTIFIER_CONFLICT` | `REVIEW` |
| `NOT_FOUND` | `PENDING` mientras la ventana siga abierta |

Suite falla hacia el lado conservador. `REVIEW` puede resolverse en ejecuciones posteriores.

## Last-touch

Una misma reactivación puede acreditarse a una sola campaña.

Si un episodio vencido fue incluido en varias campañas `SENT`, gana la campaña con el `sent_at` más reciente que sea anterior al pago y cuya ventana todavía incluya ese pago.

Ejemplo:

- campaña A: 1-sep
- campaña B: 8-sep
- pago: 10-sep

Resultado: B recibe el crédito; A no lo duplica.

## Estados de outcome

- `PENDING`: ventana abierta, sin evidencia concluyente.
- `REACTIVATED`: reactivación confirmada y atribuida. Es terminal.
- `REVIEW`: existe posible coincidencia pero la identidad/evidencia no es suficiente.
- `WINDOW_CLOSED`: la fuente canónica ya cubre el final de la ventana y no hubo reactivación atribuible.

`WINDOW_CLOSED` nunca se determina únicamente por el reloj. Se requiere un snapshot canónico con `cutoff_date >= fin de ventana`.

## Persistencia

### Campaña

`marketing_reactivation_campaigns.attribution_window_days`

V1: 14. Constraint permitido: 1 a 90 días.

### Resultado 1:1

Tabla:

`marketing_reactivation_campaign_recipient_outcomes`

Campos principales:

- `campaign_recipient_id` único
- `status`
- `reactivated_at_local`
- `active_snapshot_id`
- `active_snapshot_row_id`
- `active_id_socio`
- `active_sucursal`
- `review_reason`
- `first_detected_at`
- `last_checked_at`
- `created_at`
- `updated_at`

`days_to_reactivation` es derivado y no se persiste.

## Historia

El motor puede revisar snapshots canónicos históricos posteriores al envío. Esto permite detectar a una persona que estuvo activa durante la ventana aunque ya no aparezca activa en el snapshot actual.

Una vez persistido `REACTIVATED`, el resultado es terminal y no desaparece por cambios posteriores del universo activo.

## Automatización

Servicio:

`backend/app/services/marketing_reactivation_outcome_service.py`

Job:

`backend/app/warehouse/jobs/reactivation_outcomes_daily_job.py`

Scheduler:

`reports-scheduler`

Horario default: **09:15 America/Tijuana**, después de `reactivation_sources_daily` de las 09:00.

Si las fuentes del día no terminaron, outcomes no se considera completado y agenda retry. El ciclo existente mantiene `db.session.remove()`.

El job es idempotente y puede procesar campañas `SENT` históricas para las que exista evidencia disponible.

## API

- `GET /api/marketing/reactivation/outcomes/summary`
  - `date_from`
  - `date_to`
  - `region_id`
  - `sucursal`
- `GET /api/marketing/reactivation/outcomes/campaigns/<campaign_id>`
- `POST /api/marketing/reactivation/outcomes/run`

Todos los endpoints vuelven a resolver permisos en backend.

## Métricas

Principal:

`Reactivados atribuidos / destinatarios enviados`

Se exponen:

- enviados
- reactivados
- conversión
- pendientes
- review
- ventana cerrada
- en seguimiento (`PENDING + REVIEW`)

El denominador es la audiencia congelada de la campaña `SENT`, no el preview original.

## Alcance geográfico

Los resultados respetan el alcance de Marketing existente.

El crédito operativo queda en la sucursal desde la que se realizó la campaña. Si el socio reaparece activo en otra sucursal, esa sucursal se conserva como evidencia pero no mueve automáticamente el crédito.

## Frontend

La ruta sigue siendo:

`/#/marketing/reactivation`

La preparación de campañas no cambia. Debajo se incorpora seguimiento con filtros de periodo, región y sucursal, tarjetas de enviados/reactivados/conversión/en seguimiento y drill-down de reactivados por campaña.

## Fuera de V1

- métrica `Respondió`;
- lecturas de WhatsApp;
- ingreso recuperado;
- modificación del KPI de Reactivaciones de Track;
- envío automático hacia iVentas;
- cambios a reglas actuales de elegibilidad, tarifas o protección semanal.

## Deploy

La PR requiere migración Alembic:

```bash
docker compose exec -T backend flask db upgrade
```

Después se reconstruyen backend, frontend y reports-scheduler según el flujo normal de producción.
