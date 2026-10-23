# Contrato global — Inventarios V2: Auditoría y Validación por Sucursal

**Proyecto:** Suite Ultra (Angular + Flask + PostgreSQL).
**Fecha de acuerdo:** 2026-10-23.
**Versión del contrato:** 1.0.
**Estado:** ALCANCE FUNCIONAL ACORDADO / IMPLEMENTACIÓN V2 PENDIENTE.
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

**Hallazgo de seguridad real, no resuelto por este documento:** `_resolve_inventory_read_sucursal_ids` actualmente contempla lectura acotada para roles no globales mediante `sucursal_id`. Como la ruta Angular está protegida solo por `AuthGuard`, **un GERENTE podría alcanzar la lectura mediante URL directa aunque no tenga menú**, sujeto al alcance que resuelva el backend. No afirmar que GERENTE ya está bloqueado; hay que verificarlo con QA de rol real y diseñar el gate adecuado. **No ampliar permisos durante E1–E4.** Antes de publicar endpoints/datos V2 o afirmar aislamiento de gerentes, cerrar el hardening necesario en un PR de seguridad separado, conservando las capacidades existentes autorizadas. El gate final exige bloqueo backend+frontend probado para rol no liberado y alcance correcto al habilitarlo.

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

| Entregable | Estado al crear contrato (2026-10-23) | Evidencia |
|---|---|---|
| E1 — Dashboard Existencias + listado | **PENDIENTE** | Vista V1 existente inspeccionada; sin PR V2. |
| E2 — Solicitudes | **BLOQUEADO por E1** | No implementado. |
| E3 — Validaciones | **BLOQUEADO por E2** | No implementado. |
| E4 — Levantamiento/corte | **BLOQUEADO por E3** | No implementado. |
| E5 — GERENTES | **BLOQUEADO por E1–E4 y autorización explícita** | Rollout V2 no autorizado. |

### Estado de partida, que NO debe reimplementarse

- Inventarios V1 QA: catálogo, entradas, salidas, existencias, anulaciones y exportación existentes.
- Reportes/dashboard V1 ya desarrollados; referencias PRs **#1059**, **#1060**, **#1061** y ajuste de layout **#1064**. La corrección global de scroll del layout fue PR **#1066**. **Estos PR no aceptan E1 de Inventarios V2**.
- `/#/inventario/existencias` aún es tabla básica; la captura gerencial propuesta debe construirse allí sin eliminar lista.
- Esta fase **NO ha sido desplegada ni habilitada** por crear el contrato.

### Primer trabajo permitido al reanudar

**E1 — Renovación de Existencias, en un PR únicamente frontend y de lectura.** Primero planificar cambios concretos para `frontend/src/app/inventario/existencias/existencias.component.ts`, `.html` y `.css`; evaluar si `inventario.service.ts` debe aceptar `sucursal_id` y asegurar coherencia de datos por sucursal. No introducir solicitudes falsas, tablas de auditoría, cambios de roles ni menú gerente. **No abrir a GERENTE.**

**Instrucción útil para una nueva conversación:** “Lee `docs/contratos/inventarios_v2/CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md` en main, revisa el estado real del repositorio y continúa solo el primer entregable pendiente respetando el gate de no habilitar GERENTES”.

**Gobierno de cambios:** actualizar esta sección al aceptar cada etapa y enmendar el contrato mediante PR si cambia una decisión funcional; no desplazar reglas de manera tácita ni confundir un objetivo contractual con una función ya existente.
