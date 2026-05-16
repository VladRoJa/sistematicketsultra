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