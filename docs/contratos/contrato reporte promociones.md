Va. Este contrato lo cerraría así: **no como reporte estático**, sino como primer módulo de **BI Comercial / Promociones** dentro de Warehouse, preparado para que cada mes entren promos nuevas sin romper el análisis.

# Contrato — BI Comercial: Análisis de Promociones

## 1. Objetivo

Construir un MVP en Suite Ultra para analizar promociones comerciales a partir de **Venta Total**, permitiendo responder:

> ¿Qué promociones funcionan mejor, en qué meses y en qué sucursales?

El módulo debe ser **auditable, escalable y adaptable**, porque las promociones cambian mes a mes y Gasca no maneja nombres estandarizados.

---

# 2. Principio rector

No vamos a depender permanentemente de esto:

```sql
CASE
  WHEN descripcion ILIKE '%PROMO FEBRERO%' THEN 'Promo Febrero'
  WHEN descripcion ILIKE '%HOT SALE%' THEN 'Hot Sale'
END
```

Eso sirvió para el análisis exploratorio, pero **no debe ser la solución final**.

La solución correcta es:

```text
descripcion_raw de Gasca
→ catálogo comercial
→ promo_canon / familia / clasificación
→ reporte
```

Y si aparece una descripción nueva, el sistema no debe romperse. Debe marcarla como:

```text
Sin clasificar / Pendiente de catalogar
```

---

# 3. Alcance del MVP

## Sí entra

El MVP debe mostrar:

1. **Resumen ejecutivo**

   * promo ganadora general;
   * ingreso promocional;
   * porcentaje sobre Venta Total de clubes canonizados;
   * sucursales con impacto fuerte;
   * periodo analizado.

2. **Ranking general de promociones**

   * promo canon;
   * meses con venta;
   * operaciones;
   * unidades;
   * ingreso;
   * ticket promedio;
   * porcentaje sobre denominador Venta Total canonizado.

3. **Top promociones por mes**

   * mes;
   * corte snapshot;
   * promo;
   * ingreso;
   * ticket promedio;
   * porcentaje sobre Venta Total del mes.

4. **Promo ganadora por sucursal**

   * sucursal canon;
   * promo ganadora;
   * ingreso promo;
   * porcentaje sobre ingreso de sucursal;
   * lectura de impacto.

5. **Detalle por descripción Gasca**

   * promo canon;
   * descripción raw;
   * ingreso;
   * operaciones;
   * primer mes detectado;
   * último mes detectado.

6. **Descripciones sin clasificar**

   * descripciones nuevas o no mapeadas;
   * ingreso asociado;
   * operaciones;
   * última fecha detectada.

Esta última parte es clave para escalar.

---

## No entra en MVP

No entra todavía:

* IA;
* predicciones;
* gráficas complejas;
* edición visual del catálogo desde Angular;
* exportador Excel completo desde Suite;
* administración avanzada de reglas;
* comparación automática contra Track consolidado;
* agregadoras.

---

# 4. Fuente de datos

Fuente principal:

```text
venta_total_snapshots
venta_total_snapshot_rows
```

Alias de sucursal:

```text
track_branch_aliases
```

El análisis usa Venta Total porque ahí vive:

```text
descripcion
```

y esa descripción es la que permite identificar promociones.

---

# 5. Alcance financiero del análisis

Este módulo **no reemplaza Track**.

El análisis de promociones se basa en:

```text
Venta Total de sucursales canonizadas
```

No incluye:

```text
agregadoras
CORPORATIVO
BECA
SUCURSAL EN LÍNEA
GIMNASIO PRUEBA
```

Para evitar confusión, ninguna columna debe llamarse simplemente:

```text
Ingreso total
```

Debe llamarse:

```text
Denominador Venta Total
```

o:

```text
Ingreso Venta Total canonizado
```

---

# 6. Regla de canonicalidad

Para evitar duplicados por snapshots:

```text
usar solo snapshot_kind = daily
usar solo is_canonical = true
usar el último snapshot canónico de cada mes
tomar solo filas cuya fecha pertenezca al mismo mes del snapshot
```

Regla conceptual:

```text
1 snapshot mensual válido
→ filas de ese mismo mes
→ ventas activas
→ sucursal canonizada
→ clasificación comercial
```

---

# 7. Modelo escalable de clasificación

## Tabla nueva sugerida

```text
warehouse_commercial_catalog
```

Campos:

```text
id
raw_description
normalized_description
commercial_canon
family
subfamily
is_promo
is_membership
is_retail
is_aggregator
is_active
needs_business_validation
notes
created_at
updated_at
```

Ejemplo:

| raw_description                | commercial_canon      | family         | is_promo |
| ------------------------------ | --------------------- | -------------- | -------- |
| 50% 1ER MES 12 MESES $499      | 50% Primer Mes        | incentivo      | true     |
| BORRON Y CUENTA NUEVA 12 MESES | Borrón y Cuenta Nueva | reactivacion   | true     |
| PROMO FEBRERO 12 MESES         | Promo Febrero         | promo_temporal | true     |
| AGUA E-PURA 1 LITRO            | Retail Bebidas        | retail         | false    |

---

# 8. Regla para nuevas promociones

Cuando aparezca una descripción nueva en Venta Total:

## Si existe en catálogo

Se clasifica automáticamente.

## Si no existe

Debe aparecer en:

```text
Descripciones sin clasificar
```

Con:

```text
descripcion_raw
operaciones
ingreso_total
primer_mes_detectado
ultimo_mes_detectado
```

Así cada mes se puede revisar:

> “Estas son las descripciones nuevas que Gasca empezó a usar.”

