# SUITE ULTRA — M3-B: contrato de impacto selectivo y continuidad MTD (fase inicial)

**Estado:** diseño ejecutable y pruebas sintéticas en PR DRAFT; **NO reconstrucción**, staging de Track, promoción canónica, deploy ni cambio de DB productiva.

## Fuente y alcance

- M1 aprobado identifica diferencias semánticas en los ocho campos de `kpi_desempeno`. M3-A almacena el candidato **non-canonical** sin afectar al canónico.
- M3-B debe consumir un resultado M1 validado, fecha de negocio explícita y una serie MTD verificada por sucursal/día. La procedencia de cada valor es obligatoria cuando se implemente el loader productivo; en esta primera fase se pasan fixtures puramente sintéticas.
- No inferir alias ni trasplantar valores entre sucursales. Las identidades `branch_key` M1 y las de la serie deben coincidir exactamente. `ADDED/REMOVED`, fechas ambiguas y datos faltantes bloquean.
- La serie se consulta por fecha de negocio en `America/Tijuana`, jamás por hora de descarga. Los acumulados MTD se comparan **por sucursal y métrica** y se reinician al pasar al primer día del mes.
- Una disminución en `reactivaciones_real_mtd` o `bajas_reales_mtd` entre fechas consecutivas del mismo mes **bloquea por defecto**; no se compensa, reparte ni convierte a cero. Un día vecino faltante siempre bloquea. Una revisión documentada de origen, cuyo par de valores, sucursal, métrica, fechas y procedencia fueron verificados por un futuro cargador confiable, puede quedar clasificada para **revisión humana**, nunca publicación automática.

## Mapeo exclusivo de KPI -> Track F3

| M1 KPI | Track campo | Regla |
|---|---|---|
| `socios_activos_del_mes` | `usuarios_activos_actual` | Impacto directo en fecha/sucursal |
| `reactivaciones` | `reactivaciones_real_mtd` | Impacto directo + continuidad y deltas derivados |
| `bajas` | `bajas_reales_mtd` | Impacto directo + continuidad y deltas derivados |
| `socios_activos_inicio_mes`, `clientes_nuevo_real`, `renovaciones`, `meta_socios_activos_del_mes`, `alcance_meta` | Ninguno en F3 | Solo registrar diferencias documentales, sin mutar otros orígenes |

**Invariante contractual:** ingresos (base, total y agregadoras), domiciliados, tienda, clientes nuevos Track, metas y todos los demás campos del mart permanecen byte-a-byte / valor-a-valor intactos. El planificador es una función pura, no emite SQL, no crea versiones ni publica.

## Interfaz pure/read-only (primer entregable)

`plan_kpi_desempeno_mtd_impact(business_date, diff, observed_mtd, source_revision_evidence=())`

- `diff`: resultado inmutable de `compare_kpi_desempeno_parsed()`, con `business_date` exacta.
- `observed_mtd`: `date -> branch_key -> {reactivaciones_real_mtd: int, bajas_reales_mtd: int}`, obtenido de fuentes ya validadas. Las claves de sucursal son las identidades del detector; un adaptador de alias necesita auditoría posterior y está fuera de esta fase.
- `changed_snapshot_fields`: campo(s) originales KPI por sucursal, incluidos los que NO alimentan Track.
- `track_field_changes`: solo (business_date, sucursal, columna F3, previous, current) para campos mapeados.
- `continuity_days`: días vecino anterior/D/posterior del **mismo mes** cuando cambia una métrica MTD (sin inventar cruces de mes).
- `derived_delta_impacts`: (día, sucursal, métrica MTD) en D y D+1, ya que `delta(D)=MTD(D)-MTD(D-1)` y `delta(D+1)=MTD(D+1)-MTD(D)`. **No implican** escribir nuevas filas mart en D+1 si su MTD no cambió.
- `blocking_issues`: evidencia precisa por sucursal/métrica/par fechas en disminución o con datos incompletos.
- `source_revision_evidence`: tupla opcional de `M3BSourceRevisionEvidence`, **vacía por defecto**. Cada entrada apunta a un **par diario decreciente exacto** (sucursal/identidad M1, métrica MTD, fechas consecutivas, acumulados anterior y posterior), los identificadores de ambos Warehouse uploads, ambos hashes SHA-256, el identificador del revisor autorizado y una referencia de revisión auditable.
- `documented_decreases`: hallazgos `MTD_SOURCE_REVISION_REVIEW` aceptados para **revisión**, distintos de `blocking_issues` y visibles con delta negativo íntegro.
- `blocking_issues`: toda disminución no respaldada continúa como `MTD_DECREASE`; evidencia malformada, duplicada o que no corresponde exactamente a una disminución observada también bloquea. `BASELINE_MISMATCH`, días/identidades faltantes, valores inválidos y los demás bloqueos no se pueden exceptuar con evidencia.
- `status`: `READY_FOR_REVIEW` si no hay bloqueos (aunque existan descensos documentados pendientes de revisión humana), o `BLOCKED` en caso contrario. **Ningún estado es autorización de publicación**.

