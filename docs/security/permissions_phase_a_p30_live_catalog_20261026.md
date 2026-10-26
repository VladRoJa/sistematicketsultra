# Suite Ultra — Fase A P30: conciliación con acciones **vigentes** en PostgreSQL

**Fuente primaria:** salida del operador de `docker compose exec -T backend python` con `SET TRANSACTION READ ONLY`, del **2026-10-26T23:48:39.184263+00:00**. Host `git rev-parse HEAD`: `8abfb04e23a4f99a881b8aa63515fd5da855fa80` (P29 fusionado). El SHA de host y la coincidencia del inventario son consistentes; por sí solos no prueban la identidad binaria de la imagen Docker. Ninguna fila de datos personales ni secretos se copió al repositorio.

## 1. Confirmación del catálogo live

| Evidencia | Corte P30 |
|---|---:|
| Módulos existentes | **11** |
| Acciones existentes | **40**, todas `is_active=True`, en módulo activo |
| Filas `permission_route_map` activas | **69** |
| Enlace exacto Flask⇄map | **68** |
| Enlace por alias de handler | **1** |
| Divergencias de handler / mapa inactivo en Flask | **0 / 0** |
| Métodos Flask sin entrada de catálogo | **359** = **112** no-GET + **247** GET |
| Grants según `is_active=True` y `deleted_at IS NULL` | **2** filas agregadas: `allow` + `user` + `global` |

**Los dos grants no son “permisos globales concedidos a todos”**: `principal_type=user` significa que se asociaron a usuarios particulares, cuyas identidades no se recogieron. El corte no incluyó `action_id` de esos grants, sus fechas `starts_at/expires_at` ni evaluación de efectos. No se conoce su acción de destino ni se puede inferir que estén vigentes temporalmente o que anulen hard stops.

## 2. Revisión de las 10 sugerencias P29 (no cambiar catálogo automáticamente)

Las seis acciones sugeridas en P29 **existen, están activas** y pertenecen a **módulos activos y asignables**. No tienen grants individuales sobre esas *seis claves* en la consulta agregada (`grants_activos_flag=0`). Eso **NO** implica que sus rutas nieguen acceso: se aplican roles/guards legacy y otras acciones más específicas. Tampoco indica a qué acciones se refieren los otros 2 grants.

**Corrección sustantiva:** `tickets.maintenance.coordinate` está activo en PostgreSQL y es el guard semántico **real** de `PUT /api/tickets/maintenance/<id>/coordinate` y `PUT /api/tickets/maintenance/<id>/reassign`, de acuerdo con:
- `backend/app/utils/tickets_maintenance_permissions.py::has_maintenance_coordination_permission`: administradores, reglas de exclusión de roles regionales/técnicos, `can_pm_view`, grant individual de `tickets.maintenance.coordinate` con restricciones.
- `backend/app/services/ticket_maintenance_coordination_service.py::prepare_maintenance_coordination/prepare_maintenance_reassignment`: comprueban dicho guard, alcance por sucursal y estado permitido del ticket antes de mutar.
- `tickets.maintenance.read_assigned_only` existe pero **limita** visibilidad; no representa poder de coordinar ni una alternativa a `tickets.update`.

Por tanto P30 reemplaza **solo en el anexo de diagnóstico** las 2 asociaciones previas de `tickets.update` por `tickets.maintenance.coordinate`. **No cambia** `backend`, el route map o ningún grant.

| Grupo | Cantidad | Decisión P30 |
|---|---:|---|
| Coordinación/reasignación Mantenimiento | **2** | Evidencia del guard de servicio **verificada**; candidato fuerte `tickets.maintenance.coordinate`, aún no catalogado y requiere validación final de paridad antes de un mapeo oficial |
| Resto de las 10 candidatas P29 | **8** | Acciones efectivamente existentes pero **NO** certificada la equivalencia actor/objeto/estado; no mapear aún |
| Operaciones restantes | **102** | Se mantiene el diseño funcional pendiente, agrupado en los 35 grupos P28; **no son 102 permisos nuevos** |
| **Total** | **112** | Matriz [P30 por operación](permissions_phase_a_p30_live_action_reconciliation_20261026.csv) |

