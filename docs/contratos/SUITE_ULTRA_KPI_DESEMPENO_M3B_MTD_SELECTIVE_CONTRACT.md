# SUITE ULTRA — M3-B: contrato de impacto selectivo y continuidad MTD (fase inicial)

**Estado:** diseño ejecutable y pruebas sintéticas en PR DRAFT; **NO reconstrucción**, staging de Track, promoción canónica, deploy ni cambio de DB productiva.

## Fuente y alcance

- M1 aprobado identifica diferencias semánticas en los ocho campos de `kpi_desempeno`. M3-A almacena el candidato **non-canonical** sin afectar al canónico.
- M3-B debe consumir un resultado M1 validado, fecha de negocio explícita y una serie MTD verificada por sucursal/día. La procedencia de cada valor es obligatoria cuando se implemente el loader productivo; en esta primera fase se pasan fixtures puramente sintéticas.
- No inferir alias ni trasplantar valores entre sucursales. Las identidades `branch_key` M1 y las de la serie deben coincidir exactamente. `ADDED/REMOVED`, fechas ambiguas y datos faltantes bloquean.
- La serie se consulta por fecha de negocio en `America/Tijuana`, jamás por hora de descarga. Los acumulados MTD se comparan **por sucursal y métrica** y se reinician al pasar al primer día del mes.
- En el **planificador puro**, cualquier disminución en `reactivaciones_real_mtd` o `bajas_reales_mtd` queda bloqueada, incluso ante una declaración textual de revisión. El **puente de fuente verificada** puede reclasificar un descenso cuando la auditoría real de Warehouse comprueba exactamente fecha, sucursal, métrica y ambos valores, sin exigir aprobación manual por cada caída. Faltantes y errores de identidad siguen bloqueados.

## Mapeo exclusivo de KPI -> Track F3

| M1 KPI | Track campo | Regla |
|---|---|---|
| `socios_activos_del_mes` | `usuarios_activos_actual` | Impacto directo en fecha/sucursal |
| `reactivaciones` | `reactivaciones_real_mtd` | Impacto directo + continuidad y deltas derivados |
| `bajas` | `bajas_reales_mtd` | Impacto directo + continuidad y deltas derivados |
| `socios_activos_inicio_mes`, `clientes_nuevo_real`, `renovaciones`, `meta_socios_activos_del_mes`, `alcance_meta` | Ninguno en F3 | Solo registrar diferencias documentales, sin mutar otros orígenes |

**Invariante contractual:** ingresos (base, total y agregadoras), domiciliados, tienda, clientes nuevos Track, metas y todos los demás campos del mart permanecen byte-a-byte / valor-a-valor intactos. El planificador es una función pura, no emite SQL, no crea versiones ni publica.

## Interfaz pure/read-only (primer entregable)

`plan_kpi_desempeno_mtd_impact(business_date, diff, observed_mtd, source_revision_claims=())`

