# Contrato global — Tickets V2

**Estado:** BASE ARQUITECTÓNICA / PENDIENTE DE INVESTIGACIÓN  
**Fecha:** 2026-10-02  
**Alcance:** estrategia de sustitución progresiva de Tickets V1 por Tickets V2 sin interrumpir la operación actual.  
**Repositorio inspeccionado al redactar:** `main` en `c8c7852f7237531588c40a3d42fa28b07e276994`.

---

## Cómo usar este documento

Este contrato conserva la dirección arquitectónica acordada para Tickets V2.

No autoriza por sí solo la implementación de tablas, workers, endpoints, eventos ni migraciones descritas aquí. Antes de escribir código deberá completarse la investigación técnica definida en **M0 — Investigación y contrato ejecutable** y actualizar este documento o generar contratos de fase con los hallazgos reales del repositorio.

Reglas obligatorias:

- Tickets V1 continúa siendo la autoridad operativa durante la etapa shadow.
- Tickets V2 se construye en paralelo y se alimenta de lo que sucede realmente en V1.
- No habrá edición humana independiente simultánea en V1 y V2 sobre el mismo caso.
- El cambio de autoridad canónica V1 -> V2 será explícito, medible y reversible durante una ventana definida.
- No se modificará V1 para “parecerse” a V2 si el cambio aumenta riesgo operativo.
- V2 no deberá copiar ciegamente la semántica de las columnas de V1.
- Todo bridge creado mientras V2 no esté listo deberá diseñarse para integrarse o proyectarse a V2 sin reconstrucción destructiva.
- Backend será la autoridad de permisos, workflow, auditoría, canonicidad e idempotencia.
- No inventar respuestas para puntos marcados como pendientes de investigación.

---

# 1. Problema que resuelve Tickets V2

Tickets fue el origen funcional de Suite Ultra y creció alrededor de una lógica principalmente departamental.

La investigación inicial de V1 muestra que hoy distintas responsabilidades se encuentran acopladas alrededor de la misma entidad `Ticket` y de campos como `departamento_id` y `estado`.

Entre otras cosas, en V1 el departamento influye en:

- visibilidad;
- destinatarios de correo;
- permisos de actualización;
- clasificación;
- Planner de Mantenimiento;
- reportes;
- acciones disponibles en frontend.

El estado principal también mezcla semánticas de operación y cierre:

```text
abierto
en progreso
por_validar
finalizado
```

`por_validar` representa actualmente el flujo de validación de cierre y ya alimenta alertas, métricas y reportes.

El objetivo de V2 no es reescribir V1 con nombres nuevos.

El objetivo es crear una base donde un caso operativo pueda responder independientemente:

1. qué tipo de proceso es;
2. quién lo solicitó;
3. quién participa;
4. quién es responsable actual;
5. qué etapa del workflow está activa;
6. qué eventos ocurrieron;
7. qué documentos pertenecen al expediente;
8. qué permisos aplican;
9. cuál es su estado global;
10. cuál fue su origen.

---

# 2. Estrategia de migración

La migración será paralela y progresiva.

Principio rector:

> **V1 seguirá siendo utilizado normalmente mientras V2 se alimenta de la operación real de V1. Solo cuando V2 haya demostrado paridad suficiente, consistencia y operación estable se transferirá la autoridad canónica.**

Modelo conceptual inicial:

```text
USUARIOS
   |
   v
TICKETS V1
   |
   | cambios reales de producción
   v
CAPA DE CAPTURA / OUTBOX
   |
   v
ADAPTER / PROJECTOR V1 -> V2
   |
   v
TICKETS V2
   |
   +-- validación shadow
   +-- reconciliación
   +-- UI V2 progresiva
```

Durante esta etapa:

```text
V1 READ   = habilitado
V1 WRITE  = habilitado
V2 READ   = inicialmente restringido
V2 WRITE  = únicamente projector / procesos nativos explícitos
```

