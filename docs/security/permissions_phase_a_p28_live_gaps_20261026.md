# Suite Ultra — Fase A P28: conciliación integral de 112 diferencias del catálogo VIGENTE

Corte proporcionado por el operador: **2026-10-26T22:30:04.294972+00:00**. Fuente: comando manual `python -m app.utils.permission_route_inventory`, ejecutado sobre PostgreSQL con `SET TRANSACTION READ ONLY` y `ROLLBACK`. **El SHA del backend que produjo ese corte no viene en la salida suministrada; no se declara paridad binaria host/main.**

> Objetivo: registrar diferencias reales entre catálogo y `app.url_map`, mantener una identidad reproducible de las 112 mutaciones y ordenar la auditoría por impacto **sin crear permisos, cambiar guards, modificar grants, escribir DB ni desplegar servicios**.

## 1. Resultado de la conciliación en PostgreSQL

| Indicador | Resultado | Interpretación |
|---|---:|---|
| Operaciones HTTP en Flask | 428 | método + regla Flask |
| Filas de catálogo activas | 69 | entradas vigentes; NO enforcement |
| Coincidencias exactas | 68 | método + ruta + handler |
| Alias de handler | 1 | coincidencia por nombre de función; no es pendiente |
| Handler divergente | 0 | no hay deriva de handler detectada para parejas catalogadas |
| Método+ruta no catalogados | 359 | 247 GET + 112 otros métodos |
| Mutaciones por conciliar | **112** | 17 familias; revisarlas, no concederles acceso |
| Entradas en catálogo sin ruta | **3** | tres POST RRHH de Tickets, todas `is_active=False` y `review_status=decommissioned` |

Los tres registros históricos inactivos (no reactivar, tampoco purgar sin política de retención):
- `POST /api/tickets/rrhh/aprobar/<int:ticket_id>`
- `POST /api/tickets/rrhh/rechazar/<int:ticket_id>`
- `POST /api/tickets/rrhh/solicitar/<int:ticket_id>`

La discrepancia **111 (corte previo) → 112 (este corte)** es +1 método no catalogado. El archivo entregado no contiene las 111 identidades del corte previo ni el HEAD host, por lo que su causa concreta **no está demostrada**. Revisar diferencial de ambos JSON y SHAs antes de atribuirlo a Tapizado u otro módulo.

## 2. Registro individual y agrupación de revisión

El anexo [permissions_phase_a_p28_live_mutations_20261026.csv](permissions_phase_a_p28_live_mutations_20261026.csv) contiene **las 112 operaciones**, una por fila y con las siguientes columnas: `family`, `method`, `route`, `handler`, `review_group` (grupo funcional propuesto), `risk_triage` (prioridad heurística), `catalog_classification` (= `not_cataloged` al momento del corte).

**Importante**:
- `review_group` **no es una nueva acción del catálogo ni un nombre definitivo de permiso**; es una unidad de trabajo de revisión. Se comprobará si corresponde reutilizar un `permission_action` vigente o decidir formalmente una acción nueva.
- `risk_triage` se deriva de la operación y los nombres de rutas. **No es un diagnóstico de vulnerabilidad** ni prueba de lectura/escritura. Los POST de preview, resumen y tests pueden realizar consultas, generar datos o tener efectos laterales: revisar implementación.
- Todos los 112 son `not_cataloged` según la fotografía; **ninguno se declara público ni desprotegido** por esta propiedad.
- El test de CI confirma identidad **contra el Flask del checkout**, sin leer PostgreSQL. No intenta aprobar el acceso efectivo.

### Distribución por familia

| Familia | Mutaciones | Foco de revisión |
|---|---:|---|
| Marketing | 42 | dispatch, aprobaciones, proveedor, previews, configuración, alcance por sucursal |
| Requisiciones | 19 | decisiones financieras, estado, cotizaciones, adjuntos, configuración de aprobadores |
| Integraciones | 11 | Google Ads M6: ingest/corrección, publicación canónica, OAuth |
| Contact Center | 10 | contacto/caso, cita, importación/fusión, compra y alcance de sucursal |
| Tickets | 6 | coordinación mantenimiento, cambios de estado, recepción Tapizado |
| Track Alerts | 5 | generación/test y entrega por correo |
| Auth | 3 | protocolo login, refresh y logout; excepciones JWT intencionales |
| Inventario | 3 | corrección de código, anulación de movimiento, solicitudes |
| Chequeo Diario | 3 | entrega, posponer, configuración de rollout BI |
| Routine Control | 2 | decisión sin rutina y revocación |
| Warehouse | 2 | generación de consolidado y solicitud de job |
| Planner, Mantenimiento Equipos, Aperturas, Permisos, RPA, Track | 1 c/u | control por sucursal/actor, configuración, SMS, cierre canónico |
| **TOTAL** | **112** | |

Son **35 grupos funcionales provisionales**. Priorización automática *para revisión* (no autorizaciones certificadas): **21 críticas, 76 altas, 15 medias**. La revisión de fuentes puede subir o bajar una prioridad; nunca asumir que una ruta de prioridad media puede quedar desprotegida.

