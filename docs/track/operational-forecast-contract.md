# Contrato Forecast Operativo

## Objetivo

Definir una sola proyección oficial para los cinco indicadores que se
presentarán en Seguimiento Regional, Centro de Control y Forecast Excel.

Los consumidores no deben recalcular el forecast. Deben recibir y presentar
el resultado del backend.

## Contrato visible

Cada indicador expone:

- `actual_mtd`
- `projected_close`
- `benchmark`
- `benchmark_kind`
- `projected_gap`
- `status`
- `method`
- cobertura del agregado

La brecha general es:

`projected_gap = projected_close - benchmark`

Para Bajas, un valor positivo representa exceso proyectado sobre el límite.

## Ingreso

El contrato recibe la proyección oficial producida por
`build_branch_income_projection_summary()`.

Por sucursal:

- menos de 12 meses operando: `linear_mtd_pace`;
- 12 meses o más: ritmo histórico estable, sujeto a controles de calidad.

Los agregados se construyen sumando forecasts de sucursal. No se vuelve a
proyectar el total agregado.

## Venta nueva

Método:

`recent_valid_daily_average_7_calendar_days`

Se usan los deltas diarios válidos de los últimos 7 días calendario y se
requieren al menos 3 deltas válidos.

`projected_close = actual_mtd + recent_daily_average * remaining_days`

La curva weekday existente sigue siendo una regla de pacing contra meta; no es
el forecast de cierre.

## Reactivaciones

Usa la misma metodología de promedio diario reciente que Venta nueva, pero con
su propia serie de deltas.

## Bajas

Método:

`chain_daily_median_share_of_month_close`

La curva se construye con snapshots diarios canónicos de KPI Desempeño de
meses anteriores completos. Para cada día se calcula la mediana histórica del
porcentaje del cierre mensual que ya se había materializado.

`projected_close = actual_mtd / historical_progress_ratio`

Se conserva el número de meses disponibles y P25/P75 en la curva de origen
para auditoría. El contrato operativo usa la mediana.

Campos adicionales:

- `projected_excess`
- `projected_remaining_margin`
- `projected_limit_usage_pct`

## Tienda

Versión inicial oficial:

`recent_valid_daily_average_7_calendar_days`

Usa la misma ventana y mínimos que Venta nueva y Reactivaciones.

`projected_close = actual_mtd + recent_daily_average * remaining_days`

La metodología puede evolucionar cuando exista evidencia suficiente para una
curva histórica propia, pero los consumidores no deben implementar esa lógica
por separado.

## Agregación

Para todos los indicadores:

`scope_projected_close = SUM(branch_projected_close)`

No se permite:

`SUM(actual_mtd) -> volver a proyectar el agregado`

Esto preserva la metodología particular de cada sucursal.

Si una sucursal no tiene forecast disponible, el agregado no publica un
`projected_close` parcial. En su lugar reporta cobertura incompleta.

## Alcance de esta implementación

Este contrato backend no modifica todavía:

- Centro de Control;
- Forecast Excel;
- layout de Seguimiento Regional;
- base de datos;
- migraciones.

El siguiente paso es conectar los consumidores al mismo contrato sin duplicar
fórmulas.