La autoridad de escritura sobre casos originados en V1 permanecerá en V1 hasta el cutover.

---

# 3. Principio de autoridad única

Nunca deberá existir un periodo normal donde un mismo caso pueda modificarse manualmente en V1 y V2 de forma independiente.

Antes del cutover:

```text
Autoridad canónica de escritura = V1
V2 = shadow / proyección
```

Después del cutover:

```text
Autoridad canónica de escritura = V2
V1 = readonly / compatibilidad temporal si aplica
```

Si se implementa una réplica inversa V2 -> V1 durante la ventana de rollback, esa réplica será técnica y controlada; V1 no volverá a ser una segunda fuente humana de verdad.

---

# 4. V2 deberá modelar procesos, no departamentos

V1 responde principalmente:

> ¿A qué departamento pertenece este ticket?

V2 deberá responder:

> ¿Qué proceso representa este caso, quién participa y qué etapa está activa?

Un caso V2 podrá tener participantes distintos:

```text
REQUESTER
REVIEWER
OWNER
ASSIGNEE
OBSERVER
```

y dichos participantes podrán resolverse mediante:

- usuario;
- rol;
- departamento;
- sucursal;
- región;
- reglas futuras de routing.

El departamento deja de ser simultáneamente tipo de caso, propietario, bandeja, permiso y destino de notificación.

La existencia exacta de una tabla `ticket_v2_participants` o estructura equivalente queda **pendiente de M0**.

---

# 5. Separación entre estado global y etapa del workflow

V2 deberá evitar que un único enum acumule todas las semánticas del negocio.

Conceptualmente deberá existir:

## 5.1 Estado global

Conjunto pequeño y estable, por ejemplo:

```text
OPEN
ACTIVE
COMPLETED
CANCELLED
```

Los valores definitivos quedan pendientes de investigación.

## 5.2 Workflow / etapa

Describe el punto real del proceso.

Ejemplo conceptual de requisición:

```text
PENDING_SPORTS_REVIEW
APPROVED
SOURCING
ORDERED
DELIVERED
```

Ejemplo conceptual de incidente:

```text
REPORTED
TRIAGED
IN_PROGRESS
WAITING_REQUESTER
RESOLVED
CONFIRMED
```

Dos procesos podrán tener workflows diferentes sin expandir indefinidamente el estado global de Ticket.

---

# 6. Identidad del caso V2

V2 deberá usar una identidad propia.

Conceptualmente:

```text
ticket_v2
- id interno
- public_id / folio
- type
- global_status
- workflow_key
- created_by
- source_branch_id
- created_at
- updated_at
```

Los nombres y columnas no quedan aprobados hasta M0.

El folio público no deberá depender necesariamente del PK.

V2 deberá poder conservar una referencia al origen legacy:

```text
source_system = TICKETS_V1
legacy_ticket_id = 5832
```

La relación de origen deberá ser idempotente y evitar duplicar un ticket legacy durante backfill o reproyección.

Una restricción equivalente a:

```text
UNIQUE(source_system, legacy_ticket_id)
```

deberá evaluarse durante M0.

---

# 7. Event log como capacidad de primera clase

V2 deberá conservar una secuencia auditable de eventos.

No dependerá de un JSON mutable similar a `historial_fechas` como única fuente de auditoría.

Conceptualmente:

```text
ticket_v2_events
- event_id
- ticket_id
- event_type
- actor
- occurred_at
- metadata
- schema_version
```

Ejemplos:

```text
CREATED
WORKFLOW_STARTED
STAGE_CHANGED
OWNER_CHANGED
ASSIGNEE_CHANGED
COMMITMENT_SET
COMMITMENT_CHANGED
APPROVED
REJECTED
ATTACHMENT_ADDED
COMPLETED
REOPENED
```

No todos estos eventos quedan aprobados como catálogo final.

El event log deberá permitir:

- auditoría;
- timeline;
- debugging;
- SLA;
- reconciliación;
- futuras notificaciones;
- reconstrucción de contexto.

