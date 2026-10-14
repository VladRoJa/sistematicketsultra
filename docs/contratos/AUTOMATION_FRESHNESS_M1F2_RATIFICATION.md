# Control de Automatizaciones — M1-F2: evidencia y decisiones de exigibilidad

Estado: **propuesta para decisión de negocio**. Ningún horario de este
documento constituye un SLA ratificado ni activa semáforos en producción.

## Lo que sí queda comprobable técnicamente

1. **Track:** `track_branch_catalog.is_track_active` + exclusión de demos
   es el universo usado por `_load_active_analytical_branches()` al crear el
   mart. Una versión elegible requiere `is_current=true`,
   `status=success`, `version_type=cierre_canonico` (preferida) o
   `base_nocturna_canonica` y filas con el mismo
   `track_daily_version_id`, `track_date` y
   `generation_mode=official_closed_day`. Se detectan sucursales faltantes,
   sobrantes y repetidas. *No* se considera el preview.
2. **Funnel:** el corte compartido requiere la intersección de iVentas
   COMPLETED, Meta COMPLETED, Venta Total canónica daily, detalle de
   ventas nuevas canónico MTD y KPI canónico daily; los periodos anteriores
   a julio 2026 no certifican los cinco componentes CRM.
3. **Horarios técnicos actuales del código (no contratos SLA):**
   Track base nocturna 23:30 America/Tijuana por defecto, reintento 00:30
   sujeto al fallo anterior, cierre canónico sujeto a disponibilidad de
   agregadoras; Marketing sincronización por slots 08:20/12:20/16:20/20:20
   por defecto con retry a partir de 15 minutos. **En producción pueden
   existir overrides**; los reporta el worker vía M1-C.

## Lo que el catálogo Track todavía no demuestra

El catálogo Track **no tiene fechas de validez** (inicio/fin de inclusión
por sucursal). Por ello una versión histórica que coincida con el
catálogo activo *hoy* **no equivale a cobertura histórica certificada**.
El endpoint M1-F2 presenta `latest_catalog_matched_business_date`, cuentas
y diferencias, pero deja `latest_complete_business_date=null`,
`expected_business_date=null`, `due_at=null` y `status=UNKNOWN`.

No introducir una tabla de vigencias como migración hasta definir la
fuente autoritativa del calendario de aperturas, cierres y exclusiones
Track. Un backfill automático desde estado actual fabricaría historia.

## Decisiones de negocio que faltan

| Dataset | Decisión pendiente | Responsable propuesto |
| --- | --- | --- |
| Track Daily | ¿El corte exigible es el del día anterior o del mismo día después de base nocturna/cierre? ¿Qué estado requiere: base, cierre con agregadoras o ambos? | BI + Operaciones |
| Track Daily | ¿Hora límite local America/Tijuana y margen en fallos/reintentos? ¿Qué hacer fines de semana y festivos? | BI + Operaciones |
| Track Daily | ¿Dónde se registra vigencia de cada sucursal para cada business_date, incluyendo nuevas aperturas? | Operaciones + BI |
| Funnel Venta Nueva | ¿Qué corte debe existir por slot: mismo día parcial o día anterior cerrado? | Marketing + BI |
| Funnel Venta Nueva | ¿Cuánto tiempo después del slot vence iVentas/Meta y qué tolerancia para Warehouse/canonicalidad? | Marketing + BI |
| Ambos | ¿Cómo definir `LAGGING` frente a `LATE`, política para fines de semana y periodo histórico consultado? | Dirección + BI |

## Gates para habilitar semáforos

- Ratificación explícita del conjunto `expected_business_date`, zona,
  vencimiento/tolerancia por dataset y versión del contrato.
- Reconstrucción de universo Track *por fecha*, con pruebas de aperturas,
  cierres, duplicados, filas de versiones sustituidas y sucursales demo.
- Permisos de sucursal/region verificados en backend; no exponer fechas
  globales en vistas limitadas.
- SQL/CI sobre PostgreSQL, tests de tiempo Tijuana y transiciones
  `NOT_DUE → LAGGING → LATE` sin false-green.
- Sin ejecuciones automáticas, envíos, cierres ni cambios de producción.