- `diff`: resultado inmutable de `compare_kpi_desempeno_parsed()`, con `business_date` exacta.
- `observed_mtd`: `date -> branch_key -> {reactivaciones_real_mtd: int, bajas_reales_mtd: int}`, obtenido de fuentes ya validadas. Las claves de sucursal son las identidades del detector; un adaptador de alias necesita auditoría posterior y está fuera de esta fase.
- `changed_snapshot_fields`: campo(s) originales KPI por sucursal, incluidos los que NO alimentan Track.
- `track_field_changes`: solo (business_date, sucursal, columna F3, previous, current) para campos mapeados.
- `continuity_days`: días vecino anterior/D/posterior del **mismo mes** cuando cambia una métrica MTD (sin inventar cruces de mes).
- `derived_delta_impacts`: (día, sucursal, métrica MTD) en D y D+1, ya que `delta(D)=MTD(D)-MTD(D-1)` y `delta(D+1)=MTD(D+1)-MTD(D)`. **No implican** escribir nuevas filas mart en D+1 si su MTD no cambió.
- `source_revision_claims`: tupla opcional de `M3BSourceRevisionClaim`, **vacía por defecto**. Cada declaración referencia un par diario decreciente exacto (sucursal, métrica MTD, fechas consecutivas, valores), dos Warehouse upload IDs, dos SHA-256 y la identidad/referencia de un supuesto revisor. **Todos son datos declarados, no autenticados por el planificador**.
- `matched_revision_claims`: hallazgos `MTD_SOURCE_REVISION_CLAIM` cuya declaración coincide exactamente con una caída observada, con delta negativo íntegro. Además, `blocking_issues` contiene `SOURCE_REVISION_UNVERIFIED` para esos mismos pares, manteniendo `status=BLOCKED`.
- `blocking_issues`: toda caída sin declaración coincidente continúa como `MTD_DECREASE`; declaraciones malformadas, duplicadas, inexactas o falsas continúan bloqueadas. `BASELINE_MISMATCH`, días/identidades faltantes y valores inválidos nunca se exceptúan.
- `status`: `BLOCKED` para la función pura con descensos no verificados; `READY_FOR_REVIEW` exige cero bloqueos. El puente auditado puede producir `READY_FOR_PROCESSING` si todos los descensos observados están respaldados por archivos verificados y no hay otros bloqueos. **Ningún estado por sí solo autoriza publicar**.

## Determinación selectiva del alcance

1. Para cada diferencia M1, registrar el indicador KPI; derivar modificaciones Track **solo** de las tres métricas F3, y únicamente en fecha D y sucursal afectada.
2. Para cada (sucursal, métrica MTD) alterada, proyectar únicamente ese nuevo acumulado sobre una copia lógica de la serie; comparar (D−1,D) y (D,D+1) si ambas fechas están en el mismo mes. Requerir días vecinos; fail-closed ante faltantes. Si existe descenso, contrastar con declaraciones exactas de ese par y conservar el bloqueo. Nunca alterar la serie ni su delta negativo.
3. Las diferencias de socios activos no producen deltas diarios MTD. Los otros cinco indicadores tampoco deben alimentar campos Track.
4. Días candidatos a revalidación de informes de actividad: D y D+1 para cada métrica MTD cambiada. Semanales/mensuales se evalúan mediante contrato de reportes en etapa posterior, **sin generación ni publicación ahora**.
5. Un plan `BLOCKED` muestra el alcance y las declaraciones coincidentes para diagnóstico. Ningún plan da permiso para reconstruir, canonicizar ni publicar.
6. **Límite de confianza:** el planificador puro solo valida estructura y coincidencia exacta; **no puede comprobar que un hash corresponda al fichero, que un upload exista o que el revisor tenga autorización**. Por ello incluso las declaraciones con forma válida permanecen `BLOCKED`. El puente interno `kpi_desempeno_m3b_verified_plan.py` llama a la auditoría real del Warehouse sobre la **serie mensual completa**, vuelve a cargar los documentos del día y sus vecinos y coteja los cambios F3 de M1 antes de clasificar una disminución. No acepta booleans, una lista de claims ni hash inventado como validación. La ejecución operativa debe verificar además que el lote sea el más reciente y oficial de Gasca; la fuente documental no se autentica únicamente por un SHA. Ninguna firma/aprobación extra por descenso es requerida.
7. La evaluación de un día con vecinos canónicos **no equivale** a evaluar una serie corregida de 15 días. La reconciliación del lote completo, sus fuentes y su gobierno de versiones es un gate posterior.

## Caso obligatorio de bloqueo

**Secuencia de control agregada sin datos reales de sucursales:** 6/oct `1,253` reactivaciones MTD -> candidato 7/oct `963`. En el planificador puro queda `BLOCKED` con diferencia `-290`. El puente de Warehouse puede reclasificar ese descenso **solo** si lo encuentra exactamente en la serie candidata verificada, y no hay otros errores de continuidad. Esto no autoriza por sí solo reescribir el 6, 7, 8 ni días posteriores.