Debe investigarse si V2 será event-sourced completamente o si mantendrá estado materializado + eventos append-only. La preferencia inicial es **estado materializado + event log**, no event sourcing puro, salvo evidencia en M0 que justifique otra cosa.

---

# 8. Archivos y expediente

V2 deberá soportar múltiples archivos por caso.

Los adjuntos V1 actuales tienen semántica limitada y V1 permite en su servicio actual un máximo funcional de un adjunto de imagen por ticket.

V2 deberá contemplar expediente multiartefacto.

Ejemplos conceptuales:

```text
IMAGE
EVIDENCE
QUOTE
INVOICE
PURCHASE_ORDER
DOCUMENT
OTHER
```

La infraestructura física de almacenamiento deberá investigarse antes de duplicarla.

V2 deberá preferir reutilizar almacenamiento seguro existente si puede desacoplarse correctamente de `ticket_attachments`.

La política de retención deberá definirse por tipo de expediente y no heredarse accidentalmente de la regla V1 de eliminación física posterior al cierre.

---

# 9. Captura de cambios V1

La sincronización V1 -> V2 no deberá depender únicamente de llamadas best-effort después del commit.

Patrón preferido a investigar:

**Transactional Outbox.**

Conceptualmente:

```text
BEGIN

cambio V1

INSERT ticket_v1_outbox (...)

COMMIT
```

Luego:

```text
outbox
  -> worker
  -> adapter
  -> projector V2
```

La finalidad es evitar el hueco:

```text
V1 commit OK
proceso cae
V2 nunca recibe el cambio
```

La implementación final deberá estudiar todos los caminos reales de escritura de Tickets V1 antes de afirmar que un outbox captura el 100% de cambios.

No se autoriza agregar outbox hasta concluir esa investigación.

---

# 10. Eventos V1 y traducción semántica

V2 no deberá replicar solamente snapshots de columnas.

La capa adapter deberá traducir hechos V1 a conceptos V2.

Ejemplo:

```text
V1:
estado: abierto -> en progreso
fecha_solucion: 2026-10-08

V2:
global_status = ACTIVE
workflow_stage = IN_PROGRESS
commitment_due_at = 2026-10-08
```

La traducción deberá ser explícita, versionada y testeable.

Eventos conceptuales que M0 deberá localizar en V1:

- creación;
- inicio/en progreso;
- asignación de compromiso;
- reprogramación;
- solicitud de cierre;
- aceptación de cierre;
- rechazo de cierre;
- cierre administrativo;
- adjunto agregado;
- cambios de clasificación;
- cambios de diagnóstico/refacción;
- cambios de sucursal destino;
- cualquier mutación hoy posible fuera de `ticket_routes.py`.

La lista definitiva depende de investigación de rutas, servicios, scripts y writes directos.

---

# 11. Idempotencia

Todo pipeline de V1 -> V2 deberá ser idempotente.

Procesar dos o más veces un mismo evento no deberá:

- duplicar tickets;
- duplicar eventos V2;
- duplicar adjuntos;
- duplicar notificaciones;
- avanzar etapas varias veces.

Cada unidad de captura deberá tener una identidad estable.

Conceptualmente:

```text
event_id
source_system
aggregate_id
event_type
occurred_at
schema_version
```

V2 deberá registrar qué eventos de origen ya fueron procesados o resolver idempotencia mediante una estrategia equivalente comprobable.

Retries serán comportamiento normal, no caso excepcional.

---

# 12. Snapshot inicial / backfill

V2 no puede comenzar únicamente con eventos futuros.

Antes de shadow productivo deberá existir un backfill inicial.

Conceptualmente:

```text
1. iniciar captura durable de cambios
2. registrar watermark
3. ejecutar snapshot/backfill histórico
4. reprocesar cambios posteriores al watermark
5. reconciliar
6. declarar shadow consistente
```

El orden exacto deberá diseñarse para evitar una ventana de pérdida.

