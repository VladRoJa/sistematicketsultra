# Suite Ultra — Fase A P27: auditoría integral transversal de autorizaciones

Corte de referencia: 26/oct/2026; base de rama main 4709433db23e14e334a0314c3674c20cd994c7cc.
Alcance estrictamente diagnóstico: no se alteran guards, grants, JWT, roles, bases de datos, flags, políticas de autorización ni servicios.

## Inventario Flask activo

Se revisaron cinco blueprints registrados por app/__init__.py::create_app. El contrato automatizado compara app.url_map y el código AST de los handlers, sin invocar endpoints ni consultar la base de datos.

| Blueprint | Métodos HTTP | Métodos distintos de GET | Fuente inicial de control |
|---|---:|---:|---|
| contact_center | 18 | 10 POST | JWT, _context(), verificaciones de operador/caso/cita |
| purchase_requisition | 24 | 17 POST, 2 PUT | JWT, _current_user(), políticas delegadas a servicios |
| system_daily_check | 5 | 2 POST | JWT, _current_user(), _requested_branch_id() |
| system_daily_check_bi | 11 | 1 PUT | JWT, _current_user(), _require_bi_access(), servicio de rollout |
| automation_control | 14 | 0 | JWT, guard de lectura y sanitización |
| **Total** | **72** | **32** | **No reemplaza la autorización del backend** |

Un POST no siempre implica escritura y un GET puede exponer datos sensibles. El censo de métodos es un control de cambio de superficie, no un informe de vulnerabilidad.

## Archivos incluidos

- backend/tests/routes/test_permissions_phase_a_cross_family_p27.py: registra exactamente las 72 operaciones; valida JWT de los handlers, guarda la lista exacta de 32 no GET y comprueba llamadas estructurales a resolutores de entrada.
- .github/workflows/permissions-phase-a-live-map-ci.yml: ejecuta P21, P22, P25 y P27 junto con regresiones ya existentes; se dispara también ante cambios de rutas, resolutores y servicios relevantes.
- Este documento consigna cobertura, límites, riesgos y pasos pendientes.

## Evidencia y límites de interpretación

- Contact Center: AST comprueba _context, _assert_operator_access, _assert_case_access y _assert_appointment_access cuando corresponde. Tests existentes: test_contact_center_access.py y test_contact_center_manager_scope_contract.py; el segundo es contrato de fuente, no prueba HTTP de acceso a filas.
- Requisiciones: los 19 métodos no GET mantienen _current_user y su delegación al servicio. Tests P23/P24 sobre SQLite efímero prueban invariantes de aprobación/rechazo financiero; no equivalen a prueba HTTP ni a paridad contra PostgreSQL productivo.
- Chequeo Diario: los POST submit/postpone usan usuario y sucursal; BI rollout combina _require_bi_access y servicio de configuración. Seguir comprobando estado, evidencia, rollback y scope en sus suites funcionales.
- Automation Control: cero métodos no GET en el blueprint; la suite test_read_api.py cubre autenticación, whitelist, semántica de lectura y sanitización.
- Todas las comprobaciones de AST identifican presencia de rutas, decoradores o llamadas. **No certifican ejecución del guard, autorización sobre una sucursal/objeto, invariantes SQL, ni ausencia de efectos laterales reales.**
- No ejecutar envíos, compras, importaciones ni cambios de permisos en producción como parte de este bloque.

## Riesgos y pendientes priorizados

| Prioridad | Frente | Prueba funcional pendiente o evidencia requerida |
|---|---|---|
| Crítica | Requisiciones, aprobar/rechazar financiamiento | Permisos del actor/allowlist y transición de estado; cero escrituras en denegaciones sobre datos controlados |
| Alta | Contact Center, fusionar/importar CRM/verificar compra | Acceso efectivo a caso y cita, propietario, alcance de sucursal y protección de datos personales |
| Alta | Chequeo Diario, submit/postpone y rollout | Denegación por rol y sucursal, estado, archivos adjuntos y rollback |
| Media | Automation Control | JWT, whitelist, redacción de información interna y sin escrituras |
| Bloqueante global | Catálogo actual permission_route_map | Snapshot de solo lectura del catálogo en PostgreSQL, comparado con app.url_map de la MISMA versión |

P25 compara el registro Flask con la tabla ACTUAL permission_route_map mediante SET TRANSACTION READ ONLY + ROLLBACK, pero el snapshot de producción publicado en el issue #1053 reportó **111 mutaciones pendientes** en un corte anterior. No trasladar ese total a un commit posterior ni confundirlo con los 350 faltantes del seed histórico. Una diferencia en el catálogo no demuestra acceso público ni un bypass.

## Conciliación pendiente de base vigente

Con una imagen backend desplegada por el proceso normal y que corresponda exactamente al commit que se estudia, el operador autorizado puede ejecutar una sola lectura:

    docker compose exec -T backend python -m app.utils.permission_route_inventory > /tmp/permissions-route-map-phase-a.json

El programa usa transacción PostgreSQL READ ONLY y ROLLBACK; no es un job automático y no se debe editar el servidor manualmente. Revisar by_classification, by_family, unreviewed_mutations y catalog_only_method_routes. Mantener la diferencia entre exact, handler_alias, handler_mismatch, catalog_inactive y not_cataloged. El alias conocido de PUT /api/admin/usuarios/<int:user_id>/sucursales no es una mutación nueva.

## Criterios de cierre

P27 puede integrarse después de tests/CI verde y revisión del diferencial. P27 solo certifica inventario estructural y regresión existente; no sustituye una auditoría funcional por recurso. La **Fase A global #1053 permanece abierta** hasta obtener la fotografía vigente del catálogo, reconciliar diferencias reales y registrar decisiones de compatibilidad. Ningún resultado habilita enforcement global, grants, nuevas migraciones, despliegue o cambios de permisos de forma implícita.
