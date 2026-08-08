# Contrato canónico — Identidad de sucursales 23–26

**Proyecto:** Suite Ultra
**Estado:** APROBADO PARA IMPLEMENTACIÓN CONTROLADA
**Fecha:** 2026-08-08
**Versión:** 1.0

---

## 1. Propósito

Este contrato establece de forma definitiva la identidad numérica de las
sucursales 23–26 dentro de Suite Ultra.

La regla aplica al `sucursal_id` real utilizado como clave primaria de
`sucursales` y como clave foránea en todos los módulos estructurados.

Este contrato existe para eliminar definitivamente discrepancias históricas
entre ambientes local y producción y para evitar que se vuelva a confundir:

- `sucursal_id`
- `orden_apertura`
- `display_order`
- nombres RAW de fuentes externas
- claves canónicas de Track

La identidad oficial definida aquí no deberá reinterpretarse en migraciones
posteriores.

---

## 2. Identidad oficial e inmutable

La identidad oficial de Suite Ultra queda establecida así:

| sucursal_id | sucursal |
|---:|---|
| 23 | Tlalnepantla |
| 24 | Saltillo Villalta |
| 25 | Metepec |
| 26 | Serranía |

Por lo tanto:

```text
23 = Tlalnepantla
24 = Saltillo Villalta
25 = Metepec
26 = Serranía
```

Esta tabla es la fuente de verdad.

---

## 3. Orden oficial de apertura

El atributo `sucursales.orden_apertura` debe quedar alineado con la misma
secuencia:

```text
Tlalnepantla       -> orden_apertura 23
Saltillo Villalta  -> orden_apertura 24
Metepec            -> orden_apertura 25
Serranía           -> orden_apertura 26
```

No debe utilizarse `orden_apertura` como sustituto conceptual de
`sucursal_id`.

Ambos valores coinciden para estas cuatro sucursales por decisión de negocio,
pero siguen siendo columnas con responsabilidades diferentes.

---

## 4. Track Branch Catalog

`track_branch_catalog` debe quedar:

| sucursal_canon | sucursal_id | display_order |
|---|---:|---:|
| TLALNEPANTLA | 23 | 23 |
| SALTILLO_VILLALTA | 24 | 24 |
| METEPEC | 25 | 25 |
| SERRANIA | 26 | 26 |

En consecuencia:

```text
TLALNEPANTLA       -> sucursal_id 23 -> display_order 23
SALTILLO_VILLALTA  -> sucursal_id 24 -> display_order 24
METEPEC            -> sucursal_id 25 -> display_order 25
SERRANIA           -> sucursal_id 26 -> display_order 26
```

---

## 5. La Viga

LA VIGA fue cancelada y no debe poseer una identidad operativa dentro de la
Suite.

Reglas:

1. `sucursales.sucursal_id = 26` pertenece exclusivamente a Serranía.
2. LA VIGA no debe existir como sucursal operativa.
3. LA VIGA no debe permanecer en `track_branch_catalog`.
4. No deben existir aliases activos que resuelvan hacia `LA_VIGA`.
5. Los datos estructurados operativos que todavía dependan de una identidad
   numérica de LA VIGA deben eliminarse o desacoplarse según el dominio.
6. Los registros RAW históricos de fuentes externas que contengan literalmente
   `LA VIGA` deben conservarse para trazabilidad.
7. Un registro histórico RAW de LA VIGA nunca debe reinterpretarse como
   Serranía solamente porque Serranía utilice posteriormente el ID 26.

---

## 6. Estado conocido de producción antes de la corrección

Producción se encuentra actualmente en Alembic:

```text
c9f21d7a4b30
```

Estado actual de `sucursales`:

```text
23 = Tlalnepantla
24 = Metepec
25 = Saltillo Villalta
26 = Serranía
```

Estado actual relevante de `track_branch_catalog`:

```text
TLALNEPANTLA       -> sucursal_id 23 -> display_order 23
SALTILLO_VILLALTA  -> sucursal_id 25 -> display_order 24
METEPEC            -> sucursal_id 24 -> display_order 25
SERRANIA           -> sucursal_id 26 -> display_order 26
```

Por tanto, producción requiere intercambiar la identidad numérica de:

