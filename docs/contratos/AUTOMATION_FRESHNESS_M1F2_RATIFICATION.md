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
