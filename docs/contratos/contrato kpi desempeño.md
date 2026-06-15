# Contrato funcional, visual y técnico — KPI Desempeño / Núcleo Ultra 2.0

**Versión:** v0.3  
**Estado:** Contrato de producto en planeación  
**Implementación inicial:** Fase 1 únicamente  
**Proyecto:** Suite Ultra  
**Módulo:** KPI Desempeño  
**Nombre estratégico interno:** Núcleo Ultra 2.0  

---

## 1. Contexto general

Suite Ultra es una plataforma interna de operación e inteligencia de negocio construida con:

- **Frontend:** Angular, Angular Material, standalone components, rutas con hash `/#/ruta`.
- **Backend:** Flask, SQLAlchemy, Alembic/Flask-Migrate, blueprints bajo `/api`.
- **Base de datos:** PostgreSQL.
- **Despliegue:** Docker Compose.
- **Módulos existentes:** Tickets, Inventario, Mantenimiento Preventivo, Warehouse documental/estructurado y Track/BI.

El nuevo módulo nace para llevar a Suite Ultra los reportes mensuales que actualmente se presentan como PowerPoint, usando como fuente el histórico ya cargado de **KPI Desempeño** en Warehouse.

La prioridad inicial **no es inventar un dashboard nuevo**, sino replicar las gráficas existentes del informe mensual, pero actualizadas y alimentadas desde datos canónicos.

---

## 2. Principio rector del módulo

El módulo debe ser:

- Ejecutivo.
- Cerrado.
- Claro.
- Operativo.
- No intimidante.
- No tipo Power BI.
- Basado en reglas de negocio explícitas.
- Alimentado por Warehouse/Track respetando canonicalidad.

Principio técnico:

```text
Warehouse como fuente
snapshots canónicos como verdad
backend como dueño de reglas
frontend como visualización controlada
```

---

## 3. Objetivo del producto

Crear dentro de Suite Ultra un panel de **KPI Desempeño** que permita consultar y analizar la evolución de socios, crecimiento y desempeño operativo a partir de snapshots canónicos.

El módulo debe iniciar como una digitalización controlada del informe mensual actual, y evolucionar gradualmente hacia una capa ejecutiva de análisis llamada internamente **Núcleo Ultra 2.0**.

---

## 4. Nombre y ubicación

### Nombre visible recomendado

```text
KPI Desempeño
```

### Nombre estratégico interno

```text
Núcleo Ultra 2.0
```

### Ubicación en menú

```text
Track / KPI Desempeño
```

### Ruta frontend conceptual

```text
/#/track/kpi-desempeno
```

### Endpoint base conceptual

```text
/api/track/kpi-desempeno
```

Motivo: aunque la fuente nace en Warehouse, el consumo es de BI/Track. El usuario final no debe pensar en snapshots, sino en desempeño.

---

## 5. Alcance por fases

## Fase 1 — Informe mensual vivo

### Objetivo

Replicar las gráficas conocidas del PowerPoint mensual, pero alimentadas desde Warehouse y actualizadas al mes seleccionado.

### Incluye

1. **Cierre semanal de socios**.
2. **Cierre mensual de socios**.
3. **Histórico de socios desde 2023**.

### No incluye

- Penetración tecnológica.
- Trainingym.
- Nueva app Gasca.
- Metas históricas.
- Ranking por sucursal.
- Motor de crecimiento.
- Pulso semanal.
- IA narrativa.
- Proyecciones.
- Forecast.

### Regla central de Fase 1

Usar snapshots canónicos de KPI Desempeño:

```text
report_type_key = 'kpi_desempeno'
snapshot_kind = 'daily'
is_canonical = true
```

---

## Fase 2 — Lecturas operativas controladas

### Objetivo

Convertir el informe mensual en una herramienta de análisis operativo sin hacerlo intimidante.

### Vistas candidatas

1. **Ranking por sucursal**.
2. **Motor de crecimiento**.
3. **Pulso semanal**.
4. **Comparativos rápidos**.

### Métricas principales

- `socios_activos_inicio_mes`
- `socios_activos_cierre_mes`
- `crecimiento_real`
- `clientes_nuevos`
- `reactivaciones`
- `bajas`
- `movimiento_reportado`
- `ajuste_no_explicado`

### Reglas de negocio

```text
crecimiento_real = socios_activos_cierre_mes - socios_activos_inicio_mes
```

```text
movimiento_reportado = clientes_nuevos + reactivaciones - bajas
```

```text
ajuste_no_explicado = crecimiento_real - movimiento_reportado
```

### Nota importante

La fórmula:

```text
clientes_nuevos + reactivaciones - bajas
```

no debe usarse como crecimiento principal. Solo debe usarse como auditoría o explicación del movimiento reportado.

---

## Fase 3 — Núcleo Ultra 2.0

### Objetivo

Convertir KPI Desempeño en una capa ejecutiva de lectura estratégica.

### Vistas candidatas

1. **Antes / después de Julián**.
2. **Comparativo mismo mes año anterior**.
3. **Comparativo mes anterior**.
4. **Tendencia nacional**.
5. **Narrativa ejecutiva automática**.
6. **Penetración tecnológica con nueva app Gasca**.

### Nota sobre penetración tecnológica

La penetración tecnológica queda fuera de Fase 1 porque Gasca está en proceso de crear una nueva app que suplirá a Trainingym.

No tiene sentido generar un reporte basado en Trainingym si la fuente será reemplazada. Esta vista debe retomarse cuando la nueva app Gasca esté liberada y los datos sean estables.

---

## 6. Estado de datos

### Histórico cargado en Warehouse

Rango histórico validado:

```text
2023-01-01 a 2025-09-07
```

Cobertura:

- Sin días faltantes en el rango validado.
- Sin duplicados canónicos.
- De septiembre 2025 a actualidad ya existe información en producción.

### Tablas principales

```text
kpi_desempeno_snapshots
kpi_desempeno_snapshot_rows
```

### Regla mensual oficial

Usar el último snapshot canónico disponible de cada mes:

```text
report_type_key = 'kpi_desempeno'
snapshot_kind = 'daily'
is_canonical = true
business_date = último business_date disponible del mes
```

### Regla semanal oficial

Usar cierre semanal, no promedio semanal:

```text
Para cada sucursal y semana:
cierre_semanal = último snapshot canónico disponible dentro de la semana
```

### Regla bimestral / trimestral

```text
Para cada periodo:
usar el último business_date canónico disponible dentro del periodo
```

Ejemplo trimestral:

```text
Q1 = último snapshot canónico disponible de marzo
Q2 = último snapshot canónico disponible de junio
Q3 = último snapshot canónico disponible de septiembre
Q4 = último snapshot canónico disponible de diciembre
```

Ejemplo bimestral:

```text
Ene-Feb = último snapshot canónico disponible de febrero
Mar-Abr = último snapshot canónico disponible de abril
May-Jun = último snapshot canónico disponible de junio
Jul-Ago = último snapshot canónico disponible de agosto
Sep-Oct = último snapshot canónico disponible de octubre
Nov-Dic = último snapshot canónico disponible de diciembre
```

---

## 7. Contrato visual general

La estructura visual debe estar preparada para todas las fases, aunque inicialmente solo se muestre Fase 1.

### Header

```text
KPI Desempeño
Fuente: Warehouse · KPI Desempeño · snapshots canónicos
Corte seleccionado: Mes / Año
```

### Filtros base

Desde Fase 1 deben considerarse estos filtros:

- Año.
- Mes.
- Sucursal / Todas.
- Agrupación histórica: mensual, bimestral, trimestral.

### Recomendación de UI

No mostrar tabs vacíos en Fase 1. Internamente el módulo puede quedar preparado para crecer, pero visualmente solo debe mostrar lo útil y activo.

---

## 8. Contrato visual — Fase 1

### Pantalla inicial

```text
KPI Desempeño
Informe mensual vivo
```

### Bloques visibles

1. **Cierre semanal de socios**.
2. **Cierre mensual de socios**.
3. **Histórico de socios desde 2023**.

---

## 8.1 Cierre semanal de socios

### Objetivo

Mostrar el comportamiento de socios por semana dentro del mes seleccionado.

### Visual esperado

Gráfica de barras agrupadas.

### Métrica

```text
socios_activos al cierre semanal
```

### Regla

```text
Para cada sucursal y semana:
usar el último snapshot canónico disponible de la semana
```

### Fuente

```text
kpi_desempeno_snapshots
kpi_desempeno_snapshot_rows
```

### Notas

- Se decidió usar cierre semanal para mantener consistencia.
- No usar promedio semanal.
- El nombre exacto del campo debe validarse contra el modelo real.

---

## 8.2 Cierre mensual de socios

### Objetivo

Replicar la gráfica mensual del informe PowerPoint.

### Visual esperado

Gráfica de barras agrupadas por sucursal y mes.

### Métrica

```text
socios_activos_cierre_mes
```

### Regla

```text
Para cada sucursal y mes:
usar el último snapshot canónico disponible del mes
```

### Fuente

```text
kpi_desempeno_snapshots
kpi_desempeno_snapshot_rows
```

---

## 8.3 Histórico de socios desde 2023

### Objetivo

Mostrar evolución histórica desde 2023 sin saturar la gráfica.

### Visual esperado

Gráfica de barras o líneas controladas, según se valide visualmente.

### Agrupaciones permitidas

```text
Mensual
Bimestral
Trimestral
```

### Default recomendado

```text
Trimestral
```

### Métrica

```text
socios_activos_cierre_periodo
```

### Regla

```text
Para cada sucursal y periodo:
usar el último snapshot canónico disponible del periodo
```

### Motivo

Evitar una gráfica de demasiadas líneas, barras o colores al analizar desde 2023.

---

## 9. Vistas futuras — Fase 2

## 9.1 Ranking por sucursal

### Objetivo

Identificar rápidamente sucursales con mejor y peor desempeño.

### Rankings candidatos

- Top crecimiento real.
- Bottom crecimiento real.
- Top clientes nuevos.
- Top reactivaciones.
- Top bajas.
- Mayor ajuste no explicado.

### Métricas base

```text
crecimiento_real
clientes_nuevos
reactivaciones
bajas
movimiento_reportado
ajuste_no_explicado
```

---

## 9.2 Motor de crecimiento

### Objetivo

Explicar de dónde viene el crecimiento real.

### Vista conceptual

```text
Socios inicio
+ Clientes nuevos
+ Reactivaciones
- Bajas
+/- Ajuste no explicado
= Socios cierre
```

### Regla principal

```text
crecimiento_real = socios_activos_cierre_mes - socios_activos_inicio_mes
```

### Regla de auditoría

```text
movimiento_reportado = clientes_nuevos + reactivaciones - bajas
```

```text
ajuste_no_explicado = crecimiento_real - movimiento_reportado
```

### Valor del análisis

Esta vista explica el crecimiento, no solo lo muestra.

---

## 9.3 Pulso semanal

### Objetivo

Crear una vista operativa basada en ventas, reactivaciones y bajas.

### Inspiración

Archivo Excel de referencia: `Ventas y reactivación.xlsx`.

### Métricas candidatas

- Ventas nuevas últimos 7 días.
- Reactivaciones últimos 7 días.
- Bajas últimos 7 días.
- Crecimiento últimos 7 días.
- Comparativo contra 7 días previos.

