# Track Forecast / Proyección y Metas — Contrato funcional y técnico

Estado: draft_v1.1
Módulo: Track / Proyección y Metas
Última actualización: 2026-07

---

## 1. Propósito del módulo

El módulo Track Forecast / Proyección y Metas existe para dar una lectura anticipada del cierre mensual de ingresos de Ultra Gym.

No busca adivinar el cierre exacto. Busca responder preguntas operativas:

- ¿El mes va arriba o abajo del ritmo esperado?
- ¿Qué cohortes explican la tendencia?
- ¿El núcleo histórico se está comportando bien?
- ¿Los gimnasios nuevos están aportando como se esperaba?
- ¿La proyección es estable o solo experimental?
- ¿Qué tan lejos estamos de la meta, si la meta ya fue cargada?

---

## 2. Principio rector

La proyección no es garantía.

Mensaje obligatorio de interpretación:

> Esta es una proyección estadística basada en histórico y tendencia actual. No representa meta, garantía ni compromiso de cierre. Puede variar por promociones, campañas, cierres, clima, incidencias operativas o cambios comerciales.

---

## 3. Alcance actual

El módulo trabaja sobre ingresos mensuales acumulados MTD.

Actualmente contempla:

- Forecast nacional.
- Forecast por sucursal.
- Forecast por cohortes.
- Comparativo histórico mismo día.
- Diagnóstico de drivers por sucursal.
- Quality gates para evitar proyecciones engañosas.
- Referencias experimentales cuando una proyección no es estable.
- Lectura contra meta solo cuando la meta existe.

---

## 4. Conceptos clave

### 4.1 Real MTD

Ingreso real acumulado al corte seleccionado.

En Track, el ingreso real puede componerse de:

- ingreso base.
- ingreso agregadoras.
- ingreso total.

Campos relevantes:

- ingreso_real_base_mtd
- ingreso_real_agregadora_mtd
- ingreso_real
- ingreso_real_total_mtd, si existe en el mart.

Regla conceptual:

ingreso_real_total_mtd = ingreso_real_base_mtd + ingreso_real_agregadora_mtd

Si el mart ya trae un campo total oficial, debe respetarse como fuente principal.

### 4.2 Histórico Venta Total

El histórico de Venta Total viene de snapshots canónicos del Warehouse.

Fuente principal:

track_venta_total_daily_branch_agg

Esta tabla representa venta diaria agregada por sucursal, día y snapshot.

Se usa para construir:

- curva diaria histórica.
- avance acumulado esperado.
- patrón de cobranza por día.
- históricos comparables por cohorte/sucursal.

### 4.3 Meta mensual

La meta mensual viene de Track Daily Mart cuando está cargada.

Campo principal:

meta_faycgo_mes

Regla:

Si meta_faycgo_mes no existe o es 0:
- goal_status = pending.
- ocultar o desactivar lectura de brecha contra meta.
- no mostrar cumplimiento contra meta como si fuera información válida.

---

## 5. Cohortes

El forecast no debe depender solo de una lectura nacional simple, porque Ultra ha cambiado su cantidad de sucursales con el tiempo.

Por eso se usan cohortes.

### 5.1 ULTRA 21 GYMS

Representa el núcleo histórico comparable.

Regla actual:

track_branch_catalog.display_order <= 21

Uso:

- comparar contra histórico amplio.
- medir si el núcleo original va arriba o abajo de su propio comportamiento esperado.

### 5.2 ULTRA NUEVOS

Representa sucursales nuevas.

Regla actual:

track_branch_catalog.display_order > 21

Uso:

- medir aporte de crecimiento.
- evitar mezclar gimnasios sin historia suficiente con el núcleo histórico.

### 5.3 ULTRA GYM

Representa total consolidado.

Regla:

ULTRA GYM = ULTRA 21 GYMS + ULTRA NUEVOS

---

## 6. Métodos de proyección

El módulo puede mostrar varios métodos de proyección. No todos tienen el mismo nivel de confianza.

### 6.1 Historical Curve Forecast

Método base actual.

Fórmula:

projected_close = real_mtd / historical_progress_pct

Donde:

historical_progress_pct = historical_mtd_total / historical_month_total

Uso correcto:

- útil cuando hay histórico suficiente.
- útil después de varios días del mes.
- útil para comparar contra años anteriores.

Riesgo:

- puede castigar demasiado al inicio del mes.
- puede inflar sucursales o cohortes con poca historia.
- puede mezclar mal si el tamaño actual de la operación no es comparable con años anteriores.

### 6.2 Same Day History

Compara el corte actual contra el mismo día del mes en años anteriores.

Ejemplo:

Julio 2026 día 6 vs Julio 2025 día 6 vs Julio 2024 día 6 vs Julio 2023 día 6.

Uso:

- explicar si el corte actual va arriba o abajo contra el patrón histórico.
- mostrar avance acumulado promedio.
- detectar días de cobranza relevantes.

### 6.3 Cohort Forecast