**Distribución de las ocho pendientes con acción activa:** `tickets.update_status` ×2; `tickets.update` ×2 (recepción Tapizado); `inventory.master_write` ×1; `inventory.movement_write` ×1; `openings.manage` ×1; `users.manage` ×1.

La etiqueta `service_guard_semantics_verified` para las 2 rutas de mantenimiento solo asegura la **relación de código entre el guard y los servicios**. No constituye prueba dinámica 401/403/200/409 ni garantiza cualquier acceso por excepción.

## 3. Lo que NO debemos cambiar por este corte

- No poblar masivamente `permission_route_map` con 112 filas: la tabla es inventario de observabilidad y no reemplaza las comprobaciones legacy.
- No crear/otorgar 102 permisos, no reasignar los dos grants de usuario existentes y no convertir una acción de edición general en coordinación.
- No usar `is_active` de una acción, `module.is_assignable`, un grant activo o el menú frontend como única prueba de ejecución autorizada.
- No concluir que las 359 rutas son públicas, ni que las 247 GET son inocuas (exportaciones, preview y datos privados).
- No afirmar origen del incremento histórico 111→112 sin snapshots completos pareados.
- No asumir que el reporte HTTP de P29 prueba autorización de los 112 handlers.

## 4. Herramienta repetible P30 y sus límites

`python -m app.utils.permission_live_action_snapshot`, invocado **manualmente dentro del backend**, consulta PostgreSQL bajo transacción `READ ONLY` con `ROLLBACK`. Produce JSON con:
- claves y estados de módulos/acciones, conteos de rutas catalogadas por acción;
- clasificación de Flask con comparación al route map actual y 112/247 como indicadores dinámicos;
- conteo agregado de grants por `effect`, tipo principal, alcance, bandera de actividad, y por acción (filas activas y filas dentro de ventana temporal).

Nunca selecciona o exporta `principal_user_id`, usuarios, contraseñas, `reason`, IP, agente o `scope_payload`. La agregación **no evalúa** si el principal existe/está habilitado, hard stops, departamentos, sucursales o permisos efectivos; las ventanas de tiempo se comparan, pero la autorización completa sigue siendo del servicio. La herramienta no se conecta automáticamente a un scheduler, API o frontend.

Regresión en `backend/tests/routes/test_permissions_phase_a_p30_live_action_parity.py`: prueba la conservación de las **112** identidades P29, **2 + 8 + 102** decisiones, la relación entre los dos handlers y la acción especializada, y la ausencia de identificadores de usuarios en un ejemplo sintético del reporte. **No escribe la BD ni llama endpoints**.

## 5. Próximo paso para cerrar los bloques de la Fase A

1. Revisar y validar las **2 operaciones** `tickets.maintenance.coordinate` con usuarios autorizados/denegados, sucursales y estados: las pruebas negativas existentes de tickets ayudan. Después proponer (si aporta observabilidad) una **migración Alembic de route map sin tocar guards ni grants**.
2. Resolver en bloque las otras **8 candidatas**, priorizando `users.manage`, anulación de inventario y recepción de Tapizado; hacer una decisión explícita por capacidad y conservar hard stops.
3. Revisar las **102** contra permisos legados y la decisión operativa por grupo; casos prioritarios Marketing (42), Requisiciones (19), Integraciones (11), Contact Center (10). Muchos POST pueden ser consultas, no writes.
4. Ampliar revisión a **247 GET** antes del cierre de Fase A y comparar cortes históricos completos para 111→112.

**P30 es una conciliación auditada de datos**, no una autorización para conceder accesos ni para desplegar un cambio de seguridad. Fase A issue #1053 queda **OPEN**.