M1-F2 aporta comparador real contra catálogo **actual**, no habilita un
SLA de negocio ni convierte el indicador neutral en semáforo falso.

---

## Ratificación posterior — M1-F3 base nocturna Track (14/10/2026)

**Aprobado por el propietario en la conversación del 14/10/2026:**

- Para business_date **D**, el corte `base_nocturna_canonica` debe
  estar disponible el día **D+1 a las 02:00**, zona `America/Tijuana`.
- Si no hay una versión `is_current=true` y `status=success` de esa
  misma fecha/tipo, el estado pasa a `LAGGING` desde las **02:00:00**
  hasta las **02:59:59.999…**, y `LATE` desde las **03:00:00**.
- Antes de las 02:00 es `NOT_DUE`. Aplica **todos los días**,
  incluyendo fines de semana y días festivos. No hay exclusiones.
- En el cambio de horario de verano donde **02:00 local no existe**,
  el límite se normaliza al primer instante real (03:00). Como coinciden
  los instantes UTC de vencimiento y atraso, no existe una ventana de
  tolerancia ficticia de una hora.
- Para selección histórica, se evalúa si el corte sigue disponible
  **al momento de la consulta**, no si se publicó puntualmente en el
  pasado. Sin `finished_at`/auditoría de cobertura histórica certificada
  no se afirma retrospectivamente que «cumplió a tiempo».
- Sin fecha explícita en Control de Automatizaciones, se examina el
  **último día de negocio nocturno (ayer)**; en Track se respeta la fecha
  seleccionada por el usuario.
- Una base con versión current success **no implica semáforo verde**:
  hasta contar con el universo Track historizado por sucursal,
  `UP_TO_DATE` no se certifica; se conserva `UNKNOWN` cuando el plazo
  ya venció aunque coincida con el catálogo vigente actual.
- Si hay más de una versión current de la base, la condición es
  `UNKNOWN` (ambigüedad), nunca se inventa cumplimiento ni atraso.
- El **cierre canónico** y su dependencia de agregadoras permanecen
  **independientes** y **sin SLA fijo ratificado**.
- El horario del scheduler (23:30 por defecto, retry 00:30 condicional)
  no se modifica; el SLA se evalúa por lectura, no por ejecución.

**Siguen pendientes** la vigencia histórica del universo Track, el SLA
de Funnel y la ratificación del cierre canónico. Esta sección sustituye
únicamente la pregunta de hora límite/tolerancia de la base Track.


---

## M1-F4 — SLA de sincronización Marketing (ratificado 14/10/2026)

**Alcance aprobado:** iVentas y Meta, **cada fuente por su slot atribuido**,
independiente de la disponibilidad del Funnel comercial de cinco fuentes.

- Para `business_date D`, los slots son los que reporte realmente el worker
  saludable, único y `America/Tijuana`. Valores de referencia:
  **08:20 / 12:20 / 16:20 / 20:20**, todos los días incluidos festivos.
- Si falta una ejecución canónica y atribuida al slot:
  **`NOT_DUE` antes de slot +60 minutos**; **`LAGGING` desde
  slot +60 hasta antes de +120 minutos**; **`LATE` desde slot +120**.
  Los límites se calculan en UTC, con representación local Tijuana.
- Los slots se atribuyen mediante `scheduler_slot_at` en ambos sync_runs;
  el valor es nullable y se crea con el run `RUNNING` antes de los HTTP.
  Un reintento conserva el slot original. Corridas legacy/manuales no
  reciben retroactivamente una atribución inventada.
- `UP_TO_DATE` en **el subindicador de sincronización** exige que ambas
  fuentes tengan corrida `COMPLETED`, canónica vigente, con `finished_at`
  y fecha exacta del slot. Una corrida completada que perdió canonicalidad
  por reemplazo no acredita cumplimiento histórico: `UNKNOWN`.
- Si el worker no atestigua un horario estable/único, las fuentes divergen
  o se consulta una fecha histórica sin configuración de esa fecha:
  `UNKNOWN`; nunca marcar verdes ni rojos extrapolando defaults.
- El scheduler puede posponer reintentos por la prioridad de Track,
  pero su estado y el resultado del dataset se reportan por separado.