No se deberá requerir detener Suite salvo que M0 demuestre que es inevitable y el costo esté justificado.

El backfill deberá ser:

- reanudable;
- idempotente;
- auditable;
- medible;
- capaz de reportar registros no traducibles.

Los casos que no puedan clasificarse semánticamente deberán conservarse como legacy genérico en vez de descartarse.

Ejemplo conceptual:

```text
type = LEGACY_GENERIC
```

La etiqueta final queda pendiente.

---

# 13. Clasificación de tickets legacy

La migración deberá investigar reglas determinísticas para traducir V1.

Ejemplos posibles:

```text
Mantenimiento + Aparatos
-> MAINTENANCE_EQUIPMENT_INCIDENT

Mantenimiento + Edificio
-> MAINTENANCE_BUILDING_INCIDENT

Sistemas + Dispositivos
-> IT_DEVICE_INCIDENT
```

Estas reglas son ejemplos, no decisiones aprobadas.

M0 deberá:

1. inventariar clasificaciones reales activas e históricas;
2. medir volumen por árbol/departamento;
3. identificar inconsistencias;
4. proponer mapping;
5. cuantificar porcentaje traducible automáticamente;
6. definir fallback.

No se hardcodeará un mapping incompleto solo para alcanzar 100% nominal.

---

# 14. Shadow validation

V2 deberá poder demostrar que representa correctamente la operación de V1.

Se requiere una reconciliación automática.

Métricas mínimas a estudiar:

```text
total casos
casos activos
casos finalizados
por sucursal
por departamento/tipo traducido
por estado
compromisos
fechas clave
adjuntos
discrepancias
eventos pendientes de proyectar
edad máxima del lag
```

Ejemplo de reporte:

```text
V1 activos                 418
V2 equivalentes            418
discrepancias críticas       0
outbox pendiente             0
lag máximo                  12s
```

La reconciliación deberá distinguir:

- diferencia esperada por transformación semántica;
- diferencia temporal por lag;
- error real;
- registro legacy no traducible.

---

# 15. Fases de exposición

## Etapa A — V2 invisible

```text
V1 READ   ON
V1 WRITE  ON
V2 READ   restringido
V2 WRITE  projector
```

Objetivo: construir y reconciliar.

## Etapa B — Shadow UI

Admins/desarrollo podrán consultar V2.

No se realizarán acciones humanas sobre casos legacy desde V2.

Objetivo: comparar UX y semántica con producción real.

## Etapa C — Lecturas V2 controladas

Determinados usuarios o feature flags podrán usar V2 como vista de consulta.

Las escrituras legacy continúan en V1.

Objetivo: demostrar que bandejas, filtros, permisos y datos V2 son operativamente confiables.

## Etapa D — Procesos nativos V2

Procesos nuevos podrán nacer directamente en V2 sin existir en V1.

Esto deberá autorizarse por contrato específico.

Un proceso nativo V2 no deberá escribirse retrospectivamente en V1 salvo que exista una necesidad de compatibilidad explícita.

## Etapa E — Cutover

Cuando se cumplan los criterios:

```text
V1 WRITE  OFF
V2 WRITE  ON
V2 READ   ON
V1 READ   readonly / oculto
```

La autoridad canónica pasa a V2.

---

# 16. Rollback y réplica inversa

Antes del cutover deberá definirse un plan de rollback.

Podrá evaluarse una ventana corta de compatibilidad:

```text
V2 canónico
   |
   +--> proyección técnica a V1
```

La réplica inversa no es requisito obligatorio todavía.

M0/Milestone de cutover deberá determinar:

- si aporta valor real;
- qué campos V1 podrían representar V2 sin pérdida;
- cuánto tiempo se mantendría;
- cómo evitar loops V1 -> V2 -> V1;
- qué evento define el punto de no retorno.

Si la semántica V2 supera lo que V1 puede representar, se preferirá backup + rollback operacional claro en vez de una falsa réplica bidireccional.