### Regla conceptual

```text
crecimiento_semanal = ventas_nuevas + reactivaciones - bajas
```

### Nota

Esta vista debe considerarse operativa, no como crecimiento oficial mensual.

---

## 9.4 Comparativos rápidos

### Objetivo

Permitir análisis ejecutivo sin abrir exploración libre.

### Comparativos candidatos

- Mes seleccionado vs mes anterior.
- Mes seleccionado vs mismo mes del año anterior.
- Sucursal vs nacional.
- Región vs nacional.

---

## 10. Vistas futuras — Fase 3

## 10.1 Antes / después de Julián

### Objetivo

Evaluar desempeño comparando periodos antes y después de un punto operativo relevante.

### Nota

Debe definirse una fecha oficial de corte antes de implementar.

---

## 10.2 Tendencia nacional

### Objetivo

Mostrar evolución agregada nacional.

### Métricas candidatas

- Socios activos cierre.
- Crecimiento real.
- Clientes nuevos.
- Reactivaciones.
- Bajas.

---

## 10.3 Narrativa ejecutiva automática

### Objetivo

Generar lectura ejecutiva breve basada en reglas.

### Ejemplo de salida esperada

```text
En el mes seleccionado, la cadena cerró con X socios activos,
lo que representa un crecimiento real de Y socios contra el inicio del mes.
Las sucursales con mayor crecimiento fueron A, B y C.
El principal riesgo operativo se observa en D por incremento de bajas.
```

### Regla

No debe depender de respuestas mágicas. Debe usar métricas calculadas y criterios explícitos.

---

## 10.4 Penetración tecnológica con nueva app Gasca

### Objetivo

Medir adopción de la nueva app cuando Gasca libere la fuente definitiva.

### Estado actual

Pendiente.

### Motivo de exclusión actual

Trainingym será reemplazado. Construir sobre esa fuente ahora generaría deuda técnica.

---

## 11. Arquitectura técnica propuesta

## Backend

La ruta no debe contener lógica pesada. Debe recibir filtros, validar permisos y llamar servicios.

### Archivos conceptuales

```text
backend/app/routes/track_kpi_desempeno_routes.py
backend/app/warehouse/services/kpi_desempeno_query_service.py
backend/app/warehouse/services/kpi_desempeno_metrics_service.py
backend/app/warehouse/services/kpi_desempeno_response_builder.py
```

### Responsabilidades

#### `track_kpi_desempeno_routes.py`

- Exponer endpoints.
- Validar JWT.
- Validar permisos.
- Recibir filtros.
- Delegar consultas/cálculos.
- No calcular métricas complejas.

#### `kpi_desempeno_query_service.py`

- Consultar snapshots canónicos.
- Aplicar reglas de `business_date`.
- Resolver periodos semanales, mensuales, bimestrales y trimestrales.
- Respetar `report_type_key`, `snapshot_kind` e `is_canonical`.

#### `kpi_desempeno_metrics_service.py`

- Calcular `crecimiento_real`.
- Calcular `movimiento_reportado`.
- Calcular `ajuste_no_explicado`.
- Preparar métricas futuras sin romper Fase 1.

#### `kpi_desempeno_response_builder.py`

- Armar JSON listo para frontend.
- Mantener contrato estable por secciones.
- Evitar que cada gráfica tenga una respuesta incompatible.

---

## 12. Endpoints conceptuales

## Fase 1

```text
GET /api/track/kpi-desempeno/monthly-report
```

Debe devolver:

- `metadata`
- `sections.weekly_closing`
- `sections.monthly_closing`
- `sections.historical_closing`

---

## Fase 2

```text
GET /api/track/kpi-desempeno/growth-engine
```

Debe devolver:

- `socios_inicio`
- `clientes_nuevos`
- `reactivaciones`
- `bajas`
- `movimiento_reportado`
- `ajuste_no_explicado`
- `socios_cierre`

```text
GET /api/track/kpi-desempeno/ranking
```

Debe devolver rankings cerrados:

- `top_crecimiento`
- `bottom_crecimiento`
- `top_clientes_nuevos`
- `top_reactivaciones`
- `top_bajas`
- `mayor_ajuste_no_explicado`

---

## Fase 3

```text
GET /api/track/kpi-desempeno/executive-summary
```

Debe devolver narrativa ejecutiva basada en reglas y métricas calculadas.

---

## 13. Contrato JSON conceptual

La respuesta debe nacer por secciones para soportar crecimiento futuro.

```json
{
  "metadata": {
    "source": "warehouse",
    "report_type_key": "kpi_desempeno",
    "snapshot_kind": "daily",
    "canonical_only": true,
    "selected_period": "2025-02",
    "generated_at": "2026-06-15T00:00:00-07:00"
  },
  "filters": {
    "year": 2025,
    "month": 2,
    "branch_scope": "all",
    "historical_granularity": "quarterly"
  },
  "sections": [
    {
      "key": "weekly_closing",
      "title": "Cierre semanal de socios",
      "chart_type": "grouped_bar",
      "data": []
    },
    {
      "key": "monthly_closing",
      "title": "Cierre mensual de socios",
      "chart_type": "grouped_bar",
      "data": []
    },
    {
      "key": "historical_closing",
      "title": "Histórico de socios",
      "chart_type": "grouped_bar",
      "granularity": "quarterly",
      "data": []
    }
  ]
}
```

### Motivo

Fase 2 y Fase 3 podrán agregar nuevas secciones sin romper el contrato de Fase 1.

---

## 14. Frontend propuesto

### Carpeta conceptual

```text
frontend/src/app/track/kpi-desempeno/
```

### Componentes base

