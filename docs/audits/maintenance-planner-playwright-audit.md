# Maintenance Planner E2E Audit

Fecha: 2026-09-13  
Entorno auditado: instancia local (`http://localhost:4200`, backend `http://localhost:5000`)  
Método: Playwright headless + inspección estática acotada para respaldar contratos no ejercitables sin sesión.

## Resumen ejecutivo

- **PASS:** La ruta protegida redirige a `/#/login` sin errores de consola ni respuestas fallidas en 1920x1080 y 1366x768.
- **WARNINGS:** El reporte XLSX de mantenimiento vive en la pantalla de Tickets, no en Maintenance Planner; no se pudo descargar ni inspeccionar el archivo por falta de sesión ADMICORP.
- **FAILURES:** Se confirmó por flujo de código una posible elevación de capacidad para reprogramar desde el endpoint genérico de Tickets (P0; requiere reproducción autenticada para cerrar la evidencia dinámica).
- **BLOCKED:** No hay `BASE_URL`, `ADMICORP_*`, `REGIONAL_*`, `GERENTE_*` ni `MANTENIMIENTO_*` disponibles para el proceso de auditoría. Por ello no se ejecutaron pruebas autenticadas, mutaciones en ULTRA DEMO, descarga XLSX ni validación real de scopes.

## Hallazgos críticos

### P0 — La reprogramación del Planner no usa su endpoint con permiso PM y puede permitir modificación por roles de solo consulta

- **Severidad:** P0
- **Rol afectado:** GERENTE y GERENTE_REGIONAL (y cualquier rol que tenga scope de Tickets pero no `can_pm_execute`).
- **Ruta:** `/#/maintenance-planner`; endpoint efectivo `PUT /api/tickets/update/:id`.
- **Pasos para reproducir:**
  1. Autenticarse como GERENTE o GERENTE_REGIONAL con un ticket de Mantenimiento dentro de su scope.
  2. Enviar a `PUT /api/tickets/update/<ticket_id>` un cuerpo con `estado: "en progreso"`, `fecha_solucion`, `fecha_en_progreso`, `historial_fechas` y `motivo_cambio`.
  3. Recargar el Planner y comprobar fecha e historial.
- **Resultado esperado:** Roles sin `can_pm_execute` deben recibir 403 para reprogramar desde Planner o mediante el backend.
- **Resultado real:** Confirmado por código: el componente llama `TicketService.updateTicket()` para reprogramar; la ruta genérica solo exige que el ticket esté dentro de `filtrar_tickets_por_usuario`, y no invoca `can_pm_execute`. El endpoint específico `PUT /api/maintenance-planner/tickets/:id/schedule`, que sí exige `can_pm_execute`, está definido pero no se usa en esos flujos.
- **Evidencia:** `frontend/src/app/maintenance-planner/maintenance-planner.service.ts` (`applyCommitmentUpdate`); `backend/app/routes/ticket_routes.py` (`update_ticket_status`); `backend/app/maintenance_planner/service.py` (`_scoped_maintenance_ticket`).
- **Endpoint involucrado:** `PUT /api/tickets/update/:id`; endpoint no utilizado: `PUT /api/maintenance-planner/tickets/:id/schedule`.
- **Archivo de código probable:** los tres archivos citados.
- **Estado de evidencia dinámica:** BLOCKED por ausencia de credenciales. No se intentó mutar ningún dato.

## Hallazgos funcionales

### P2 — El selector `Finalizados` deja la bandeja y KPIs activos vacíos aunque el calendario sí puede contener finalizados