## 3. Límites reales de autorización, por bloque

**Marketing (42).** P26.1–P26.9 aportan regresiones HTTP/JWT y censo de 82 operaciones activas, con 42 no GET. Se observaron rutas con permisos de gestión regional distintos del step-up global para dispatch. Catalogarlas requiere decidir acción operativa, alcance por sucursal, banderas, propietario y estado; las pruebas AST y mocks no certifican escritura PostgreSQL ni cada servicio.

**Requisiciones (19).** P23/P24 prueban invariantes de aprobaciones/rechazos con ORM SQLite efímero. La ruta recupera el actor y delega a servicio. Debe verificarse autoridad financiera, pertenencia de requisición, estado, allowlist, notificación después del commit y que los 403/409 no escriban datos.

**Integraciones (11).** Las rutas M6 de aprobación/promoción/publicación de Google Ads incluyen feature flags, controles de ADMICORP y para publicación/correcciones el acceso de upload a Warehouse. Inspeccionar cada handler y servicio antes de compartir un permiso de ingestión con publicar o promover. OAuth requiere su propio modelo de identidad; nunca asumir que todos los POST exigen exactamente un JWT de acceso.

**Contact Center (10).** P27 cubre estructura JWT y guard inicial; además existen tests de operador/gerente. Es necesario validar permisos de caso/cita concreta, sucursales, titularidad, fusión, importación de CRM y verificación de compra. No confundir `_context` con la autorización final del objeto.

**Chequeo Diario (3).** `submit`/`postpone` resuelven actor y sucursal; `bi/rollout` separa autorización BI y servicio de configuración. Conservar tests de estado, rollback, evidencia y scope.

**Tickets/Inventario (9).** Validar las transiciones de recepción de Tapizado al 100%, propiedad y sucursal de tickets; para Inventario, integridad de existencias, anulación, duplicados y autorización por sucursal. No aplicar catálogo como enforcement sustituto de los guards existentes.

**Auth (3).** Login, refresh y logout son protocolos de credenciales/cookies/sesiones; que no tengan `@jwt_required()` es esperado. Se revisan por origen, cookies, rotación, revocación y límites de abuso; no intentar añadir JWT a login.

**Permisos (1).** `PUT /api/permissions/catalog/users/<int:user_id>/module-access` llama a `_current_admin_user_or_error()` y exige revisión de cambios por administrador, auditabilidad, límites y hard stops; catalogación de esta ruta no permite elevar privilegios.

**RPA SMS/Track/Track Alerts/Warehouse (9).** La solicitud SMS tiene guard del módulo; cierre canónico de Track exige rol admin; alertas pueden enviar correos; jobs de Warehouse pueden iniciar trabajo posterior. Documentar quién solicita, alcance, deduplicación y permisos del scheduler/worker, no solo del HTTP.

**Otros** (Planner, Mantenimiento Equipos, Aperturas y Routine Control): comprobar actor/rol, sucursal, estado y trazabilidad con los tests de cada dominio.

## 4. Criterios para una futura migración de mapeos

1. Recuperar **snapshots DB y código de la misma versión**; guardar commit e instante. El CSV inicial es evidencia del corte reportado, no un inventario que se actualice automáticamente.
2. Para cada `review_group`, identificar **acción existente** (si la hay), propietario del control backend, políticas específicas de recurso/sucursal/estado y hard stops; no conceder grants ni crear roles combinados.
3. Separar mapeo documental (qué guard se observa) de autorización efectiva (cuándo se deniega/autoriza y qué side effects ocurren).
4. Resolver los 247 GET fuera de catálogo en inventario separado, particularmente exportaciones y datos sensibles; **no cerrar Fase A solo por cubrir las 112 mutaciones**.
5. Proponer migración **Alembic revisada y reversible** para cambios de tablas, sin imponer nuevas reglas de enforcement. Toda discrepancia que requiera modificar permisos efectivos necesita decisión funcional independiente.
6. Reconciliar el catálogo luego del merge/deploy autorizado y documentar cualquier nueva diferencia, incluyendo el +1 todavía no explicado.

## 5. Comprobación automática y alcance del PR

`backend/tests/routes/test_permissions_phase_a_p28_snapshot_contract.py` valida cardinalidad, distribución, unicidad y valores del CSV; y que los 112 métodos+rutas+handlers sigan registrados en Flask y las 3 rutas RRHH no vuelvan a registrarse. **No ejecuta handlers, no lee la base, no prueba JWT ni eleva permisos**. Se ejecuta en el workflow de la Fase A junto con P21/P22/P25/P27 y regresiones existentes.

**Estado de cierre:** P28 puede cerrarse al confirmar CI del repositorio actual, pero el issue global #1053 queda **ABIERTO** por decisiones de mapeo, lectura GET y conciliación real en DB tras una migración posterior. No requiere migración ni despliegue.
