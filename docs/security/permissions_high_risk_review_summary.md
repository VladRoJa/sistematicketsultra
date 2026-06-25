# Permissions High-Risk Review — Executive Summary

## Objetivo

Cerrar documentalmente la revisión inicial de rutas high-risk de Suite Ultra.

Esta revisión cubre rutas clasificadas inicialmente como:

- `high_delete`
- `high_job_or_import`
- `medium_write`

## Resultado general

- Total de rutas high-risk revisadas: **72**
- Rutas pendientes: **0**

## Conteo por estado

| estado | rutas |
|---|---:|
| decommissioned | 3 |
| needs_manual_decision | 8 |
| ok_hardened | 61 |

## Conteo por riesgo inicial

| riesgo inicial | rutas |
|---|---:|
| high_delete | 7 |
| high_job_or_import | 4 |
| medium_write | 61 |

## Conteo por módulo

| módulo | rutas high-risk |
|---|---:|
| Tickets | 14 |
| Aperturas | 11 |
| Nube Corporativa | 11 |
| Planning / Metas | 8 |
| Catálogos | 6 |
| Inventario | 6 |
| PM | 5 |
| Usuarios / Admin | 4 |
| General / Otro | 2 |
| Track / BI | 2 |
| Warehouse | 2 |
| Reportes | 1 |

## Decisiones futuras detectadas

| módulo | riesgo inicial | método | ruta | función | motivo |
|---|---|---|---|---|---|
| Inventario | high_delete | DELETE | `/<int:inventario_id>` | `eliminar_inventario` | Guard correcto. Hard delete permitido si no hay movimientos; evaluar soft delete/env gate/auditoría futura. |
| Inventario | high_delete | DELETE | `/movimientos/<int:id>` | `eliminar_movimiento` | Guard correcto. Revierte stock y borra histórico; evaluar cancelación/reverso auditado. |
| Inventario | high_job_or_import | POST | `/importar` | `importar_inventario` | Guard correcto. Import masivo directo a InventarioGeneral; evaluar deduplicación, validación fuerte, auditoría/import batch y rollback controlado. |
| Aperturas | medium_write | POST | `/<int:opening_id>/tasks/<int:task_id>/comments` | `create_task_comment` | Es write real, pero usa guard de lectura. Puede ser intencional como colaboración; decidir si comentar requiere permiso específico. |
| Usuarios / Admin | medium_write | POST | `` | `crear_usuario` | Guard correcto. Permite crear cualquier rol/sucursal/departamento; futuro: política granular de roles altos y catálogo de roles permitidos. |
| Usuarios / Admin | medium_write | PUT | `/<int:user_id>` | `editar_usuario` | Guard correcto. Permite modificar rol/sucursal/departamento/password/email; futuro: política granular para cambios sensibles y autoedición. |
| Warehouse | medium_write | POST | `/uploads` | `warehouse_create_upload` | Guard correcto con WarehouseOperatorORM y can_upload. Futuro: agregar is_active o política formal de desactivación de operador. |
| Warehouse | medium_write | PATCH | `/uploads/<int:upload_id>/archive` | `warehouse_archive_upload` | Guard correcto con WarehouseOperatorORM y can_archive. Futuro: agregar is_active o política formal de desactivación de operador. |

## Rutas retiradas

| módulo | método | ruta | función | motivo |
|---|---|---|---|---|
| Tickets | POST | `/rrhh/solicitar/<int:ticket_id>` | `rrhh_solicitar` | Endpoint RRHH fuera del flujo actual; removido de backend. |
| Tickets | POST | `/rrhh/aprobar/<int:ticket_id>` | `rrhh_aprobar` | Endpoint RRHH fuera del flujo actual; removido de backend. |
| Tickets | POST | `/rrhh/rechazar/<int:ticket_id>` | `rrhh_rechazar` | Endpoint RRHH fuera del flujo actual; removido de backend. |

## Conclusión

- No quedaron rutas high-risk pendientes.
- No se detectaron rutas abiertas dentro del alcance revisado.
- Las decisiones pendientes son de diseño/gobierno de permisos, no hotfix urgente.
- El siguiente paso recomendado es diseñar el módulo global de permisos tomando como referencia los patrones robustos encontrados en Planning y Warehouse.