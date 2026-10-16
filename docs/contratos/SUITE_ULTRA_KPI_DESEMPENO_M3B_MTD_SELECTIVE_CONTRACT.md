# SUITE ULTRA — M3-B: contrato de impacto selectivo y continuidad MTD (fase inicial)

**Estado:** diseño ejecutable y pruebas sintéticas en PR DRAFT; **NO reconstrucción**, staging de Track, promoción canónica, deploy ni cambio de DB productiva.

## Fuente y alcance

- M1 aprobado identifica diferencias semánticas en los ocho campos de `kpi_desempeno`. M3-A almacena el candidato **non-canonical** sin afectar al canónico.
- M3-B debe consumir un resultado M1 validado, fecha de negocio explícita y una serie MTD verificada por sucursal/día. La procedencia de cada valor es obligatoria cuando se implemente el loader productivo; en esta primera fase se pasan fixtures puramente sintéticas.
- No inferir alias ni trasplantar valores entre sucursales. Las identidades `branch_key` M1 y las de la serie deben coincidir exactamente. `ADDED/REMOVED`, fechas ambiguas y datos faltantes bloquean.
- La serie se consulta por fecha de negocio en `America/Tijuana`, jamás por hora de descarga. Los acumulados MTD se comparan **por sucursal y métrica** y se reinician al pasar al primer día del mes.
- Una disminución en `reactivaciones_real_mtd` o `bajas_reales_mtd` entre dos fechas consecutivas del mismo mes bloquea; no se compensa, reparte ni convierte a cero. Un día vecino que debería existir y falta también bloquea.

## Mapeo exclusivo de KPI -> Track F3

| M1 KPI | Track campo | Regla |
|---|---|---|
| `socios_activos_del_mes` | `usuarios_activos_actual` | Impacto directo en fecha/sucursal |
| `reactivaciones` | `reactivaciones_real_mtd` | Impacto directo + continuidad y deltas derivados |
| `bajas` | `bajas_reales_mtd` | Impacto directo + continuidad y deltas derivados |
| `socios_activos_inicio_mes`, `clientes_nuevo_real`, `renovaciones`, `meta_socios_activos_del_mes`, `alcance_meta` | Ninguno en F3 | Solo registrar diferencias documentales, sin mutar otros orígenes |

**Invariante contractual:** ingresos (base, total y agregadoras), domiciliados, tienda, clientes nuevos Track, metas y todos los demás campos del mart permanecen byte-a-byte / valor-a-valor intactos. El planificador es una función pura, no emite SQL, no crea versiones ni publica.

## Interfaz pure/read-only (primer entregable)

`plan_kpi_desempeno_mtd_impact(business_date, diff, observed_mtd)`

- `diff`: resultado inmutable de `compare_kpi_desempeno_parsed()`, con `business_date` exacta.
- `observed_mtd`: `date -> branch_key -> {reactivaciones_real_mtd: int, bajas_reales_mtd: int}`, obtenido de fuentes ya validadas. Las claves de sucursal son las identidades del detector; un adaptador de alias necesita auditoría posterior y está fuera de esta fase.
- `changed_snapshot_fields`: campo(s) originales KPI por sucursal, incluidos los que NO alimentan Track.
- `track_field_changes`: solo (business_date, sucursal, columna F3, previous, current) para campos mapeados.
- `continuity_days`: días vecino anterior/D/posterior del **mismo mes** cuando cambia una métrica MTD (sin inventar cruces de mes).
- `derived_delta_impacts`: (día, sucursal, métrica MTD) en D y D+1, ya que `delta(D)=MTD(D)-MTD(D-1)` y `delta(D+1)=MTD(D+1)-MTD(D)`. **No implican** escribir nuevas filas mart en D+1 si su MTD no cambió.
- `blocking_issues`: evidencia precisa por sucursal/métrica/par fechas en disminución o con datos incompletos.
- `status`: `READY_FOR_REVIEW` o `BLOCKED`. No hay estados publicables.

## Determinación selectiva del alcance

1. Para cada diferencia M1, registrar el indicador KPI; derivar modificaciones Track **solo** de las tres métricas F3, y únicamente en fecha D y sucursal afectada.
2. Para cada (sucursal, métrica MTD) alterada, proyectar únicamente ese nuevo acumulado sobre una copia lógica de la serie; comparar (D−1,D) y (D,D+1) si ambas fechas están en el mismo mes. Requerir los días vecinos de la ventana histórica solicitada; fail-closed ante faltantes.
3. Las diferencias de socios activos no producen deltas diarios MTD. Los otros cinco indicadores tampoco deben alimentar campos Track.
4. Días candidatos a revalidación de informes de actividad: D y D+1 para cada métrica MTD cambiada. Semanales/mensuales se evalúan mediante contrato de reportes en etapa posterior, **sin generación ni publicación ahora**.
5. Un plan BLOCKED puede mostrar el alcance para diagnóstico, pero ningún consumidor debe interpretarlo como permiso para reconstruir.

## Caso obligatorio de bloqueo

**Secuencia de control agregada sin datos reales de sucursales:** 6/oct `1,253` reactivaciones MTD -> candidato 7/oct `963`. El resultado debe ser `BLOCKED` con diferencia `-290`. Es evidencia de una serie incompatible, **no** autorización para reescribir el 6, el 7, el 8 ni días posteriores.

Se debe revisar 6/7/8 por sucursal con fuentes verificadas antes de cualquier corrección real. Una corrección de KPI en D que cambie la derivada de D+1 obliga a revalidar el informe afectado, **no** a reconstruir indiscriminadamente todos los marts.

## Límites y próximo gate

Esta fase solo valida determinación de impacto y continuidad sobre datos sintéticos. No modifica `kpi_desempeno_repository`, el parser M1, `track_source_desempeno_daily`, `track_daily_mart`, `track_daily_versions`, scheduler ni reportes. No crea PR de M3-C. Antes de cualquier persistencia real posterior deberán auditarse prioridad cierre/base, versiones candidatas no visibles, transacciones, bloqueos, roster, y datos efectivos de Warehouse/Track con una autorización adicional.

**Criterio de CI:** una suite determinista sintética, negativas de días faltantes y decrecientes, selección exacta de campos/fechas, ausencia de SQL o efectos secundarios, regresión M1, más aislamiento PostgreSQL si se usa DB como fuente de fixtures. `CI PASS` no implica M3-B ACCEPTED ni permiso de despliegue.