Método que separa:

ULTRA GYM = ULTRA 21 GYMS + ULTRA NUEVOS

Uso:

- evitar que el total nacional oculte problemas del núcleo histórico.
- evitar que nuevos gimnasios inflen la lectura total.
- entender si el crecimiento viene de nuevos o de recuperación del núcleo.

### 6.4 Anchored Remaining Forecast

Método recomendado para la siguiente evolución.

Fórmula conceptual:

expected_close_before_cutoff = previous_closed_total * seasonal_factor

expected_mtd_at_cutoff = expected_close_before_cutoff * expected_cumulative_pct

expected_remaining = expected_close_before_cutoff - expected_mtd_at_cutoff

projected_close = current_mtd + expected_remaining

Interpretación:

No proyecta todo el mes desde el corte actual. Toma el real actual y estima solo lo que falta del mes.

Ventaja:

- evita castigar demasiado por un corte temprano.
- permite usar cierre anterior como ancla operativa.
- permite ajustar por estacionalidad mensual.
- permite separar ULTRA 21 y ULTRA NUEVOS.

Uso recomendado:

ULTRA 21 GYMS:
- usar cierre anterior.
- usar factor estacional histórico del mes.
- usar curva acumulada histórica del día.

ULTRA NUEVOS:
- usar cierre anterior.
- usar patrón diario reciente.
- no usar factor estacional si no hay historia suficiente.

ULTRA GYM:
- sumar cohortes.

---

## 7. Factores estacionales

El factor estacional compara el cierre de un mes contra el cierre del mes anterior.

Ejemplo:

factor_julio = cierre_julio / cierre_junio

Uso:

- no asumir que cada mes debe superar al anterior.
- capturar estacionalidad fitness.
- ajustar expectativa mensual antes de calcular brechas.

Ejemplo:

expected_close_julio = cierre_junio * factor_estacional_julio

Si no hay suficientes años comparables, el factor debe marcarse como baja confianza.

---

## 8. Patrón diario de cobranza

El ingreso no se comporta linealmente.

Hallazgos iniciales:

- Día 6 suele ser relevante.
- Día 15 suele ser relevante.
- Día 20 puede concentrar cobranza fuerte.
- Día 29/30 suele tener picos de cierre.
- ULTRA NUEVOS tiene un comportamiento distinto al núcleo histórico.

Ejemplo detectado:

ULTRA NUEVOS día 20 ≈ 10.76% promedio del mes.

Conclusión:

No se debe proyectar dividiendo por días transcurridos. Se debe usar curva acumulada histórica por día del mes.

---

## 9. Quality Gates

El módulo debe bloquear o degradar proyecciones cuando los datos no sean confiables.

### 9.1 Branch Quality Gate

Aplicable a sucursal.

Una proyección por sucursal debe marcarse como débil si cumple alguna condición:

- historical_months < 3
- confidence != alta
- historical_expected_mtd < 50000
- trend_factor > 3.0

Resultado esperado:

- projected_close = null
- projected_close_experimental = cálculo exploratorio
- projection_quality_issue.code = insufficient_branch_history

### 9.2 Cohort Quality Gate

Aplicable a cohortes.

Una cohorte debe bloquear proyección estable si cumple alguna condición:

- historical_months < 3
- confidence != alta
- historical_expected_mtd < 50000
- trend_factor > 3.0

Resultado esperado:

- projected_close = null
- projected_close_experimental = cálculo exploratorio
- projection_quality_issue.code = insufficient_cohort_history

### 9.3 Total Quality Gate

Si una cohorte necesaria no tiene proyección estable:

- ULTRA GYM.projected_close = null
- ULTRA GYM.projected_close_experimental = suma exploratoria
- ULTRA GYM.projection_quality_issue.code = partial_cohort_history

---

## 10. Confianza

La confianza debe reflejar cuántos meses comparables existen y qué tan estable es la base.

Categorías:

- alta
- media
- baja
- mixta

Regla conceptual:

Alta:
- suficientes meses comparables.
- sin señales extremas.

Media:
- histórico parcial, pero usable.

Baja:
- pocos meses.
- base pequeña.
- tendencia extrema.

Mixta:
- aplica a total cuando combina cohortes con diferente calidad.

---

## 11. Lectura ejecutiva

La lectura ejecutiva debe separar tres cosas.

### 11.1 Ritmo histórico

Pregunta:

¿Vamos arriba o abajo contra el comportamiento histórico esperado?

### 11.2 Ritmo contra meta

Pregunta:

¿Vamos arriba o abajo contra la meta mensual?

Solo aplica si hay meta cargada.

### 11.3 Calidad de proyección

Pregunta:

¿Este número se puede usar como proyección estable o solo como referencia experimental?

---

## 12. Reglas de interpretación

### 12.1 Si histórico dice bien pero meta dice mal

Mensaje correcto:

El ritmo histórico es positivo, pero la operación va por debajo del ritmo necesario para alcanzar la meta.