```text
Metepec:
24 -> 25

Saltillo Villalta:
25 -> 24
```

Tlalnepantla 23 y Serranía 26 ya tienen el ID definitivo.

---

## 7. Estado conocido del ambiente local antes de la corrección

El ambiente local se encuentra actualmente en:

```text
c81b2e6a4f90
```

Estado local de `sucursales`:

```text
23   = Metepec
24   = Tlalnepantla
25   = Saltillo Villalta
26   = La Viga
1001 = Serranía
```

Por tanto, local requiere converger así:

```text
Tlalnepantla:
24 -> 23

Saltillo Villalta:
25 -> 24

Metepec:
23 -> 25

Serranía:
1001 -> 26

La Viga:
26 -> sin identidad operativa
```

La migración debe preservar la identidad de cada registro y no limitarse a
cambiar nombres sobre los IDs existentes.

---

## 8. Principio de migración por identidad

Cuando un `sucursal_id` cambie, deberán migrarse conjuntamente todas las
referencias estructuradas que pertenecen a esa sucursal.

Ejemplo incorrecto:

```sql
UPDATE sucursales
SET sucursal = 'Saltillo Villalta'
WHERE sucursal_id = 24;
```

Esto convertiría datos históricos de Metepec en Villalta.

La operación correcta deberá trasladar la identidad completa:

```text
Sucursal padre
+
foreign keys
+
datos estructurados dependientes
+
hashes derivados cuando corresponda
```

hasta el ID oficial.

---

## 9. Foreign keys

Las auditorías encontraron múltiples foreign keys hacia:

```text
sucursales.sucursal_id
```

incluyendo dominios como:

- usuarios y alcance por sucursal;
- tickets;
- inventario;
- mantenimiento preventivo;
- permisos;
- aperturas;
- Marketing;
- RPA Gasca SMS;
- Control de Rutinas;
- regiones;
- Warehouse estructurado;
- Track.

Las foreign keys conocidas utilizan principalmente:

```text
ON UPDATE NO ACTION
```

Por tanto, no es válido cambiar directamente el PK de una fila mientras tenga
referencias activas.

La implementación deberá utilizar una estrategia transaccional segura para
mover las identidades sin dejar referencias huérfanas.

---

## 10. Descubrimiento dinámico de foreign keys

La migración definitiva no debe depender solamente de una lista manual de
tablas encontrada durante la auditoría.

Debe inspeccionar las foreign keys reales existentes hacia:

```text
sucursales.sucursal_id
```

en el esquema donde se ejecute.

Objetivo:

- soportar diferencias razonables entre local y producción;
- evitar olvidar módulos agregados recientemente;
- no asumir que las mismas 19 foreign keys existirán para siempre.

Las excepciones sin foreign key deberán tratarse explícitamente.

---

## 11. Tablas con identidad textual

Una columna textual que ya identifica correctamente la sucursal no debe
modificarse solamente porque cambie `sucursal_id`.

Ejemplos:

```text
routine_control_members.source_branch_name
ventas_nuevos_socios_detalle_snapshot_rows.sucursal_raw
venta_total_snapshot_rows.sucursal
reporte_direccion_snapshot_rows.sucursal
kpi_desempeno_snapshot_rows.sucursal
kpi_ventas_nuevos_socios_snapshot_rows.sucursal
corte_caja_snapshot_rows.sucursal
```

Ejemplo:

```text
sucursal_raw = METEPEC
```

debe continuar siendo `METEPEC`.

Lo que puede necesitar corrección es su `sucursal_id` estructurado asociado.

---

## 12. Datos canónicos de Track

Las claves canónicas como:

```text
TLALNEPANTLA
SALTILLO_VILLALTA
METEPEC
SERRANIA
```

representan identidad semántica y no deben intercambiarse.

Tablas como:

```text
track_daily_mart
track_monthly_targets
track_source_agregadoras_daily
track_source_desempeno_daily
track_source_domiciliados_efectivos_daily
track_source_ingresos_daily
track_source_nuevos_daily
track_source_tienda_daily
track_venta_total_daily_branch_agg
track_branch_aliases
```

no deberán tener sus valores `sucursal_canon` renombrados solo para acomodar
un cambio de ID.

---

## 13. RAW histórico

Principio obligatorio:

```text
RAW FIRST
```

Los datos RAW históricos deben conservar exactamente la identidad que entregó
la fuente.

Ejemplos de valores históricos como:

```text
LA VIGA
METEPEC
SALTILLO VILLALTA
TLALNEPANTLA
```

no deberán reescribirse para simular el nuevo catálogo.

La corrección de IDs debe realizarse en capas estructuradas/canónicas, no
alterando evidencia RAW.

---

## 14. Control de Rutinas

`routine_control_members` conserva tanto:

```text
sucursal_id
source_branch_name
```

El `source_branch_name` será usado como evidencia para validar que el nuevo
`sucursal_id` conserve la misma identidad.

Después de una reasignación de `sucursal_id`, debe recalcularse
`payload_hash` cuando dicho hash incluya el ID de sucursal.

Validación mínima:

```text
TLALNEPANTLA       -> 23
SALTILLO VILLALTA  -> 24
METEPEC            -> 25
SERRANIA           -> 26
```

sin mismatch entre `source_branch_name` y `sucursal_id`.

---

## 15. Ventas Nuevos Socios Detalle

`ventas_nuevos_socios_detalle_snapshot_rows` conserva:

```text
sucursal_raw
sucursal_id
```

Después de la migración:

```text
TLALNEPANTLA       -> 23
SALTILLO VILLALTA  -> 24
METEPEC            -> 25
SERRANIA           -> 26
```

`row_hash` no deberá recalcularse exclusivamente por el cambio de
`sucursal_id` si continúa definido sobre campos RAW.

---

## 16. Estructuras legacy existentes solamente en local

Durante la auditoría local se encontraron:

```text
track_dim_sucursal
track_fact_ingresos_daily
```

Estas tablas no existen actualmente en producción.

### 16.1 track_dim_sucursal

Posee foreign key a `sucursales.sucursal_id`.

La identidad textual `track_name` debe prevalecer para determinar el nuevo ID.

Debe converger a:

```text
TLALNEPANTLA       -> 23
SALTILLO VILLALTA  -> 24
METEPEC            -> 25
SERRANIA           -> 26
```

La dimensión operativa de `LA VIGA` no debe terminar asociada al ID 26 de
Serranía.

### 16.2 track_fact_ingresos_daily

No posee foreign key de `sucursal_id` hacia `sucursales`.

Posee simultáneamente:

```text
sucursal_id
sucursal_name
```

El nombre deberá ser autoridad para corregir los IDs legacy:

```text
TLALNEPANTLA       -> 23
SALTILLO VILLALTA  -> 24
METEPEC            -> 25
SERRANIA           -> 26
LA VIGA            -> NULL
```

Los registros históricos de LA VIGA deben conservarse como históricos y no
reinterpretarse como Serranía.

---

## 17. Índices únicos

La migración deberá considerar como mínimo índices compuestos que incluyan
`sucursal_id`, por ejemplo:

```text
(inventario_id, sucursal_id)
(month_start, sucursal_id)
(user_id, sucursal_id)
(sucursal_id, region_id, valid_from)
```

No deberá realizarse un swap directo que produzca colisiones temporales.

La estrategia podrá utilizar identificadores temporales dentro de una única
transacción siempre que:

1. no representen sucursales reales;
2. no queden persistidos al finalizar;
3. todas las FK y estructuras derivadas sean reconciliadas;
4. exista validación final antes del commit.

---

## 18. Alembic y divergencia histórica

Actualmente existe una divergencia:

```text
LOCAL:
c81b2e6a4f90

PRODUCCIÓN:
c9f21d7a4b30
```

La revisión `c9f21d7a4b30` presupone un estado de `sucursales` que no existe en
la base local legítima y por ello actualmente no puede reproducirse allí.

Antes de agregar la migración canónica definitiva se deberá resolver de forma
explícita la reproducibilidad del trayecto:

```text
c81b2e6a4f90
->
c9f21d7a4b30
```

Reglas obligatorias:

1. No utilizar `flask db stamp` para ocultar la diferencia.
2. No modificar manualmente la DB local.
3. No modificar manualmente producción.
4. No ejecutar SQL correctivo fuera de Alembic.
5. No volver a ejecutar `flask db upgrade head` local hasta resolver este
   trayecto.