- **Severidad:** P2
- **Rol:** cualquier rol con acceso.
- **Ruta:** `/#/maintenance-planner`.
- **Pasos para reproducir:** seleccionar `Finalizados` en el filtro de estado cuando existan tickets finalizados en la semana.
- **Resultado esperado:** La bandeja y los contadores deben comunicar claramente el universo filtrado o una vista coherente de finalizados.
- **Resultado real:** El backend entrega finalizados en `days`, pero `active_rows` excluye todo estado distinto de `abierto`, `en progreso` y `por_validar`; la bandeja se deriva de esas colecciones activas. En consecuencia, la vista puede mostrar tarjetas de finalizados en calendario y `0` en la bandeja/KPIs.
- **Evidencia:** `backend/app/maintenance_planner/service.py` (`ACTIVE_STATES`, `active_rows`, `week_rows`); `frontend/src/app/maintenance-planner/maintenance-planner.component.ts` (`allActiveItems`, `focusItems`).
- **Endpoint involucrado:** `GET /api/maintenance-planner/board?estado=finalizado`.
- **Archivo de código probable:** `backend/app/maintenance_planner/service.py` y `frontend/src/app/maintenance-planner/maintenance-planner.component.ts`.
- **Estado de evidencia dinámica:** BLOCKED por falta de sesión.

### P2 — Contrato de reprogramación duplicado e inconsistente

- **Severidad:** P2
- **Rol:** perfiles con ejecución PM.
- **Ruta:** `/#/maintenance-planner`.
- **Pasos para reproducir:** reprogramar desde el modal o drag & drop.
- **Resultado esperado:** Usar el contrato público del Planner, que normaliza fecha a 07:00 America/Tijuana, exige motivo y registra auditoría en backend.
- **Resultado real:** El método `scheduleTicket()` existe pero no tiene llamadas. Los flujos UI construyen historial y fecha en cliente y usan el endpoint genérico de Tickets. Esto hace divergentes los contratos y debilita la validación centralizada.
- **Evidencia:** `frontend/src/app/maintenance-planner/maintenance-planner.service.ts`.
- **Endpoint involucrado:** definido pero sin uso: `PUT /api/maintenance-planner/tickets/:id/schedule`.
- **Archivo de código probable:** `frontend/src/app/maintenance-planner/maintenance-planner.service.ts`.

## Hallazgos UX

### P2 — El reporte de mantenimiento no está accesible desde Maintenance Planner

- **Severidad:** P2
- **Rol:** ADMICORP.
- **Ruta:** el control actual está en la pantalla de Tickets, no en `/#/maintenance-planner`.
- **Pasos para reproducir:** iniciar sesión como ADMICORP y buscar el reporte desde Planner.
- **Resultado esperado:** El reporte asociado al Planner debe estar accesible desde el módulo o indicarse claramente su ubicación.
- **Resultado real:** El botón `Reporte equipos` está implementado en `pantalla-ver-tickets`; no existe control de descarga en la plantilla del Planner.
- **Evidencia:** `frontend/src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.html`; `frontend/src/app/maintenance-planner/maintenance-planner.component.html`.
- **Endpoint involucrado:** `GET /api/mantenimiento-equipos/reporte`.
- **Archivo de código probable:** `frontend/src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.ts`.

### P3 — No se pudo validar visualmente el Planner autenticado

- **Severidad:** P3
- **Ruta:** `/#/maintenance-planner`.
- **Resultado esperado:** Verificar hero, KPI, sticky headers, calendario, bandeja, clipping y scroll en 1920x1080 y 1366x768.
- **Resultado real:** La protección redirige a login antes de renderizar el módulo. No hubo error visual del login ni errores de consola.
- **Evidencia:** `artifacts/maintenance-planner-audit/screenshots/anonymous-1920x1080.png` y `artifacts/maintenance-planner-audit/screenshots/anonymous-1366x768.png`.

## Permisos y scope

- **ADMICORP:** BLOCKED. La política de UI permite el reporte solo si `username === 'ADMICORP'`; no se pudo validar board, catálogo de sucursales, `Todas`, ULTRA DEMO ni permisos efectivos.
- **GERENTE_REGIONAL:** BLOCKED dinámicamente. Estáticamente, el board endurece el alcance a `sucursales_ids` para evitar el fallback por creador; el catálogo se construye con todas sus sucursales asignadas aun sin tickets. La brecha P0 persiste por el endpoint genérico de actualización.
- **GERENTE:** BLOCKED dinámicamente. `can_pm_view` permite vista y `can_pm_execute` la deniega; la acción visible queda oculta por `can_schedule`, pero el control backend del endpoint genérico requiere prueba autenticada y es insuficiente según la inspección estática.
- **MANTENIMIENTO:** BLOCKED. El contrato estático lo incluye en lectura y ejecución PM.
- **Backend específico de Planner:** `PUT /api/maintenance-planner/tickets/:id/schedule` sí exige `can_pm_execute` y scope de ticket. La UI no lo utiliza para sus reprogramaciones actuales.