```text
kpi-desempeno-page.component.ts
kpi-desempeno-page.component.html
kpi-desempeno-page.component.css
```

### Componentes hijos

```text
components/kpi-filter-bar/
components/kpi-source-badge/
components/kpi-weekly-closing-chart/
components/kpi-monthly-closing-chart/
components/kpi-historical-closing-chart/
```

### Servicio Angular

```text
frontend/src/app/track/services/kpi-desempeno.service.ts
```

### Regla Angular

- Lógica en `.ts`.
- HTML solo estructura visual.
- Bindings simples.
- Llamadas a métodos ya definidos.
- Sin cálculos complejos en template.
- Componentes separados en `.ts`, `.html` y `.css`.
- No templates inline.
- No estilos inline.

---

## 15. Permisos

El backend debe ser la fuente real de permisos.

### Roles sugeridos

```text
SUPER_ADMIN
ADMINISTRADOR
ADMIN
LECTOR_GLOBAL
GERENTE_REGIONAL
GERENTE
SISTEMAS
```

### Reglas

```text
GERENTE ve solo su sucursal o sucursales permitidas.
GERENTE_REGIONAL ve sus regiones/sucursales asignadas.
LECTOR_GLOBAL / ADMIN / SISTEMAS ve nacional.
```

### Nota

El frontend puede ocultar o guiar la UI, pero no debe ser la fuente real de seguridad.

---

## 16. Reglas de negocio obligatorias

### Canonicalidad

Todas las vistas deben respetar:

```text
report_type_key = 'kpi_desempeno'
snapshot_kind = 'daily'
is_canonical = true
```

### Fechas

Las reglas deben basarse en `business_date`, no en fecha de carga.

### Métrica principal de crecimiento

```text
crecimiento_real = socios_activos_cierre_mes - socios_activos_inicio_mes
```

### Métrica de auditoría

```text
movimiento_reportado = clientes_nuevos + reactivaciones - bajas
```

### Ajuste no explicado

```text
ajuste_no_explicado = crecimiento_real - movimiento_reportado
```

---

## 17. Qué no debe hacerse

- No crear un Power BI interno.
- No crear filtros infinitos.
- No usar metas históricas no confiables.
- No construir penetración tecnológica sobre Trainingym.
- No mezclar fecha de carga con `business_date`.
- No calcular reglas críticas en frontend.
- No depender de ocultar botones para permisos.
- No meter hacks para cuadrar crecimiento.
- No escribir lógica Angular compleja en HTML.

---

## 18. Orden de trabajo recomendado

### Paso 1

Cerrar contrato funcional, visual y técnico del módulo.

### Paso 2

Validar nombres reales de campos en `kpi_desempeno_snapshot_rows`.

### Paso 3

Definir contrato JSON exacto de Fase 1.

### Paso 4

Diseñar estructura visual final de la pantalla.

### Paso 5

Implementar backend Fase 1.

### Paso 6

Implementar frontend Fase 1.

### Paso 7

Validar contra PowerPoint original.

### Paso 8

Publicar Fase 1.

### Paso 9

Abrir Fase 2.

---

## 19. Validación de Fase 1

La Fase 1 se considera correcta cuando:

- Las tres gráficas principales existen en Suite.
- Los datos vienen de Warehouse.
- Solo se usan snapshots canónicos.
- Las fechas usan `business_date`.
- La gráfica semanal usa cierre semanal.
- La gráfica histórica permite mensual, bimestral y trimestral.
- El default histórico es trimestral.
- El resultado replica la intención del informe mensual sin meter vistas nuevas.
- No se incluye penetración tecnológica.
- No se incluye Trainingym.
- No se incluyen metas históricas no confiables.

---

## 20. Estado actual del contrato

```text
Producto completo:
KPI Desempeño / Núcleo Ultra 2.0

Implementación inicial:
Fase 1 solamente

Estructura técnica:
Preparada para Fase 2 y Fase 3

Fuente:
Warehouse · KPI Desempeño · snapshots canónicos

Pendiente antes de código:
Contrato JSON exacto de Fase 1
Validación de campos reales en DB/modelos
```

---

## 21. Decisiones cerradas

1. El módulo se llamará **KPI Desempeño**.
2. El nombre estratégico interno será **Núcleo Ultra 2.0**.
3. Fase 1 replica las gráficas existentes, no inventa dashboard nuevo.
4. La gráfica semanal usará **cierre semanal**, no promedio.
5. La gráfica histórica tendrá agrupación mensual, bimestral y trimestral.
6. El default histórico será trimestral.
7. Penetración tecnológica queda fuera hasta nueva app Gasca.
8. Trainingym no se usará como base de nuevos reportes.
9. Las metas históricas antes de septiembre 2025 no serán foco.
10. El crecimiento principal será `crecimiento_real`, no `clientes_nuevos + reactivaciones - bajas`.

---

## 22. Decisiones pendientes

1. Validar nombres exactos de campos en `kpi_desempeno_snapshot_rows`.
2. Definir si las gráficas serán barras agrupadas, líneas o combinación según legibilidad.
3. Definir librería visual si la actual de Suite no cubre bien estas gráficas.
4. Definir contrato JSON exacto de Fase 1.
5. Definir permisos finales por rol/sucursal/región.
6. Definir si el histórico nacional y por sucursal se muestran en la misma gráfica o en modo alterno.
7. Definir fecha oficial para análisis antes/después de Julián en Fase 3.
8. Definir fuente definitiva para penetración tecnológica cuando Gasca libere la app.

---




##   FASE 1



# Contrato JSON Fase 1 — KPI Desempeño / Núcleo Ultra 2.0