Se debe revisar 6/7/8 por sucursal con fuentes verificadas antes de cualquier corrección real. Una corrección de KPI en D que cambie la derivada de D+1 obliga a revalidar el informe afectado, **no** a reconstruir indiscriminadamente todos los marts.

## Límites y próximo gate

Esta fase solo valida determinación de impacto y continuidad sobre datos sintéticos. No modifica `kpi_desempeno_repository`, el parser M1, `track_source_desempeno_daily`, `track_daily_mart`, `track_daily_versions`, scheduler ni reportes. No crea PR de M3-C. Antes de cualquier persistencia real posterior deberán auditarse prioridad cierre/base, versiones candidatas no visibles, transacciones, bloqueos, roster, y datos efectivos de Warehouse/Track con una autorización adicional.

**Criterio de CI:** una suite determinista sintética, negativas de días faltantes y decrecientes, selección exacta de campos/fechas, declaraciones exactas sintéticas, rechazo de datos falsos/no relacionados y bloqueo explícito de declaraciones formalmente válidas pero no verificadas, ausencia de SQL o efectos secundarios, regresión M1 y aislamiento PostgreSQL cuando corresponda. `CI PASS` no implica M3-B ACCEPTED ni permiso de despliegue.

## Oct 2026 — investigación operativa (sin autorización de publicación)

Los datos documentales del 1–15/oct han generado 14 candidatos KPI no canónicos. En la serie propuesta se detectaron 75 descensos de bajas, 59 compartidos con la serie anterior, 16 que aparecen y seis que desaparecen respecto al canónico, concentrándose los 22 cambios de condición en el 5–7/oct. **Esto muestra revisión de los valores reportados, no prueba automáticamente legitimidad de cada descenso.** Ninguna revisión externa se considera certificada solo por esos conteos.

Este cambio incorpora **exclusivamente la clasificación de declaraciones de revisión**, nunca una verificación de procedencia. Por diseño ninguna declaración desbloquea los descensos. No crea todavía evidencia real para los 75 casos, no modifica Warehouse/Track productivos, no implementa cargador de procedencia, no reconcilia serie multifecha, no levanta por sí mismo los bloqueos productivos y no modifica PR M3-C1/M3-C2.

## 2026-10-20 — política Gasca y puente auditado

Gasca determina los valores de KPI Desempeño. La ejecución autenticada por un
operador autorizado de Suite Ultra expresa la intención de reemplazar la serie
anterior por el último corte oficial disponible de Gasca. Un acumulado MTD
decreciente confirmado en esos archivos puede ser correcto.

`plan_kpi_desempeno_verified_source_impact(...)` ejecuta la auditoría
`audit_kpi_desempeno_m3b_provenance()` antes de planificar, relee el día
corregido y vecinos, valida que el diff M1 F3 coincide con canónico/candidato,
y reclasifica únicamente disminuciones que coincidan **exactamente** con
`report.declines` de la fuente verificada. Devuelve
`verified_source_revisions` y, sin otros bloqueos, `READY_FOR_PROCESSING`.

La firma antigua `source_revision_claims` del planificador puro es diagnóstica
y no otorga ninguna excepción. No debe ser utilizada como autorización para
procesar. Errores de SHA, fecha, roster, M1, vecino o procedencia provocan
excepción o `BLOCKED`.

**Pendiente en otro gate:** comprobar última entrega oficial Gasca con
metadatos del proveedor, orquestar en orden seguro publicación canónica, actualización de Track,
reportes e idempotencia/recuperación ante fallos. El puente ya distingue el
último día del lote auditado, por lo que no exige un D+1 inexistente. Un día
**intermedio** faltante continúa siendo inconsistencia bloqueante. Nada de este módulo
ejecuta escritura, reingesta, promoción o reconstrucción en producción.