## Determinación selectiva del alcance

1. Para cada diferencia M1, registrar el indicador KPI; derivar modificaciones Track **solo** de las tres métricas F3, y únicamente en fecha D y sucursal afectada.
2. Para cada (sucursal, métrica MTD) alterada, proyectar únicamente ese nuevo acumulado sobre una copia lógica de la serie; comparar (D−1,D) y (D,D+1) si ambas fechas están en el mismo mes. Requerir días vecinos; fail-closed ante faltantes. Si existe descenso, comparar contra evidencia exacta de ese par; aceptar **solo la clasificación para revisión**, sin alterar la serie ni su delta negativo.
3. Las diferencias de socios activos no producen deltas diarios MTD. Los otros cinco indicadores tampoco deben alimentar campos Track.
4. Días candidatos a revalidación de informes de actividad: D y D+1 para cada métrica MTD cambiada. Semanales/mensuales se evalúan mediante contrato de reportes en etapa posterior, **sin generación ni publicación ahora**.
5. Un plan `BLOCKED` puede mostrar el alcance para diagnóstico; `READY_FOR_REVIEW` con `documented_decreases` tampoco da permiso para reconstruir, canonicizar ni publicar.
6. **Límite de confianza:** el planificador puro solo valida estructura y coincidencia exacta; **no puede comprobar que un hash corresponda al fichero, que un upload exista o que el revisor tenga autorización**. Un futuro cargador interno autorizado debe verificar las dos fuentes originales de Warehouse, los bytes/SHA, el contexto de corte, identidad de sucursal y la revisión aprobada. Está prohibido aceptar objetos de evidencia suministrados por UI, clientes externos o flags booleanos sin dichas verificaciones. Todavía no existe este adaptador productivo.
7. La evaluación de un día con vecinos canónicos **no equivale** a evaluar una serie corregida de 15 días. La reconciliación del lote completo, sus fuentes y su gobierno de versiones es un gate posterior.

## Caso obligatorio de bloqueo

**Secuencia de control agregada sin datos reales de sucursales:** 6/oct `1,253` reactivaciones MTD -> candidato 7/oct `963`. **Sin evidencia válida exacta**, el resultado debe ser `BLOCKED` con diferencia `-290`. Es evidencia de una serie incompatible, **no** autorización para reescribir el 6, el 7, el 8 ni días posteriores.

Se debe revisar 6/7/8 por sucursal con fuentes verificadas antes de cualquier corrección real. Una corrección de KPI en D que cambie la derivada de D+1 obliga a revalidar el informe afectado, **no** a reconstruir indiscriminadamente todos los marts.

## Límites y próximo gate

Esta fase solo valida determinación de impacto y continuidad sobre datos sintéticos. No modifica `kpi_desempeno_repository`, el parser M1, `track_source_desempeno_daily`, `track_daily_mart`, `track_daily_versions`, scheduler ni reportes. No crea PR de M3-C. Antes de cualquier persistencia real posterior deberán auditarse prioridad cierre/base, versiones candidatas no visibles, transacciones, bloqueos, roster, y datos efectivos de Warehouse/Track con una autorización adicional.

**Criterio de CI:** una suite determinista sintética, negativas de días faltantes y decrecientes, selección exacta de campos/fechas, evidencia exacta sintética, rechazo de datos falsos/no relacionados, ausencia de SQL o efectos secundarios, regresión M1 y aislamiento PostgreSQL cuando corresponda. `CI PASS` no implica M3-B ACCEPTED ni permiso de despliegue.

## Oct 2026 — investigación operativa (sin autorización de publicación)

Los datos documentales del 1–15/oct han generado 14 candidatos KPI no canónicos. En la serie propuesta se detectaron 75 descensos de bajas, 59 compartidos con la serie anterior, 16 que aparecen y seis que desaparecen respecto al canónico, concentrándose los 22 cambios de condición en el 5–7/oct. **Esto muestra revisión de los valores reportados, no prueba automáticamente legitimidad de cada descenso.** Ninguna revisión externa se considera certificada solo por esos conteos.

Este cambio incorpora **exclusivamente una vía de clasificación condicionada a procedencia atestiguada** en un modelo y pruebas puras. No crea todavía evidencia real para los 75 casos, no modifica Warehouse/Track productivos, no implementa cargador de procedencia, no reconcilia serie multifecha, no levanta por sí mismo los bloqueos productivos y no modifica PR M3-C1/M3-C2.