**Versión:** v0.1  
**Estado:** Propuesta de contrato técnico antes de código  
**Módulo:** KPI Desempeño  
**Nombre estratégico:** Núcleo Ultra 2.0  
**Implementación inicial:** Fase 1 solamente  
**Estructura preparada para:** Fase 2 y Fase 3  

---

## 1. Propósito del contrato

Este documento define el contrato técnico entre backend y frontend para la **Fase 1** del módulo **KPI Desempeño** dentro de Suite Ultra.

La Fase 1 busca replicar las gráficas conocidas del informe mensual tipo PowerPoint, pero alimentadas desde Warehouse con snapshots canónicos de KPI Desempeño.

El objetivo no es crear un Power BI ni un dashboard abierto. El objetivo es crear una pantalla cerrada, clara, ejecutiva y operativa, que pueda crecer hacia Fase 2 y Fase 3 sin romper estructura.

---

## 2. Alcance Fase 1

### Incluye

La Fase 1 incluye únicamente tres visuales:

1. **Cierre semanal de socios**
2. **Cierre mensual de socios**
3. **Histórico de socios desde 2023**

### No incluye en Fase 1

Queda fuera de esta fase:

- Penetración tecnológica
- Trainingym
- Nueva app Gasca
- Metas históricas
- Ranking por sucursal
- Motor de crecimiento
- Pulso semanal de ventas/reactivaciones/bajas
- Ajuste no explicado
- Narrativa ejecutiva automática
- Forecast
- Comparativos antes/después de Julián

La estructura del contrato sí debe permitir agregar esas vistas después sin rehacer el módulo.

---

## 3. Fuente de datos oficial

### Tablas base

- `kpi_desempeno_snapshots`
- `kpi_desempeno_snapshot_rows`

### Filtros obligatorios de Warehouse

Toda consulta de Fase 1 debe respetar:

```sql
report_type_key = 'kpi_desempeno'
snapshot_kind = 'daily'
is_canonical = true
```

### Regla de fuente

Warehouse es la fuente de verdad para KPI Desempeño.

El backend debe resolver las reglas de snapshots, fechas, permisos y canonicalidad. El frontend solo debe renderizar el contrato recibido.

---

## 4. Reglas de negocio Fase 1

### 4.1 Cierre semanal

Para cada sucursal y semana:

```text
cierre_semanal = último snapshot canónico disponible dentro de la semana
```

La gráfica semanal **no usará promedio semanal**.

Decisión cerrada:

```text
La métrica semanal será cierre semanal para mantener consistencia.
```

---

### 4.2 Cierre mensual

Para cada sucursal y mes:

```text
cierre_mensual = último snapshot canónico disponible dentro del mes
```

Métrica principal:

```text
socios_activos_cierre_mes
```

Si el nombre real del campo difiere, el backend debe normalizarlo en la respuesta como `active_members_closing`.

---

### 4.3 Histórico desde 2023

El histórico debe permitir granularidad controlada para evitar gráficas saturadas.

Granularidades permitidas:

- `monthly`
- `bimonthly`
- `quarterly`

Default recomendado:

```text
quarterly
```

Regla:

```text
Para cada periodo histórico:
usar el último snapshot canónico disponible dentro del periodo.
```

Ejemplo trimestral:

```text
Q1 = último snapshot canónico disponible de enero-marzo
Q2 = último snapshot canónico disponible de abril-junio
Q3 = último snapshot canónico disponible de julio-septiembre
Q4 = último snapshot canónico disponible de octubre-diciembre
```

Ejemplo bimestral:

```text
B1 = enero-febrero
B2 = marzo-abril
B3 = mayo-junio
B4 = julio-agosto
B5 = septiembre-octubre
B6 = noviembre-diciembre
```

---

## 5. Endpoint principal Fase 1

### Método

```http
GET /api/track/kpi-desempeno/monthly-report
```

### Responsabilidad

Este endpoint debe devolver todas las secciones necesarias para la Fase 1:

- Metadata del corte
- Filtros aplicados
- Cierre semanal
- Cierre mensual
- Histórico de socios
- Advertencias de datos si aplica

---

## 6. Query params permitidos

### Parámetros

| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---:|---:|---:|---|
| `year` | integer | Sí | — | Año del corte mensual seleccionado |
| `month` | integer | Sí | — | Mes del corte mensual seleccionado, 1 a 12 |
| `branch_scope` | string | No | `all` | Alcance de sucursal |
| `branch_id` | integer | No | null | ID de sucursal cuando se consulta una sucursal específica |
| `region_id` | integer | No | null | ID de región cuando se consulta una región específica |
| `historical_granularity` | string | No | `quarterly` | Granularidad del histórico |
| `historical_start_year` | integer | No | `2023` | Año inicial del histórico |
| `historical_end_year` | integer | No | año seleccionado | Año final del histórico |

---

## 7. Enums de contrato

### `branch_scope`

Valores permitidos:

```json
[
  "all",
  "branch",
  "region"
]
```

### `historical_granularity`

Valores permitidos:

```json
[
  "monthly",
  "bimonthly",
  "quarterly"
]
```

### `section.key`

Valores Fase 1:

```json
[
  "weekly_closing",
  "monthly_closing",
  "historical_closing"
]
```

### `chart_type`

Valores Fase 1:

```json
[
  "grouped_bar",
  "line",
  "table"
]
```

Aunque Fase 1 probablemente use `grouped_bar`, el contrato permite otros tipos para crecimiento posterior.

---

## 8. Request ejemplo

### Consulta nacional default

```http
GET /api/track/kpi-desempeno/monthly-report?year=2025&month=2&historical_granularity=quarterly
```

### Consulta por sucursal

```http
GET /api/track/kpi-desempeno/monthly-report?year=2025&month=2&branch_scope=branch&branch_id=12&historical_granularity=quarterly
```