## Reporte Excel

- **Ubicación actual:** pantalla de Tickets, menú `Reporte equipos`; no vive en Planner.
- **Endpoint:** `GET /api/mantenimiento-equipos/reporte`.
- **Estado:** BLOCKED: no hubo sesión ADMICORP para iniciar descarga; por lo tanto no se creó XLSX ni se ejecutó `openpyxl` sobre un artefacto real.
- **Revisión estática limitada:** el generador declara columnas para `Tickets`, `Edificio`, `Por validar` e `Histórico mensual`; la hoja `Edificio por categoría` calcula categorías dinámicas y una fila `TOTAL`. Esto no sustituye la validación del XLSX descargado.
- **No validado:** orden de hojas, resumen ejecutivo, fórmulas resultantes, consistencia de totales, familias de aparatos ni alcance real por región.

## Console / Network

| Viewport | Resultado Playwright | Console errors | 4xx/5xx inesperados |
| --- | --- | ---: | ---: |
| 1920x1080 | `200` inicial, redirección a `/#/login` | 0 | 0 |
| 1366x768 | `200` inicial, redirección a `/#/login` | 0 | 0 |

- Consulta anónima directa a `GET /api/maintenance-planner/board`: `401`, esperado sin JWT.
- No se registraron tokens, credenciales ni cuerpos sensibles en evidencias.
- Playwright se ejecutó con una copia temporal y Chromium local; no se modificó `package.json` ni se instaló dependencia en el proyecto.

## Casos no probados

BLOCKED por las credenciales no disponibles:

- Smoke autenticado, menú, hero, KPIs, calendario y bandeja.
- Selector de sucursal y comparación UI/API.
- Filtro de estado con datos reales.
- Modal, historial y visualización de tickets Equipo/Edificio.
- Cambio de fecha, drag & drop y rollback exclusivamente en ULTRA DEMO.
- Flujo de cierre seguro de un ticket de prueba.
- Scope real de ADMICORP, GERENTE_REGIONAL, GERENTE y MANTENIMIENTO, incluidas respuestas 403.
- Descarga e inspección `openpyxl` del XLSX.
- Prueba de 1024x768.

## Recomendaciones priorizadas

1. **P0:** Centralizar la reprogramación en el endpoint del Planner o aplicar en `/api/tickets/update/:id` la misma autorización de ejecución PM cuando se muten fechas/estado de tickets de Mantenimiento. Añadir una prueba de integración negativa para GERENTE y GERENTE_REGIONAL.
2. **P1:** Proveer credenciales efímeras de auditoría para ADMICORP, REGIONAL, GERENTE y MANTENIMIENTO, con un ticket ULTRA DEMO reversible, y repetir la batería E2E completa.
3. **P2:** Decidir y alinear el comportamiento de bandeja/KPIs bajo `Finalizados` para que no contradiga el calendario.
4. **P2:** Exponer o enlazar el reporte de mantenimiento desde Planner si forma parte del cierre funcional esperado del módulo.
5. **P2:** Añadir Playwright al flujo de desarrollo del proyecto (configuración y pruebas reproducibles), sin depender de una instalación temporal.

## Veredicto

**NEEDS FIXES**

Qué falta antes de dar por terminado Maintenance Planner:

- Cerrar y reproducir la brecha P0 de autorización.
- Ejecutar los flujos autenticados con datos ULTRA DEMO y validar sus rollbacks.
- Descargar e inspeccionar el XLSX real con `openpyxl`.
- Validar visualmente el módulo autenticado en los dos viewports requeridos.