---

# 17. V1 durante la transición

Tickets V1 permanecerá estable.

Principio recomendado:

> V1 entra progresivamente en mantenimiento funcional. Bugs y operación actual se corrigen; capacidades nuevas deben evaluarse primero como módulos bridge o procesos V2.

Esto no significa congelar V1 inmediatamente si existe una urgencia de negocio.

Mientras V2 está pendiente, se podrán crear módulos temporales/modulares que:

- resuelvan una necesidad inmediata;
- no contaminen la entidad `tickets` innecesariamente;
- usen identidades Suite existentes;
- conserven eventos y auditoría;
- tengan mapping claro hacia un tipo/workflow V2;
- puedan migrarse 1:1 o mediante un adapter simple.

El contrato específico de cada bridge deberá documentar ese mapping.

---

# 18. Requisiciones como primer bridge / futuro proceso V2

Existe una necesidad urgente de registrar requisiciones/compras, inicialmente para equipo de gimnasio.

Su implementación inmediata se definirá en un contrato independiente.

Este contrato global únicamente fija la restricción de compatibilidad:

> **El módulo urgente de Requisiciones deberá poder integrarse a Tickets V2 como un tipo de caso nativo sin depender de la tabla legacy `tickets` ni de semánticas exclusivas de V1.**

El futuro mapping esperado, solo conceptual, es:

```text
purchase_requisition
    ->
Ticket V2
type = PURCHASE_REQUISITION
workflow = ...
events = ...
attachments = ...
participants = ...
```

Los nombres y estructura definitivos se resolverán en el contrato de Requisiciones y M0 de Tickets V2.

---

# 19. Capacidades V2 objetivo

Tickets V2 deberá eventualmente soportar, mediante un núcleo común:

- incidentes;
- solicitudes;
- requisiciones;
- autorizaciones;
- servicios internos;
- tareas operativas ligadas a un caso.

No todos los tipos deben implementarse desde el inicio.

V2 no será un BPM genérico ilimitado.

Se priorizarán workflows reales de Ultra y una abstracción suficiente para no reconstruir el motor con cada nuevo caso.

---

# 20. Permisos y participantes

Los permisos V2 no deberán inferirse únicamente del departamento.

Se deberá investigar una política basada en combinación de:

- rol;
- usuario;
- participación en caso;
- sucursal;
- región;
- permisos globales;
- etapa del workflow.

Ejemplo conceptual:

```text
puede ver
puede comentar
puede ejecutar transición
puede asignar
puede aprobar
puede cerrar
puede administrar
```

La UI nunca será la autoridad.

Toda transición deberá validarse en backend.

Participar en un caso no deberá otorgar automáticamente permisos superiores.

---

# 21. Routing

V2 deberá distinguir:

- tipo de caso;
- workflow;
- actor solicitante;
- reviewer;
- owner;
- assignee;
- observers.

Ejemplo:

```text
PURCHASE_REQUISITION / GYM_EQUIPMENT

REQUESTER
  sucursal

REVIEWER
  GERENCIA DEPORTIVA

OWNER después de aprobación
  MANTENIMIENTO
```

La configuración final de routing queda pendiente.

No se deberá codificar un árbol de `if role == ...` creciente si puede modelarse mediante una política explícita.

Tampoco se construirá un motor genérico de reglas antes de demostrar necesidad real.

---

# 22. Notificaciones

V2 deberá generar notificaciones desde eventos/acciones de negocio, no inferir todas las comunicaciones exclusivamente del departamento del caso.

Ejemplos:

```text
CASE_CREATED
REVIEW_REQUIRED
APPROVED
REJECTED
OWNER_CHANGED
ASSIGNED
COMMENT_MENTIONED
COMMITMENT_DUE
COMPLETED
```

Los canales podrán incluir:

- in-app;
- email;
- futuros canales.

M0 deberá investigar la infraestructura de notificaciones actual y definir qué puede reutilizarse.