### Consulta por región

```http
GET /api/track/kpi-desempeno/monthly-report?year=2025&month=2&branch_scope=region&region_id=3&historical_granularity=bimonthly
```

---

## 9. Response JSON general

El backend debe responder por secciones. Esto evita que el frontend quede amarrado a una sola gráfica fija.

```json
{
  "metadata": {},
  "filters": {},
  "sections": [],
  "warnings": [],
  "permissions": {}
}
```

---

## 10. Metadata

### Estructura

```json
{
  "metadata": {
    "module_key": "kpi_desempeno",
    "module_name": "KPI Desempeño",
    "strategic_name": "Núcleo Ultra 2.0",
    "source": "warehouse",
    "report_type_key": "kpi_desempeno",
    "snapshot_kind": "daily",
    "canonical_only": true,
    "selected_year": 2025,
    "selected_month": 2,
    "selected_period_label": "Febrero 2025",
    "generated_at": "2026-06-15T00:00:00-07:00",
    "timezone": "America/Tijuana",
    "data_range": {
      "historical_start_date": "2023-01-01",
      "historical_end_date": "2025-09-07",
      "production_continues_from": "2025-09-08"
    }
  }
}
```

### Notas

- `generated_at` debe estar en zona horaria `America/Tijuana`.
- `data_range` documenta el rango histórico validado.
- El frontend puede mostrar esta metadata como badge de fuente.

---

## 11. Filters

### Estructura

```json
{
  "filters": {
    "year": 2025,
    "month": 2,
    "branch_scope": "all",
    "branch_id": null,
    "region_id": null,
    "historical_granularity": "quarterly",
    "historical_start_year": 2023,
    "historical_end_year": 2025
  }
}
```

---

## 12. Permissions

### Estructura

```json
{
  "permissions": {
    "can_view_national": true,
    "can_view_region": true,
    "can_view_branch": true,
    "allowed_branch_ids": [],
    "allowed_region_ids": []
  }
}
```

### Reglas esperadas

- `SUPER_ADMIN`, `ADMINISTRADOR`, `ADMIN`, `LECTOR_GLOBAL`, `SISTEMAS` pueden ver nacional.
- `GERENTE_REGIONAL` puede ver sus regiones/sucursales asignadas.
- `GERENTE` puede ver solo su sucursal o sucursales permitidas.
- El frontend puede ocultar opciones, pero el backend filtra realmente.

---

# 13. Sections

Todas las gráficas se devuelven dentro de `sections`.

Cada sección debe tener estructura común:

```json
{
  "key": "weekly_closing",
  "title": "Cierre semanal de socios",
  "description": "Último snapshot canónico disponible de cada semana.",
  "chart_type": "grouped_bar",
  "status": "ready",
  "data_rule": "last_canonical_snapshot_in_period",
  "x_axis": {},
  "y_axis": {},
  "series": [],
  "summary": {},
  "source_snapshots": []
}
```

---

## 14. Section 1 — Weekly closing

### Key

```text
weekly_closing
```

### Título UI

```text
Cierre semanal de socios
```

### Descripción UI

```text
Socios activos al cierre de cada semana del mes seleccionado, usando el último snapshot canónico disponible de la semana.
```

### Regla

```text
Último snapshot canónico disponible dentro de cada semana.
```

### Response ejemplo

```json
{
  "key": "weekly_closing",
  "title": "Cierre semanal de socios",
  "description": "Socios activos al cierre de cada semana del mes seleccionado.",
  "chart_type": "grouped_bar",
  "status": "ready",
  "data_rule": "last_canonical_snapshot_in_week",
  "x_axis": {
    "key": "week_label",
    "label": "Semana"
  },
  "y_axis": {
    "key": "active_members_closing",
    "label": "Socios activos"
  },
  "series": [
    {
      "branch_id": 1,
      "branch_canon": "ADLM",
      "branch_label": "ADLM",
      "points": [
        {
          "period_key": "2025-W05",
          "period_label": "Semana 1",
          "start_date": "2025-02-01",
          "end_date": "2025-02-02",
          "business_date": "2025-02-02",
          "active_members_closing": 1380,
          "snapshot_id": 1001
        },
        {
          "period_key": "2025-W06",
          "period_label": "Semana 2",
          "start_date": "2025-02-03",
          "end_date": "2025-02-09",
          "business_date": "2025-02-09",
          "active_members_closing": 1412,
          "snapshot_id": 1008
        }
      ]
    }
  ],
  "summary": {
    "branches_count": 1,
    "periods_count": 5,
    "selected_month": "2025-02",
    "national_closing_last_week": 1412
  },
  "source_snapshots": [
    {
      "snapshot_id": 1001,
      "business_date": "2025-02-02",
      "snapshot_kind": "daily",
      "is_canonical": true
    }
  ]
}
```

---

## 15. Section 2 — Monthly closing

### Key

```text
monthly_closing
```

### Título UI

```text
Cierre mensual de socios
```

### Descripción UI

```text
Socios activos al cierre de cada mes, usando el último snapshot canónico disponible del mes.
```

### Regla

```text
Último snapshot canónico disponible dentro de cada mes.
```

### Response ejemplo