- **El estado global `marketing.sales_funnel` se mantiene `UNKNOWN`**,
  pues su SLA de cinco fuentes no está ratificado. Se conserva la
  intersección exacta de iVentas, Meta, Venta Total, Nuevos Socios y KPI,
  sin cambiar el lector comercial del Funnel.
- Tras migrar e instrumentar, la evidencia nueva solo es verificable
  prospectivamente. El despliegue de app debe suceder después de
  `flask db upgrade` (o equivalente Alembic), nunca antes.

**Sin cambios de horario del scheduler**, sin trigger externo, sin
alteraciones del cierre Track, sin ejecución masiva ni despliegue implícito.
Sigue pendiente ratificar la publicación de las tres fuentes Warehouse
y la condición canónica del lector comercial legado antes de habilitar
el verde del Funnel completo.


---

## M1-F5 — SLA del Funnel consolidado **operativo** (ratificado 14/10/2026)

**Regla autorizada:** para `business_date=D`, publicación conjunta del corte
operativo de cinco fuentes, con fecha exacta D, en `America/Tijuana`:
`NOT_DUE` antes de **D+1 03:00**; `LAGGING` desde las
**03:00 hasta antes de 04:00**; `LATE` desde **D+1 04:00**.
Aplica todos los días, incluidos fines de semana y festivos. Se comparan
instantes absolutos y los límites se construyen con el huso local, sin
fijar offset UTC permanente; ver pruebas del horario de verano.

Las cinco fuentes requeridas son **iVentas, Meta, Venta Total, Detalle de
Ventas Nuevos Socios y KPI Desempeño**. El SLA consulta cada fuente
independientemente con `business_date=D`, los reportes estructurados
canónicos en Warehouse y, para iVentas/Meta, `status=COMPLETED`
**y** `is_canonical=true`; ello NO altera el lector comercial legacy
(`_iventas_cutoff_dates`/`_meta_cutoff_dates`) que hoy solo comprueba
`COMPLETED`. El lector legacy continúa mostrando el último corte
conjunto; su fecha NO es por sí sola certificación de puntualidad.

### Límites de certificación / no falsas señales verdes

- El último **D exigible es ayer** (fecha del negocio en Tijuana),
  independientemente del corte seleccionado del dashboard.
- Cuando el usuario consulta un mes histórico distinto del mes de D,
  el semáforo principal sigue `UNKNOWN`: no asignar atrasos de hoy a ese mes.
  El objeto `funnel_operational_sla` queda independiente y rotulado.
- Si falta una fecha exacta canónica, el estado usa la fase temporal
  ratificada; si hay más de un canónico por fuente, `UNKNOWN`.
- Si **las cinco fechas están presentes**, mostrar
  `UNKNOWN/FIVE_DATES_PRESENT_LINEAGE_UNVERIFIED` en esta fase, **no
  `UP_TO_DATE`**. La existencia de snapshots no certifica por sí sola
  linaje a versión Track vigente, cobertura histórica de sucursales o
  conservación de canonicalidad durante reintentos.
- El indicador no equivale al **cierre definitivo con agregadoras**;
  conserva `operational_not_final=true` y esa condición no posee SLA
  horario ratificado.
- Para permisos `FILTERED` o lectura global no certificada, no leer
  ni exponer fechas, faltantes o versiones corporativas: `UNKNOWN`.
- La comprobación por slots de Marketing M1-F4 y la base nocturna Track
  M1-F3 siguen **independientes**.

**Implementación M1-F5:** `backend/app/services/automation_control/
funnel_operational_sla_service.py` (5 consultas de existencia acotadas,
sin N+1 por sucursal), `freshness_service.py::_funnel_evidence`
(separación fecha seleccionada vs. D exigible) y el indicador Angular
(estado operativo y faltantes explícitos). Pruebas de límites exactos,
DST, rollover mensual, canonicalidad, ambigüedad y permisos. **Sin
migración Alembic:** el cambio es estrictamente read-only. **Sin
reprogramar Track/Marketing/Control de Rutinas ni modificar pipelines.**
La certificación de linaje/cobertura se trabaja en una fase posterior y
no se reemplaza por un false-green de la fuente actual.
