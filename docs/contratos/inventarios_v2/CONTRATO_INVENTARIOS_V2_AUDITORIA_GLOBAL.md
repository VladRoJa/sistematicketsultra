# Contrato global — Inventarios V2: Auditoría y Validación por Sucursal

**Proyecto:** Suite Ultra (Angular + Flask + PostgreSQL).
**Fecha de acuerdo:** 2026-10-23.
**Versión del contrato:** 1.1.
**Estado:** E1 aceptado; E2 operativo (QA documental de roles por consolidar); E3 operativo, con ajuste oficial verificado en PostgreSQL; E4 pendiente de implementación; E5 GERENTES NO AUTORIZADO.
**Organización:** UN milestone lógico con CINCO entregables secuenciales (E1–E5). No equivale a cinco milestones distintos de GitHub.
**Decisión irrevocable sin nueva autorización explícita:** NO abrir Inventarios V2 a GERENTE antes de terminar y aprobar E1–E4 y el gate de E5.

## 0. Uso obligatorio en una nueva conversación

Este documento es el **punto de reanudación** del trabajo de Inventarios V2. Está diseñado para ser comprensible sin la conversación que lo originó.

Antes de proponer un cambio:

1. Leer íntegramente este contrato y su bitácora de progreso (`14).
2. Consultar `3 (evidencia real del repositorio) y volver a inspeccionar `main`, porque el código y el despliegue pueden haber cambiado.
3. Identificar el **primer entregable NO ACEPTADO**, sus dependencias y criterios de salida.
4. Explicar **archivo, función/método, objetivo y motivo** antes de modificar código.
5. Ejecutar **un cambio/prueba cada vez**, con QA dirigido; si cambia el síntoma, analizar antes de continuar.
6. Trabajar por PRs pequeños; no implementar varios entregables en un solo PR.
7. Tras aceptar cada entregable, **actualizar la bitácora de este contrato** con estado, PR/commit, evidencia QA, decisiones y siguiente paso. No declarar “terminado” por suposición.

**Este contrato fija alcance, no ejecuta cambios:** no autoriza por sí solo migraciones, habilitación de permisos, escrituras en producción, despliegues ni rollout.

## 1. Problema y objetivo de negocio

Inventarios V1 ya dispone de catálogo, existencias por sucursal, entradas, salidas, anulaciones auditadas, reportes y dashboard. El núcleo funcional pasó QA técnico, **pero no existe todavía un levantamiento físico integral validado**.

Los activos actualmente cargados son mayormente **equipos/activos de baja rotación**, no mercancía con alto volumen de entradas y salidas. No se debe forzar el uso diario de movimientos como requisito artificial.

**Objetivo de V2:** cada sucursal debe poder consultar lo que el sistema dice que tiene, verificarlo físicamente, reportar discrepancias, solicitar correcciones sin modificar datos oficiales y obtener finalmente un corte de inventario confiable, con historial.

Preguntas operativas:
- ¿Qué activos/referencias aparecen registrados en mi sucursal?
- ¿Qué se encontró y en qué cantidad, y qué no pudo localizarse?
- ¿Qué datos están incompletos o equivocados?
- ¿Qué diferencias están pendientes, aprobadas o rechazadas?
- ¿Quién verificó, quién autorizó y cuándo se cerró el levantamiento?

**Regla de autoridad:** el gerente OBSERVA, VERIFICA y PROPONE. No tiene escritura directa sobre el inventario oficial.

## 2. Límites y decisiones explícitas

1. **Un solo milestone:** “Inventarios V2 — Auditoría y Validación por Sucursal”, con E1, E2, E3, E4 y E5.
2. **E5 es la apertura a gerentes y ocurre al final.** Hasta entonces no agregar la opción Inventario al menú de GERENTE, no habilitar funcionalidades V2 para ese rol ni ejecutar un rollout encubierto.
3. **Primero afinar la vista de Existencias.** Debe contener dashboard compacto **y** listado completo; no reemplazar el listado con tarjetas.
4. La acción futura del gerente se llama preferentemente **“Solicitar corrección”**; no es edición inmediata.
5. Una solicitud pendiente **jamás modifica stock, catálogo maestro ni asignaciones**. Los cambios oficiales requieren decisión autorizada y registro de auditoría.
6. Conservar el inventario original y mostrar diferencias; no hacer limpieza destructiva ni sustituir silenciosamente la base.
7. V1 continúa operando normalmente. No rehacer entradas/salidas, exportaciones o Reportes solo para implantar auditoría.
8. No duplicar activos de Mantenimiento Preventivo por defecto. Investigar identidad y vínculos antes de unir PM e Inventario.
9. No inventar indicadores “verificados”, “pendientes de auditoría” o “conciliados” con los datos actuales: solo aparecerán cuando exista evidencia persistida para sustentarlos.
10. No introducir mínimos de stock, reposición, consumo/rotación, BI predictivo o transferencias como requisitos de este milestone. Son backlog distinto.

## 3. Fotografía técnica verificada en main al 2026-10-23

Referencias a inspeccionar (las ubicaciones son evidencia de partida, **no garantía de que sigan idénticas**):

| Área | Archivo / ubicación | Hallazgo |
|---|---|---|
| Ruta principal | `frontend/src/app/app.routes.ts` | `/inventario` usa `AuthGuard`; no constituye por sí solo autorización específica de Inventarios. |
| Rutas hijas | `frontend/src/app/inventario/inventario.routes.ts` | `inventario`, `movimientos`, `existencias`, `reportes` cargan bajo `InventarioLayoutComponent`. |
| Menú general | `frontend/src/app/layout/layout.component.ts` | El menú gerencial actual no incluye Inventario; ocultarlo NO garantiza bloqueo de URL directa. |
| Existencias | `frontend/src/app/inventario/existencias/existencias.component.ts` | Tabla simple; `esAdmin` toma el rol de `localStorage`; selecciona sucursal y filtra en navegador datos de `verExistencias()`. |
| Vista y estilos | `frontend/src/app/inventario/existencias/existencias.component.html` y `.css` | Mat-table sin dashboard, búsqueda ni filtros detallados. |
| Servicio frontend | `frontend/src/app/services/inventario.service.ts` | `verExistencias()` invoca `GET /api/inventario/existencias` sin pasar filtro de sucursal. |
| Sesión central | `frontend/src/app/core/auth/session.service.ts` | Disponible `SessionService`; usarlo para el rol de presentación, no leer token/rol manualmente si no es necesario. |
| API lectura | `backend/app/routes/inventarios.py::ver_existencias()` | Devuelve referencia, código, tipo, marca, proveedor, categoría, unidad_medida, stock y sucursal; aplica `_resolve_inventory_read_sucursal_ids`. |
| API resumen | `backend/app/routes/inventarios.py::resumen_dashboard_inventario()` | `GET /api/inventario/reportes/resumen`, con filtro por sucursal y período. |
| Agregados | `backend/app/services/inventario_dashboard_service.py` | Cuenta **referencias inventario-sucursal**, no piezas; sin sucursal explícita excluye DEMO; período afecta movimientos, no stock actual. |
| Escrituras V1 | `backend/app/routes/inventarios.py` | Guards de escritura global/movimientos existentes; el código interno ya tiene un flujo de corrección auditada que no debe eludirse. |
| Reportes V1 | `frontend/src/app/inventario/reportes/reportes.component.*` | Dashboard ya trabajado y aprobado; **no confundirlo con la nueva pantalla de Existencias**. |

**Observación de datos:** el HTML actual pide `e.unidad`, mientras el backend devuelve `unidad_medida`. Corregir el mapeo al renovar la vista, conservando compatibilidad si existen variantes.

**Hallazgo legacy y mitigación V2:** `_resolve_inventory_read_sucursal_ids` conserva alcance acotado por `sucursal_id` para ciertos roles en **V1**. El PR #1103 separó la lectura visual V2 como `GET /api/inventario/v2/existencias`, con guard de rol piloto que deniega GERENTE/GERENTE_REGIONAL; E2 incorpora guard DB propio para la API de solicitudes (PR #1105) y la interfaz no ofrece acciones a esos roles (PR #1108). **No confundir esto con bloqueo total de V1:** `GET /api/inventario/existencias` sigue con política legacy por compatibilidad y necesita evaluación/hardening sin romper consumidores. No ampliar permisos durante E1–E4 ni declarar abierto el gate E5 sin QA real de rol/API/ruta.

## 4. Conceptos de datos obligatorios

- **Identidad de referencia:** `(sucursal_id, inventario_id)`. Dos filas con el mismo nombre no son el mismo activo.
- **Referencia no equivale a pieza:** `COUNT(referencias)` y `SUM(stock)` son magnitudes diferentes; el stock puede usar unidades heterogéneas y no debe sumarse sin contexto.
- **InventarioGeneral** contiene campos maestros potencialmente compartidos; **InventarioSucursal** representa existencia por sucursal. Una corrección de marca, categoría, descripción o código maestro puede impactar varias sucursales y necesita revisión del alcance real antes de aprobarse.
- Una diferencia física de cantidad no es necesariamente una salida/consumo. **No crear movimientos de salida falsos** para cuadrar auditorías; definir un ajuste auditado autorizado y su integración con V1 cuando se implemente.
- Debe poder declararse **“no localizado”**, cantidad física distinta, dato incorrecto y **“encontrado pero no registrado”** sin inventar un `inventario_id` canónico.
- La fecha de negocio se interpreta en `America/Tijuana`; eventos y auditorías deben guardar timestamps inequívocos (preferir UTC y presentar TZ local). Distinguir corte lógico de hora de captura.
- No mezclar un ciclo de auditoría con el stock vivo. Una solicitud debe conservar valor antes/propuesto y referencia al corte/versionado para detectar decisiones obsoletas.

## 5. E1 — Dashboard de Existencias + listado (PRs frontend de alcance mínimo)

**Objetivo:** renovar `/#/inventario/existencias` para usuarios **ya autorizados**; no abrir rol GERENTE.

Elementos:
- Encabezado claro y selector de sucursal para los perfiles que pueden elegirla; sin global para un usuario scoped.
- Resumen compacto basado solo en datos verificables: referencias con stock, referencias sin stock, categorías y distribución por categoría. Nunca llamar “activos físicos auditados” al número de referencias.
- Tabla completa conservada debajo, con búsqueda transversal (nombre/código/marca/tipo), filtros razonables de categoría/sucursal/estado de stock, vacío/cargando/error, visualización legible en escritorio y móvil.
- Columnas fieles a la API, incluyendo `unidad_medida`. Evitar paneles gigantes sin información y scrollbar horizontal de página. Scroll local de tabla solo cuando sea necesario.
- Cambios de sucursal deben actualizar dashboard y listado **coherentemente**. Priorizar filtro backend `sucursal_id`, no descargar indiscriminadamente inventarios para filtrarlos solo en Angular.
- Preferir reutilizar el resumen existente, con cuidado de que el modo global excluye DEMO implícitamente y la tabla de Existencias no tiene necesariamente la misma política. Documentar/corregir la semántica antes de mostrar cifras aparentemente contradictorias.
- Las futuras métricas de avance, verificados y diferencias **se omiten o identifican como no disponibles** hasta E4.

**Código previsto:** `existencias.component.ts` para cálculos/estado/acciones; `.html` para estructura/bindings simples; `.css` para presentación; `inventario.service.ts` solamente si requiere parámetro de lectura. Reutilizar estilos visuales de Reportes sin copiar lógica incompatible.

**Salida E1:** vista visualmente aprobada; selector, cifras y listado consistentes; búsqueda/filtros y carga/errores funcionales; Angular build y QA específico verdes; **sin cambios de permisos ni escrituras**.

## 6. E2 — Solicitudes de corrección, sin aplicación automática

**Objetivo:** registrar de manera persistente solicitudes independientes del inventario oficial.

Casos mínimos: dato maestro incorrecto (con delimitación de alcance), cantidad física distinta, artículo no localizado y artículo encontrado pero no registrado. Cada solicitud debe incluir creador autenticado, sucursal efectiva, referencia/identidad si existe, campo y valor original, valor propuesto, motivo, fecha, estado y evidencia/captura física según política por definir.

- No permitir que frontend imponga `created_by`, sucursal efectiva o permiso.
- El envío guarda una **propuesta**, no llama a `editarInventario()` ni actualiza existencias.
- Prevenir solicitudes duplicadas accidentales; definir comportamiento frente a cambios concurrentes.
- Estados mínimos conceptuales: `PENDING`, `APPROVED`, `REJECTED`, con transiciones controladas; nomenclatura de BD/API por definir al diseñar el modelo.
- Para código interno, respetar el proceso existente de corrección auditada; nunca mutarlo directamente para saltarse historial.
- La identidad de nuevos hallazgos debe ser provisional hasta aprobación; no autocrear registros maestros.
- Nuevas tablas requieren **migraciones Alembic**, índices/constraints y QA de permisos/alcance.

**Salida E2:** propuesta persistida, visible y auditable; V1 sin cambios antes de una aprobación; rol no liberado no puede crear solicitudes V2.

## 7. E3 — Bandeja de validaciones y aplicación controlada

**Objetivo:** autorizar/rechazar cada solicitud con responsables definidos y sin elevar permisos.

**Aprobadores objetivo de negocio:** ADMICORP, Mantenimiento, coordinación de Yuliana y gerentes regionales, **solo según capacidades reales, sucursales asignadas y categoría/tipo de activo aplicable**. No otorgar acceso por nombre de usuario o etiqueta visual. Antes de desarrollar, verificar cómo se modelan roles, áreas, usuario-sucursal y permisos existentes.

Matriz funcional a implementar (no es descripción de permisos ya existentes):

| Perfil/capacidad | Alcance previsto |
|---|---|
| Administración corporativa | Global, si el backend confirma esa capacidad. |
| Mantenimiento autorizado | Sucursales y clases de activos de su competencia. |
| Coordinación de mantenimiento (Yuliana) | Sucursales asignadas y permisos de coordinación efectivos. |
| Regional autorizado | Solo sucursales a cargo y operaciones que su permiso permita. |

Invariantes:
- **Nadie aprueba su propia solicitud.**
- Backend decide rol/capacidad, sucursal, categoría y elegibilidad **en cada lectura y transición**.
- Aprobar/rechazar es transaccional, idempotente y registra actor, motivo y timestamp.
- Propuesta obsoleta ante cambio de inventario → conflicto/revisión, **no sobrescribir** valor canónico nuevo.
- Cambiar cantidades exige ajuste/movimiento auditado consistente, sin stock negativo ni doble aplicación.
- Cambios a propiedades maestras compartidas exigen autorización de ese alcance, no se convierten en “ajustes de sucursal” por conveniencia.
- Rechazar deja el registro oficial intacto y la historia consultable.

**Salida E3:** bandeja por competencia; aprobación y rechazo seguros; QA de autoaprobación, IDOR entre sucursales, concurrencia, doble click y trazabilidad.

## 8. E4 — Levantamiento físico y corte por sucursal

**Objetivo:** auditar de forma trazable el inventario existente, sin confundirlo con su modificación.

**Contrato funcional vigente:** [E4 — Levantamiento físico, validación y conciliación](CONTRATO_FUNCIONAL_E4_LEVANTAMIENTO_FISICO.md). Sus reglas son permanentes y no dependen de la cantidad de sucursales ni de archivos entregados. Alcance inicial: APARATOS.

- Crear ciclo/levantamiento por sucursal, con fecha, responsable, baseline/identidad de referencias y estado.
- Capturar confirmación física por referencia y, cuando corresponda, **cantidad realmente encontrada**; distingue “no revisado”, “coincide”, “diferencia”, “no localizado” y “hallazgo no registrado”.
- Mostrar progreso auténtico calculado sobre el universo definido por el corte, no extrapolado del stock vivo.
- Enlazar hallazgos con solicitudes E2 y decisiones E3 sin perder el registro original ni la evidencia.
- Flujo conceptual `NOT_STARTED → IN_PROGRESS → SUBMITTED → RECONCILIATION → CLOSED`. La implementación final de estados se define al diseñar el esquema.
- Un cierre almacena snapshot histórico, autor/cierre y resumen. Las diferencias pendientes no pueden aparecer falsamente como “conciliadas”: o bloquean el cierre o se documentan **explícitamente como excepciones autorizadas**, conforme a política por aprobar.
- Distinguir corte validado de simple “revisión enviada”. Reapertura/cancelación debe ser auditable si aplica.
- No sustituir el ciclo con una fecha editable o con un botón visual que no guarde evidencia.

**Salida E4:** piloto completo en sucursal autorizada, corte reproducible y auditable; sin cifras ficticias; UI y backend probados.

## 9. E5 — Gate de liberación a GERENTES (ÚLTIMO)

**No iniciar E5 sin que E1–E4 estén ACEPTADOS.** Habilitar gerentes requiere aprobación explícita del responsable del proyecto después de QA.

Verificar antes de activar:
1. Pantallas y proceso de auditoría aprobados con piloto real.
2. Permisos backend explícitos: GERENTE puede leer y proponer solo en su(s) sucursal(es) autorizada(s), pero **no aprobar ni modificar inventario oficial** por esa capacidad.
3. Usuarios sin permiso o de otra sucursal reciben 403, también por URL directa, identificador manipulado, querystring, exportación o request sin menú.
4. Separación de navegación: experiencia gerente centrada en `Mi inventario`; no mostrar herramientas maestras, cargas masivas, entradas/salidas y demás funciones administrativas por herencia del menú.
5. Lectura global restringida; las aprobaciones regionales/coordinación obedecen matriz backend efectiva.
6. QA por rol, sucursal, nivel de autorización y regresión de funciones V1; deploy controlado y confirmación de rollout.

**Estado contractual actual:** `GERENTE_ROLLOUT = OFF / NO AUTORIZADO`. El documento no activa una feature flag ni constituye una garantía de que las rutas V1 estén técnicamente bloqueadas; atender hallazgo de `3.

## 10. Exclusiones de este milestone

- No reescribir el movimiento de almacén de V1 ni obligar a capturar entradas/salidas para cada activo inmóvil.
- No recatalogar PM o consolidar automáticamente sus equipos.
- No dashboards predictivos, precios/compras, mínimos, reposición, depreciación ni activos fijos contables.
- No acceso gerente “solo porque la UI oculta el botón”; los permisos son backend.
- No se autoriza edición masiva del inventario oficial ni eliminación física de históricos.
- No presentar datos ficticios de auditoría en producción.

## 11. Estrategia técnica y garantías transversales

- **Stack:** Angular standalone con componentes separados `.ts` / `.html` / `.css`; lógica en TS, HTML solo estructura y bindings; Flask app factory, blueprints bajo `/api`; PostgreSQL/SQLAlchemy; migraciones Alembic obligatorias para esquema nuevo.
- Mantener V1 operativo y pruebas de regresión; separar los cambios de UX, persistencia, autorización, workflow y rollout por PR.
- La autoridad sobre rol, sucursal, aprobación y actualizaciones de stock reside en backend/DB, nunca en `localStorage` ni en filtros de cliente.
- Consultas de gerentes/lectores nunca deben traer primero datos globales para ocultarlos después.
- Usar identificadores estables, idempotencia y control de concurrencia; todas las transiciones críticas auditan antes/después.
- Despliegue correcto: desarrollo/commit/PR/merge → servidor `git pull` → `docker compose up -d --build` del servicio pertinente → `flask db upgrade heads` cuando aplique, en orden seguro aprobado. No editar manualmente archivos en servidor.
- Aplicar cambios mínimos; si aparece un síntoma nuevo, detenerse a diagnosticar; evitar hacks y `overflow-x: hidden` global para ocultar problemas.
- Respetar la TZ de negocio `America/Tijuana` al mostrar fechas y periodos.

## 12. Pruebas y criterios de aceptación del milestone completo

No aceptar el milestone por un PR verde aislado. Se requiere evidencia conjunta de:
- E1: cifras dashboard/listado consistentes por sucursal, filtros, responsive, estados vacíos, errores, QA visual y compilación.
- E2: creación de propuestas inmutables sin efecto en inventario canónico, cobertura de valores y hallazgos, auditoría.
- E3: aprobación/rechazo autorizados; stock y maestro actualizados exclusivamente cuando corresponda, de forma transaccional; regresión, autoaprobación prohibida, IDOR y concurrencia.
- E4: captura física real, indicadores de avance basados en evidencia, diferencias/corte histórico íntegros y trazables.
- E5: pruebas negativas/positivas reales con GERENTE, GERENTE_REGIONAL y aprobadores según política; sin acceso indebido por menú/ruta/API/exportación, y autorización explícita de apertura.

## 13. Preguntas abiertas a resolver cuando corresponda

Estas decisiones **no se deben inventar ni bloquear E1 si todavía no le afectan**:
- Campos definitivos de corrección: cuáles son maestros compartidos y cuáles deben vivir por sucursal; ¿existe ubicación física específica en el modelo?
- Política y límites de evidencias (fotos, notas, tamaño, retención, privacidad) y si son obligatorias en algún tipo de diferencia.
- Umbral/flujo de aprobación para cantidad versus atributo maestro; si distintas clases de activos necesitan revisores diferentes.
- Quién puede levantar y cerrar, cuántos ciclos simultáneos, cadencia del primer levantamiento y método de corte/baseline.
- Qué hacer con discrepancias aún abiertas al cerrar: bloqueo o excepción documentada y firmada; definir en E4.
- Catálogo de roles/capacidades efectivos para ADMICORP, Yuliana, Mantenimiento y regionales; verificación DB, no inferencia.
- Relación con PM en los equipos que representen el mismo activo.
- Política de sucursales DEMO/global en la nueva pantalla, evitando conteos discrepantes.

## 14. Bitácora viva y siguiente paso

| Entregable | Estado al 2026-10-23 | Evidencia / siguiente acción |
|---|---|---|
| E1 — Dashboard Existencias + listado | **ACEPTADO — QA visual por sucursal** | Último PR E1 **#1086**, merge **`9781cbee`**. QA-E1 Villas del Rey: tarjetas, categorías, familias y listado conciliados. CI verdes reportados. |
| E2 — Solicitudes de corrección | **IMPLEMENTADO TÉCNICAMENTE — QA VISUAL PENDIENTE** | Modelo y Alembic #1104; API de crear/listar/detalle #1105; frontend formulario/seguimiento #1108. Validaciones automáticas en CI aprobadas, sin actualización del maestro/stock; falta desplegar frontend y QA autenticado por sucursal. |
| E3 — Validaciones | **OPERATIVO; QA de ajuste oficial en producción confirmado** | Autorización transaccional, ajuste y auditoría comprobados; PRs #1134, #1168, #1170, #1171 y #1173. |
| E4 — Levantamiento/corte | **PENDIENTE** | [Contrato funcional E4](CONTRATO_FUNCIONAL_E4_LEVANTAMIENTO_FISICO.md) acordado; siguiente: importación y validación sin cambiar stock oficial. |
| E5 — GERENTES | **BLOQUEADO por E1–E4 y autorización explícita** | `GERENTE_ROLLOUT = OFF / NO AUTORIZADO`; no agregar menú, permisos V2 ni habilitar mediante URL directa. |

### Evidencia de aceptación E1 — Villas del Rey (2026-10-23)

- **Fuente:** dos capturas de la pantalla desplegada `/#/inventario/existencias`, aportadas durante el QA operativo de Villas del Rey. Las capturas muestran resumen, composición, filtros y las primeras filas del listado. La verificación de todas las filas se apoya adicionalmente en la implementación de filtrado por sucursal en backend y en los QA automatizados; no se afirma haber inspeccionado individualmente las 156 filas en pantalla.
- **Tarjetas:** 156 referencias registradas; 156 con stock; 0 sin stock. Conciliación: `156 = 156 + 0`.
- **Categorías:** 6 categorías; Cardio 53, Peso Libre 47, Selectorizado 37, Equipo gerencia 9, Equipo recepción 9, Uso común 1. Conciliación: `53 + 47 + 37 + 9 + 9 + 1 = 156`.
- **Familias (solo aparatos):** 137 referencias; Peso Libre 47, Peso Integrado 37, Spinning 26, Caminadora 11, Elíptica 11, Recumbente 3, Escaladora 1, Sin familia 1. Conciliación: `47 + 37 + 26 + 11 + 11 + 3 + 1 + 1 = 137`. Dispositivos/otras categorías: `156 - 137 = 19`, sin contarlos como pendientes de familia.
- **Cardio:** `26 + 11 + 11 + 3 + 1 + 1 = 53` (incluye un aparato sin familia); coincide con la categoría.
- **Listado:** 156 resultados sin filtros adicionales; las filas visibles en la captura tienen sucursal **Villas del rey**. La ruta piloto `GET /api/inventario/v2/existencias?sucursal_id=...` aplica filtro SQL por sucursal autorizada; el componente reconstruye tarjetas/composición/listado sobre esa misma respuesta, limpia filtros al cambiar sucursal e ignora respuestas obsoletas.
- **QA técnico:** PR **#1086** integró filtros de familia/categoría no redundantes; sus pruebas cubren autoselección cuando es inequívoca, filtros cruzados, estado de carga, alcance, errores y paginación. Los CI se reportaron verdes al retomar esta fase. No se ejecutó aquí una nueva prueba automatizada de producción.
- **Observación no bloqueante:** 1 aparato sin familia real en Villas del Rey. Clasificarlo corresponde a la calidad de datos, no a recalcular E1 ni a modificar automáticamente el catálogo.
- **Alcance de la aprobación:** E1 es una vista de **solo lectura** para perfiles ya autorizados. No representa levantamiento físico ni confirma existencias verificadas; no autoriza apertura a GERENTES. El acceso V2 tiene guard backend propio desde #1103; la lectura legacy V1 conserva su política y su deuda de hardening descrita en §3. Ninguno de esos cambios autoriza E5.

### Estado de partida que se conserva

- Inventarios V1 QA: catálogo, entradas, salidas, existencias, anulaciones y exportación existentes, sin reimplementarlos.
- Reportes/dashboard V1: PRs **#1059**, **#1060**, **#1061**, layout **#1064**, corrección de scroll **#1066**. No confundir Reportes con E1 de Existencias.
- E1 de Existencias: dashboard, categorías oficiales, familias, filtros inteligentes y listado conservado; último PR **#1086**, commit merge **`9781cbee`**.

### Registro de implementación E2 (2026-10-23)

- **Seguridad piloto:** PR **#1103**, endpoint `/api/inventario/v2/existencias` protegido por rol y sucursal, sin alterar V1. El gate `GERENTE_ROLLOUT = OFF` permanece vigente.
- **Persistencia aislada:** PR **#1104**, modelo `InventarioSolicitudCorreccionORM` y migración Alembic `v2e2a7c92623`. Se verificó PostgreSQL 16 temporal, constraints de sucursal e idempotencia, rollback protegido; ninguna modificación a maestro ni stock. El responsable confirmó posteriormente que el despliegue del esquema levantó correctamente.
- **API autenticada:** PR **#1105**, `POST/GET /api/inventario/solicitudes` y `GET /api/inventario/solicitudes/<id>`, guard por rol DB y sucursal, cuatro tipos, 409 por stale baseline/UUID conflicto, paginación/filtros SQL; **13 pruebas** de PostgreSQL temporal y regresiones aprobadas. El responsable confirmó que el backend actualizado levantó bien.
- **Interfaz:** PR **#1108**, acciones por referencia, hallazgo no registrado, formulario aislado, seguimiento con filtros, mensajes de éxito/error, estados PENDING, reintento idempotente y prohibición de abrir modal para GERENTE; QA y type-check Angular, build de producción y regresión QA-13 en CI aprobados. **Aún no hay confirmación de despliegue frontend ni QA visual real.**
- **No incluido en E2:** aprobación/rechazo, modificación de códigos oficiales, movimientos, ajustes de existencias, revisión transaccional de E3, levantamiento/corte E4, apertura GERENTE E5. No confundir estado `PENDING` con corrección aplicada.

### Próximo control para aceptar E2

1. Desplegar **frontend** desde `main` por el flujo Docker establecido. No ejecutar migración adicional para el PR #1108.
2. En `/#/inventario/existencias` hacer QA visual por sucursal piloto (por ejemplo, Villas del Rey): formulario por fila y hallazgo provisional, obligatorio motivo, stock/maestro oficiales en solo lectura, guardado `PENDING` y filtro de seguimiento, sin modificar KPI/listado E1.
3. Verificar por rol y sucursal real (API directa inclusive) que GERENTE/GERENTE_REGIONAL no puedan utilizar E2; comprobar SR/AUX y rol global. No cambiar permisos hasta la aprobación del gate correspondiente.
4. Comparar registros oficiales antes/después del piloto: `inventario_general`, `inventario_sucursal` y movimientos sin cambios. Solo entonces registrar **E2 ACEPTADO**. E3 continúa bloqueado hasta ese control.

**Gobierno de cambios:** un PR lógico a la vez; explicar archivo, método, objetivo y motivo antes de tocar código. No iniciar E5 sin aprobación explícita tras E1–E4.