```json
{
  "key": "monthly_closing",
  "title": "Cierre mensual de socios",
  "description": "Socios activos al cierre mensual por sucursal.",
  "chart_type": "grouped_bar",
  "status": "ready",
  "data_rule": "last_canonical_snapshot_in_month",
  "x_axis": {
    "key": "month_label",
    "label": "Mes"
  },
  "y_axis": {
    "key": "active_members_closing",
    "label": "Socios activos"
  },
  "series": [
    {
      "branch_id": 1,
      "branch_canon": "ADLM",
      "branch_label": "ADLM",
      "points": [
        {
          "period_key": "2025-01",
          "period_label": "Enero 2025",
          "start_date": "2025-01-01",
          "end_date": "2025-01-31",
          "business_date": "2025-01-31",
          "active_members_closing": 1360,
          "snapshot_id": 980
        },
        {
          "period_key": "2025-02",
          "period_label": "Febrero 2025",
          "start_date": "2025-02-01",
          "end_date": "2025-02-28",
          "business_date": "2025-02-28",
          "active_members_closing": 1435,
          "snapshot_id": 1028
        }
      ]
    }
  ],
  "summary": {
    "branches_count": 1,
    "periods_count": 2,
    "selected_month": "2025-02",
    "national_selected_month_closing": 1435
  },
  "source_snapshots": [
    {
      "snapshot_id": 1028,
      "business_date": "2025-02-28",
      "snapshot_kind": "daily",
      "is_canonical": true
    }
  ]
}
```

---

## 16. Section 3 — Historical closing

### Key

```text
historical_closing
```

### Título UI

```text
Histórico de socios desde 2023
```

### Descripción UI

```text
Evolución histórica de socios activos, agrupada por granularidad controlada para evitar saturación visual.
```

### Granularidad default

```text
quarterly
```

### Response ejemplo

```json
{
  "key": "historical_closing",
  "title": "Histórico de socios desde 2023",
  "description": "Evolución histórica de socios activos por periodo.",
  "chart_type": "grouped_bar",
  "status": "ready",
  "data_rule": "last_canonical_snapshot_in_period",
  "granularity": "quarterly",
  "x_axis": {
    "key": "period_label",
    "label": "Periodo"
  },
  "y_axis": {
    "key": "active_members_closing",
    "label": "Socios activos"
  },
  "series": [
    {
      "branch_id": 1,
      "branch_canon": "ADLM",
      "branch_label": "ADLM",
      "points": [
        {
          "period_key": "2023-Q1",
          "period_label": "Q1 2023",
          "start_date": "2023-01-01",
          "end_date": "2023-03-31",
          "business_date": "2023-03-31",
          "active_members_closing": 1150,
          "snapshot_id": 201
        },
        {
          "period_key": "2023-Q2",
          "period_label": "Q2 2023",
          "start_date": "2023-04-01",
          "end_date": "2023-06-30",
          "business_date": "2023-06-30",
          "active_members_closing": 1215,
          "snapshot_id": 290
        }
      ]
    }
  ],
  "summary": {
    "branches_count": 1,
    "periods_count": 12,
    "historical_start_year": 2023,
    "historical_end_year": 2025,
    "granularity": "quarterly"
  },
  "source_snapshots": [
    {
      "snapshot_id": 201,
      "business_date": "2023-03-31",
      "snapshot_kind": "daily",
      "is_canonical": true
    }
  ]
}
```

---

## 17. Warnings

El backend debe devolver advertencias no fatales cuando haya datos incompletos, decisiones automáticas o casos relevantes.

### Estructura

```json
{
  "warnings": [
    {
      "code": "PARTIAL_CURRENT_MONTH",
      "message": "El mes seleccionado aún no está cerrado; se usó el último snapshot canónico disponible.",
      "severity": "info"
    }
  ]
}
```

### Códigos sugeridos

| Código | Severidad | Significado |
|---|---|---|
| `PARTIAL_CURRENT_MONTH` | info | El mes actual no está cerrado |
| `NO_DATA_FOR_PERIOD` | warning | No hay datos para el periodo solicitado |
| `LIMITED_BY_PERMISSIONS` | info | El usuario solo ve sucursales permitidas |
| `HISTORICAL_RANGE_ADJUSTED` | info | El rango histórico fue ajustado por disponibilidad |
| `BRANCH_WITHOUT_DATA` | warning | Una sucursal esperada no tiene datos en el periodo |
| `SNAPSHOT_NOT_MONTH_END` | info | El cierre usa último snapshot disponible, no necesariamente fin natural de mes |

---

## 18. Errores esperados

### Formato general

```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "El parámetro month debe estar entre 1 y 12.",
    "details": {
      "field": "month",
      "value": 15
    }
  }
}
```

### Códigos

| Código | HTTP | Caso |
|---|---:|---|
| `UNAUTHORIZED` | 401 | No hay JWT válido |
| `FORBIDDEN` | 403 | El usuario no tiene permiso para el módulo o alcance solicitado |
| `INVALID_FILTER` | 400 | Query param inválido |
| `MISSING_REQUIRED_FILTER` | 400 | Falta `year` o `month` |
| `NO_CANONICAL_DATA` | 404 | No existen snapshots canónicos para el periodo |
| `INTERNAL_ERROR` | 500 | Error inesperado |

---

## 19. Contrato de permisos backend

El backend es la fuente real de permisos.

### Roles con vista nacional

- `SUPER_ADMIN`
- `ADMINISTRADOR`
- `ADMIN`
- `LECTOR_GLOBAL`
- `SISTEMAS`

### Roles con vista limitada

- `GERENTE_REGIONAL`
- `GERENTE`

### Regla

```text
El frontend puede ocultar opciones, pero el backend debe filtrar datos siempre.
```

---

## 20. Contrato frontend Fase 1

### Ruta conceptual

```text
/#/track/kpi-desempeno
```

### Servicio Angular conceptual

```text
frontend/src/app/track/services/kpi-desempeno.service.ts
```

### Componentes conceptuales