Y se agregan al catálogo sin romper reportes anteriores.

---

# 9. Familias comerciales iniciales

Usar estas familias:

```text
incentivo
reactivacion
promo_temporal
domiciliado
recurrente
convenio
agregadora
retail
penalizacion
regular
estudiante
preventa
sin_clasificar
```

Para este MVP, el reporte principal solo considera:

```text
is_promo = true
```

Pero conservar `is_retail`, `is_membership`, etc. permite escalar después.

---

# 10. Backend

## Archivo nuevo

```text
backend/app/warehouse/services/commercial_promotions_service.py
```

Responsabilidad:

* obtener último snapshot canónico por mes;
* filtrar ventas activas;
* resolver sucursal canonizada;
* unir contra catálogo comercial;
* excluir no canonizados del análisis por club;
* generar ranking general;
* generar top mensual;
* generar ranking por sucursal;
* detectar descripciones sin clasificar.

## Ruta nueva

```text
backend/app/routes/warehouse_commercial_routes.py
```

Endpoints MVP:

```text
GET /api/warehouse/commercial/promotions/summary
GET /api/warehouse/commercial/promotions/ranking
GET /api/warehouse/commercial/promotions/by-month
GET /api/warehouse/commercial/promotions/by-branch
GET /api/warehouse/commercial/promotions/raw-descriptions
GET /api/warehouse/commercial/promotions/unmapped
```

Permisos:

```text
require_warehouse_operator()
```

No confiar en frontend para permisos.

---

# 11. Frontend

## Ruta sugerida

```text
/#/warehouse/comercial/promociones
```

## Archivos

```text
frontend/src/app/warehouse/commercial-promotions/commercial-promotions.component.ts
frontend/src/app/warehouse/commercial-promotions/commercial-promotions.component.html
frontend/src/app/warehouse/commercial-promotions/commercial-promotions.component.css
frontend/src/app/warehouse/services/commercial-promotions.service.ts
```

Nada de lógica en HTML.
HTML solo estructura, bindings simples y llamadas a métodos ya definidos.

---

# 12. Pantalla MVP

La pantalla debe tener:

## Encabezado

```text
BI Comercial / Promociones
```

Nota visible:

```text
Análisis basado en Venta Total de sucursales canonizadas. No incluye agregadoras ni registros no asociados a club.
```

## Tarjetas

* promo ganadora general;
* ingreso promocional;
* porcentaje promo sobre Venta Total canonizado;
* sucursales con impacto fuerte;
* periodo.

## Secciones

1. Ranking general.
2. Top por mes.
3. Promo ganadora por sucursal.
4. Detalle por descripción Gasca.
5. Descripciones sin clasificar.

---

# 13. Migración

Sí requiere migración Alembic para crear:

```text
warehouse_commercial_catalog
```

En MVP no crearía todavía mart físico.
Primero resolvería en query/servicio.

Después, F2 puede crear:

```text
commercial_promo_monthly_mart
```

---

# 14. Criterios de aceptación

El MVP se considera correcto si:

1. El ranking general reproduce los resultados validados manualmente.
2. El top por mes no duplica snapshots.
3. El análisis por sucursal usa `sucursal_canon`.
4. `CORPORATIVO`, `BECA`, `SUCURSAL EN LÍNEA` no contaminan análisis por club.
5. Las promociones nuevas no rompen el reporte.
6. Las promociones nuevas aparecen en `unmapped`.
7. El usuario puede explicar claramente que el análisis no incluye agregadoras.
8. El endpoint está protegido por permisos Warehouse.
9. La pantalla carga sin afectar Track.
10. No hay lógica de negocio en Angular HTML.

---

# 15. Riesgos

| Riesgo                                  | Mitigación                               |
| --------------------------------------- | ---------------------------------------- |
| Gasca cambia nombres de promos          | Catálogo + unmapped                      |
| Se duplican snapshots                   | Último snapshot canónico por mes         |
| Se compara contra Track incorrectamente | Nota metodológica clara                  |
| Sucursales duplicadas                   | Reusar `track_branch_aliases`            |
| Nuevas promos no aparecen               | Endpoint de descripciones sin clasificar |
| Catálogo mal clasificado                | `needs_business_validation`              |
| Query pesada                            | MVP read-only; después mart mensual      |

---

# 16. Fases

## F1 — MVP funcional

* crear catálogo;
* seed inicial con promos actuales;
* endpoints read-only;
* pantalla básica;
* unmapped descriptions.

## F2 — Administración de catálogo

* pantalla para clasificar nuevas descripciones;
* activar/desactivar;
* marcar `needs_business_validation`;
* notas.

## F3 — Mart mensual

* tabla calculada;
* job manual;
* histórico congelado;
* export Excel.

## F4 — BI Comercial extendido

* vendedores;
* ticket promedio por campaña;
* promociones vs socios nuevos;
* promociones vs permanencia;
* reactivaciones reales.

## F5 — IA controlada

* preguntas guardadas;
* queries aprobadas;
* lenguaje natural sobre métricas seguras;
* nada de SQL libre contra producción.

---

# Veredicto

Sí lo podemos subir como MVP, pero el contrato debe dejar clara esta regla:

> La primera versión puede consultar directo desde Venta Total, pero la clasificación de promociones debe vivir en un catálogo, no en SQL quemado.

Ese es el punto que lo hace escalable.

Hoy el objetivo no es hacerlo perfecto.
El objetivo es que cuando Gasca saque una promo nueva, la Suite diga:

```text
Detecté una nueva descripción comercial sin clasificar.
```

Y no:

```text
El reporte se rompió o ignoró ventas sin avisar.
```
