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
