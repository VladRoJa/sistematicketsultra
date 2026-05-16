# Warehouse / Track UI v1

## Objetivo

Aplicar Suite Ultra UI v1 a los módulos Warehouse y Track sin modificar su lógica funcional ni sus contratos backend.

Warehouse y Track son módulos estratégicos para centralizar información, reportes, datos históricos y análisis BI de Suite Ultra.

---

## Principio visual

Warehouse debe sentirse como el centro de almacenamiento, trazabilidad y consulta de información.

Track debe sentirse como la capa ejecutiva/BI construida sobre datos consolidados del Warehouse.

---

## Alcance inicial

### Warehouse Home

Se aplicará UI v1 a:

- Header del módulo.
- Cards de acceso.
- Acciones principales.
- Paneles de carga/listado si están en la pantalla principal.
- Estados vacíos/carga.
- Colores, bordes, sombras y espaciados usando tokens globales.

### Track Dashboard

Se aplicará UI v1 a:

- Header del dashboard.
- Controles superiores.
- Cards KPI.
- Tablas/resúmenes.
- Estados de carga/vacío/error.
- Consistencia visual con login, menú y Tickets.

---

## No alcance

No se modificará:

- Endpoints Warehouse.
- Endpoints Track.
- Pipeline diario.
- Canonicalidad.
- Snapshots.
- Upload documental.
- Ingesta estructurada.
- Permisos backend.
- Cálculos de Track.
- Alias de sucursal.
- Scheduler.

---

## Reglas de implementación

- No agregar lógica nueva en HTML.
- No mover lógica funcional al template.
- No cambiar contratos API.
- No cambiar permisos.
- No cambiar nombres de campos.
- Usar tokens globales de Suite Ultra UI v1.
- Mantener componentes separados en `.ts`, `.html` y `.css`.
- Hacer cambios pequeños y verificables.

---

## Primer bloque de implementación

### Nombre

```text
style(warehouse): apply Suite Ultra UI v1 to warehouse home
```

---

## Warehouse uploads: filtros y paginación

### Objetivo

Evitar que Warehouse cargue y renderice todo el histórico de uploads en la pantalla principal.

Warehouse debe mostrar por defecto un subconjunto operativo útil y permitir consultar el histórico mediante filtros y paginación real.

---

### Problema actual

La pantalla principal lista los uploads cargados en una tabla de histórico.

A medida que Warehouse crezca, cargar todos los registros puede provocar:

- Lentitud en frontend.
- Respuestas backend más pesadas.
- Tabla difícil de usar.
- Peor experiencia para usuarios operativos.
- Mayor consumo innecesario de memoria y red.

---

### Comportamiento objetivo

Al abrir Warehouse, el listado debe cargar por defecto:

```text
date_preset = today
page = 1
page_size = 25
status = ALL