6. Producción, que ya tiene `c9f21d7a4b30`, no debe repetir destructivamente
   operaciones históricas de esa migración.
7. La solución debe permitir reconstruir una base desde la cadena Alembic de
   forma reproducible.

La implementación concreta del mecanismo de compatibilidad deberá revisarse
antes de modificar una migración ya aplicada.

---

## 19. Estado convergente obligatorio

Después de completar todas las migraciones, tanto local como producción deben
producir exactamente:

```text
sucursales
23 | Tlalnepantla
24 | Saltillo Villalta
25 | Metepec
26 | Serranía
```

Y:

```text
orden_apertura
23 | Tlalnepantla
24 | Saltillo Villalta
25 | Metepec
26 | Serranía
```

Y:

```text
track_branch_catalog
TLALNEPANTLA       | 23 | 23
SALTILLO_VILLALTA  | 24 | 24
METEPEC            | 25 | 25
SERRANIA           | 26 | 26
```

No debe existir:

```text
sucursales -> La Viga
track_branch_catalog -> LA_VIGA
alias activo -> LA_VIGA
```

---

## 20. Validaciones obligatorias

Antes de declarar terminada la migración deberán comprobarse al menos:

1. revisión Alembic esperada;
2. cuatro sucursales con IDs exactos 23–26;
3. `orden_apertura` exacto 23–26;
4. Track catalog exacto;
5. ausencia operativa de LA VIGA;
6. cero FK huérfanas;
7. cero mismatches entre `sucursal_id` y campos RAW/textuales verificables;
8. Control de Rutinas consistente;
9. Ventas Nuevos Socios Detalle consistente;
10. usuarios y permisos conservan su sucursal real;
11. tickets conservan la sucursal real;
12. inventario conserva la sucursal real;
13. regiones conservan la sucursal real;
14. Marketing conserva la sucursal real;
15. openings de Serranía continúa asociada a Serranía;
16. tablas legacy locales, si existen, quedan reconciliadas;
17. datos RAW históricos no fueron reescritos;
18. `git diff --check`;
19. pruebas backend afectadas;
20. único head Alembic al finalizar.

---

## 21. Regla para código nuevo

A partir de este contrato queda prohibido introducir nuevas reglas de negocio
basadas en IDs históricos contradictorios.

Si código nuevo requiere la identidad numérica:

```text
23 -> Tlalnepantla
24 -> Saltillo Villalta
25 -> Metepec
26 -> Serranía
```

Si puede resolver por catálogo, alias o nombre canónico, deberá preferirse la
resolución semántica correspondiente para fuentes externas.

Ninguna integración externa debe asumir que sus propios códigos de sucursal
son iguales a `sucursal_id`.

---

## 22. Relación con iVentas

La integración iVentas no deberá crear aliases ni persistencia definitiva
hasta que este contrato haya sido aplicado y las bases local y producción
hayan convergido.

Una vez convergidas:

```text
TLALNEPANTLA       -> sucursal_id 23
SALTILLO_VILLALTA  -> sucursal_id 24
METEPEC            -> sucursal_id 25
SERRANIA           -> sucursal_id 26
```

Los aliases de `iventas_family` deberán apoyarse sobre estas identidades
definitivas.

La validación independiente del branch code de Sendero Saltillo continúa
siendo requisito separado antes de congelar el catálogo iVentas.

---

## 23. Criterio de aceptación

Este contrato se considera implementado únicamente cuando:

```text
LOCAL == PRODUCCIÓN == CONTRATO OFICIAL
```

para la identidad estructurada de estas cuatro sucursales.

No basta con que el dashboard se vea correcto.

No basta con que `display_order` sea correcto.

No basta con que los nombres sean correctos.

La PK real y todas sus referencias estructuradas deben representar la misma
identidad de negocio.

---

## 24. Fuente de verdad definitiva

A partir de esta versión:

```text
23 = Tlalnepantla
24 = Saltillo Villalta
25 = Metepec
26 = Serranía
```

es una decisión canónica de Suite Ultra.

Cualquier código, migración, seed, script o dato estructurado que contradiga
esa identidad deberá considerarse legacy o incorrecto y deberá corregirse de
forma explícita, auditable y mediante migración.