Una notificación fallida no deberá, por regla general, revertir una transición de negocio ya persistida.

---

# 23. Conversación / mini chat

La idea de conversación anclada a cada ticket queda preservada, pero fuera del alcance inicial de V2.

Dirección futura:

- mensajes humanos separados de eventos de sistema;
- conversación ligada al caso;
- adjuntos;
- mentions;
- unread;
- participantes;
- posible evolución posterior a canales internos.

No se implementará en el núcleo inicial únicamente porque esté descrita aquí.

M0 deberá revisar comentarios/historial actuales antes de diseñarla.

---

# 24. Observabilidad

El pipeline V1 -> V2 deberá ser observable.

Como mínimo deberá poder conocerse:

- último evento V1 capturado;
- último evento V2 aplicado;
- backlog;
- retries;
- eventos fallidos;
- dead-letter o equivalente;
- lag;
- duración de backfill;
- discrepancias de reconciliación;
- versión del projector.

No deberá existir un shadow silencioso donde “parece estar sincronizado” sin evidencia.

---

# 25. Versionado

Los eventos de integración deberán tener versión de esquema.

Ejemplo conceptual:

```text
event_type = TICKET_STARTED
schema_version = 1
```

Un cambio futuro en payload no deberá romper la reproyección histórica.

El adapter/proyector también deberá tener una estrategia de versionado o migración de reglas.

---

# 26. Reproyección

Debe investigarse la capacidad de reconstruir V2 desde:

- snapshot V1;
- eventos outbox;
- ambos.

La reproyección deberá ser una herramienta de recuperación y validación, no el mecanismo normal de operación.

Si un cambio de mapping requiere reprocesar historia, deberá existir un proceso controlado y medible.

---

# 27. M0 — Investigación obligatoria antes de implementar V2

M0 debe producir un documento técnico actualizado con evidencia de repositorio y, cuando sea necesario, consultas a base de datos.

## 27.1 Inventario de escrituras V1

Localizar todas las vías que mutan `tickets` y entidades asociadas:

- rutas;
- servicios;
- workers;
- scripts;
- imports;
- tareas programadas;
- módulos de Mantenimiento;
- inventario;
- cierres;
- adjuntos;
- posibles SQL directos.

Resultado requerido:

tabla `acción -> código -> transacción -> side effects -> evento candidato`.

## 27.2 Estado y workflow reales

Inventariar:

- estados existentes;
- `estado_cierre`;
- restos de `requiere_aprobacion`;
- historial;
- fechas;
- compromisos;
- cierres especiales;
- transiciones permitidas por rol.

Distinguir flujo vivo de código muerto.

## 27.3 Clasificaciones

Medir:

- departamentos;
- árboles de clasificación;
- nodos activos/inactivos;
- volumen histórico por rama;
- tickets sin clasificación;
- tickets con inventario;
- inconsistencias.

Proponer mapping V1 -> tipos V2.

## 27.4 Permisos

Documentar:

- `filtrar_tickets_por_usuario`;
- guards globales;
- roles;
- sucursales;
- regiones;
- permisos de Mantenimiento;
- administración;
- excepciones por username.

Proponer política V2 sin perder alcance actual.

## 27.5 Notificaciones

Inventariar:

- destinatarios;
- eventos;
- emails;
- fallbacks;
- async/sync;
- fallos;
- plantillas.

Definir frontera entre evento de negocio y entrega de notificación.

## 27.6 Adjuntos

Investigar:

- almacenamiento;
- permisos;
- retención;
- worker cleanup;
- límites;
- dependencia de `ticket_id`;
- capacidad de extraer infraestructura compartida.

## 27.7 Planner y reportes

Inventariar consumidores downstream de `tickets`:

- Maintenance Planner;
- reportes;
- inventario;
- KPIs;
- exports;
- dashboards;
- validaciones.

Clasificarlos:

```text
migrar a V2
adaptar
mantener legacy
retirar
```

## 27.8 Frontend

