# Suite Ultra — Nombres amigables de acciones de permisos (2026-10-23)

## Alcance y fuente única

Presentación administrativa en la pantalla `/#/admin/permisos-observabilidad` para las **40 acciones** identificadas en el historial de siembra: 34 originales, 3 acciones base de entrada, 1 eliminación masiva de tickets y 2 acciones de coordinación de mantenimiento. El archivo de fuente de verdad para los **textos** es `frontend/src/app/permissions-observability/permission-action-labels.ts`, no esta tabla documental.

**Regla de seguridad:** el alias, la descripción y la categoría son *etiquetas de interfaz*, nunca permisos reales. El backend conserva `full_key`, guard/rol/sucursal, decisiones trivalentes y estimaciones. Los nombres no se guardan en PostgreSQL ni modifican los grants. Si una acción no figura en este conjunto, se muestra el `name`/`description` entregado por el catálogo como fallback; no se infiere acceso permitido o denegado.

Los textos se presentan desde un helper TS puro y compartido: selector de acciones, tres perspectivas de la matriz, Acciones, Rutas high-risk, Grants beta y Usuario efectivo. En listas y CSV se conserva la clave técnica, además de ofrecer el alias. Las razones técnicas del catálogo/guard siguen visibles dentro de un detalle expandible.

## Catálogo auditado

| Módulo | Clave técnica inmutable | Nombre amigable | Finalidad |
|---|---|---|---|
| tickets | `tickets.view` | Consultar tickets | Consultar |
| tickets | `tickets.create` | Crear tickets | Crear |
| tickets | `tickets.update` | Editar datos de tickets | Modificar |
| tickets | `tickets.update_status` | Cambiar estado de tickets | Modificar |
| tickets | `tickets.close` | Cerrar o validar tickets | Validar |
| tickets | `tickets.notify` | Enviar avisos de tickets | Comunicar |
| tickets | `tickets.delete_all` | Eliminar todos los tickets | Administrar |
| tickets | `tickets.maintenance.coordinate` | Coordinar atención de mantenimiento | Coordinar |
| tickets | `tickets.maintenance.read_assigned_only` | Limitar vista a tickets asignados | Restringir |
| inventory | `inventory.read` | Consultar inventario y existencias | Consultar |
| inventory | `inventory.master_write` | Administrar inventario general | Administrar |
| inventory | `inventory.movement_write` | Registrar movimientos de inventario | Registrar |
| pm | `pm.read` | Consultar mantenimiento preventivo | Consultar |
| pm | `pm.execute` | Registrar mantenimiento preventivo | Registrar |
| pm | `pm.validate` | Validar mantenimiento preventivo | Validar |
| pm | `pm.configure` | Configurar mantenimiento preventivo | Configurar |
| warehouse | `warehouse.view` | Consultar reportes de Warehouse | Consultar |
| warehouse | `warehouse.upload` | Cargar reportes a Warehouse | Cargar |
| warehouse | `warehouse.archive` | Archivar reportes de Warehouse | Administrar |
| warehouse | `warehouse.catalogs` | Administrar catálogos de Warehouse | Administrar |
| internal_documents | `internal_documents.view` | Consultar Nube Corporativa | Consultar |
| internal_documents | `internal_documents.manage` | Administrar Nube Corporativa | Administrar |
| track | `track.read` | Consultar indicadores de Track | Consultar |
| track | `track.run_daily_pipeline` | Ejecutar actualización diaria de Track | Ejecutar |
| track | `track.run_agregadoras` | Ejecutar integración de agregadoras | Ejecutar |
| planning | `planning.read` | Consultar metas y planeación | Consultar |
| planning | `planning.edit` | Modificar metas y planeación | Modificar |
| planning | `planning.submit` | Enviar metas a revisión | Enviar |
| planning | `planning.approve` | Aprobar o rechazar metas | Validar |
| planning | `planning.publish` | Publicar metas aprobadas | Publicar |
| planning | `planning.configure_model` | Configurar modelos de metas | Configurar |
| openings | `openings.read` | Consultar proyectos de apertura | Consultar |
| openings | `openings.manage` | Administrar proyectos de apertura | Administrar |
| openings | `openings.comment` | Comentar tareas de apertura | Comunicar |
| catalogs | `catalogs.view` | Consultar catálogos del sistema | Consultar |
| catalogs | `catalogs.manage` | Administrar catálogos del sistema | Administrar |
| users | `users.view` | Consultar usuarios del sistema | Consultar |
| users | `users.manage` | Administrar usuarios y sucursales | Administrar |
| reports | `reports.read` | Consultar reportes operativos | Consultar |
| reports | `reports.create_error_report` | Reportar errores operativos | Registrar |

## Notas de significado

- `tickets.maintenance.read_assigned_only` es una **restricción de visibilidad**, no un permiso de ampliación; el alias lo explicita.
- `tickets.delete_all` representa eliminación masiva sujeta a salvaguardas del backend; el nombre no implica disponibilidad irrestricta.
- `internal_documents.view` requiere comprobación de visibilidad por documento; el nombre no concede acceso universal.
- `inventory.movement_write` puede representar varios flujos de movimiento, mientras el guard específico por recurso sigue separado.
- `track.read` permanece como diagnóstico de lectura. No implica poder ejecutar los pipelines `track.run_daily_pipeline` o `track.run_agregadoras`.
- Vistas y CSV etiquetan exactamente los mismos identificadores, sin cambiar filtros `action_key`, navegación, estado de auditoría ni paginación.

## Validación

`backend/tests/routes/test_permissions_action_alias_contract.py` deriva automáticamente las 40 claves desde las migraciones Alembic pertinentes y exige correspondencia 1:1 sin duplicados, nombres legibles y fallback seguro. El workflow `permissions-visual-audit-ci.yml` ejecuta ese test junto al resto de la matriz y compila Angular. La validación visual posterior a despliegue debe recorrer las tres perspectivas, el selector, Acciones, Usuario efectivo, Grants beta, Rutas y CSV.

**Estado:** UI de solo lectura; sin cambios de DB/guards/grants/resolvedor global; no requiere migraciones ni despliegue de scheduler.