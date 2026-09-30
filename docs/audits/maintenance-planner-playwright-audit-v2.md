# Maintenance Planner E2E Audit V2

Fecha: 2026-09-13  
Entorno disponible: frontend local `http://localhost:4200`; backend local `http://localhost:5000`  
Método: Playwright headless para navegación disponible y revisión estática dirigida a los contratos que requieren autenticación.

## Resumen ejecutivo

La auditoría autenticada no pudo iniciar: ninguna de las variables requeridas (`BASE_URL`, `ADMICORP_*`, `REGIONAL_*`, `GERENTE_*`, `MANTENIMIENTO_*`) está disponible para el proceso. Por seguridad no se intentaron credenciales alternativas, no se crearon sesiones, y no hubo mutaciones.

El supuesto fix de autorización PM **no queda validado**. La inspección del código actual muestra que la reprogramación del Planner sigue usando `PUT /api/tickets/update/:id`, mientras que el endpoint propio del Planner —que sí exige `can_pm_execute`— permanece sin usar en esos flujos. La ruta genérica sigue sin un guard PM específico. Este resultado es una evidencia estática de regresión/no-fix; falta la reproducción HTTP autenticada solicitada para registrar el status y body reales.

Resultados ejecutados:

- Playwright anónimo a `/#/maintenance-planner` en 1920x1080 y 1366x768: PASS de protección de ruta; redirección a `/#/login`, sin `console.error`, excepciones ni 4xx/5xx observados en los recursos de la navegación.
- `GET /api/maintenance-planner/board` sin JWT: 401 esperado (validado en la pasada previa; no se usa como evidencia de autorización por rol).
- Pruebas con roles, API mutante, ULTRA DEMO, drag & drop, modal, XLSX, UI/API y Edificio: BLOCKED por credenciales ausentes.

## Validación del fix de autorización

| Caso requerido | Resultado V2 | Evidencia |
| --- | --- | --- |
| GERENTE + `PUT /api/tickets/update/:id` PM | **BLOCKED dinámico / FAIL estático** | No hay credenciales. `update_ticket_status` verifica scope de Ticket y no invoca `can_pm_execute`; el payload de reprogramación del Planner apunta a esta ruta. |
| GERENTE_REGIONAL + `PUT /api/tickets/update/:id` PM | **BLOCKED dinámico / FAIL estático** | Mismo guard genérico. El endurecimiento regional existe para el board, no en este handler de actualización. |
| MANTENIMIENTO + endpoint Planner schedule | **BLOCKED** | El servicio `schedule_ticket` exige `can_pm_execute`; falta sesión y ticket ULTRA DEMO confirmado para ejercerlo. |
| GERENTE + endpoint Planner schedule | **BLOCKED** | El servicio tiene guard `can_pm_execute`; la respuesta 403 real no se pudo capturar sin JWT. |
| GERENTE_REGIONAL + endpoint Planner schedule | **BLOCKED** | Igual que el caso GERENTE. |

Hallazgo estático exacto:

- `MaintenancePlannerService.applyCommitmentUpdate()` construye `estado`, `fecha_solucion`, `fecha_en_progreso`, `historial_fechas` y `motivo_cambio`, y llama `TicketService.updateTicket()`.
- Drag & drop y el botón de cambiar fecha llegan a `reprogramCommitmentFromDate()`, que desemboca en ese método.
- `PUT /api/maintenance-planner/tickets/:id/schedule` existe y delega a `schedule_ticket()`, cuyo primer guard es `can_pm_execute(user)`, pero `scheduleTicket()` no tiene llamadas en los flujos revisados.
- `PUT /api/tickets/update/:id` está protegido por JWT, `bloquea_lectores_globales` y `filtrar_tickets_por_usuario(actor)`; no contiene una comprobación equivalente de ejecución PM para cambios de fecha/estado en tickets de Mantenimiento.

## Hallazgos críticos

### P0 — El bypass de autorización PM no está demostrado como corregido

- **Rol:** GERENTE y GERENTE_REGIONAL con ticket PM dentro de su scope.
- **Ruta / endpoint:** `/#/maintenance-planner`; `PUT /api/tickets/update/:id`.
- **Esperado:** 403 para el payload mutante descrito en el alcance.
- **Resultado actual:** No reproducible por falta de credenciales. El código aún permite el flujo técnico que motivó el hallazgo V1: el Planner usa el handler genérico y éste no valida `can_pm_execute`.
- **Evidencia:** `frontend/src/app/maintenance-planner/maintenance-planner.service.ts` (`applyCommitmentUpdate`); `backend/app/routes/ticket_routes.py` (`update_ticket_status`); `backend/app/maintenance_planner/service.py` (`_scoped_maintenance_ticket`).
- **Acción requerida antes de cerrar:** ejecutar los dos `PUT` con GERENTE y GERENTE_REGIONAL, guardar status/body sanitizado y recargar el ticket para confirmar inmutabilidad. Si no responde 403, el hallazgo queda confirmado dinámicamente.

## Hallazgos funcionales

### P2 — El endpoint propio del Planner sigue sin ser el usado por reprogramación y drag & drop

- **Esperado:** Drag & drop y cambio de fecha deben solicitar `PUT /api/maintenance-planner/tickets/:id/schedule`.
- **Resultado estático:** Ambos usan `reprogramCommitmentFromDate()` y terminan en `PUT /api/tickets/update/:id`.
- **Evidencia:** `frontend/src/app/maintenance-planner/maintenance-planner.component.ts`; `frontend/src/app/maintenance-planner/maintenance-planner-ticket-dialog.component.ts`; `frontend/src/app/maintenance-planner/maintenance-planner.service.ts`.
- **Prueba de red real:** BLOCKED por falta de sesión y ticket ULTRA DEMO.