### 12.2 Si total va bien pero ULTRA 21 va mal

Mensaje correcto:

El total se ve favorecido por la aportación de gimnasios nuevos, pero el núcleo histórico opera por debajo de su ritmo esperado.

### 12.3 Si nuevos van bien pero tienen poco histórico

Mensaje correcto:

Los gimnasios nuevos aportan positivamente al corte, pero la proyección debe tomarse con cautela por histórico insuficiente.

### 12.4 Si la proyección es experimental

Mensaje correcto:

La referencia experimental muestra una posible dirección, pero no debe tratarse como proyección estable.

---

## 13. Fuentes de datos

### 13.1 Track Daily Mart

Fuente para:

- real MTD.
- base MTD.
- agregadoras MTD.
- metas.
- versiones Track.

Tabla:

track_daily_mart

### 13.2 Track Daily Versions

Fuente para:

- corte actual.
- tipo de versión.
- preview operativo.
- cierre canónico.

Tabla:

track_daily_versions

Versiones relevantes:

- preview_operativo
- cierre_canonico
- base_nocturna_canonica

### 13.3 Warehouse Venta Total

Fuente para:

- histórico diario.
- curva acumulada.
- patrones por día.
- cierre mensual histórico base.

Tablas:

- venta_total_snapshots
- track_venta_total_daily_branch_agg

### 13.4 Catálogo de sucursales Track

Fuente para:

- sucursales activas.
- orden Track.
- clasificación de cohortes.

Tabla:

track_branch_catalog

---

## 14. Exclusiones

El forecast debe excluir:

- CORPORATIVO
- GIMNASIO PRUEBA
- LA_VIGA

---

## 15. Permisos

El endpoint debe estar protegido por JWT.

Debe respetar permisos backend.

Reglas actuales:

- solo roles con lectura Track.
- beta allowlist para usuarios habilitados.

El frontend solo oculta o guía UI. El backend es la fuente real de permisos.

---

## 16. Endpoint principal

Endpoint:

GET /api/track/forecast/venta-total

Parámetros principales:

- track_date
- generation_mode
- scope
- branch

Ejemplos:

- /api/track/forecast/venta-total?track_date=2026-07-06&generation_mode=manual_preview&scope=national
- /api/track/forecast/venta-total?track_date=2026-07-06&generation_mode=manual_preview&scope=branch&branch=INSURGENTES

---

## 17. Response conceptual

El response puede contener:

- summary
- executive_status
- forecast_explanation
- forecast_cutoff
- same_day_history
- branch_drivers
- cohort_forecast
- anchored_remaining_forecast
- warnings
- data_quality

---

## 18. Warnings esperados

Warnings comunes:

- preview_operativo
- goal_pending
- insufficient_branch_history
- insufficient_cohort_history
- partial_cohort_history
- mixed_sources_base_vs_total

---

## 19. Riesgos conocidos

### 19.1 Mezcla base vs total

Riesgo:

Histórico Venta Total puede representar base, mientras Track Daily Mart puede representar base + agregadoras.

Acción:

Separar base, agregadoras y total antes de consolidar una proyección ejecutiva.

### 19.2 Histórico no comparable

Riesgo:

Comparar 2026 con 26 sucursales contra 2023 con 21 sucursales puede distorsionar el forecast.

Acción:

Usar cohortes.

### 19.3 Nuevos con poco histórico

Riesgo:

Los gimnasios nuevos pueden inflar la proyección por falta de histórico.

Acción:

Usar quality gates y ancla de cierre anterior.

### 19.4 Primeros días del mes

Riesgo:

Un rezago temprano puede multiplicarse demasiado si se usa curva pura.

Acción:

Usar anchored remaining forecast o blended forecast.

---

## 20. Decisiones pendientes

### 20.1 Método ejecutivo principal

Pendiente decidir si el método principal será:

- historical_curve
- cohort_forecast
- anchored_remaining_forecast
- blended_forecast

### 20.2 Tratamiento de agregadoras

Pendiente decidir si se proyectan como total:

base + agregadoras

o si se proyectan por separado:

base_forecast + agregadoras_forecast = total_forecast

### 20.3 Meta mensual

Pendiente decidir si el hero principal debe priorizar:

- proyección estadística
- brecha contra meta

Recomendación actual:

Mostrar ambas, pero no convertir la meta en la única lectura del módulo.

---

## 21. Criterios de aceptación

El módulo será considerado confiable cuando:

- separe correctamente base, agregadoras y total.
- muestre cohortes.
- bloquee proyecciones con histórico débil.
- explique claramente qué método se está usando.
- permita ver diferencia entre proyección estable y referencia experimental.
- muestre la brecha contra meta solo cuando exista meta.
- no compare total 2026 contra históricos no comparables sin advertencia.
- mantenga trazabilidad de versión Track y snapshot usado.

---

## 22. Estado actual

Estado: draft_v1.1

Este contrato debe actualizarse cada vez que cambie la metodología del forecast.