Inventariar:

- Crear Ticket;
- Ver Tickets;
- filtros;
- modales;
- acciones;
- guards;
- menús;
- rutas;
- componentes especializados.

Definir qué UI puede evolucionar a V2 y qué conviene reemplazar.

## 27.9 Base de datos

Medir:

- conteo histórico;
- crecimiento;
- índices;
- tiempos de consulta;
- tamaño de JSON;
- cantidad de adjuntos;
- distribución por año;
- anomalías.

Dimensionar backfill y shadow.

## 27.10 Infraestructura de workers

Investigar si existe una infraestructura de jobs/schedulers suficientemente robusta para:

- outbox projector;
- retries;
- reconciliación;
- backfill.

No crear un nuevo runtime si uno existente satisface las garantías necesarias.

---

# 28. Entregables de M0

M0 deberá cerrar al menos:

1. diagrama real de V1;
2. matriz de mutaciones;
3. matriz de consumidores;
4. mapping preliminar V1 -> V2;
5. diseño confirmado de captura durable;
6. estrategia de snapshot/backfill;
7. modelo V2 mínimo confirmado;
8. política de permisos;
9. plan de reconciliación;
10. feature flags;
11. estrategia de cutover;
12. estrategia de rollback;
13. estimación de deuda V1 que no se migrará;
14. lista de decisiones pendientes de negocio.

Solo después deberá aprobarse M1.

---

# 29. Roadmap contractual preliminar

Este orden es orientativo y podrá cambiar tras M0.

## M0 — Investigación y contrato ejecutable

Sin cambios funcionales productivos.

## M1 — Boundary V2

- namespace;
- modelos mínimos;
- feature flags;
- health/diagnostics;
- ninguna UI de producción.

## M2 — Captura durable V1

- outbox o mecanismo confirmado;
- eventos versionados;
- sin afectar UX V1.

## M3 — Snapshot + projector

- backfill;
- adapter;
- proyección V2;
- idempotencia.

## M4 — Reconciliation

- métricas;
- diferencias;
- lag;
- alertas técnicas.

## M5 — Shadow UI

- acceso restringido;
- lectura;
- comparación.

## M6 — Lecturas V2 controladas

- feature flag;
- cohorts de usuarios;
- sin writes legacy desde V2.

## M7 — Procesos nativos V2

- contratos específicos;
- Requisiciones podrá ser uno de ellos o llegar previamente como bridge migrable.

## M8 — Paridad operativa prioritaria

- incorporar workflows legacy seleccionados por valor/riesgo.

## M9 — Cutover

- V1 readonly;
- V2 canónico;
- rollback documentado.

## M10 — Retiro V1

- ocultar navegación;
- retirar runtime innecesario;
- conservar histórico/acceso si negocio lo requiere.

---

# 30. Criterios preliminares para cutover

No se autorizará por “ya se ve bien”.

Deberán existir métricas objetivas.

Pendiente definir umbrales en M0/M9, pero deberán contemplar:

- cero discrepancias críticas durante una ventana acordada;
- backlog estable en cero o dentro de SLA;
- lag dentro de SLA;
- ningún evento perdido conocido;
- permisos validados por perfiles principales;
- bandejas V2 verificadas;
- writes V2 probados;
- planes de rollback probados;
- backups;
- observabilidad;
- documentación de operación;
- aprobación funcional.

---

# 31. Hallazgos iniciales de V1 que motivan la separación

La investigación inicial realizada antes de este contrato detectó:

1. `Ticket.estado` es un enum limitado a `abierto`, `en progreso`, `por_validar`, `finalizado`.
2. `por_validar` tiene semántica concreta de cierre y alimenta alertas/reportes.
3. Existen campos antiguos de preaprobación RRHH cuyos endpoints activos fueron retirados.
4. `departamento_id = 1` activa semántica especial de Mantenimiento en Planner, reportes y guards.
5. Las notificaciones actuales derivan destinatarios en gran medida del departamento.
6. La visibilidad principal usa `filtrar_tickets_por_usuario`.
7. El servicio actual de adjuntos V1 limita funcionalmente a un adjunto de imagen por ticket y aplica una política de retención posterior al cierre.
8. Existen tablas/endpoints de formularios configurables, pero la creación refactor actual usa principalmente clasificación jerárquica y subformularios específicos.
9. `asignado_a` existe, pero no representa por sí solo un workflow moderno de participantes.
10. Existen consumidores de tickets fuera de la pantalla principal, por lo que un reemplazo directo sería de alto riesgo.

Estos hallazgos justifican el enfoque shadow en lugar de un refactor destructivo.

M0 deberá volver a verificar cada punto contra el HEAD vigente.

---

# 32. No objetivos iniciales

Tickets V2 no incluirá automáticamente:

- Slack interno completo;
- presencia en tiempo real;
- chat;
- motor BPM de propósito general;
- diseñador visual de workflows;
- integración contable;
- compras completas;
- facturación;
- proveedores;
- órdenes de compra;
- migración inmediata de todo histórico a semántica perfecta;
- retiro inmediato de V1.

Cada capacidad deberá justificar su entrada mediante un caso real.

---

# 33. Invariantes

Estas reglas se consideran parte central del contrato:

### I1
Durante shadow, V1 es la autoridad de escritura para tickets legacy.

### I2
No habrá edición humana dual del mismo caso.

### I3
V2 no copiará semántica legacy por conveniencia cuando pueda modelarla correctamente.

### I4
La captura de cambios deberá ser durable e idempotente.

### I5
La operación V1 no se detendrá para desarrollar V2 salvo intervención aprobada.

### I6
Toda discrepancia V1/V2 deberá ser observable.

### I7
El cutover será explícito; nunca ocurrirá accidentalmente por feature drift.

### I8
Los procesos nuevos podrán ser nativos V2 mediante contrato específico.

### I9
Los módulos bridge creados antes de V2 deberán declarar cómo migran a V2.

### I10
El histórico legacy no se descartará porque no pueda clasificarse perfectamente.

### I11
Backend será autoridad de permisos y transiciones.

### I12
Eventos de sistema y mensajes humanos serán conceptos distintos si se implementa conversación.

---

# 34. Decisiones pendientes

Quedan deliberadamente abiertas hasta M0:

- nombres definitivos de tablas;
- esquema definitivo del Ticket Core V2;
- catálogo de estados globales;
- catálogo de eventos;
- si se implementará outbox en PostgreSQL o mecanismo equivalente;
- worker/runtime del projector;
- granularidad de eventos V1;
- estrategia final de backfill;
- retención de eventos;
- estrategia de reproyección;
- folio público;
- tipos V2 iniciales;
- mapping histórico;
- participantes;
- routing;
- permisos;
- almacenamiento de adjuntos;
- política de retención;
- forma de shadow UI;
- mecanismo de feature flags;
- SLA de sincronización;
- umbral de cutover;
- réplica inversa V2 -> V1;
- duración readonly de V1;
- estrategia de retiro físico de V1.

No deberán resolverse por suposición durante implementación.

---

# 35. Definición de éxito

Tickets V2 se considerará exitoso cuando Suite pueda realizar la transición:

```text
HOY
Usuarios -> V1 -> operación

TRANSICIÓN
Usuarios -> V1
             |
             +-> V2 shadow

MADUREZ
Usuarios -> V2 lectura
Escrituras -> V1
             |
             +-> V2

CUTOVER
Usuarios -> V2 canónico
V1 -> readonly

FINAL
Usuarios -> V2
V1 -> histórico/retirado
```

sin pérdida de información, sin doble autoridad y con evidencia de reconciliación.

El valor principal de V2 no será únicamente una UI nueva.

Será convertir Tickets en una plataforma de casos y workflows de Suite Ultra capaz de evolucionar sin repetir el acoplamiento histórico de V1.