### P2 — Vista `Finalizados` conserva incoherencia de bandeja/KPI frente al calendario

- **Esperado:** Una selección de finalizados debe exponer una bandeja y contadores coherentes con las tarjetas de calendario.
- **Resultado estático:** `days` puede contener finalizados, pero la bandeja deriva de `active_rows`, que los excluye.
- **Evidencia:** `backend/app/maintenance_planner/service.py` y `frontend/src/app/maintenance-planner/maintenance-planner.component.ts`.
- **Prueba visual con datos:** BLOCKED.

## Permisos y scope

- **ADMICORP:** BLOCKED. No se pudo confirmar acceso global, selector, exclusión de Administrador/Corporativo ni reporte.
- **GERENTE_REGIONAL:** BLOCKED dinámicamente. El board construye catálogo desde `sucursales_ids` y aplica scope regional estricto; falta verificarlo con respuesta y UI reales.
- **GERENTE:** BLOCKED dinámicamente. La política PM estática concede vista y niega ejecución; falta comprobar que el endpoint genérico devuelva 403 para el payload específico.
- **MANTENIMIENTO:** BLOCKED. La política PM estática concede ejecución; falta comprobar el endpoint propio sobre ULTRA DEMO.
- **No PM:** BLOCKED. No se pudo confirmar que el guard corregido no afecte tickets de otros departamentos.

## ULTRA DEMO

No se pudieron enumerar sucursales ni tickets sin sesión autenticada. Por lo tanto:

- no se confirmó que ULTRA DEMO aparezca en el selector;
- no se confirmó `sucursal_id_destino` de ningún ticket;
- no se ejecutó ninguna mutación, rollback, drag & drop, primera asignación ni cierre;
- no hay IDs de tickets de prueba que reportar.

## Edificio

BLOCKED dinámicamente. El contrato estático serializa una alternativa segura para equipo (`ticket.equipo`, `ticket.detalle` o `Sin equipo`) y la plantilla usa placeholders para campos opcionales; falta validar con un ticket real de Edificio en Planner y modal.

## Reporte XLSX

BLOCKED. La descarga actual permanece fuera de Planner, en la pantalla de Tickets, mediante `GET /api/mantenimiento-equipos/reporte`. No hubo sesión ADMICORP, no se descargó archivo y no se ejecutó `openpyxl`. Por tanto siguen pendientes todas las verificaciones de hojas, resumen, matriz Edificio por categoría, totales y familias.

## UI vs API

BLOCKED. Sin un board autenticado no fue posible comparar métricas, tarjetas, criticidad, estado, sucursal, fechas ni duplicados.

## Console / Network

| Viewport | URL final | Console errors | Respuestas fallidas observadas |
| --- | --- | ---: | ---: |
| 1920x1080 | `http://localhost:4200/#/login` | 0 | 0 |
| 1366x768 | `http://localhost:4200/#/login` | 0 | 0 |

Evidencias:

- `artifacts/maintenance-planner-audit-v2/screenshots/anonymous-1920x1080.png`
- `artifacts/maintenance-planner-audit-v2/screenshots/anonymous-1366x768.png`
- `artifacts/maintenance-planner-audit-v2/network/anonymous-playwright-results.json`

No se almacenaron tokens, passwords ni JWT.

## Casos no probados

- Los cinco resultados HTTP por rol exigidos en la sección de validación del fix.
- Reversión y persistencia de `schedule` con MANTENIMIENTO en ULTRA DEMO.
- Drag & drop, cambio de fecha y primera asignación de fecha, incluidos endpoints reales.
- Selector de sucursal, calendario, sticky headers, KPIs, bandeja, modal y responsive autenticados.
- Scope efectivo, query params y 403 de GERENTE/GERENTE_REGIONAL.
- Tickets de Edificio.
- Descarga e inspección del XLSX con `openpyxl`.

## Recomendaciones priorizadas

1. **P0:** No declarar cerrado el fix hasta demostrar con credenciales de GERENTE y GERENTE_REGIONAL que `PUT /api/tickets/update/:id` sobre ticket PM devuelve 403 y no persiste cambios.
2. **P0:** Confirmar que el frontend real de reprogramación y drag & drop usa el endpoint Planner, no la actualización genérica; el código presente todavía no lo hace.
3. **P1:** Proveer credenciales temporales de auditoría y tickets reversibles de ULTRA DEMO para completar todas las pruebas bloqueadas.
4. **P2:** Alinear la bandeja y los KPIs cuando el filtro es `Finalizados`.
5. **P2:** Añadir una configuración Playwright reproducible al proyecto, con datos demo controlados y una aserción de red para impedir regresión al endpoint genérico.

## Veredicto

**BLOCKED**

Qué falta antes de considerar terminado Maintenance Planner:

- Credenciales de auditoría para los cuatro roles y un ticket ULTRA DEMO reversible.
- Evidencia HTTP autenticada de los cinco casos de autorización requeridos.
- Confirmación de endpoint en drag & drop, modal y primera asignación.
- Validación de datos/UI, Edificio y XLSX con artefacto real.
- Resolver o descartar con evidencia el P0 estático actual.