```text
frontend/src/app/track/kpi-desempeno/kpi-desempeno-page.component.ts
frontend/src/app/track/kpi-desempeno/kpi-desempeno-page.component.html
frontend/src/app/track/kpi-desempeno/kpi-desempeno-page.component.css

frontend/src/app/track/kpi-desempeno/components/kpi-filter-bar/
frontend/src/app/track/kpi-desempeno/components/kpi-source-badge/
frontend/src/app/track/kpi-desempeno/components/kpi-section-card/
frontend/src/app/track/kpi-desempeno/components/kpi-weekly-closing-chart/
frontend/src/app/track/kpi-desempeno/components/kpi-monthly-closing-chart/
frontend/src/app/track/kpi-desempeno/components/kpi-historical-closing-chart/
```

### Regla Angular

- Lógica en `.ts`
- HTML solo estructura visual
- Bindings simples
- Llamadas a métodos ya definidos
- Componentes separados en `.ts`, `.html` y `.css`
- Nada de cálculos complejos en template

---

## 21. Contrato backend conceptual

### Ruta

```text
backend/app/routes/track_kpi_desempeno_routes.py
```

Responsabilidad:

- Exponer endpoints
- Validar JWT
- Validar permisos
- Validar filtros
- Llamar servicios
- No calcular métricas complejas dentro de la ruta

### Servicios sugeridos

```text
backend/app/warehouse/services/kpi_desempeno_query_service.py
backend/app/warehouse/services/kpi_desempeno_metrics_service.py
backend/app/warehouse/services/kpi_desempeno_response_builder.py
```

### Responsabilidades

#### `kpi_desempeno_query_service.py`

- Consultar snapshots canónicos
- Resolver último `business_date` por semana, mes, bimestre o trimestre
- Aplicar filtros de Warehouse
- Aplicar alcance de sucursal/región ya validado

#### `kpi_desempeno_metrics_service.py`

- Normalizar campos de KPI Desempeño
- Preparar métricas base
- Dejar lista la estructura para Fase 2:
  - `crecimiento_real`
  - `movimiento_reportado`
  - `ajuste_no_explicado`

#### `kpi_desempeno_response_builder.py`

- Construir JSON por secciones
- Garantizar contrato estable para frontend
- Agregar metadata, warnings y source snapshots

---

## 22. Campos normalizados para frontend

Aunque el nombre real en base de datos sea distinto, el frontend debe recibir nombres estables.

| Campo frontend | Significado |
|---|---|
| `branch_id` | ID interno de sucursal |
| `branch_canon` | Nombre canónico / alias Track si aplica |
| `branch_label` | Nombre visible |
| `period_key` | Llave estable del periodo |
| `period_label` | Texto visible del periodo |
| `start_date` | Inicio del periodo |
| `end_date` | Fin del periodo |
| `business_date` | Fecha real del snapshot usado |
| `active_members_closing` | Socios activos al cierre del periodo |
| `snapshot_id` | Snapshot usado |

---

## 23. Bases para Fase 2

Aunque Fase 2 no se implemente todavía, el contrato debe reservar la forma de crecer.

### Secciones futuras

```json
[
  "growth_engine",
  "branch_ranking",
  "weekly_pulse",
  "quick_comparisons"
]
```

### Métricas futuras normalizadas

```json
{
  "active_members_opening": 0,
  "active_members_closing": 0,
  "real_growth": 0,
  "new_clients": 0,
  "reactivations": 0,
  "cancellations": 0,
  "reported_movement": 0,
  "unexplained_adjustment": 0
}
```

### Reglas futuras

```text
real_growth = active_members_closing - active_members_opening

reported_movement = new_clients + reactivations - cancellations

unexplained_adjustment = real_growth - reported_movement
```

---

## 24. Bases para Fase 3

### Secciones futuras

```json
[
  "executive_summary",
  "year_over_year_comparison",
  "previous_month_comparison",
  "before_after_julian",
  "technology_penetration"
]
```

### Nota sobre tecnología / app

La vista de penetración tecnológica queda fuera hasta que Gasca libere la nueva app que sustituirá a Trainingym y el origen de datos sea estable.

No se debe construir una vista sobre Trainingym si la fuente será reemplazada.

---

## 25. Criterios de aceptación Fase 1

La Fase 1 se considera correcta cuando:

1. La pantalla muestra las tres gráficas definidas.
2. Todas las gráficas usan snapshots canónicos.
3. La gráfica semanal usa cierre semanal, no promedio.
4. La gráfica mensual usa cierre mensual canónico.
5. El histórico permite `monthly`, `bimonthly` y `quarterly`.
6. El default histórico es `quarterly`.
7. El backend filtra por permisos.
8. El frontend no calcula reglas de negocio.
9. El JSON responde por secciones.
10. La estructura permite agregar Fase 2 y 3 sin romper contrato.

---

## 26. Pendientes antes de código

Antes de implementar se debe validar:

1. Nombre exacto de campos reales en `kpi_desempeno_snapshot_rows`.
2. Relación exacta entre snapshot y rows.
3. Campo real equivalente a `socios_activos_cierre_mes`.
4. Si existe campo de sucursal canónica o se debe resolver con alias Track.
5. Si el módulo vivirá en rutas existentes de Track o en un blueprint separado.
6. Librería de gráficas a usar en frontend.
7. Diseño visual final de tarjetas y filtros.

---

## 27. Decisión final de implementación inicial

La implementación inicial será solamente:

```text
GET /api/track/kpi-desempeno/monthly-report
```

con estas secciones:

```text
weekly_closing
monthly_closing
historical_closing
```

Todo lo demás queda diseñado, pero no implementado todavía.

---

## 28. Filosofía del módulo

KPI Desempeño no debe ser un tablero abierto.

Debe ser:

```text
claro
cerrado
ejecutivo
operativo
fácil de leer
fiel al informe mensual conocido
preparado para análisis más profundos
```

Primero se replica lo conocido. Después se agrega valor.

