# Contrato técnico — Control de asignación de rutinas

## Bloque 1: modelo de datos, estados e idempotencia

**Versión:** 0.1
**Estado:** Propuesta para validación
**Dependencia:** Contrato funcional v1.0
**Alcance de este bloque:** Persistencia, identidad, estados, auditoría, ejecuciones e idempotencia.
**Fuera de este bloque:** Endpoints, frontend, worker, providers y despliegue.

---

## 1. Principios técnicos

1. El control operativo vivirá en PostgreSQL.
2. Trainingym y Gasca serán proveedores externos intercambiables.
3. Warehouse podrá guardar archivos crudos, pero no estados operativos.
4. Cada socio nuevo será una entidad independiente por cohorte.
5. El estado vigente estará almacenado para consultas eficientes, pero solo podrá modificarse mediante el servicio de reconciliación.
6. Todo cambio de estado generará un evento histórico.
7. Las decisiones manuales se almacenarán separadas de las evidencias automáticas.
8. Las incidencias no se mezclarán con los tres estados funcionales.
9. No habrá eliminaciones físicas de información operativa.
10. Fechas de negocio usarán `DATE`; timestamps técnicos usarán `TIMESTAMPTZ`.

---

## 2. Separación de conceptos

El dominio tendrá seis conceptos principales:

```text
Socio nuevo por cohorte
Evidencia de rutina
Decisión manual
Estado vigente
Historial de estado
Ejecución de proveedores
```

Además, existirá un registro separado de incidencias de conciliación.

---

## 3. Modelo principal: socio nuevo por cohorte

### Tabla propuesta

```text
routine_control_members
```

Representa una alta de socio nuevo dentro de una cohorte mensual.

No representa necesariamente una identidad universal de la persona. El mismo correo podrá aparecer en diferentes cohortes.

### Columnas propuestas

```text
id
source_system
source_record_id
source_identity_key
sucursal_id
member_name
email_original
email_normalized
sale_date
cohort_month
classification_status
current_status
status_version
first_routine_at
latest_routine_at
current_instructor_name
routine_assignment_type
first_seen_at
last_seen_at
source_updated_at
created_at
updated_at
```

### Definición de campos

#### `id`

Identificador interno de Suite.

Tipo recomendado:

```text
BIGINT
```

#### `source_system`

Proveedor que informó el socio nuevo.

Valor inicial:

```text
gasca
```

#### `source_record_id`

Identificador estable entregado por Gasca, cuando exista.

Podrá ser nulo mientras no se confirme qué identificador ofrece la fuente real.

#### `source_identity_key`

Llave técnica determinista utilizada para idempotencia.

Prioridad:

```text
Si existe source_record_id:
    gasca:<source_record_id>

Si no existe:
    hash de datos estables acordados
```

La composición exacta del fallback no se cerrará hasta revisar el archivo real de Gasca.

#### `sucursal_id`

FK al catálogo canónico de sucursales de Suite.

No se almacenará el nombre textual como fuente de autorización.

El nombre original podrá conservarse dentro de metadata de origen o evidencia raw.

#### `member_name`

Nombre mostrado del socio.

No se utilizará como llave de conciliación.

#### `email_original`

Correo tal como fue recibido de Gasca.

#### `email_normalized`

Correo utilizado para conciliación:

```text
trim + lowercase
```

Podrá ser nulo cuando el registro no tenga correo válido.

#### `sale_date`

Fecha oficial de venta nueva informada por Gasca.

Tipo:

```text
DATE
```

#### `cohort_month`

Primer día del mes de `sale_date`.

Ejemplo:

```text
sale_date:    2026-07-13
cohort_month: 2026-07-01
```

Tipo:

```text
DATE
```

No se almacenará como texto `2026-07`.

#### `classification_status`

Indica si el registro pudo clasificarse funcionalmente.

Valores:

```text
CLASSIFIED
INCIDENT
```

#### `current_status`

Estado funcional vigente.

Valores permitidos:

```text
SIN_RUTINA
CON_RUTINA
NO_DESEA_RUTINA
```

Será nulo cuando:

```text
classification_status = INCIDENT
```

Esto permite conservar exactamente tres estados funcionales sin clasificar silenciosamente una incidencia como pendiente.

#### `status_version`

Entero incremental para control de concurrencia y actualizaciones optimistas.

Cada cambio efectivo de estado incrementará este valor.

#### `first_routine_at`

Fecha de la primera rutina válida conocida.

#### `latest_routine_at`

Fecha de la rutina válida más reciente conocida.

#### `current_instructor_name`

Instructor asociado a la evidencia vigente o más reciente.

Será un dato informativo, no una llave.

#### `routine_assignment_type`

Valor derivado al comparar `first_routine_at` contra `sale_date`.

Valores:

```text
PREEXISTENTE
MISMO_DIA
POSTERIOR
```

Será nulo si el socio no tiene rutina.

#### `first_seen_at`

Primer momento en que Suite observó el socio.

#### `last_seen_at`

Último momento en que fue observado en una extracción válida.

#### `source_updated_at`

Timestamp informado por la fuente, si existe.

#### `created_at` y `updated_at`

Timestamps técnicos controlados por Suite.

---

## 4. Identidad del socio por cohorte

La identidad deberá seguir esta prioridad:

### Nivel 1: identificador estable de Gasca

Cuando Gasca entregue un ID único:

```text
UNIQUE(source_system, source_record_id)
```

### Nivel 2: llave técnica fallback

Cuando no exista ID estable:

```text
UNIQUE(source_system, source_identity_key)
```

La llave fallback deberá ser determinista, pero no se definirá usando únicamente el correo.

Deberá considerar los datos que realmente estén disponibles, posiblemente:

```text
sucursal
correo normalizado
fecha de venta
identificador de movimiento o socio
```

### Regla de duplicidad

La existencia de dos registros con el mismo correo no provocará que uno sobrescriba al otro.

Los registros se conservarán y se generará una incidencia.

### Mismo correo en diferentes cohortes

Será permitido.

Ejemplo:

```text
correo: socio@correo.com
cohorte: 2026-01-01

correo: socio@correo.com
cohorte: 2026-07-01
```

Suite deberá evaluar cada alta como un registro operativo distinto.

---

## 5. Evidencias de rutina

### Tabla propuesta

```text
routine_assignment_evidences
```

Representa un hecho observado que indica que existe una rutina.

### Columnas propuestas

```text
id
member_id
provider_key
provider_record_id
evidence_identity_key
email_original
email_normalized
external_member_id
external_routine_id
provider_center_key
sucursal_id
assigned_at
instructor_name
first_observed_at
last_observed_at
first_provider_run_id
last_provider_run_id
payload_hash
is_valid
invalidated_at
invalidated_by_user_id
invalidation_reason
created_at
updated_at
```

### Reglas

* Una evidencia no se eliminará porque deje de aparecer en una extracción.
* Una evidencia repetida actualizará `last_observed_at`.
* Solo una corrección explícita podrá establecer `is_valid = false`.
* La invalidación requerirá motivo y auditoría.
* Una evidencia válida tendrá prioridad sobre `NO_DESEA_RUTINA`.

### Identidad de evidencia

Prioridad:

```text
Si existe external_routine_id:
    provider_key + external_routine_id

Si no existe:
    evidence_identity_key determinista
```

El fallback podrá construirse con:

```text
provider
correo normalizado
fecha de rutina
instructor
centro
```

La composición final dependerá de las columnas reales de Trainingym.

### Restricciones únicas

Propuesta:

```text
UNIQUE(provider_key, provider_record_id)
```

cuando exista ID externo.

Y alternativamente:

```text
UNIQUE(provider_key, evidence_identity_key)
```

para registros sin ID externo.

Las restricciones deberán admitir valores nulos sin impedir el segundo mecanismo.

---

## 6. Decisiones manuales

### Tabla propuesta

```text
routine_control_decisions
```

Representa decisiones humanas independientes de la información automática.

### Columnas propuestas

```text
id
member_id
decision_type
reason_code
notes
is_active
created_by_user_id
created_at
revoked_by_user_id
revoked_at
revocation_reason
created_from_sucursal_id
metadata
```

### `decision_type`

Valor inicial permitido:

```text
NO_DESEA_RUTINA
```

Se utiliza una tabla independiente para permitir futuras decisiones sin modificar el historial existente.

### Decisión activa

Solo podrá existir una decisión activa de tipo `NO_DESEA_RUTINA` por socio.

Restricción parcial propuesta:

```text
UNIQUE(member_id, decision_type)
WHERE is_active = true
```

### Reversión

La reversión:

* No eliminará el registro.
* Cambiará `is_active` a `false`.
* Guardará usuario, fecha y motivo.
* Generará un evento de estado cuando el estado efectivo cambie.

---

## 7. Estado vigente

El estado se calculará con esta prioridad:

```text
1. Evidencia válida de rutina
   → CON_RUTINA

2. Sin evidencia válida y con decisión activa
   → NO_DESEA_RUTINA

3. Sin evidencia válida y sin decisión activa
   → SIN_RUTINA
```

Para registros con incidencias que impidan conciliación:

```text
classification_status = INCIDENT
current_status = NULL
```

### Fuente de actualización

`current_status` no podrá actualizarse directamente desde routes, providers o scripts.

Solo podrá cambiar mediante un servicio de dominio, provisionalmente:

```text
RoutineControlReconciliationService
```

### Transacción

Un cambio de estado deberá guardar en la misma transacción:

1. Nuevo estado vigente.
2. Incremento de `status_version`.
3. Evento histórico.
4. Referencia a la evidencia, decisión o ejecución que provocó el cambio.

Si falla cualquiera de estos pasos, toda la transacción se revierte.

---

## 8. Historial de estados

### Tabla propuesta

```text
routine_control_status_events
```

### Columnas propuestas

```text
id
member_id
previous_status
new_status
cause_code
actor_type
actor_user_id
provider_run_id
evidence_id
decision_id
event_key
occurred_at
metadata
```

### `cause_code`

Valores iniciales:

```text
MEMBER_CREATED
ROUTINE_DETECTED
NO_ROUTINE_CONFIRMED
NO_ROUTINE_DECLARED
NO_ROUTINE_DECLARATION_REVOKED
ROUTINE_EVIDENCE_INVALIDATED
SOURCE_DATA_CORRECTED
INCIDENT_OPENED
INCIDENT_RESOLVED
ADMIN_CORRECTION
```

### `actor_type`

Valores:

```text
SYSTEM
USER
```

### `event_key`

Llave determinista para evitar eventos duplicados durante una reejecución.

Ejemplo conceptual:

```text
member_id
new_status
cause_code
evidence_id o decision_id
```

Restricción:

```text
UNIQUE(event_key)
```

Un pipeline reejecutado con la misma evidencia no deberá generar un segundo evento idéntico.

---

## 9. Incidencias

### Tabla propuesta

```text
routine_control_incidents
```

### Columnas propuestas

```text
id
member_id
provider_run_id
incident_code
severity
status
sucursal_id
email_normalized
source_record_reference
details
created_at
last_seen_at
resolved_at
resolved_by_user_id
resolution_notes
```

### Estados

```text
OPEN
RESOLVED
IGNORED
```

### Severidades

```text
INFO
WARNING
ERROR
```

### Regla de repetición

Si la misma incidencia vuelve a aparecer:

* No se crea indefinidamente una nueva fila.
* Se actualiza `last_seen_at`.
* Se asocia la ejecución más reciente.
* Si había sido resuelta y reaparece, podrá reabrirse según la regla técnica.

La identidad de incidencia deberá utilizar una llave determinista basada en:

```text
incident_code
source
source_record_reference
cohorte o fecha de negocio
```

---

## 10. Ejecuciones del pipeline

Se separarán la ejecución global y las ejecuciones de cada proveedor.

### 10.1. Tabla principal

```text
routine_control_pipeline_runs
```

Columnas:

```text
id
business_date
generation_mode
status
idempotency_key
started_at
finished_at
triggered_by_user_id
trigger_source
records_created
records_updated
status_changes
incidents_created
error_code
error_message
created_at
```

### `generation_mode`

```text
SCHEDULED
MANUAL
BACKFILL
RETRY
```

### `status`

```text
PENDING
RUNNING
SUCCESS
PARTIAL
FAILED
```

### 10.2. Ejecución por proveedor

```text
routine_control_provider_runs
```

Columnas:

```text
id
pipeline_run_id
provider_key
dataset_key
status
attempt_count
started_at
finished_at
date_from
date_to
content_hash
raw_warehouse_upload_id
records_received
records_valid
records_rejected
records_created
records_updated
error_code
error_message
diagnostic_artifact_path
created_at
```

### `provider_key`

Valores iniciales:

```text
gasca
trainingym
```

### `dataset_key`

Valores iniciales:

```text
new_members
routine_assignments
```

Esto permite que en el futuro Gasca entregue ambos datasets.

---

## 11. Idempotencia de ejecuciones

La idempotencia se aplicará en cuatro niveles.

### Nivel 1: bloqueo de ejecución

Antes de comenzar una ejecución, el worker deberá obtener un advisory lock PostgreSQL basado en:

```text
módulo
fecha de negocio
modo de ejecución
```

No podrán ejecutarse simultáneamente dos pipelines incompatibles para el mismo corte.

### Nivel 2: contenido del proveedor

Cada extracción calculará un `content_hash`.

Si ya existe una ejecución exitosa con:

```text
provider_key
dataset_key
date_from
date_to
content_hash
```

el sistema podrá reutilizar el resultado sin duplicar ingesta.

### Nivel 3: registros normalizados

Cada socio y evidencia tendrá una llave técnica determinista.

Un upsert repetido:

* No crea otra entidad.
* Actualiza `last_seen_at`.
* Actualiza campos modificables cuando exista una corrección real.
* Conserva el origen anterior mediante auditoría.

### Nivel 4: eventos

Cada evento tendrá `event_key`.

Si el estado efectivo no cambia:

* No se genera un nuevo evento.
* No se incrementa `status_version`.
* No se altera `updated_at` innecesariamente.

---

## 12. Manejo de cambios de origen

Si Gasca modifica un dato previamente procesado:

### Cambio de nombre

* Actualiza el nombre vigente.
* No cambia identidad.
* Registra auditoría si el cambio es material.

### Cambio de correo

* Conserva correo anterior en historial o metadata de origen.
* Reejecuta conciliación.
* No elimina las evidencias anteriores automáticamente.
* Puede generar una incidencia.

### Cambio de sucursal

* No se acepta silenciosamente como una simple actualización.
* Se registra el cambio.
* Se valida si corresponde a corrección o transferencia.
* Se recalcula el alcance de acceso.

### Cambio de fecha de venta

* Recalcula la cohorte.
* Registra evento de corrección.
* No genera un segundo socio si se confirma que es el mismo registro fuente.
* Recalcula indicadores de ambas cohortes afectadas.

---

## 13. Restricciones e índices

### `routine_control_members`

Índices recomendados:

```text
(cohort_month)
(sucursal_id, cohort_month)
(current_status, cohort_month)
(classification_status, cohort_month)
(email_normalized)
(sucursal_id, current_status, cohort_month)
(sale_date)
```

Restricciones:

```text
CHECK current_status IN (...)
CHECK classification_status IN (...)
CHECK cohort_month sea primer día del mes
```

### `routine_assignment_evidences`

Índices:

```text
(member_id, assigned_at)
(email_normalized)
(provider_key, assigned_at)
(is_valid, member_id)
```

### `routine_control_decisions`

Índices:

```text
(member_id, is_active)
(created_by_user_id, created_at)
```

### `routine_control_status_events`

Índices:

```text
(member_id, occurred_at)
(actor_user_id, occurred_at)
(cause_code, occurred_at)
```

### `routine_control_incidents`

Índices:

```text
(status, created_at)
(sucursal_id, status)
(incident_code, status)
```

### Runs

Índices:

```text
(business_date, status)
(provider_key, dataset_key, date_to)
(pipeline_run_id)
```

---

## 14. Tipos de columnas

Para estados y códigos se recomienda:

```text
VARCHAR + CHECK CONSTRAINT
```

en lugar de PostgreSQL ENUM.

Motivo:

* Facilita agregar estados mediante Alembic.
* Reduce migraciones complejas de tipos.
* Mantiene validación a nivel DB.
* Es consistente con un dominio que todavía evolucionará.

Para metadata:

```text
JSONB
```

solo cuando el contenido sea variable o auxiliar.

Los datos requeridos para filtros, permisos e indicadores deberán tener columnas explícitas y no vivir únicamente dentro de JSONB.

---

## 15. Relaciones y borrado

Relaciones principales:

```text
Sucursal
  └── RoutineControlMember

RoutineControlMember
  ├── RoutineAssignmentEvidence
  ├── RoutineControlDecision
  ├── RoutineControlStatusEvent
  └── RoutineControlIncident

PipelineRun
  └── ProviderRun
```

Política de borrado:

* No se eliminarán físicamente socios, evidencias, decisiones o eventos.
* Una evidencia podrá invalidarse.
* Una decisión podrá revocarse.
* Una incidencia podrá resolverse.
* Una ejecución permanecerá histórica.
* Las FKs históricas no deberán usar cascadas que borren auditoría.

---

## 16. Reglas de consistencia

La base deberá impedir:

* Más de una decisión activa equivalente por socio.
* Eventos duplicados.
* Evidencias duplicadas del mismo proveedor.
* Un `current_status` fuera de los tres valores permitidos.
* Un socio clasificado como incidencia con estado funcional vigente.
* Un socio clasificado normalmente sin estado.
* Una cohorte que no corresponda al primer día del mes.
* Una decisión manual sin usuario.
* Una invalidación sin motivo.
* Una ejecución marcada como exitosa sin fecha de término.

---

## 17. Casos de prueba del modelo

### Rutina preexistente

```text
sale_date = 2026-07-02
assigned_at = 2026-06-30

current_status = CON_RUTINA
routine_assignment_type = PREEXISTENTE
```

### Decisión manual sin rutina

```text
evidencias válidas = 0
decisión activa = NO_DESEA_RUTINA

current_status = NO_DESEA_RUTINA
```

### Decisión manual seguida de rutina

```text
decisión activa = NO_DESEA_RUTINA
evidencia válida nueva = 1

current_status = CON_RUTINA
```

La decisión continúa activa históricamente, pero no determina el estado vigente mientras exista la evidencia.

### Extracción repetida

```text
misma evidencia
mismo content_hash
mismo estado efectivo
```

Resultado:

```text
sin nueva evidencia
sin nuevo evento
sin incremento de status_version
```

### Correo vacío

```text
classification_status = INCIDENT
current_status = NULL
incidente = EMAIL_VACIO
```

### Correo duplicado

```text
se conservan ambos registros fuente
no se fusionan automáticamente
se genera incidencia
```

---

## 18. Decisiones pendientes antes de crear modelos

Todavía deben confirmarse:

1. Identificador estable disponible en Gasca.
2. Columnas reales del reporte individual de socios nuevos.
3. Identificador estable de rutina en Trainingym.
4. Si Trainingym entrega fecha real de asignación.
5. Si el reporte contiene múltiples rutinas por socio.
6. Composición exacta de `source_identity_key`.
7. Composición exacta de `evidence_identity_key`.
8. Política ante cambios de sucursal.
9. Periodo de backfill inicial.
10. Retención de raw y artifacts.
11. Roles autorizados para invalidar evidencias.
12. Si una decisión activa debe cerrarse automáticamente cuando aparece una rutina o permanecer activa como antecedente.

---

## 19. Decisión recomendada sobre “No desea rutina”

Se recomienda que la decisión permanezca registrada como activa hasta que un usuario la revoque, aunque el estado vigente cambie a `CON_RUTINA`.

Razón:

* Conserva la declaración original.
* Permite saber que posteriormente cambió la situación.
* Evita alterar una decisión humana de manera silenciosa.
* El estado vigente ya queda correctamente determinado por la prioridad de evidencia.

Para indicadores y bandejas siempre se utilizará `current_status`, no la existencia aislada de la decisión.

---

## 20. Criterios de aceptación del bloque

Este bloque quedará cerrado cuando se apruebe:

* Separación entre socio, evidencia, decisión y evento.
* Uso de cohorte como `DATE`.
* Tres estados funcionales.
* Clasificación técnica separada para incidencias.
* Prioridad de evidencia sobre decisión.
* Persistencia de rutinas históricas.
* Modelo de runs y provider runs.
* Estrategia de idempotencia en cuatro niveles.
* Ausencia de eliminaciones físicas.
* Uso de IDs canónicos de sucursal y usuario.
* Preguntas pendientes que deberán resolverse antes de la migración.


  # Bloque 2: servicios de dominio y transiciones de estado

**Versión:** 0.2
**Estado:** Propuesta para validación
**Dependencia:** Bloque 1 — modelo de datos, estados e idempotencia
**Alcance:** Servicios internos, comandos, reglas de transición, transacciones y concurrencia.
**Fuera de alcance:** Providers concretos, endpoints HTTP, Angular, scheduling y despliegue.

---

## 21. Objetivo del bloque

Definir qué componentes podrán crear o modificar:

* Socios nuevos.
* Evidencias de rutina.
* Decisiones manuales.
* Incidencias.
* Estado vigente.
* Historial.
* Ejecuciones.

La regla principal será:

> Ninguna route, provider, job o componente externo actualizará directamente el estado vigente de un socio.

Toda modificación deberá pasar por servicios de dominio con reglas explícitas y transacciones controladas.

---

## 22. Organización preliminar

Estructura candidata:

```text
backend/app/routine_control/
├── domain/
│   ├── constants.py
│   ├── commands.py
│   ├── results.py
│   └── exceptions.py
├── services/
│   ├── member_ingestion_service.py
│   ├── routine_evidence_service.py
│   ├── decision_service.py
│   ├── reconciliation_service.py
│   ├── incident_service.py
│   ├── pipeline_run_service.py
│   └── audit_service.py
└── repositories/
    ├── member_repository.py
    ├── evidence_repository.py
    ├── decision_repository.py
    ├── incident_repository.py
    └── run_repository.py
```

Los nombres son provisionales.

La implementación podrá mantener repositorios simples sobre SQLAlchemy, pero las reglas de negocio no deberán quedar distribuidas entre routes y modelos ORM.

---

## 23. Servicios principales

### 23.1. `RoutineMemberIngestionService`

Responsable de incorporar y actualizar socios nuevos observados por un provider.

Funciones conceptuales:

```python
upsert_member(command)
upsert_members(commands)
apply_source_correction(command)
```

Responsabilidades:

* Resolver la identidad técnica.
* Crear un nuevo socio por cohorte.
* Actualizar `last_seen_at`.
* Detectar cambios de origen.
* Resolver `sucursal_id`.
* Calcular `cohort_month`.
* Abrir incidencias cuando el registro no sea clasificable.
* Solicitar reconciliación cuando cambien correo, fecha o sucursal.
* No decidir por sí mismo el estado funcional final.

No será responsable de:

* Consultar Gasca.
* Descargar archivos.
* Crear rutinas.
* Autorizar usuarios.
* Generar Excel.

---

### 23.2. `RoutineEvidenceService`

Responsable de registrar evidencias de rutina normalizadas.

Funciones conceptuales:

```python
register_evidence(command)
register_evidences(commands)
invalidate_evidence(command)
```

Responsabilidades:

* Resolver la identidad de la evidencia.
* Evitar duplicados.
* Asociar la evidencia al socio correcto.
* Actualizar `last_observed_at`.
* Conservar la primera observación.
* Validar fecha, correo y provider.
* Abrir incidencias si no puede asociarse.
* Solicitar reconciliación del socio afectado.
* Invalidar evidencia únicamente con autorización y motivo.

No eliminará físicamente evidencias.

---

### 23.3. `RoutineDecisionService`

Responsable de las decisiones manuales.

Funciones conceptuales:

```python
declare_no_routine(command)
revoke_no_routine(command)
```

Responsabilidades:

* Validar que el socio exista.
* Validar que el usuario tenga alcance.
* Validar motivo y observación.
* Impedir decisiones activas duplicadas.
* Crear o revocar la decisión.
* Solicitar reconciliación.
* Generar auditoría.
* Mantener la decisión separada del estado vigente.

La route no establecerá directamente:

```text
current_status = NO_DESEA_RUTINA
```

La route creará el comando y el servicio calculará el resultado efectivo.

---

### 23.4. `RoutineControlReconciliationService`

Será el único servicio autorizado para modificar:

```text
routine_control_members.current_status
routine_control_members.classification_status
routine_control_members.status_version
routine_control_members.first_routine_at
routine_control_members.latest_routine_at
routine_control_members.current_instructor_name
routine_control_members.routine_assignment_type
```

Funciones conceptuales:

```python
reconcile_member(member_id, context)
reconcile_members(member_ids, context)
reconcile_cohort(cohort_month, scope)
```

Responsabilidades:

* Obtener evidencias válidas.
* Obtener decisiones manuales activas.
* Obtener incidencias bloqueantes.
* Calcular el estado efectivo.
* Detectar si el estado realmente cambió.
* Actualizar campos derivados.
* Crear un evento histórico.
* Incrementar `status_version`.
* Evitar eventos redundantes.
* Ejecutar todo dentro de una transacción.

---

### 23.5. `RoutineIncidentService`

Responsable de abrir, actualizar, resolver y reabrir incidencias.

Funciones conceptuales:

```python
open_or_touch_incident(command)
resolve_incident(command)
reopen_incident(command)
```

Responsabilidades:

* Calcular la identidad determinista.
* Evitar incidencias duplicadas.
* Actualizar `last_seen_at`.
* Relacionar la ejecución más reciente.
* Resolver incidencias de manera auditada.
* Solicitar reconciliación cuando una incidencia bloqueante se resuelva.

---

### 23.6. `RoutinePipelineRunService`

Responsable del ciclo de vida de ejecuciones.

Funciones conceptuales:

```python
create_pipeline_run(command)
start_pipeline_run(run_id)
finish_pipeline_run(run_id, result)
fail_pipeline_run(run_id, error)
create_provider_run(command)
finish_provider_run(run_id, result)
fail_provider_run(run_id, error)
```

Responsabilidades:

* Impedir transiciones inválidas.
* Registrar conteos.
* Sanitizar errores.
* Asociar artifacts.
* Registrar fechas.
* Garantizar cierre de ejecuciones.
* No ejecutar Playwright directamente.

---

## 24. Comandos de dominio

Los servicios recibirán comandos estructurados, no diccionarios libres provenientes directamente de una route o provider.

### 24.1. Alta o actualización de socio

```python
UpsertRoutineMemberCommand(
    provider_key,
    source_record_id,
    source_identity_key,
    source_name,
    source_branch_key,
    member_name,
    email_original,
    sale_date,
    source_updated_at,
    provider_run_id,
    raw_payload_reference,
)
```

### 24.2. Registro de evidencia

```python
RegisterRoutineEvidenceCommand(
    provider_key,
    provider_record_id,
    evidence_identity_key,
    external_member_id,
    external_routine_id,
    provider_center_key,
    email_original,
    assigned_at,
    instructor_name,
    provider_run_id,
    payload_hash,
)
```

### 24.3. Decisión manual

```python
DeclareNoRoutineCommand(
    member_id,
    reason_code,
    notes,
    actor_user_id,
    requested_scope,
    expected_status_version,
)
```

### 24.4. Reversión

```python
RevokeNoRoutineCommand(
    member_id,
    decision_id,
    revocation_reason,
    actor_user_id,
    expected_status_version,
)
```

### 24.5. Invalidación de evidencia

```python
InvalidateRoutineEvidenceCommand(
    evidence_id,
    reason,
    actor_user_id,
    expected_status_version,
)
```

Los nombres y tipos finales se definirán durante implementación, pero el contrato de entrada deberá ser explícito.

---

## 25. Resultados de dominio

Cada operación deberá devolver un resultado estructurado.

Ejemplo:

```python
RoutineMemberMutationResult(
    member_id,
    created,
    source_changed,
    previous_status,
    current_status,
    status_changed,
    status_version,
    incident_ids,
    event_id,
)
```

El resultado permitirá que:

* El pipeline acumule conteos.
* La API devuelva el estado real.
* Las pruebas validen efectos.
* La auditoría no dependa de mensajes de texto.

---

## 26. Contexto de reconciliación

Cada reconciliación recibirá un contexto que indique su causa.

Ejemplo:

```python
ReconciliationContext(
    cause_code,
    actor_type,
    actor_user_id,
    provider_run_id,
    evidence_id,
    decision_id,
    correlation_id,
)
```

Esto permitirá distinguir:

* Cambio por ingesta automática.
* Cambio por decisión humana.
* Corrección administrativa.
* Resolución de incidencia.
* Backfill.
* Invalidación de evidencia.

---

## 27. Algoritmo de reconciliación

Para cada socio:

```text
1. Bloquear o cargar el registro para actualización.
2. Leer incidencias abiertas que bloqueen clasificación.
3. Leer evidencias válidas.
4. Leer decisión activa NO_DESEA_RUTINA.
5. Calcular clasificación.
6. Calcular estado efectivo.
7. Calcular fechas e instructor derivados.
8. Comparar contra estado almacenado.
9. Actualizar únicamente si hay diferencia material.
10. Crear evento idempotente.
11. Incrementar status_version si cambió el estado.
12. Confirmar la transacción.
```

Pseudocódigo:

```python
if has_blocking_incident:
    classification_status = "INCIDENT"
    effective_status = None

elif has_valid_routine_evidence:
    classification_status = "CLASSIFIED"
    effective_status = "CON_RUTINA"

elif has_active_no_routine_decision:
    classification_status = "CLASSIFIED"
    effective_status = "NO_DESEA_RUTINA"

else:
    classification_status = "CLASSIFIED"
    effective_status = "SIN_RUTINA"
```

---

## 28. Incidencias bloqueantes y no bloqueantes

No todas las incidencias deberán impedir clasificación.

### Bloqueantes iniciales

* `EMAIL_VACIO`
* `EMAIL_DUPLICADO_GASCA`
* `COINCIDENCIA_AMBIGUA`
* `SUCURSAL_NO_RESUELTA`
* `FECHA_VENTA_INVALIDA`
* `COHORTE_NO_DETERMINADA`
* `REGISTRO_ORIGEN_INVALIDO`

Resultado:

```text
classification_status = INCIDENT
current_status = NULL
```

### No bloqueantes iniciales

* Instructor vacío.
* Centro de Trainingym no resuelto, si la asociación por correo es inequívoca.
* ID externo de rutina ausente.
* Metadata opcional incompleta.

Estas incidencias podrán permitir clasificación mientras queden visibles para revisión.

La lista final deberá centralizarse en código, no dispersarse en condicionales.

---

## 29. Transiciones permitidas

### Desde creación válida

```text
SIN ESTADO
    → SIN_RUTINA
    → CON_RUTINA
    → NO_DESEA_RUTINA
```

El resultado dependerá de evidencias y decisiones ya existentes.

### Desde `SIN_RUTINA`

```text
SIN_RUTINA → CON_RUTINA
```

Causa típica:

```text
ROUTINE_DETECTED
```

```text
SIN_RUTINA → NO_DESEA_RUTINA
```

Causa típica:

```text
NO_ROUTINE_DECLARED
```

```text
SIN_RUTINA → NULL / INCIDENT
```

Solo cuando una corrección de origen provoque una incidencia bloqueante.

---

### Desde `NO_DESEA_RUTINA`

```text
NO_DESEA_RUTINA → CON_RUTINA
```

Cuando aparece evidencia válida.

```text
NO_DESEA_RUTINA → SIN_RUTINA
```

Cuando se revoca la decisión y no existe rutina.

```text
NO_DESEA_RUTINA → NULL / INCIDENT
```

Cuando una corrección provoque una incidencia bloqueante.

---

### Desde `CON_RUTINA`

```text
CON_RUTINA → CON_RUTINA
```

Cuando aparecen más evidencias o cambia la última rutina.

No generará un evento de estado si continúa en el mismo estado, aunque podrá actualizar datos derivados y auditoría de fuente.

```text
CON_RUTINA → NO_DESEA_RUTINA
```

No ocurrirá automáticamente.

Solo sería posible después de invalidar todas las evidencias válidas y existir una decisión manual activa.

```text
CON_RUTINA → SIN_RUTINA
```

Solo será posible si:

* Todas las evidencias válidas fueron invalidadas.
* No existe una decisión activa.
* La invalidación fue autorizada y auditada.

No ocurrirá porque una extracción deje de devolver la rutina.

---

### Desde incidencia

```text
NULL / INCIDENT → SIN_RUTINA
NULL / INCIDENT → CON_RUTINA
NULL / INCIDENT → NO_DESEA_RUTINA
```

Después de resolver la incidencia bloqueante y reconciliar nuevamente.

---

## 30. Decisión activa frente a estado vigente

Una decisión `NO_DESEA_RUTINA` podrá permanecer activa aunque el estado vigente sea `CON_RUTINA`.

Ejemplo:

```text
Decisión activa: NO_DESEA_RUTINA
Evidencia válida: sí
Estado vigente: CON_RUTINA
```

Esto significa:

* El socio declaró inicialmente no querer rutina.
* Posteriormente se detectó una rutina.
* La decisión histórica continúa registrada.
* La bandeja e indicadores utilizan `current_status`.
* El socio aparece en `Con rutina`.
* No aparece en `No desean rutina`.

Para que vuelva a `NO_DESEA_RUTINA`, tendrían que invalidarse todas las evidencias válidas.

---

## 31. Cálculo de fechas derivadas

### `first_routine_at`

Fecha mínima entre evidencias válidas.

### `latest_routine_at`

Fecha máxima entre evidencias válidas.

### `current_instructor_name`

Instructor asociado a la evidencia válida más reciente.

En caso de empate de fecha:

1. Preferir evidencia con timestamp más preciso.
2. Después, evidencia observada más recientemente.
3. Finalmente, usar el ID interno como desempate determinista.

### `routine_assignment_type`

```text
first_routine_at < sale_date
    → PREEXISTENTE

first_routine_at = sale_date
    → MISMO_DIA

first_routine_at > sale_date
    → POSTERIOR
```

### Días para asignación

No será necesario persistirlo inicialmente.

Se calculará como:

```text
first_routine_at - sale_date
```

Para rutina preexistente podrá mostrarse:

* `0` para indicadores operativos; y
* el tipo `PREEXISTENTE` por separado.

No se recomienda mostrar días negativos como desempeño favorable sin explicación.

---

## 32. Días sin rutina

Para socios `SIN_RUTINA`:

```text
fecha de corte - sale_date
```

Para socios `NO_DESEA_RUTINA`:

* No se considera pendiente.
* Podrá mostrarse el tiempo transcurrido hasta la decisión como indicador futuro.

Para socios `CON_RUTINA`:

```text
max(first_routine_at - sale_date, 0)
```

La fecha de corte deberá ser explícita en API y exportación cuando se consulten históricos.

---

## 33. Transacciones

### Ingesta individual

Cada socio o evidencia podrá procesarse en una transacción independiente durante lotes grandes.

Ventajas:

* Un registro inválido no revierte todo el archivo.
* Permite registrar incidencias parciales.
* Reduce locks prolongados.

### Reconciliación

El registro del socio, sus campos derivados y el evento de estado deberán confirmarse en la misma transacción.

### Decisiones manuales

La operación deberá incluir en una sola transacción:

1. Validación de alcance.
2. Validación de `status_version`.
3. Creación o revocación de decisión.
4. Reconciliación.
5. Evento.
6. Auditoría.

Si falla cualquier paso, no se guarda ningún cambio parcial.

---

## 34. Concurrencia

### 34.1. Bloqueo pesimista interno

La reconciliación utilizará bloqueo de fila cuando sea necesario:

```sql
SELECT ... FOR UPDATE
```

sobre el socio afectado.

Esto evita que dos procesos modifiquen el mismo estado simultáneamente.

### 34.2. Control optimista para acciones de usuario

Las acciones manuales recibirán:

```text
expected_status_version
```

Si la versión actual ya cambió, la acción será rechazada con conflicto.

Ejemplo:

```text
Versión mostrada al usuario: 5
Versión actual en DB: 6
Resultado: conflicto; recargar el detalle
```

Esto evita que una decisión manual sobrescriba una rutina detectada mientras el usuario tenía abierta la pantalla.

### 34.3. Advisory lock de pipeline

El worker utilizará advisory lock para impedir pipelines incompatibles concurrentes.

El advisory lock global no sustituirá los locks de fila.

---

## 35. Idempotencia de servicios

### Ingesta de socio

Misma identidad y mismos datos:

```text
created = false
source_changed = false
status_changed = false
```

Solo podrá actualizarse `last_seen_at`.

### Evidencia

Misma llave de evidencia:

* No crea otra fila.
* Actualiza `last_observed_at`.
* Asocia la ejecución más reciente.
* No genera otro evento si el estado ya era `CON_RUTINA`.

### Decisión

Mismo socio con decisión activa:

* No crea otra decisión.
* La API deberá informar que ya existe.
* No genera otro evento.

### Reversión repetida

Una decisión ya revocada:

* No se revoca nuevamente.
* Se devuelve un resultado idempotente o un conflicto controlado.
* No genera eventos adicionales.

---

## 36. Correcciones de datos de origen

### Correo corregido

Proceso:

1. Actualizar correo original y normalizado.
2. Registrar auditoría.
3. Reevaluar duplicidades.
4. Buscar evidencias compatibles.
5. Abrir o resolver incidencias.
6. Reconciliar.

No se deberán reasignar evidencias ambiguas sin regla explícita.

### Fecha de venta corregida

Proceso:

1. Actualizar `sale_date`.
2. Recalcular `cohort_month`.
3. Recalcular tipo de asignación.
4. Registrar cambio.
5. Invalidar caches o agregados afectados.
6. Reconciliar.

### Sucursal corregida

Proceso:

1. Validar sucursal canónica.
2. Actualizar `sucursal_id`.
3. Registrar sucursal anterior y nueva.
4. Reevaluar permisos.
5. Recalcular indicadores.
6. No borrar historial.

---

## 37. Conciliación de evidencias por correo

La asociación inicial será exacta sobre:

```text
email_normalized
```

### Una coincidencia

La evidencia se asocia al socio candidato.

### Ninguna coincidencia

Se conserva como evidencia no asociada o staging técnico y se abre incidencia.

No se pierde el registro.

### Varias coincidencias

No se elige automáticamente.

Se abre:

```text
COINCIDENCIA_AMBIGUA
```

La evidencia no cambia el estado de ningún socio hasta resolver la ambigüedad.

### Mismo correo en distintas cohortes

No se deberá asignar indiscriminadamente la misma evidencia a todas las cohortes.

Regla preliminar:

* La rutina puede asociarse a la cohorte cuya fecha de venta tenga relación temporal más razonable.
* La regla exacta requiere confirmar el comportamiento real de altas repetidas.
* Mientras no exista una regla cerrada, el caso se tratará como incidencia ambigua.

---

## 38. Servicios y permisos

Los servicios de dominio no dependerán de Angular.

Para acciones manuales recibirán un contexto de actor ya autenticado, pero deberán volver a validar mediante un servicio de alcance o política backend.

Conceptualmente:

```python
RoutineControlAuthorizationService.assert_can_update_member(
    user,
    member,
    action,
)
```

La validación se utilizará en:

* Crear decisión.
* Revocar decisión.
* Invalidar evidencia.
* Resolver incidencia.
* Reprocesar.
* Exportar.

No se implementarán reglas diferentes en cada route.

---

## 39. Excepciones de dominio

Excepciones iniciales:

```text
RoutineControlMemberNotFound
RoutineControlScopeDenied
RoutineControlConflict
RoutineControlDuplicateDecision
RoutineControlDecisionNotActive
RoutineControlEvidenceNotFound
RoutineControlEvidenceAlreadyInvalid
RoutineControlInvalidReason
RoutineControlBlockingIncident
RoutineControlProviderRunNotFound
RoutineControlInvalidRunTransition
```

Las routes convertirán estas excepciones a respuestas HTTP. Los servicios no deberán construir respuestas Flask directamente.

---

## 40. Observabilidad interna

Cada operación importante deberá aceptar o generar:

```text
correlation_id
```

Esto permitirá relacionar:

* Pipeline run.
* Provider run.
* Logs.
* Evidencias.
* Eventos.
* Incidencias.
* Acción manual.
* Exportación.

Los logs no deberán incluir credenciales ni payloads completos con información sensible.

---

## 41. Pruebas unitarias mínimas

### Reconciliación

* Sin evidencia ni decisión → `SIN_RUTINA`.
* Evidencia válida → `CON_RUTINA`.
* Decisión activa sin evidencia → `NO_DESEA_RUTINA`.
* Evidencia y decisión → `CON_RUTINA`.
* Incidencia bloqueante → estado nulo.
* Resolver incidencia → recalcula estado.

### Idempotencia

* Evidencia repetida no duplica fila.
* Evidencia repetida no duplica evento.
* Decisión repetida no duplica decisión.
* Reconciliación sin cambio no incrementa versión.
* Reejecución no cambia el estado.

### Concurrencia

* `expected_status_version` incorrecta produce conflicto.
* Dos reconciliaciones simultáneas no crean dos eventos.
* Una rutina detectada durante una decisión manual no se pierde.

### Invalidación

* Invalidar la única evidencia cambia a `SIN_RUTINA` sin decisión.
* Invalidar la única evidencia cambia a `NO_DESEA_RUTINA` con decisión activa.
* Extracción incompleta no invalida evidencia.

---

## 42. Decisiones cerradas en este bloque

* Solo reconciliación modificará el estado vigente.
* Routes, providers y jobs no modificarán estados directamente.
* Las decisiones manuales estarán separadas de los estados.
* Una decisión podrá permanecer activa aunque el estado sea `CON_RUTINA`.
* Las incidencias bloqueantes producirán estado funcional nulo.
* Evidencias ausentes en una nueva extracción no se invalidarán.
* Las acciones manuales usarán control optimista.
* La reconciliación podrá usar bloqueo de fila.
* Los eventos y cambios de estado serán transaccionales.
* Las coincidencias ambiguas no se resolverán automáticamente.
* Los servicios usarán comandos y resultados estructurados.
* Las excepciones de dominio no dependerán de Flask.

---

## 43. Pendientes para bloques posteriores

* Contrato exacto de providers.
* Formato normalizado de los datasets.
* API y códigos HTTP.
* Permisos y capacidades exactas.
* Worker y scheduling.
* Manejo de staging para evidencias no asociadas.
* Resolución manual de incidencias.
* Estrategia de agregados para indicadores.
* Exportación.
* Estructura Angular.
* Estrategia de backfill.



# Bloque 3: contrato de providers Gasca y Trainingym

**Versión:** 0.3
**Estado:** Propuesta para validación
**Dependencias:**

* Bloque 1 — modelo de datos, estados e idempotencia
* Bloque 2 — servicios de dominio y transiciones

**Alcance:** Contratos de extracción, normalización, validación, fallos, seguridad y sustitución de proveedores.
**Fuera de alcance:** Endpoints HTTP, Angular, horario del worker y despliegue.

---

## 44. Objetivo del bloque

Definir una frontera estable entre el dominio de Control de Rutinas y las fuentes externas.

El dominio no deberá conocer:

* Cómo inicia sesión Trainingym.
* Cómo funciona Power BI.
* Qué selectores utiliza la página.
* Cómo se descarga el reporte de Gasca.
* Qué nombre tiene cada archivo externo.
* Qué proveedor está activo.
* Qué formato particular tiene cada Excel.

Los providers serán responsables de convertir cada fuente externa a contratos normalizados que el dominio pueda procesar.

---

## 45. Principio de aislamiento

Los providers podrán:

* Consultar sistemas externos.
* Autenticarse.
* Descargar archivos.
* Leer respuestas.
* Validar estructura.
* Normalizar registros.
* Generar artifacts técnicos.
* Reportar advertencias y errores.

Los providers no podrán:

* Modificar `current_status`.
* Crear decisiones manuales.
* Resolver permisos de usuario.
* Escribir directamente eventos de estado.
* Determinar indicadores.
* Generar respuestas Flask.
* Actualizar tablas operativas mediante SQL directo.
* Eliminar información histórica.
* Publicar un resultado como exitoso sin validación.

La persistencia operativa será responsabilidad de los servicios definidos en el Bloque 2.

---

## 46. Tipos de provider

El módulo manejará dos contratos principales.

### 46.1. Provider de socios nuevos

Contrato conceptual:

```text
NewMembersProvider
```

Responsabilidad:

> Obtener socios nuevos dentro de una ventana explícita y devolver registros normalizados.

Implementación inicial:

```text
GascaNewMembersProvider
```

### 46.2. Provider de asignaciones de rutina

Contrato conceptual:

```text
RoutineAssignmentsProvider
```

Responsabilidad:

> Obtener evidencias de rutinas dentro de una ventana explícita y devolver registros normalizados.

Implementación inicial:

```text
TrainingymRoutineAssignmentsProvider
```

Implementación futura:

```text
GascaRoutineAssignmentsProvider
```

---

## 47. Registro de providers

Los providers se resolverán mediante un registro central.

Conceptualmente:

```python
ProviderRegistry(
    new_members_providers={
        "gasca": GascaNewMembersProvider,
    },
    routine_assignment_providers={
        "trainingym": TrainingymRoutineAssignmentsProvider,
        "gasca": GascaRoutineAssignmentsProvider,
    },
)
```

El pipeline no deberá contener condicionales distribuidos como:

```python
if provider == "trainingym":
    ...
elif provider == "gasca":
    ...
```

La selección se realizará por configuración.

Configuración preliminar:

```text
ROUTINE_CONTROL_NEW_MEMBERS_PROVIDER=gasca
ROUTINE_CONTROL_ROUTINES_PRIMARY_PROVIDER=trainingym
ROUTINE_CONTROL_ROUTINES_SHADOW_PROVIDER=
```

Los nombres exactos podrán ajustarse en implementación.

---

## 48. Contexto de extracción

Todo provider recibirá una ventana explícita.

Contrato conceptual:

```python
ProviderExtractionContext(
    pipeline_run_id,
    provider_run_id,
    business_date,
    date_from,
    date_to,
    generation_mode,
    correlation_id,
    timezone,
    diagnostics_enabled,
)
```

### Reglas

* El provider no calculará “ayer” internamente.
* El provider no asumirá el primer día del mes.
* El worker o el orquestador definirán la ventana.
* La zona de negocio será `America/Tijuana`.
* `date_from` y `date_to` serán inclusivos.
* Un backfill podrá solicitar cualquier ventana soportada.
* Una reejecución recibirá exactamente la misma ventana original.

Esto permite reproducir resultados históricos.

---

## 49. Resultado normalizado de extracción

Todos los providers devolverán un resultado estructurado.

Contrato conceptual:

```python
ProviderExtractionResult(
    provider_key,
    dataset_key,
    status,
    date_from,
    date_to,
    business_date,
    records,
    rejected_records,
    warnings,
    raw_artifacts,
    content_hash,
    records_received,
    records_valid,
    records_rejected,
    started_at,
    finished_at,
    diagnostics,
)
```

### Estados permitidos

```text
SUCCESS
SUCCESS_EMPTY
PARTIAL
FAILED
BLOCKED
```

#### `SUCCESS`

La consulta terminó y los registros válidos fueron normalizados.

#### `SUCCESS_EMPTY`

La fuente respondió correctamente y confirmó que no existen registros para la ventana.

No debe confundirse con:

* Tabla que no cargó.
* Reporte que falló.
* Archivo vacío por error.
* Sesión expirada.

#### `PARTIAL`

Se obtuvieron datos válidos, pero también existieron registros rechazados o una sección incompleta.

#### `FAILED`

No fue posible obtener un resultado confiable.

#### `BLOCKED`

La ejecución fue impedida por una condición externa, por ejemplo:

* Turnstile.
* Challenge.
* Sesión bloqueada.
* Acceso denegado.
* Requerimiento de intervención manual.

---

## 50. Registro normalizado de socio nuevo

Contrato conceptual:

```python
NewMemberRecord(
    provider_key,
    source_record_id,
    source_identity_key,
    member_name,
    email_original,
    external_branch_key,
    external_branch_name,
    sale_date,
    source_updated_at,
    raw_record_hash,
    source_row_reference,
    metadata,
)
```

### Campos obligatorios para clasificación completa

* `provider_key`
* Identidad externa o llave técnica.
* Correo original.
* Sucursal externa.
* Fecha de venta nueva.

### Campos opcionales

* Nombre.
* Timestamp de actualización.
* Metadata adicional.
* Referencia de fila.

### Regla

El provider no resolverá el estado.

Únicamente devolverá el hecho:

> La fuente informó una venta nueva con estos datos.

---

## 51. Registro normalizado de rutina

Contrato conceptual:

```python
RoutineAssignmentRecord(
    provider_key,
    provider_record_id,
    evidence_identity_key,
    external_member_id,
    external_routine_id,
    email_original,
    external_center_key,
    external_center_name,
    assigned_at,
    instructor_name,
    raw_record_hash,
    source_row_reference,
    metadata,
)
```

### Campos mínimos para conciliación

* `provider_key`
* Correo.
* Fecha de rutina o fecha válida equivalente.
* Identidad externa o llave técnica de evidencia.

### Regla

El registro representa una evidencia observada.

No representa por sí mismo:

* Estado vigente.
* Cumplimiento.
* Cohorte.
* Alcance de usuario.
* Decisión manual.

---

## 52. Separación extractor–normalizador

Cada provider podrá dividirse internamente en:

```text
Extractor
Normalizer
Validator
```

Ejemplo:

```text
TrainingymRoutineAssignmentsProvider
├── TrainingymBrowserClient
├── TrainingymWorkoutExtractor
├── TrainingymWorkoutNormalizer
└── TrainingymWorkoutValidator
```

### Extractor

Obtiene el material crudo.

### Normalizer

Convierte el material al contrato neutral.

### Validator

Confirma que el resultado sea confiable.

Esta separación permitirá probar la normalización con archivos locales sin abrir navegador.

---

## 53. Provider Gasca de socios nuevos

### Responsabilidad

Obtener el reporte individual de socios nuevos desde Gasca.

No deberá reutilizarse directamente el snapshot agregado existente de KPI de nuevos socios, porque ese snapshot no contiene identidad individual, correo ni fecha individual de venta.

### Entrada

* `date_from`
* `date_to`
* Credenciales de Gasca.
* URL configurada.
* Tipo de reporte configurado.
* Contexto de ejecución.

### Salida

Lista de:

```text
NewMemberRecord
```

### Validaciones mínimas

* El reporte seleccionado coincide con “Ventas Nuevas Socios” o su clave configurada.
* La fecha de corte aplicada coincide con la solicitada.
* El archivo fue descargado correctamente.
* La estructura contiene las columnas requeridas.
* La fecha de venta puede interpretarse.
* La sucursal está presente.
* El correo se conserva sin alteraciones destructivas.
* No se confunde footer o fila de totales con un socio.

### Fecha de corte

El provider no calculará:

```text
datetime.now() - 1 día
```

Recibirá la fecha desde el orquestador.

### Raw

El archivo original se conservará antes de cualquier transformación.

El provider no moverá el raw para convertirlo en un archivo `latest`.

---

## 54. Provider Trainingym de rutinas

### Responsabilidad

Obtener evidencias de rutinas desde el reporte Workout de Trainingym.

El provider encapsulará:

* Playwright.
* Login.
* Credenciales.
* Reintentos.
* Selección de centro.
* Navegación.
* Power BI.
* Fechas.
* Exportación.
* Descarga.
* Validación.
* Normalización.
* Artifacts técnicos.

Ningún otro componente del módulo deberá importar selectores o funciones específicas de Trainingym.

---

## 55. Máquina de estados del login de Trainingym

El login se modelará explícitamente.

Estados:

```text
LOGIN_FORM
CREDENTIALS_FILLED
CREDENTIALS_SUBMITTED
LOGIN_RETRY_REQUIRED
CENTER_SELECTION
CENTER_SELECTED
AUTHENTICATED
REPORT_LOADING
REPORT_READY
BLOCKED
UNEXPECTED_SCREEN
```

### Regla principal

No se considerará exitoso un login solamente porque el clic en `ACCEDER` no produjo una excepción.

El provider deberá observar el estado posterior.

---

## 56. Detección del refresco que borra credenciales

Después de enviar el primer formulario, el provider evaluará:

* URL actual.
* Presencia del campo de usuario.
* Presencia del campo de contraseña.
* Presencia del botón `ACCEDER`.
* Valor actual de los campos.
* Presencia del selector de centro.
* Presencia de señales de sesión autenticada.
* Presencia de challenge.

Se considerará `LOGIN_RETRY_REQUIRED` cuando:

```text
Continúa en login
+
Los campos siguen visibles
+
Los valores fueron borrados o el flujo no avanzó
```

### Comportamiento

1. Registrar el intento fallido.
2. No registrar los valores de las credenciales.
3. Esperar el intervalo configurado.
4. Volver a localizar los campos.
5. Limpiar los campos.
6. Volver a escribir las credenciales.
7. Confirmar que ambos campos contienen valores.
8. Reenviar el formulario.
9. Reevaluar el estado.

---

## 57. Estrategia de reintentos del login

Política preliminar:

### Intento 1

* Página actual.
* Llenado normal.
* Clic o submit primario.

### Intento 2

* Reubicar controles.
* Volver a llenar.
* Envío alternativo controlado.

### Intento 3

* Recargar o volver a abrir la URL de login.
* Volver a llenar.
* Reintentar desde estado limpio.

Después del máximo configurado:

```text
FAILED
error_code = TRAININGYM_LOGIN_FAILED
```

Si se detecta un challenge real:

```text
BLOCKED
error_code = TRAININGYM_AUTH_CHALLENGE
```

No se intentará evadir mecanismos de seguridad.

---

## 58. Selección de centro

La selección de centro será un paso explícito.

Estados:

```text
CENTER_SELECTION
CENTER_SELECTED
```

### Validación

El provider deberá confirmar:

* Que el selector existe.
* Que la opción configurada está disponible.
* Que la opción fue seleccionada.
* Que el valor visible coincide con el centro esperado.
* Que el segundo botón `ACCEDER` quedó habilitado.
* Que el flujo avanzó después del clic.

### Reintentos

La selección de centro tendrá reintentos independientes del login.

No se utilizará un `except` general que convierta cualquier fallo en:

```text
Centro no requerido
```

Se distinguirán:

#### Centro no requerido

El selector no aparece y la sesión ya está autenticada.

#### Centro requerido y seleccionado

La opción se seleccionó y la sesión avanzó.

#### Centro requerido, pero falló

La opción existe o la pantalla exige centro, pero no pudo completarse.

Resultado:

```text
FAILED
error_code = TRAININGYM_CENTER_SELECTION_FAILED
```

---

## 59. Validación de sesión autenticada

La sesión se considerará autenticada únicamente cuando:

* El formulario de contraseña ya no esté activo.
* El flujo haya salido de `/auth` o equivalente.
* El centro requerido esté aplicado.
* El reporte pueda abrirse.
* No exista challenge visible.
* El embed de Power BI sea accesible.

La impresión o log:

```text
Trainingym login OK
```

solo podrá ejecutarse después de esta validación.

---

## 60. Navegación al reporte

El provider deberá:

1. Abrir la URL configurada del reporte Workout.
2. Confirmar que no fue redirigido a login.
3. Cerrar únicamente modales conocidos.
4. Esperar el iframe de Power BI.
5. Confirmar que el frame navegó a una URL válida.
6. Esperar los controles esperados.
7. Aplicar la ventana de fechas.
8. Confirmar que las fechas quedaron aplicadas.
9. Esperar actualización del reporte.
10. Validar la tabla.
11. Exportar.

Una tabla visible antes de aplicar las fechas no se considerará evidencia de que el reporte ya terminó de refrescar.

---

## 61. Ventanas de fechas en Trainingym

El provider recibirá:

```text
date_from
date_to
```

No deberá asumir:

```text
primer día del mes → ayer
```

Esto permitirá:

* Backfill.
* Reejecuciones.
* Ventanas móviles.
* Comparaciones.
* Recuperación de días anteriores.
* Búsqueda de rutinas preexistentes.

### Restricción pendiente

La ventana diaria exacta se definirá en el bloque de scheduling y backfill.

El provider deberá soportar ventanas arbitrarias dentro de las capacidades reales del reporte.

---

## 62. Validación del reporte Trainingym

Antes de aceptar la extracción se validará:

* Presencia del iframe correcto.
* Presencia de los controles de fecha.
* Fechas aplicadas.
* Presencia de columnas esperadas.
* Número de filas interpretable.
* Ausencia de mensaje de error de Power BI.
* Descarga completada.
* Archivo legible.
* Hoja esperada.
* Columnas mínimas.
* Ausencia de archivo HTML renombrado como XLSX.
* Ausencia de sesión vencida durante descarga.

### `SUCCESS_EMPTY`

Solo se utilizará cuando la fuente confirme de manera confiable que no existen registros.

Una tabla que no cargó no será `SUCCESS_EMPTY`.

---

## 63. Exclusión de rutinas automáticas

La normalización inicial conservará la regla vigente de excluir registros cuyo técnico corresponda a una asignación automática.

La comparación será normalizada y configurable.

Ejemplos:

```text
Automático
Automatico
automat...
```

### Regla

La exclusión deberá ocurrir en el normalizador de Trainingym, no dentro del servicio de reconciliación.

El resultado rechazado o excluido deberá contarse para observabilidad.

Se registrará como:

```text
excluded_reason = AUTOMATIC_ROUTINE
```

No se generará evidencia operativa con esos registros.

---

## 64. Múltiples rutinas por correo

El provider devolverá todas las evidencias válidas identificables.

No deberá reducir inmediatamente el dataset a:

```text
una fila por correo
```

El dominio será responsable de determinar:

* Primera rutina.
* Última rutina.
* Instructor vigente.
* Tipo de asignación.

Esto evita perder historial.

Cuando la fuente no proporcione un ID de rutina, se utilizará una llave técnica determinista.

---

## 65. Validación del correo

Los providers conservarán:

* Correo original.
* Correo normalizado.
* Referencia de fila.
* Hash del registro.

La normalización compartida deberá residir en una utilidad común del dominio, no duplicada dentro de cada provider.

Los providers no deberán:

* Eliminar puntos.
* Corregir dominios.
* Inferir correos.
* Cambiar `+tags`.
* Fusionar registros.

---

## 66. Resolución de sucursales y centros

Los providers devolverán valores externos:

```text
external_branch_key
external_branch_name
external_center_key
external_center_name
```

Un servicio común resolverá esos valores hacia:

```text
sucursal_id
```

### Regla

Los providers no utilizarán nombres externos como fuente de autorización.

### Alias

La resolución deberá utilizar:

* Catálogo canónico de sucursales.
* Alias existentes.
* Mapeos explícitos por proveedor.
* Historial de cambios, cuando aplique.

Si no puede resolverse:

```text
SUCURSAL_NO_RESUELTA
```

o:

```text
CENTRO_TRAININGYM_NO_RESUELTO
```

según el caso.

---

## 67. Archivos raw

Cada extracción que produzca un archivo deberá conservar primero el original.

Metadata mínima:

* Provider.
* Dataset.
* Ventana.
* Fecha de negocio.
* Nombre original.
* Tamaño.
* SHA-256.
* Fecha de descarga.
* Provider run.
* Estado de validación.

### Regla

El raw no se moverá para crear un archivo `latest`.

Si se requiere una copia de trabajo, se copiará o se generará dentro del directorio temporal de la ejecución.

### Almacenamiento

El contrato de providers no obliga a Warehouse, pero deberá devolver el artifact para que el orquestador pueda:

* Guardarlo temporalmente.
* Publicarlo en Warehouse.
* Aplicar política de retención.
* Relacionarlo con el provider run.

---

## 68. Artifacts de diagnóstico

Artifacts posibles:

* Screenshot.
* HTML sanitizado.
* Trace Playwright.
* Metadata del estado.
* Lista de frames.
* Selectores encontrados.
* Archivo descargado inválido.
* Resumen de validación.

Nunca deberán contener deliberadamente:

* Usuario.
* Contraseña.
* Cookies.
* Tokens.
* Headers de autorización.
* Datos completos innecesarios del socio.
* Valores de campos secretos.

La retención será configurable.

---

## 69. Hashes

Se calcularán al menos dos hashes.

### `content_hash`

Hash del artifact completo.

Permite identificar si una extracción es idéntica.

### `raw_record_hash`

Hash determinista de cada fila normalizada o registro fuente.

Permite detectar:

* Repetición.
* Cambios de origen.
* Correcciones.
* Duplicados.

El orden de columnas y la serialización utilizada para el hash deberán ser estables.

---

## 70. Registros rechazados

Los providers no deberán descartar silenciosamente filas inválidas.

Cada rechazo incluirá:

```python
RejectedProviderRecord(
    provider_key,
    dataset_key,
    source_row_reference,
    rejection_code,
    rejection_message,
    raw_record_hash,
    sanitized_payload,
)
```

Códigos preliminares:

```text
MISSING_REQUIRED_COLUMN
INVALID_EMAIL
INVALID_DATE
MISSING_BRANCH
INVALID_FILE_STRUCTURE
AUTOMATIC_ROUTINE
DUPLICATE_SOURCE_ROW
UNSUPPORTED_RECORD
```

`AUTOMATIC_ROUTINE` podrá contabilizarse como exclusión esperada y no necesariamente como error.

---

## 71. Política de errores

Errores comunes:

```text
PROVIDER_CONFIGURATION_ERROR
PROVIDER_AUTH_FAILED
PROVIDER_AUTH_CHALLENGE
PROVIDER_NAVIGATION_FAILED
PROVIDER_REPORT_NOT_READY
PROVIDER_DOWNLOAD_FAILED
PROVIDER_FILE_INVALID
PROVIDER_SCHEMA_CHANGED
PROVIDER_TIMEOUT
PROVIDER_PARTIAL_RESULT
PROVIDER_UNKNOWN_ERROR
```

Errores específicos podrán utilizar prefijo:

```text
GASCA_...
TRAININGYM_...
```

Los mensajes persistidos deberán estar sanitizados.

---

## 72. Reintentos técnicos

Los reintentos deberán distinguir:

### Errores reintentables

* Timeout temporal.
* Formulario refrescado.
* Navegación incompleta.
* Power BI todavía cargando.
* Descarga no iniciada.
* Error de red temporal.

### Errores no reintentables inmediatos

* Credenciales faltantes.
* Columnas incompatibles.
* Centro configurado inexistente.
* Challenge persistente.
* Acceso denegado.
* Archivo estructuralmente incompatible.

Los reintentos no deberán ocultar que hubo intentos fallidos.

Cada intento se registrará en el provider run.

---

## 73. Fallo parcial de proveedores

Los datasets son independientes:

```text
new_members
routine_assignments
```

### Gasca exitoso y Trainingym fallido

* Los socios nuevos podrán persistirse.
* No se declarará que el pipeline completo fue exitoso.
* El pipeline quedará `PARTIAL`.
* Los socios previamente clasificados conservarán su estado.
* Los socios nuevos no deberán marcarse automáticamente como pendientes confirmados usando información desactualizada.
* Se abrirá o asociará una incidencia de frescura, por ejemplo:

```text
ROUTINE_PROVIDER_UNAVAILABLE
```

* La vista deberá poder mostrar la última sincronización exitosa.

### Trainingym exitoso y Gasca fallido

* Las evidencias podrán persistirse.
* Podrán asociarse a socios existentes.
* No se incorporarán socios nuevos de la ventana fallida.
* El pipeline quedará `PARTIAL`.

### Ambos fallidos

* No habrá reconciliación masiva.
* El pipeline quedará `FAILED`.
* Los estados existentes no se modificarán.

---

## 74. Frescura de datos

Cada dataset deberá exponer:

* Última ejecución exitosa.
* Última fecha cubierta.
* Ventana de la última extracción.
* Estado actual.
* Advertencias.

La ausencia de una extracción reciente no deberá interpretarse como:

```text
No existen rutinas
```

La API y la vista deberán diferenciar:

* Sin rutina confirmada con datos vigentes.
* Fuente de rutinas desactualizada.
* Provider fallido.
* Registro en incidencia.

---

## 75. Provider futuro de rutinas Gasca

`GascaRoutineAssignmentsProvider` deberá implementar el mismo contrato:

```text
RoutineAssignmentRecord
```

Podrá utilizar:

* API.
* Reporte.
* Archivo.
* Consulta interna autorizada.

El dominio no cambiará.

Solo podrán cambiar:

* Configuración.
* Provider activo.
* Mapeos.
* Identidades externas.
* Validadores particulares.

---

## 76. Modo sombra

El módulo soportará conceptualmente:

```text
primary_provider
shadow_provider
```

El provider sombra:

* Ejecutará la extracción.
* Normalizará registros.
* Registrará resultados.
* No modificará el estado vigente en su primera etapa.
* Permitirá comparar cobertura.

Comparaciones:

* Coinciden ambos.
* Solo primary.
* Solo shadow.
* Diferencia de fecha.
* Diferencia de instructor.
* Diferencia de centro.
* Registro no conciliable.

El modo sombra no se activará hasta que el provider Gasca de rutinas exista.

---

## 77. Precedencia futura entre providers

Durante una transición, la fuente de evidencia deberá conservar:

```text
provider_key
```

No se mezclará silenciosamente el origen.

Regla preliminar:

* Una evidencia válida de cualquiera de los providers autorizados podrá probar que existe rutina.
* La fuente primaria determinará la operación normal.
* La fuente sombra no cambiará estado hasta ser promovida.
* Los conflictos de fechas o identidad se registrarán.
* La precedencia definitiva se configurará y auditará.

---

## 78. Configuración y secretos

Configuración no secreta:

* URLs.
* Nombre del provider.
* Centro.
* Timeouts.
* Máximo de reintentos.
* Ventanas.
* Directorios de artifacts.
* Flags de diagnóstico.

Secretos:

* Usuario.
* Contraseña.
* Tokens.
* Cookies persistentes, cuando se autoricen.

Los secretos:

* No estarán en Angular.
* No estarán en el repositorio.
* No se imprimirán.
* No se incluirán en artifacts.
* No se pasarán como argumentos visibles del proceso.
* Se cargarán desde variables o mecanismo de secretos del servidor.

---

## 79. Navegador en producción

La implementación productiva utilizará Chromium disponible dentro de la imagen backend o una imagen RPA derivada.

No dependerá de:

```text
channel="msedge"
```

como requisito productivo.

El uso de Edge podrá mantenerse únicamente para pruebas locales si se conserva compatibilidad.

Antes de activar scheduling se deberá validar en el contenedor real:

* Inicio de Chromium.
* Xvfb, cuando aplique.
* Login.
* Selección de centro.
* Power BI.
* Descarga.
* Escritura de artifacts.
* Consumo de memoria.
* Terminación limpia del proceso.

---

## 80. Limpieza de recursos

Cada ejecución deberá cerrar, incluso ante error:

* Página.
* Contexto.
* Navegador.
* Archivos temporales no requeridos.
* Handles.
* Sesión SQLAlchemy gestionada por el orquestador.

El provider no deberá dejar procesos Chromium huérfanos.

La limpieza se realizará mediante bloques `finally` o equivalentes.

---

## 81. Contratos de prueba

Cada provider deberá aprobar pruebas de contrato comunes.

### New Members Provider

* Devuelve ventana solicitada.
* Devuelve registros normalizados.
* Conserva correo original.
* No calcula estado.
* No escribe en tablas operativas.
* Distingue vacío válido de fallo.
* Genera hash estable.
* Reporta filas rechazadas.

### Routine Assignments Provider

* Devuelve todas las evidencias identificables.
* No reduce a una sola fila por correo.
* Excluye rutinas automáticas según regla.
* Conserva fecha e instructor.
* Distingue vacío válido de fallo.
* No modifica estados.
* Genera identidad estable.
* Reporta ambigüedades o rechazos.

---

## 82. Pruebas mínimas de Trainingym

* Login exitoso en primer intento.
* Login refresca y borra campos.
* Segundo intento exitoso.
* Tres intentos fallidos.
* Selector de centro requerido.
* Selector de centro no requerido.
* Centro configurado inexistente.
* Segundo `ACCEDER` no avanza.
* Sesión ya autenticada.
* Redirección inesperada a login.
* Challenge detectado.
* Power BI tarda en cargar.
* Iframe nunca aparece.
* Fechas no quedan aplicadas.
* Tabla vacía válida.
* Tabla no cargada.
* Modal de exportación.
* Descarga fallida.
* Archivo inválido.
* Ejecución repetida.
* Cierre limpio del navegador.

---

## 83. Pruebas mínimas de Gasca

* Login exitoso.
* Pantalla intermedia “Ir a Inicio”.
* Tipo de reporte localizado.
* Tipo de reporte no disponible.
* Fecha de corte aplicada.
* Reporte con filas.
* Reporte vacío válido.
* Tabla no cargada.
* Descarga exitosa.
* Columnas faltantes.
* Footer eliminado correctamente.
* Fecha inválida.
* Sucursal vacía.
* Correo vacío.
* Archivo repetido.
* Archivo cambiado para la misma ventana.

---

## 84. Decisiones cerradas en este bloque

* El pipeline utilizará contratos neutrales.
* Existirán providers separados para socios y rutinas.
* Los providers no modificarán estados.
* Las fechas siempre serán parámetros explícitos.
* Trainingym quedará completamente encapsulado.
* El login será una máquina de estados.
* El refresco que borra credenciales tendrá reintento específico.
* La selección de centro será validada y reintentada.
* Un challenge se detectará, no se intentará evadir.
* El raw se conservará antes de transformar.
* Las rutinas automáticas se excluirán en el normalizador.
* Trainingym devolverá todas las evidencias, no solo la última por correo.
* Los providers devolverán registros rechazados.
* Una fuente fallida no se interpretará como ausencia de datos.
* Se soportará modo sombra para la transición futura.
* Producción no dependerá de Edge.
* Los secretos permanecerán fuera del código y los artifacts.

---

## 85. Pendientes antes de implementar providers

1. Identificar el reporte individual definitivo de socios nuevos en Gasca.
2. Confirmar sus columnas reales.
3. Confirmar si Gasca entrega un ID estable.
4. Confirmar las columnas reales del Excel Workout.
5. Confirmar si existe ID de rutina.
6. Confirmar la semántica exacta de la fecha de Trainingym.
7. Confirmar si el reporte puede extraer ventanas históricas amplias.
8. Confirmar si un reporte de Trainingym cubre todos los centros o uno solo.
9. Confirmar el catálogo de centros Trainingym.
10. Confirmar el mapeo a sucursales canónicas.
11. Definir la ventana inicial de backfill.
12. Definir la retención de raw y artifacts.
13. Definir el máximo de reintentos.
14. Probar Chromium dentro del contenedor de producción.
15. Definir qué incidencias de frescura serán bloqueantes.



# Bloque 4: API, permisos y alcance jerárquico

**Versión:** 0.4
**Estado:** Propuesta para validación
**Dependencias:**

* Bloque 1 — modelo de datos, estados e idempotencia
* Bloque 2 — servicios de dominio y transiciones
* Bloque 3 — providers Gasca y Trainingym

**Alcance:** API REST, autorización backend, scopes, filtros, paginación, indicadores, acciones y exportación.
**Fuera de alcance:** Implementación Angular, scheduling, Docker y despliegue.

---

## 86. Objetivo del bloque

Definir una API operativa que permita:

* Consultar socios autorizados.
* Filtrar por cohorte, estado, sucursal y región.
* Obtener indicadores consistentes.
* Consultar el detalle y el historial.
* Registrar y revertir `NO_DESEA_RUTINA`.
* Consultar incidencias.
* Exportar la información autorizada.
* Aplicar los tres niveles jerárquicos de Suite Ultra.
* Evitar que frontend, routes y exportaciones implementen reglas de alcance diferentes.

La regla principal será:

> Listado, detalle, indicadores, acciones y exportación deberán partir de la misma política de autorización y del mismo query base autorizado.

---

## 87. Blueprint y prefijo provisional

Blueprint provisional:

```text
routine_control_bp
```

Prefijo provisional:

```text
/api/routine-control
```

Los nombres exactos podrán ajustarse a las convenciones finales del repositorio, pero el módulo deberá mantenerse separado de:

* Tickets.
* Warehouse.
* Track.
* RPA.
* Internal Documents.

---

## 88. Autenticación

Todos los endpoints requerirán una sesión JWT válida.

La route deberá cargar al usuario vigente desde PostgreSQL y no confiar únicamente en los claims almacenados en el token.

La información vigente a consultar incluirá:

* Usuario activo.
* Rol actual.
* Sucursal primaria.
* Pool de sucursales.
* Departamento, cuando aplique.
* Grants o permisos particulares.
* Estado activo o bloqueado.
* Capacidades específicas del módulo.

Los claims podrán servir para identificar inicialmente al usuario, pero la autorización final se reconstruirá desde la base de datos.

---

## 89. Módulo de permisos

El módulo deberá registrarse en el catálogo central de permisos.

Clave provisional:

```text
ROUTINE_CONTROL
```

Acciones iniciales:

```text
VIEW
VIEW_ALL
VIEW_HISTORY
MARK_NO_ROUTINE
REVOKE_NO_ROUTINE
VIEW_INCIDENTS
RESOLVE_INCIDENTS
INVALIDATE_EVIDENCE
EXPORT
RUN_MANUAL_PIPELINE
VIEW_PIPELINE_RUNS
```

Las acciones podrán mapearse a routes concretas mediante el catálogo existente de permisos.

No se deberá crear un sistema paralelo de permisos.

---

## 90. Roles y capacidades

Los roles definirán capacidades por defecto, pero el contrato técnico deberá permitir grants particulares.

### 90.1. `GERENTE`

Capacidades iniciales:

```text
VIEW
VIEW_HISTORY
MARK_NO_ROUTINE
REVOKE_NO_ROUTINE
EXPORT
```

Alcance:

```text
Una sucursal autorizada
```

No podrá:

* Consultar otras sucursales.
* Resolver incidencias técnicas globales.
* Invalidar evidencias.
* Ejecutar pipelines.
* Acceder a credenciales o artifacts técnicos.

### 90.2. `GERENTE_REGIONAL`

Capacidades iniciales:

```text
VIEW
VIEW_HISTORY
MARK_NO_ROUTINE
REVOKE_NO_ROUTINE
EXPORT
```

Alcance:

```text
Pool vigente de sucursales
```

Podrá consultar:

* Consolidado regional.
* Desglose por sucursal.
* Detalle de socios dentro de su pool.

### 90.3. Roles globales autorizados

Los roles globales exactos se resolverán contra el catálogo vigente de Suite.

Capacidades posibles:

```text
VIEW
VIEW_ALL
VIEW_HISTORY
MARK_NO_ROUTINE
REVOKE_NO_ROUTINE
VIEW_INCIDENTS
RESOLVE_INCIDENTS
INVALIDATE_EVIDENCE
EXPORT
VIEW_PIPELINE_RUNS
RUN_MANUAL_PIPELINE
```

No se utilizará un listado nuevo de roles globales duplicado dentro del módulo.

La política deberá apoyarse en:

* Roles existentes.
* Scope resuelto.
* Grants.
* Acciones del módulo.

---

## 91. Contexto de autorización

Servicio provisional:

```text
RoutineControlAuthorizationService
```

Funciones conceptuales:

```python
get_context(user_id)
assert_can_access_module(context)
assert_can_view_member(context, member)
assert_can_update_member(context, member, action)
assert_can_export(context, filters)
assert_can_view_incidents(context)
assert_can_resolve_incident(context, incident)
assert_can_invalidate_evidence(context, evidence)
```

El contexto incluirá:

```python
RoutineControlAccessContext(
    user_id,
    role,
    is_global,
    allowed_branch_ids,
    capabilities,
)
```

### Regla

Las routes no deberán repetir manualmente expresiones como:

```python
if user.role == "GERENTE":
    ...
elif user.role == "GERENTE_REGIONAL":
    ...
```

La resolución deberá centralizarse.

---

## 92. Query autorizado base

Servicio o helper provisional:

```text
RoutineControlQueryService
```

Función conceptual:

```python
build_authorized_member_query(
    access_context,
    filters,
)
```

El query base aplicará:

1. Scope autorizado.
2. Filtros funcionales.
3. Búsqueda.
4. Orden.
5. Paginación, cuando aplique.

Este mismo query será reutilizado para:

* Listado.
* Conteos.
* Indicadores.
* Exportación.
* Validación de acceso al detalle.
* Selección masiva futura.

No se construirá un query distinto para exportar.

---

## 93. Reglas de scope

### 93.1. Usuario global

```text
is_global = true
```

Podrá consultar todas las sucursales autorizadas por su capacidad.

### 93.2. Gerente regional

El filtro obligatorio será:

```sql
member.sucursal_id IN allowed_branch_ids
```

Aunque solicite manualmente otra sucursal, el backend no la devolverá.

### 93.3. Gerente

El filtro obligatorio será su sucursal efectiva autorizada.

### 93.4. Usuario sin sucursal válida

Si el rol requiere sucursal y no tiene una asignación válida:

```text
403 ROUTINE_CONTROL_SCOPE_NOT_CONFIGURED
```

No se utilizará un fallback global.

### 93.5. Filtro solicitado por sucursal

Si el usuario solicita:

```text
sucursal_id = X
```

el backend deberá validar que `X` pertenezca a su scope.

Si no pertenece:

```text
403 ROUTINE_CONTROL_BRANCH_FORBIDDEN
```

No se ignorará silenciosamente el filtro.

---

## 94. Alcance regional

La región no será por sí misma la fuente final de autorización.

El backend resolverá primero:

```text
allowed_branch_ids
```

Después podrá agrupar esas sucursales por región.

Esto evita que:

* Un nombre de región otorgue acceso.
* Un cambio organizacional amplíe permisos sin actualizar el pool.
* Un usuario regional vea sucursales fuera de su asignación.

La región será un atributo de agrupación y filtro, no la llave primaria del permiso.

---

## 95. Endpoints iniciales

### 95.1. Contexto del módulo

```http
GET /api/routine-control/context
```

Devuelve:

* Capacidades.
* Alcance.
* Sucursales autorizadas.
* Regiones disponibles.
* Cohortes disponibles.
* Estado de sincronización.
* Valores permitidos para filtros y acciones.

Respuesta conceptual:

```json
{
  "capabilities": {
    "view": true,
    "mark_no_routine": true,
    "revoke_no_routine": true,
    "export": true,
    "view_incidents": false
  },
  "scope": {
    "type": "regional",
    "branch_ids": [1, 2, 3]
  },
  "available_filters": {
    "cohorts": ["2026-07-01", "2026-06-01"],
    "statuses": [
      "SIN_RUTINA",
      "CON_RUTINA",
      "NO_DESEA_RUTINA"
    ]
  },
  "freshness": {
    "new_members_last_success_at": "...",
    "routines_last_success_at": "..."
  }
}
```

El frontend utilizará este contexto para construir la interfaz, pero cada endpoint seguirá validando permisos.

---

### 95.2. Listado de socios

```http
GET /api/routine-control/members
```

Parámetros posibles:

```text
page
page_size
cohort_month
status
classification_status
sucursal_id
region_id
sale_date_from
sale_date_to
days_without_routine_min
days_without_routine_max
instructor
assignment_type
provider_key
incident_code
search
sort_by
sort_direction
as_of_date
```

Respuesta:

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 0,
    "total_pages": 0
  },
  "applied_filters": {},
  "freshness": {}
}
```

La paginación será de servidor.

No existirá un parámetro equivalente a:

```text
no_paging=true
```

para la operación normal.

---

### 95.3. Indicadores

```http
GET /api/routine-control/summary
```

Aceptará los mismos filtros funcionales que el listado.

Respuesta conceptual:

```json
{
  "total_new_members": 245,
  "with_routine": 182,
  "without_routine": 48,
  "does_not_want_routine": 15,
  "evaluable_members": 230,
  "assignment_pct": 79.13,
  "does_not_want_pct": 6.12,
  "average_assignment_days": 2.4,
  "median_assignment_days": 2,
  "open_incidents": 3,
  "freshness": {}
}
```

Los indicadores deberán calcularse sobre el mismo universo autorizado y filtrado que el listado.

---

### 95.4. Desglose jerárquico

```http
GET /api/routine-control/breakdown
```

Parámetros:

```text
group_by=region|branch|cohort|status
```

Permitirá construir:

* Consolidado nacional.
* Consolidado regional.
* Comparativo por sucursal.
* Evolución por cohorte.

El backend limitará los grupos al alcance autorizado.

---

### 95.5. Detalle de socio

```http
GET /api/routine-control/members/<member_id>
```

Devuelve:

* Datos vigentes.
* Estado.
* Cohorte.
* Sucursal.
* Evidencias.
* Decisión activa.
* Incidencias.
* Historial.
* Capacidades aplicables a ese registro.
* `status_version`.

Respuesta conceptual:

```json
{
  "member": {},
  "evidences": [],
  "active_decision": null,
  "incidents": [],
  "status_history": [],
  "capabilities": {
    "mark_no_routine": true,
    "revoke_no_routine": false
  },
  "status_version": 4
}
```

El detalle deberá validarse mediante el mismo scope autorizado del listado.

---

### 95.6. Marcar “No desea rutina”

```http
POST /api/routine-control/members/<member_id>/no-routine-decision
```

Payload:

```json
{
  "reason_code": "OWN_ROUTINE",
  "notes": "El socio indicó que ya sigue un programa externo.",
  "expected_status_version": 4
}
```

La route:

1. Autentica.
2. Carga contexto.
3. Valida alcance.
4. Construye el comando.
5. Invoca `RoutineDecisionService`.
6. Devuelve el estado efectivo resultante.

Respuesta conceptual:

```json
{
  "member_id": 123,
  "decision_id": 456,
  "previous_status": "SIN_RUTINA",
  "current_status": "NO_DESEA_RUTINA",
  "status_version": 5
}
```

---

### 95.7. Revertir decisión

```http
POST /api/routine-control/members/<member_id>/no-routine-decision/revoke
```

Payload:

```json
{
  "decision_id": 456,
  "revocation_reason": "El socio cambió de opinión.",
  "expected_status_version": 5
}
```

Respuesta:

```json
{
  "member_id": 123,
  "previous_status": "NO_DESEA_RUTINA",
  "current_status": "SIN_RUTINA",
  "status_version": 6
}
```

Si existe rutina válida, el estado resultante será `CON_RUTINA`.

---

### 95.8. Historial

```http
GET /api/routine-control/members/<member_id>/history
```

Podrá paginar eventos cuando el historial sea largo.

El usuario deberá tener:

```text
VIEW_HISTORY
```

y alcance sobre el socio.

---

### 95.9. Incidencias

```http
GET /api/routine-control/incidents
```

Filtros:

```text
status
severity
incident_code
sucursal_id
provider_key
cohort_month
created_from
created_to
search
page
page_size
```

Solo estará disponible para usuarios con:

```text
VIEW_INCIDENTS
```

El scope por sucursal seguirá aplicándose, salvo capacidades globales específicas.

---

### 95.10. Resolver incidencia

```http
POST /api/routine-control/incidents/<incident_id>/resolve
```

Payload:

```json
{
  "resolution_notes": "Correo corregido y registro conciliado.",
  "expected_member_status_version": 3
}
```

La resolución deberá:

1. Validar permiso.
2. Aplicar la corrección autorizada, cuando corresponda.
3. Resolver la incidencia.
4. Reconciliar al socio.
5. Crear auditoría.
6. Confirmar todo en una transacción.

No se resolverá una incidencia únicamente cambiando su estado visual si la causa continúa activa.

---

### 95.11. Invalidar evidencia

```http
POST /api/routine-control/evidences/<evidence_id>/invalidate
```

Payload:

```json
{
  "reason": "Registro duplicado confirmado.",
  "expected_status_version": 7
}
```

Requiere:

```text
INVALIDATE_EVIDENCE
```

La invalidación deberá:

* Conservar la evidencia.
* Guardar usuario y motivo.
* Reconciliar el socio.
* Registrar evento.
* Aplicar control de concurrencia.

No será una acción disponible para gerentes por defecto.

---

### 95.12. Ejecuciones del pipeline

```http
GET /api/routine-control/pipeline-runs
GET /api/routine-control/pipeline-runs/<run_id>
```

Requiere:

```text
VIEW_PIPELINE_RUNS
```

Devuelve:

* Estado.
* Ventanas.
* Providers.
* Conteos.
* Errores sanitizados.
* Frescura.
* Referencias de artifacts permitidos.

Las credenciales y secretos nunca se expondrán.

---

### 95.13. Ejecución manual

```http
POST /api/routine-control/pipeline-runs
```

Payload conceptual:

```json
{
  "business_date": "2026-07-13",
  "generation_mode": "MANUAL",
  "date_from": "2026-07-01",
  "date_to": "2026-07-13",
  "providers": [
    "gasca:new_members",
    "trainingym:routine_assignments"
  ]
}
```

Requiere:

```text
RUN_MANUAL_PIPELINE
```

La route no ejecutará Playwright dentro del request.

La acción deberá:

* Crear una solicitud o run `PENDING`.
* Entregar un identificador.
* Ser procesada por el worker.
* Evitar ejecución concurrente incompatible.

Respuesta:

```http
202 Accepted
```

---

## 96. Filtros funcionales

### 96.1. Cohorte

Formato:

```text
YYYY-MM-01
```

El backend validará que corresponda al primer día del mes.

### 96.2. Estado

Valores:

```text
SIN_RUTINA
CON_RUTINA
NO_DESEA_RUTINA
```

### 96.3. Clasificación

Valores:

```text
CLASSIFIED
INCIDENT
```

### 96.4. Fecha de corte

`as_of_date` permitirá calcular:

* Días sin rutina.
* Indicadores históricos.
* Exportaciones con corte explícito.

Si no se proporciona, se utilizará la fecha de negocio vigente en `America/Tijuana`.

La respuesta deberá informar qué fecha se utilizó.

---

## 97. Búsqueda

El parámetro:

```text
search
```

podrá buscar inicialmente por:

* Nombre.
* Correo original.
* Correo normalizado.

La búsqueda deberá:

* Aplicarse dentro del scope autorizado.
* Tener longitud mínima configurable.
* Escapar caracteres.
* No permitir SQL libre.
* No buscar indiscriminadamente dentro de JSONB.

Podrán añadirse índices de búsqueda cuando el volumen lo requiera.

---

## 98. Ordenamiento

Campos iniciales permitidos:

```text
sale_date
cohort_month
member_name
sucursal
current_status
days_without_routine
first_routine_at
latest_routine_at
updated_at
```

No se aceptará un nombre arbitrario de columna recibido directamente desde el cliente.

Se utilizará un mapa seguro:

```python
ALLOWED_SORT_FIELDS = {
    ...
}
```

Orden predeterminado para pendientes:

```text
days_without_routine DESC
sale_date ASC
member_name ASC
```

Orden predeterminado general:

```text
sale_date DESC
id DESC
```

---

## 99. Paginación

Parámetros:

```text
page >= 1
page_size
```

Tamaño predeterminado:

```text
50
```

Máximo inicial:

```text
200
```

El backend devolverá:

* Total.
* Página actual.
* Tamaño.
* Total de páginas.
* Si existe página siguiente.

El listado no deberá cargar todo el histórico en memoria.

---

## 100. Indicadores y query compartido

Los indicadores no deberán calcularse con datos ya paginados.

Proceso:

1. Construir query autorizado y filtrado.
2. Derivar query de agregación.
3. Calcular indicadores en PostgreSQL.
4. Derivar query paginado para las filas.
5. Devolver resultados consistentes.

La pantalla podrá llamar por separado a:

```text
/members
/summary
```

pero ambos deberán usar la misma normalización de filtros.

---

## 101. Capacidades por registro

El detalle podrá devolver capacidades específicas:

```json
{
  "can_mark_no_routine": true,
  "can_revoke_no_routine": false,
  "can_invalidate_evidence": false,
  "can_resolve_incident": false,
  "can_view_history": true
}
```

Estas capacidades dependerán de:

* Capacidad del usuario.
* Scope.
* Estado vigente.
* Existencia de decisión activa.
* Incidencias.
* Concurrencia.
* Reglas del dominio.

Aunque el frontend oculte una acción, la route volverá a validarla.

---

## 102. Reglas para “No desea rutina”

### Marcar

Se permitirá cuando:

* El usuario tenga `MARK_NO_ROUTINE`.
* El socio esté dentro de su scope.
* No exista otra decisión activa equivalente.
* El payload incluya motivo válido.
* `expected_status_version` coincida.

Aunque el estado sea `CON_RUTINA`, la acción deberá definirse cuidadosamente.

Regla inicial recomendada:

```text
No permitir una nueva declaración NO_DESEA_RUTINA
cuando el estado vigente sea CON_RUTINA.
```

Motivo:

* Ya existe evidencia objetiva de rutina.
* La declaración no modificaría el estado.
* Podría confundir la operación.

La decisión histórica previa sí podrá permanecer registrada.

### Revertir

Se permitirá cuando:

* Exista decisión activa.
* El usuario tenga `REVOKE_NO_ROUTINE`.
* El socio esté dentro de su scope.
* La versión coincida.

---

## 103. Motivos controlados

Endpoint de catálogos:

```http
GET /api/routine-control/catalogs
```

Podrá devolver:

```json
{
  "no_routine_reasons": [
    {
      "code": "NOT_INTERESTED",
      "label": "No está interesado",
      "requires_notes": false
    },
    {
      "code": "OWN_ROUTINE",
      "label": "Ya cuenta con rutina propia",
      "requires_notes": false
    },
    {
      "code": "EXTERNAL_TRAINER",
      "label": "Tiene entrenador externo",
      "requires_notes": false
    },
    {
      "code": "MEDICAL_LIMITATION",
      "label": "Limitación médica o indicación profesional",
      "requires_notes": false
    },
    {
      "code": "GROUP_CLASSES_ONLY",
      "label": "Solo utiliza clases o actividades grupales",
      "requires_notes": false
    },
    {
      "code": "OTHER",
      "label": "Otro",
      "requires_notes": true
    }
  ]
}
```

El backend validará los códigos.

No confiará en el texto recibido desde Angular.

---

## 104. Exportación

### 104.1. Exportar vista

```http
GET /api/routine-control/export
```

Aceptará los mismos filtros del listado.

Parámetros adicionales:

```text
export_mode=current_view|monthly_full
format=xlsx
```

### 104.2. Regla de autorización

La exportación reutilizará:

```text
build_authorized_member_query()
```

No se realizará una consulta global seguida de filtrado en Python.

### 104.3. Vista actual

Generará únicamente los registros correspondientes a:

* Scope.
* Pestaña o estado.
* Cohorte.
* Sucursal.
* Región.
* Filtros.
* Fecha de corte.

### 104.4. Reporte mensual completo

Requerirá una cohorte explícita.

Pestañas:

```text
Resumen
Nuevos sin rutina
Nuevos con rutina
No desean rutina
Incidencias
```

### 104.5. Límites

La primera versión podrá generar la exportación de manera síncrona si el volumen autorizado está dentro de un límite configurable.

Si excede el límite:

```text
413 o 422 EXPORT_TOO_LARGE
```

o podrá crearse una solicitud asíncrona en una fase posterior.

No se deberá mantener ocupado Gunicorn durante una exportación excesivamente grande.

### 104.6. Auditoría

Cada exportación registrará:

* Usuario.
* Scope.
* Filtros.
* Cohorte.
* Cantidad de registros.
* Fecha de corte.
* Timestamp.
* Resultado.
* Hash opcional del archivo.

---

## 105. Frescura en respuestas

Listado, indicadores y detalle deberán poder incluir:

```json
{
  "freshness": {
    "new_members": {
      "status": "current",
      "last_success_at": "...",
      "covered_through": "2026-07-13"
    },
    "routine_assignments": {
      "status": "stale",
      "last_success_at": "...",
      "covered_through": "2026-07-12"
    }
  }
}
```

Estados posibles:

```text
current
stale
failed
partial
never_run
```

La interfaz deberá poder advertir:

> La fuente de rutinas no se actualizó al último corte.

Esto evitará interpretar una falla de Trainingym como ausencia de rutinas.

---

## 106. Códigos HTTP

### `200 OK`

Consulta o acción idempotente completada.

### `201 Created`

Nueva decisión o recurso creado.

### `202 Accepted`

Pipeline manual aceptado para ejecución por worker.

### `400 Bad Request`

Formato inválido.

### `401 Unauthorized`

JWT ausente o inválido.

### `403 Forbidden`

Usuario autenticado sin permiso o fuera de scope.

### `404 Not Found`

Recurso inexistente dentro del universo autorizado.

Para evitar filtrar información, un socio fuera de scope podrá responder `404` en endpoints de detalle.

### `409 Conflict`

Versión desactualizada o transición concurrente.

### `422 Unprocessable Entity`

Payload válido sintácticamente, pero incompatible con la regla de negocio.

### `500 Internal Server Error`

Fallo no controlado, con mensaje sanitizado.

### `503 Service Unavailable`

Servicio o provider no disponible para una operación que lo requiera.

---

## 107. Códigos de error funcionales

Formato conceptual:

```json
{
  "error": {
    "code": "ROUTINE_CONTROL_CONFLICT",
    "message": "El registro cambió. Actualiza la información e intenta nuevamente.",
    "details": {}
  }
}
```

Códigos iniciales:

```text
ROUTINE_CONTROL_ACCESS_DENIED
ROUTINE_CONTROL_SCOPE_NOT_CONFIGURED
ROUTINE_CONTROL_BRANCH_FORBIDDEN
ROUTINE_CONTROL_MEMBER_NOT_FOUND
ROUTINE_CONTROL_CONFLICT
ROUTINE_CONTROL_INVALID_FILTER
ROUTINE_CONTROL_INVALID_COHORT
ROUTINE_CONTROL_INVALID_REASON
ROUTINE_CONTROL_DECISION_ALREADY_ACTIVE
ROUTINE_CONTROL_DECISION_NOT_ACTIVE
ROUTINE_CONTROL_ACTION_NOT_ALLOWED
ROUTINE_CONTROL_INCIDENT_NOT_FOUND
ROUTINE_CONTROL_EVIDENCE_NOT_FOUND
ROUTINE_CONTROL_EXPORT_TOO_LARGE
ROUTINE_CONTROL_PIPELINE_ALREADY_RUNNING
```

Los mensajes no deberán exponer SQL, rutas del servidor ni secretos.

---

## 108. Serialización

La serialización deberá realizarse mediante funciones o schemas explícitos.

No se devolverá automáticamente:

```python
model.__dict__
```

La respuesta deberá controlar:

* Campos personales.
* Fechas.
* Capacidades.
* Metadata.
* Campos técnicos.
* Datos sensibles.

Los timestamps se devolverán en ISO 8601 con zona.

Las fechas de negocio se devolverán como:

```text
YYYY-MM-DD
```

---

## 109. Datos personales por alcance

La primera versión podrá mostrar:

* Nombre.
* Correo.
* Sucursal.
* Fechas operativas.
* Estado.
* Instructor.

El contrato técnico deberá revisar si todos los roles pueden exportar correo completo.

Capacidad futura posible:

```text
EXPORT_PII
```

Si se requiere, la API podrá:

* Mostrar correo completo en detalle.
* Enmascarar correo en vistas agregadas.
* Restringir exportación completa.

No se almacenarán credenciales o datos de autenticación del socio.

---

## 110. Seguridad de parámetros

Todas las routes deberán:

* Validar tipos.
* Limitar longitudes.
* Validar fechas.
* Validar valores enumerados.
* Validar ordenamiento.
* Limitar paginación.
* Escapar búsquedas.
* Rechazar filtros no soportados.
* No construir SQL mediante concatenación de strings.

Los filtros se convertirán a un objeto estructurado:

```python
RoutineControlMemberFilters(...)
```

---

## 111. Consistencia de detalle y listado

Si un socio aparece en listado, el usuario deberá poder abrir su detalle mientras conserve el mismo permiso y scope.

Si su scope cambia entre ambas solicitudes:

* El detalle podrá devolver `404` o `403`.
* La acción deberá ser rechazada.
* El frontend deberá recargar contexto.

No se asumirán permisos permanentes por haber recibido el registro anteriormente.

---

## 112. Consistencia de indicadores y exportación

Para un mismo:

* Usuario.
* Scope.
* Cohorte.
* Filtros.
* Fecha de corte.

Deberá cumplirse:

```text
Total del resumen =
cantidad total autorizada del listado =
cantidad exportada
```

salvo que la exportación excluya explícitamente columnas o incidencias, lo cual deberá indicarse.

Se crearán pruebas de integración para esta consistencia.

---

## 113. Auditoría de acciones API

Acciones auditables:

* Marcar no desea.
* Revertir decisión.
* Resolver incidencia.
* Invalidar evidencia.
* Ejecutar pipeline manual.
* Exportar.
* Consultar artifacts sensibles.
* Corrección administrativa.

Metadata mínima:

* Usuario.
* Acción.
* Entidad.
* Scope.
* IP o contexto disponible.
* Correlation ID.
* Fecha.
* Resultado.

Las consultas normales de listado no necesitarán generar una fila de auditoría individual por request, salvo requisito futuro.

---

## 114. Correlation ID

Cada request deberá tener un:

```text
correlation_id
```

Podrá recibirse desde proxy o generarse en backend.

Se propagará a:

* Logs.
* Servicios.
* Eventos.
* Exportaciones.
* Runs manuales.
* Auditoría.

La respuesta podrá incluirlo en headers o metadata de error.

---

## 115. Rendimiento

### Listados

* Paginación SQL.
* Índices por cohorte, sucursal y estado.
* No cargar relaciones completas innecesarias.
* Evitar N+1 de sucursal, decisiones y evidencias.

### Indicadores

* Agregaciones SQL.
* No cargar filas en Python para contarlas.
* Considerar vistas o agregados únicamente si el volumen lo exige.

### Historial

* Paginado.
* Orden descendente.
* Límite configurable.

### Exportación

* Query autorizado por chunks.
* Escritura progresiva cuando sea viable.
* Límite de filas inicial.
* No mantener todo el histórico global innecesariamente en memoria.

---

## 116. Contratos de pruebas de autorización

### Gerente

* Puede listar su sucursal.
* No puede pedir otra sucursal.
* No puede abrir un socio externo.
* No puede exportar otra sucursal.
* Puede marcar un socio propio.
* No puede marcar un socio externo.

### Regional

* Puede listar su pool.
* Puede filtrar una sucursal dentro del pool.
* No puede filtrar fuera del pool.
* Los indicadores contienen únicamente su pool.
* La exportación contiene únicamente su pool.

### Global

* Puede consultar todas las sucursales según capacidad.
* Puede filtrar región.
* Puede bajar a sucursal.
* No recibe capacidades administrativas si su permiso solo es lectura.

### Cambio de scope

* Si se retira una sucursal del pool, desaparece inmediatamente del acceso.
* Un JWT antiguo no conserva acceso si la DB ya cambió.

---

## 117. Pruebas mínimas de API

### Listado

* Paginación.
* Filtros.
* Búsqueda.
* Orden permitido.
* Orden inválido.
* Cohorte inválida.
* Scope aplicado.
* Resultados vacíos.

### Resumen

* Fórmulas.
* Scope.
* Filtros idénticos al listado.
* División entre cero.
* Incidencias.

### Decisiones

* Crear.
* Duplicar.
* Revertir.
* Versión incorrecta.
* Motivo `OTHER` sin notas.
* Usuario fuera de scope.
* Estado `CON_RUTINA`.

### Exportación

* Vista actual.
* Mensual completo.
* Scope.
* Filtros.
* Límite de filas.
* Auditoría.

### Detalle

* Propio.
* Fuera de scope.
* Historial.
* Capacidades.
* Decisión activa.
* Evidencias.

---

## 118. Decisiones cerradas en este bloque

* La autorización se reconstruirá desde DB.
* Se reutilizará el catálogo central de permisos.
* El scope se resolverá en un servicio común.
* Región será agrupación, no fuente primaria de autorización.
* Listado, indicadores y exportación compartirán query autorizado.
* La paginación será de servidor.
* No habrá `no_paging=true` en operación normal.
* Las acciones usarán `expected_status_version`.
* Los runs manuales no ejecutarán Playwright dentro del request.
* La API expondrá frescura de las fuentes.
* Los filtros se normalizarán en una estructura común.
* El ordenamiento usará una allowlist.
* La exportación será auditada.
* Las capacidades del frontend no sustituirán la validación backend.
* Un recurso fuera de scope no deberá filtrar información sensible.
* La API no dependerá de Warehouse para controlar estados.

---

## 119. Pendientes para bloques posteriores

* Diseño Angular.
* Tabla y navegación.
* Comportamiento responsive.
* Worker y scheduling.
* Horario diario.
* Backfill.
* Notificaciones de falla.
* Límites exactos de exportación.
* Política final de PII.
* Catálogo exacto de roles globales.
* Rutas definitivas.
* Integración con menú.
* Integración con permisos y migraciones.


# Bloque 5: worker, scheduling, backfill y observabilidad

**Versión:** 0.5
**Estado:** Propuesta para validación
**Dependencias:**

* Bloque 1 — modelo de datos, estados e idempotencia
* Bloque 2 — servicios de dominio y transiciones
* Bloque 3 — providers Gasca y Trainingym
* Bloque 4 — API, permisos y alcance jerárquico

**Alcance:** Proceso programado, ciclo de ejecuciones, reintentos, backfill, concurrencia, frescura, limpieza y observabilidad.
**Fuera de alcance:** Implementación Angular, detalles visuales, migraciones y despliegue productivo final.

---

## 120. Objetivo del bloque

Definir cómo se ejecutará automáticamente el Control de Rutinas sin:

* Bloquear Gunicorn.
* Interferir con Track.
* Perder ejecuciones al reiniciar un contenedor.
* Duplicar información.
* Publicar estados incompletos como correctos.
* Depender de un archivo `.bat`.
* Depender de una computadora Windows.
* Depender de ejecución manual diaria.

El proceso deberá soportar:

* Ejecución diaria programada.
* Reintentos.
* Ejecuciones manuales.
* Backfill histórico.
* Recuperación después de reinicio.
* Ejecuciones parciales.
* Observabilidad.
* Cancelación controlada.
* Limpieza de recursos.

---

## 121. Servicio independiente

Se creará un servicio Docker independiente.

Nombre provisional:

```text
routine-control-scheduler
```

Comando provisional:

```text
python -m app.routine_control.scheduler.worker
```

El servicio será independiente de:

* `backend`
* `track-scheduler`
* `reports-scheduler`

### Motivo

Trainingym puede involucrar:

* Navegación Playwright.
* Power BI.
* Descargas largas.
* Reintentos.
* Timeouts elevados.
* Procesos Chromium.
* Challenges.
* Fallos externos.

Un bloqueo de Trainingym no deberá:

* Consumir un worker Gunicorn.
* Detener Track.
* Retrasar cobranza.
* Congelar la Suite.
* Mantener requests HTTP abiertos.

---

## 122. Relación con `reports-scheduler`

Aunque Cobranza ya utiliza `reports-scheduler`, Control de Rutinas tendrá inicialmente un worker separado.

Razones:

1. El dominio tendrá estado operativo persistente.
2. Tendrá ejecuciones manuales y backfill.
3. Trainingym tiene mayor complejidad que un reporte único.
4. Requiere reconciliación posterior a la extracción.
5. Requiere aislamiento de navegador.
6. Su ciclo de vida no debe depender de diccionarios en memoria.
7. Podrá incorporar un segundo provider de rutinas en modo sombra.

Una futura consolidación de schedulers requerirá un contrato específico y no será parte de la primera versión.

---

## 123. Perfil Docker

El servicio se activará mediante el profile existente de schedulers o uno equivalente.

Conceptualmente:

```yaml
routine-control-scheduler:
  profiles:
    - scheduler
```

Comandos operativos esperados:

```powershell
docker compose --profile scheduler up -d routine-control-scheduler
```

```powershell
docker compose --profile scheduler stop routine-control-scheduler
```

```powershell
docker compose --profile scheduler up -d --build routine-control-scheduler
```

Los nombres exactos se confirmarán en implementación.

---

## 124. App factory

El worker utilizará la app factory existente:

```python
create_app()
```

Estructura conceptual:

```python
app = create_app()

with app.app_context():
    run_scheduler_loop()
```

El worker no levantará un servidor HTTP.

Deberá reutilizar:

* Configuración Flask.
* SQLAlchemy.
* Modelos.
* Servicios.
* Catálogos.
* Variables de entorno.
* Logging.

---

## 125. Ciclo principal

Función provisional:

```python
run_scheduler_loop()
```

Comportamiento conceptual:

```text
1. Crear contexto Flask.
2. Verificar configuración.
3. Consultar solicitudes PENDING.
4. Determinar si corresponde ejecución programada.
5. Adquirir advisory lock.
6. Crear o tomar pipeline run.
7. Ejecutar providers.
8. Persistir resultados.
9. Reconciliar.
10. Finalizar run.
11. Liberar recursos.
12. Ejecutar db.session.remove().
13. Dormir hasta el siguiente ciclo.
```

El loop deberá capturar errores por iteración.

Un error en una ejecución no finalizará permanentemente el worker.

---

## 126. Limpieza de sesión SQLAlchemy

Cada ciclo deberá ejecutar:

```python
db.session.remove()
```

dentro de un bloque `finally`.

Esto deberá ocurrir:

* Si no había trabajo.
* Si el pipeline terminó correctamente.
* Si un provider falló.
* Si hubo excepción.
* Si no se obtuvo advisory lock.
* Después de procesar una solicitud manual.

No se conservarán sesiones entre ciclos.

Esta regla evita conexiones:

```text
idle in transaction
```

---

## 127. Frecuencia de polling

El worker podrá revisar la cola persistente en intervalos configurables.

Variable provisional:

```text
ROUTINE_CONTROL_WORKER_POLL_SECONDS
```

Valor inicial recomendado:

```text
60 segundos
```

El polling no significa que el pipeline se ejecute cada minuto.

Solo revisará:

* Solicitudes manuales pendientes.
* Backfills pendientes.
* Ejecución diaria vencida.
* Reintentos diferidos.

---

## 128. Programación diaria

La ejecución automática será diaria.

Variables provisionales:

```text
ROUTINE_CONTROL_DAILY_ENABLED
ROUTINE_CONTROL_DAILY_TIME
ROUTINE_CONTROL_TIMEZONE
```

Zona obligatoria:

```text
America/Tijuana
```

La hora exacta se definirá después de confirmar:

* Cuándo Gasca tiene completo el corte.
* Cuándo Trainingym actualiza Power BI.
* Cuándo termina el flujo operativo previo.
* Cuándo necesitan ver la información los gerentes.

### Regla

La hora no se escribirá directamente dentro del código.

Ejemplo conceptual:

```text
ROUTINE_CONTROL_DAILY_TIME=04:30
```

Este valor es solo ilustrativo y no representa una decisión cerrada.

---

## 129. Fecha de negocio programada

La ejecución diaria normalmente utilizará:

```text
business_date = fecha local actual - 1 día
```

Pero este cálculo ocurrirá únicamente en el scheduler.

Los providers recibirán siempre fechas explícitas.

Ejemplo:

```text
Ejecución física: 14 de julio
business_date: 13 de julio
```

El pipeline registrará ambas fechas por separado.

---

## 130. Ventana de socios nuevos

La ventana inicial recomendada será acumulada dentro del mes de la fecha de negocio.

Conceptualmente:

```text
date_from = primer día del mes de business_date
date_to = business_date
```

Ejemplo:

```text
business_date = 2026-07-13
date_from = 2026-07-01
date_to = 2026-07-13
```

Esta ventana permite:

* Detectar correcciones.
* Detectar altas tardías.
* Reprocesar datos del mes.
* Mantener el control mensual.

La ventana definitiva dependerá de las capacidades del reporte individual de Gasca.

---

## 131. Ventana de rutinas

La ventana de Trainingym no deberá limitarse automáticamente al mes de la cohorte.

Debe permitir detectar:

* Rutinas preexistentes.
* Rutinas creadas en meses posteriores.
* Rutinas de cohortes anteriores aún pendientes.

### Estrategia inicial recomendada

Mantener una ventana móvil configurable.

Variables provisionales:

```text
ROUTINE_CONTROL_ROUTINES_LOOKBACK_DAYS
ROUTINE_CONTROL_OPEN_COHORT_MONTHS
```

Ejemplo conceptual:

```text
Rutinas:
date_from = business_date - 120 días
date_to = business_date
```

El número definitivo no se cerrará hasta analizar:

* Volumen de Trainingym.
* Tiempo de carga de Power BI.
* Periodo normal entre pase de cortesía y alta.
* Cantidad de cohortes abiertas.
* Disponibilidad de histórico.

### Regla adicional

Las cohortes con socios `SIN_RUTINA` deberán seguir siendo revisables aunque pertenezcan a meses anteriores.

---

## 132. Cohortes abiertas

Una cohorte se considerará operativamente abierta cuando tenga:

* Socios `SIN_RUTINA`.
* Incidencias abiertas.
* Decisiones pendientes de revisión.
* Fuente incompleta.

Variable provisional:

```text
ROUTINE_CONTROL_COHORT_RETENTION_MONTHS
```

No significa que cohortes antiguas se eliminen.

Solo define:

* Cuáles se revisan diariamente.
* Cuáles se consideran cerradas para procesamiento normal.
* Cuáles requieren backfill explícito para recalcularse.

---

## 133. Solicitudes persistentes

Las ejecuciones manuales y backfills se guardarán en PostgreSQL.

No se almacenarán únicamente en memoria.

Una solicitud podrá ser representada por:

```text
routine_control_pipeline_runs
```

con:

```text
status = PENDING
```

y campos:

* Modo.
* Fecha de negocio.
* Ventana.
* Providers solicitados.
* Usuario solicitante.
* Prioridad.
* Fecha de creación.

El worker recogerá estos registros.

---

## 134. Prioridad de ejecuciones

Orden recomendado:

1. Reintento de una ejecución diaria vencida.
2. Ejecución diaria pendiente.
3. Solicitud manual.
4. Backfill.
5. Provider sombra.

La prioridad exacta podrá almacenarse en una columna.

Un backfill largo no deberá impedir indefinidamente la ejecución diaria.

---

## 135. Advisory locks

Antes de ejecutar el pipeline, el worker obtendrá un advisory lock PostgreSQL.

Llave conceptual:

```text
routine_control
+
business_date
+
run_type
```

### Objetivo

Evitar:

* Dos workers ejecutando el mismo corte.
* Ejecución manual y automática incompatible.
* Dos backfills sobre la misma ventana.
* Duplicación por reinicio.

### Resultado sin lock

Si otro proceso tiene el lock:

* No se ejecuta el pipeline.
* No se marca como fallo técnico.
* La solicitud permanece pendiente o se reprograma.
* Se registra observabilidad.

---

## 136. Estados de pipeline

Estados:

```text
PENDING
RUNNING
SUCCESS
PARTIAL
FAILED
CANCELLED
REPLACED
```

### `PENDING`

Esperando worker.

### `RUNNING`

Lock adquirido y ejecución iniciada.

### `SUCCESS`

Todos los providers requeridos y la reconciliación terminaron correctamente.

### `PARTIAL`

Parte de la información fue procesada, pero un provider o etapa falló.

### `FAILED`

No se obtuvo un resultado operativo confiable.

### `CANCELLED`

Cancelada antes de completar.

### `REPLACED`

Una ejecución posterior reemplazó técnicamente el resultado del mismo corte.

No implica eliminar el run anterior.

---

## 137. Transiciones de pipeline

Permitidas:

```text
PENDING → RUNNING
PENDING → CANCELLED
RUNNING → SUCCESS
RUNNING → PARTIAL
RUNNING → FAILED
RUNNING → CANCELLED
SUCCESS → REPLACED
PARTIAL → REPLACED
FAILED → REPLACED
```

No permitidas:

```text
SUCCESS → RUNNING
FAILED → RUNNING
CANCELLED → RUNNING
```

Un reintento deberá crear una nueva ejecución relacionada con la anterior.

---

## 138. Relación entre reintentos

Campos conceptuales:

```text
retry_of_pipeline_run_id
attempt_number
root_pipeline_run_id
```

Ejemplo:

```text
Run 100
status = FAILED
attempt_number = 1

Run 101
retry_of = 100
root = 100
attempt_number = 2
```

Esto permite:

* Auditoría.
* Métricas.
* Diagnóstico.
* Saber cuál fue el intento exitoso.

---

## 139. Reintentos de provider

Cada provider tendrá su propia política.

Variables provisionales:

```text
ROUTINE_CONTROL_GASCA_MAX_ATTEMPTS
ROUTINE_CONTROL_TRAININGYM_MAX_ATTEMPTS
ROUTINE_CONTROL_RETRY_DELAY_SECONDS
```

### Reintento inmediato

Adecuado para:

* Formulario refrescado.
* Timeout breve.
* Navegación fallida.
* Descarga no iniciada.
* Power BI todavía cargando.

### Reintento diferido

Adecuado para:

* Fuente temporalmente caída.
* Reporte todavía no actualizado.
* Error intermitente prolongado.
* Challenge que podría desaparecer.

Los reintentos diferidos se registrarán en DB.

No dependerán de un `sleep` de horas dentro del mismo proceso.

---

## 140. Backoff

Política conceptual:

```text
Intento 1: inmediato
Intento 2: +5 minutos
Intento 3: +15 minutos
Intento 4: +30 minutos
```

Los valores serán configurables.

No se aplicará backoff infinito.

Cuando se alcance el máximo:

* Provider run queda `FAILED`.
* Pipeline queda `PARTIAL` o `FAILED`.
* Se registra la próxima acción requerida.
* Se conserva evidencia diagnóstica.

---

## 141. Matriz de resultado

### Gasca exitoso + Trainingym exitoso

```text
Pipeline = SUCCESS
```

Se permite:

* Ingesta de nuevos.
* Ingesta de rutinas.
* Reconciliación.
* Indicadores actualizados.

### Gasca exitoso + Trainingym fallido

```text
Pipeline = PARTIAL
```

Se permite:

* Persistir socios nuevos.
* Registrar frescura incompleta.
* Conservar estados anteriores.

No se permite:

* Declarar automáticamente que los nuevos están confirmados como `SIN_RUTINA`.
* Presentar el corte como totalmente actualizado.

Los nuevos podrán quedar pendientes de clasificación o con incidencia de frescura hasta que Trainingym se recupere.

### Gasca fallido + Trainingym exitoso

```text
Pipeline = PARTIAL
```

Se permite:

* Registrar nuevas evidencias.
* Actualizar socios ya existentes.
* Cambiar a `CON_RUTINA` cuando corresponda.

No se permite:

* Asumir que no hubo socios nuevos.
* Cerrar el corte como completo.

### Ambos fallidos

```text
Pipeline = FAILED
```

No se ejecuta reconciliación masiva basada en ausencia.

Los estados vigentes se conservan.

---

## 142. Reconciliación después de parciales

La reconciliación se aplicará únicamente a registros con información suficiente.

Ejemplo:

* Trainingym exitoso.
* Gasca fallido.
* Evidencia coincide con socio existente.

Resultado:

```text
Puede cambiar a CON_RUTINA.
```

Ejemplo:

* Gasca exitoso.
* Trainingym fallido.
* Socio nuevo sin evidencia disponible.

Resultado:

```text
No se confirma SIN_RUTINA hasta tener fuente de rutinas vigente.
```

Esto evita falsos pendientes.

---

## 143. Estado de frescura por dataset

Cada dataset mantendrá:

* Último run exitoso.
* Última fecha cubierta.
* Último status.
* Último error.
* Próximo reintento.
* Antigüedad.

Datasets:

```text
gasca:new_members
trainingym:routine_assignments
```

Estados de frescura:

```text
CURRENT
STALE
FAILED
PARTIAL
NEVER_RUN
```

### Regla inicial

La definición exacta de `STALE` será configurable por dataset.

Ejemplo conceptual:

```text
Rutinas no actualizadas en más de 36 horas → STALE
```

---

## 144. Ejecución programada duplicada

Antes de crear una ejecución diaria, el scheduler verificará si ya existe una ejecución para:

* Fecha de negocio.
* Modo programado.
* Providers requeridos.
* Estado exitoso actual.

Si ya existe un run exitoso y no hay una reejecución explícita:

* No crea otro run.
* Registra que el corte ya estaba completo.
* Continúa el loop.

---

## 145. Reejecución del mismo corte

Una reejecución podrá solicitarse cuando:

* Se corrigió una fuente.
* Se recuperó un provider.
* Cambió el contenido.
* Se resolvió una incidencia.
* Se requiere auditoría.

La nueva ejecución:

* Tendrá su propio ID.
* Conservará relación con la anterior.
* Calculará nuevos hashes.
* Aplicará upserts idempotentes.
* Generará solo cambios reales.
* Podrá marcar el run anterior como `REPLACED`.

No borrará ejecuciones anteriores.

---

## 146. Backfill

Modo:

```text
BACKFILL
```

El backfill permitirá procesar:

* Una fecha.
* Un rango de fechas.
* Una cohorte.
* Varias cohortes.
* Un provider específico.

### Regla

El backfill no se ejecutará directamente desde una consola improvisada sobre producción.

Se creará una solicitud persistente mediante:

* Endpoint autorizado.
* Comando administrativo controlado.
* Script interno que use los mismos servicios.

---

## 147. Estrategia de backfill inicial

El backfill inicial se dividirá en etapas.

### Etapa 1: validar una fecha

* Un corte conocido.
* Comparar con el Excel actual.
* Validar Gasca.
* Validar Trainingym.
* Validar conciliación.

### Etapa 2: cohorte de un mes

* Procesar un mes completo.
* Validar duplicados.
* Validar preexistentes.
* Validar múltiples rutinas.
* Validar incidencias.

### Etapa 3: varias cohortes

* Procesar meses anteriores.
* Medir tiempos.
* Ajustar índices.
* Verificar volumen.

### Etapa 4: operación diaria

Solo después de validar backfill.

---

## 148. Backfill y operación diaria

El worker deberá evitar que un backfill largo bloquee el corte diario.

Alternativas permitidas:

* Dividir backfill en unidades pequeñas.
* Ejecutar una fecha por ciclo.
* Pausar backfill al acercarse la hora diaria.
* Aplicar prioridad.
* Usar un segundo worker de backfill en el futuro.

Primera versión recomendada:

```text
Un solo worker
+
Backfill fragmentado
+
Prioridad para corrida diaria
```

---

## 149. Unidad de backfill

La unidad mínima recomendada será:

```text
un provider
+
una ventana
+
una fecha de negocio
```

Evitar una única ejecución que intente procesar un año completo en un navegador.

Ventajas:

* Reintentos pequeños.
* Auditoría clara.
* Menor riesgo de timeout.
* Menor uso de memoria.
* Recuperación parcial.

---

## 150. Cancelación

Una solicitud `PENDING` podrá cancelarse.

Una ejecución `RUNNING` podrá marcarse para cancelación mediante:

```text
cancellation_requested_at
cancellation_requested_by_user_id
```

El worker revisará la señal entre etapas seguras.

No se matará el proceso en medio de una transacción crítica salvo emergencia.

Si se cancela:

* Cierra navegador.
* Revierte transacción activa.
* Conserva lo ya confirmado en transacciones independientes.
* Marca run `CANCELLED`.
* Registra el punto alcanzado.

---

## 151. Heartbeat

Una ejecución `RUNNING` mantendrá:

```text
heartbeat_at
worker_instance_id
```

El worker actualizará el heartbeat entre etapas.

Esto permite detectar:

* Worker muerto.
* Contenedor reiniciado.
* Proceso congelado.
* Run huérfano.

---

## 152. Runs huérfanos

Al iniciar, el worker buscará ejecuciones:

```text
status = RUNNING
```

con heartbeat vencido.

No las retomará silenciosamente desde el punto medio.

Proceso:

1. Marcar run anterior como `FAILED`.
2. Error:

```text
WORKER_HEARTBEAT_EXPIRED
```

3. Crear reintento, si aplica.
4. Volver a ejecutar mediante idempotencia.

---

## 153. Identidad del worker

Cada proceso tendrá:

```text
worker_instance_id
```

Ejemplo conceptual:

```text
hostname + process_id + startup_timestamp
```

Se registrará en:

* Logs.
* Runs.
* Heartbeats.
* Advisory locks.
* Diagnóstico.

No será un secreto.

---

## 154. Etapas observables

El pipeline registrará etapas.

Valores preliminares:

```text
INITIALIZING
ACQUIRING_LOCK
RUNNING_GASCA
NORMALIZING_GASCA
PERSISTING_MEMBERS
RUNNING_TRAININGYM
NORMALIZING_TRAININGYM
PERSISTING_EVIDENCES
RECONCILING
CALCULATING_RESULTS
FINALIZING
COMPLETED
```

El run podrá guardar:

```text
current_stage
stage_started_at
```

Esto permitirá saber dónde se quedó.

---

## 155. Métricas de tiempo

Cada provider y etapa registrará duración.

Ejemplo:

```text
login_seconds
center_selection_seconds
report_load_seconds
download_seconds
normalization_seconds
persistence_seconds
reconciliation_seconds
total_seconds
```

Las métricas podrán almacenarse en:

```text
JSONB metrics
```

porque son auxiliares y pueden evolucionar.

---

## 156. Conteos mínimos

Pipeline:

* Socios creados.
* Socios actualizados.
* Evidencias creadas.
* Evidencias actualizadas.
* Estados cambiados.
* Incidencias creadas.
* Incidencias reabiertas.
* Registros rechazados.
* Rutinas automáticas excluidas.

Provider:

* Registros recibidos.
* Registros válidos.
* Registros rechazados.
* Registros excluidos.
* Duplicados detectados.
* Filas sin correo.
* Sucursales no resueltas.

---

## 157. Logging

Formato recomendado:

```text
timestamp
level
module
correlation_id
pipeline_run_id
provider_run_id
worker_instance_id
stage
message
```

Los logs deberán ser legibles por Docker:

```text
stdout
stderr
```

No dependerán únicamente de archivos internos del contenedor.

Podrán conservarse archivos adicionales cuando sean artifacts técnicos.

---

## 158. Niveles de log

### `INFO`

* Inicio.
* Fin.
* Cambio de etapa.
* Conteos.
* Reintentos.
* Resultado.

### `WARNING`

* Registros rechazados.
* Fuente desactualizada.
* Reintento técnico.
* Resultado parcial.
* Artifact faltante no crítico.

### `ERROR`

* Provider fallido.
* Archivo inválido.
* Reconciliación fallida.
* Run huérfano.
* Fallo de DB.

### `DEBUG`

* Selectores.
* Frames.
* Tiempos detallados.
* Metadata sanitizada.

`DEBUG` no estará activo permanentemente en producción salvo configuración.

---

## 159. Sanitización

Los logs y errores persistidos no incluirán:

* Usuario Trainingym.
* Contraseña Trainingym.
* Usuario Gasca.
* Contraseña Gasca.
* Cookies.
* Tokens.
* HTML completo sin sanitizar.
* Correos masivos.
* Payloads personales completos.
* URLs con secretos.

Los correos podrán enmascararse en logs:

```text
v***@dominio.com
```

La DB operativa sí conservará el correo necesario según política de PII.

---

## 160. Artifacts por ejecución

Directorio conceptual:

```text
/tmp/routine-control/<pipeline_run_id>/<provider_run_id>/
```

Subdirectorios:

```text
raw/
normalized/
diagnostics/
exports/
```

El directorio temporal:

* No será la fuente de verdad.
* Podrá limpiarse después de persistir artifacts requeridos.
* No se compartirá entre runs.
* No utilizará un único archivo `latest`.

---

## 161. Retención de artifacts

Política configurable.

Categorías:

### Raw válido

Podrá conservarse en Warehouse según política.

### Diagnóstico de fallo

Podrá conservarse durante un periodo corto.

### Trace Playwright

Solo cuando diagnóstico esté activo o haya fallo.

### Temporales

Se eliminarán al finalizar.

Variables provisionales:

```text
ROUTINE_CONTROL_RAW_RETENTION_DAYS
ROUTINE_CONTROL_DIAGNOSTIC_RETENTION_DAYS
ROUTINE_CONTROL_TEMP_CLEANUP_HOURS
```

Los valores definitivos se decidirán antes del despliegue.

---

## 162. Limpieza de procesos Playwright

Después de cada provider run:

* Cerrar página.
* Cerrar contexto.
* Cerrar navegador.
* Esperar terminación.
* Registrar fallo de cierre si ocurre.
* No dejar Chromium huérfano.

Podrá ejecutarse una verificación adicional de procesos del contenedor si se detectan fugas repetidas.

No se matarán procesos ajenos al worker.

---

## 163. Timeout del provider

Cada provider tendrá un timeout global configurable.

Variables provisionales:

```text
ROUTINE_CONTROL_GASCA_TIMEOUT_SECONDS
ROUTINE_CONTROL_TRAININGYM_TIMEOUT_SECONDS
```

Además de timeouts por:

* Navegación.
* Selector.
* Descarga.
* Power BI.
* Login.

El timeout global impedirá que un provider permanezca indefinidamente bloqueado.

---

## 164. Timeout de pipeline

El pipeline tendrá un máximo superior al de cada provider.

Si se excede:

* Se solicita cancelación.
* Se cierran recursos.
* El run termina `FAILED`.
* Se registra:

```text
PIPELINE_TIMEOUT
```

El timeout no dependerá del timeout de Gunicorn.

---

## 165. Manejo de señales

El worker responderá a:

```text
SIGTERM
SIGINT
```

Al recibir señal:

1. Dejar de tomar nuevas ejecuciones.
2. Marcar cancelación o interrupción.
3. Cerrar navegador.
4. Cerrar recursos.
5. Ejecutar `db.session.remove()`.
6. Salir.

Esto permitirá reinicios Docker más limpios.

---

## 166. Healthcheck

El contenedor deberá exponer o permitir verificar:

* Proceso vivo.
* Loop activo.
* Último heartbeat del worker.
* Conexión DB.
* Último ciclo.

Opciones:

* Comando interno de healthcheck.
* Archivo heartbeat.
* Consulta a tabla.
* Endpoint independiente futuro.

No se utilizará el backend web como prueba de salud del worker.

---

## 167. Alertas operativas

Primera versión mínima:

* Logs de error.
* Estado visible en Suite para roles autorizados.
* Frescura visible en la pantalla.
* Runs consultables.

Alertas futuras:

* Correo.
* Telegram.
* Slack.
* WhatsApp.

No son requisito para activar la primera versión, pero una falla no deberá permanecer invisible.

---

## 168. Recuperación manual

Un usuario autorizado podrá solicitar:

* Reintentar último run.
* Ejecutar un corte específico.
* Ejecutar solo Gasca.
* Ejecutar solo Trainingym.
* Reconciliar después de recuperar un provider.
* Lanzar backfill.

La acción creará una solicitud `PENDING`.

No abrirá un navegador desde el request HTTP.

---

## 169. Reconciliación sin extracción

Modo futuro permitido:

```text
RECONCILE_ONLY
```

Útil cuando:

* Se corrigió una decisión.
* Se resolvió una incidencia.
* Se corrigió un mapeo.
* Se invalidó una evidencia.
* No hace falta consultar proveedores.

Podrá ejecutarse:

* Para un socio.
* Para una cohorte.
* Para una sucursal.

No será necesariamente una opción visible en la primera UI.

---

## 170. Modo simulación

Para backfills y pruebas se recomienda soportar:

```text
DRY_RUN
```

El modo podrá:

* Extraer.
* Normalizar.
* Calcular conteos.
* Detectar incidencias.
* Comparar resultados.

No deberá:

* Persistir estados.
* Crear decisiones.
* Modificar evidencias vigentes.
* Publicar como run exitoso productivo.

La implementación podrá postergarse si eleva demasiado la complejidad inicial.

---

## 171. Validación previa a scheduling

Antes de activar la corrida diaria se deberá comprobar:

1. Worker inicia en Docker.
2. DB conecta.
3. Advisory lock funciona.
4. Chromium inicia.
5. Xvfb funciona cuando sea requerido.
6. Gasca descarga.
7. Trainingym inicia sesión.
8. Failover de credenciales funciona.
9. Centro se selecciona.
10. Power BI carga.
11. Archivo se descarga.
12. Raw se conserva.
13. Navegador cierra.
14. `db.session.remove()` se ejecuta.
15. Run queda persistido.
16. Reejecución no duplica.
17. Reinicio recupera runs huérfanos.
18. Backend continúa respondiendo durante el RPA.

---

## 172. Validación de rendimiento

Se medirán al menos:

* Memoria del worker sin navegador.
* Memoria máxima con Chromium.
* CPU durante Power BI.
* Duración de Gasca.
* Duración de Trainingym.
* Duración de reconciliación.
* Registros por segundo.
* Crecimiento de artifacts.
* Conexiones PostgreSQL.

No se activará una ventana demasiado amplia de Trainingym sin medir impacto.

---

## 173. Pruebas mínimas del scheduler

* No es hora y no hay solicitudes.
* Es hora y no existe run.
* Ya existe run exitoso.
* Existe run fallido reintentable.
* Advisory lock ocupado.
* Reinicio con run `RUNNING`.
* Heartbeat vencido.
* Gasca falla.
* Trainingym falla.
* Ambos fallan.
* Resultado parcial.
* Solicitud manual.
* Backfill.
* Cancelación.
* `SIGTERM`.
* Limpieza de DB.
* Limpieza de navegador.
* Reejecución del mismo corte.
* Dos workers simultáneos.
* Prioridad de corrida diaria sobre backfill.

---

## 174. Decisiones cerradas en este bloque

* Existirá un worker independiente.
* No se ejecutará Playwright dentro de Gunicorn.
* No se integrará inicialmente dentro de Track Scheduler.
* Las solicitudes serán persistentes.
* El worker utilizará polling.
* La programación usará `America/Tijuana`.
* Los providers recibirán fechas explícitas.
* Se utilizarán advisory locks.
* Los reintentos crearán trazabilidad.
* Los runs no dependerán de memoria.
* Los parciales conservarán información válida sin inventar ausencias.
* Los nuevos no se clasificarán como pendientes confirmados si Trainingym está desactualizado.
* El backfill se fragmentará.
* La operación diaria tendrá prioridad.
* Cada ciclo limpiará `db.session`.
* Los runs tendrán heartbeat.
* Los runs huérfanos se marcarán fallidos y se reintentará de forma idempotente.
* Los logs irán a stdout/stderr.
* Los artifacts estarán separados por run.
* El worker responderá a señales de terminación.
* La hora exacta se decidirá después de validar disponibilidad de las fuentes.

---

## 175. Pendientes para bloques posteriores

* Diseño Angular.
* Experiencia de gerente, regional y dirección.
* Gráficas e indicadores.
* Exportación visual.
* Catálogo exacto de permisos.
* Hora diaria definitiva.
* Lookback exacto de Trainingym.
* Número de cohortes abiertas.
* Retención de artifacts.
* Alertas externas.
* Diseño de Docker Compose.
* Variables de entorno definitivas.
* Plan de migración y despliegue.


# Bloque 6: frontend, experiencia operativa y exportación visual

**Versión:** 0.6
**Estado:** Propuesta para validación
**Dependencias:**

* Bloque 1 — modelo de datos, estados e idempotencia
* Bloque 2 — servicios de dominio y transiciones
* Bloque 3 — providers Gasca y Trainingym
* Bloque 4 — API, permisos y alcance jerárquico
* Bloque 5 — worker, scheduling, backfill y observabilidad

**Alcance:** Arquitectura Angular, vistas jerárquicas, tabla operativa, filtros, detalle, acciones, estados visuales, exportación y responsive.
**Fuera de alcance:** Migraciones, implementación backend, Docker y despliegue.

---

## 176. Objetivo del bloque

Definir una pantalla operativa que permita:

* Identificar rápidamente a los socios pendientes.
* Ejecutar acciones sobre casos concretos.
* Consultar cumplimiento por cohorte.
* Comparar sucursales y regiones.
* Entender si los datos están actualizados.
* Exportar información filtrada.
* Mantener la misma lógica para gerente, regional y dirección.
* Evitar una pantalla puramente tabular sin jerarquía de análisis.

La experiencia deberá tener dos niveles principales:

```text
Nivel 1: resumen y priorización
Nivel 2: detalle operativo por socio
```

Para regionales y dirección existirá un tercer nivel:

```text
Nivel 3: desglose por región o sucursal
```

---

## 177. Ubicación del módulo

Ruta provisional:

```text
/#/control-rutinas
```

La ruta exacta deberá registrarse en:

```text
frontend/src/app/app.routes.ts
```

El módulo será accesible desde el menú principal según capacidades.

Nombre visible:

```text
Control de rutinas
```

No utilizará “Trainingym” en el menú.

---

## 178. Arquitectura Angular

Estructura provisional:

```text
frontend/src/app/routine-control/
├── routine-control.routes.ts
├── pages/
│   ├── routine-control-dashboard/
│   │   ├── routine-control-dashboard.component.ts
│   │   ├── routine-control-dashboard.component.html
│   │   └── routine-control-dashboard.component.css
│   └── routine-control-detail/
│       ├── routine-control-detail.component.ts
│       ├── routine-control-detail.component.html
│       └── routine-control-detail.component.css
├── components/
│   ├── routine-control-summary-cards/
│   ├── routine-control-filters/
│   ├── routine-control-table/
│   ├── routine-control-breakdown/
│   ├── routine-control-freshness/
│   ├── routine-control-history/
│   └── routine-control-decision-dialog/
├── services/
│   └── routine-control.service.ts
├── models/
│   ├── routine-control.models.ts
│   ├── routine-control-filters.models.ts
│   └── routine-control-permissions.models.ts
└── helpers/
    ├── routine-control-status.helpers.ts
    ├── routine-control-query.helpers.ts
    └── routine-control-export.helpers.ts
```

Los nombres podrán ajustarse.

### Regla estructural

Cada componente deberá mantener archivos separados:

```text
.ts
.html
.css
```

No se utilizarán templates ni estilos inline.

La lógica permanecerá en TypeScript.

El HTML contendrá únicamente:

* Estructura.
* Bindings simples.
* Condiciones visuales.
* Llamadas a métodos ya definidos.

---

## 179. Servicio Angular

Servicio provisional:

```text
RoutineControlService
```

Responsabilidades:

* Obtener contexto.
* Consultar listado.
* Consultar indicadores.
* Consultar desglose.
* Consultar detalle.
* Crear decisión.
* Revocar decisión.
* Consultar historial.
* Consultar incidencias.
* Exportar.
* Consultar frescura.

No deberá:

* Calcular permisos.
* Corregir scope.
* Reimplementar reglas de estado.
* Fusionar resultados de sucursales manualmente.
* Calcular indicadores a partir de la página visible.

---

## 180. Carga inicial

Al entrar a la pantalla:

```text
1. Obtener /context
2. Construir filtros permitidos
3. Seleccionar cohorte predeterminada
4. Seleccionar vista inicial según rol
5. Cargar summary
6. Cargar breakdown, si aplica
7. Cargar members
8. Mostrar frescura
```

Las consultas independientes podrán ejecutarse en paralelo cuando no exista dependencia.

La pantalla no deberá solicitar datos fuera del scope y filtrarlos después en frontend.

---

## 181. Cohorte predeterminada

La cohorte inicial será:

```text
Cohorte del mes correspondiente a la fecha de negocio vigente
```

Si todavía no existen datos para el mes:

* Seleccionar la cohorte más reciente disponible.
* Mostrar una advertencia.
* No presentar ceros como si el mes estuviera actualizado.

El usuario podrá cambiar de cohorte mediante un selector mensual.

---

## 182. Vista de gerente

El gerente verá directamente su sucursal.

No mostrará un selector de sucursal si solo tiene una autorizada.

Orden visual:

```text
1. Estado de actualización
2. Indicadores
3. Filtros rápidos
4. Pendientes prioritarios
5. Tabla completa
```

Pestaña inicial:

```text
Pendientes sin rutina
```

Objetivo:

> Mostrar primero qué debe atender hoy.

---

## 183. Vista de gerente regional

El regional verá:

```text
1. Consolidado de su pool
2. Comparativo por sucursal
3. Filtro de sucursal
4. Bandeja operativa
```

Podrá:

* Ver todos los pendientes de su región.
* Ordenar sucursales por cumplimiento.
* Seleccionar una sucursal.
* Volver al consolidado.
* Exportar el pool completo o una sucursal.

La vista no deberá mezclar sucursales sin identificar claramente el origen de cada fila.

---

## 184. Vista de dirección

Dirección verá:

```text
1. Consolidado nacional
2. Comparativo por región
3. Desglose por sucursal
4. Bandeja operativa global
```

Flujo de navegación:

```text
Nacional
    ↓
Región
    ↓
Sucursal
    ↓
Socio
```

Los filtros seleccionados deberán conservarse al bajar de nivel y al volver.

---

## 185. Encabezado de la pantalla

El encabezado mostrará:

```text
Control de asignación de rutinas
Cohorte seleccionada
Fecha de corte
Última actualización
Alcance vigente
```

Ejemplo:

```text
Control de asignación de rutinas
Cohorte: julio 2026
Corte: 13 de julio de 2026
Alcance: Región Mexicali
```

---

## 186. Indicador de frescura

Componente visible:

```text
routine-control-freshness
```

Estados:

### Actualizado

```text
Gasca actualizado al 13 de julio
Rutinas actualizadas al 13 de julio
```

### Parcial

```text
Gasca actualizado al 13 de julio
Rutinas actualizadas al 12 de julio
```

### Fallido

```text
No fue posible actualizar Trainingym
Los pendientes pueden estar incompletos
```

### Nunca ejecutado

```text
El módulo todavía no tiene una sincronización válida
```

La advertencia deberá permanecer visible mientras la fuente esté desactualizada.

No se ocultará después de cerrar un mensaje.

---

## 187. Tarjetas de indicadores

Tarjetas iniciales:

```text
Total nuevos
Con rutina
Sin rutina
No desean rutina
Cumplimiento
Promedio de días
```

Para usuarios con capacidad:

```text
Incidencias
```

Cada tarjeta podrá funcionar como filtro rápido.

Ejemplo:

```text
Click en “Sin rutina”
→ activa pestaña Pendientes
```

Las tarjetas deberán mostrar:

* Valor.
* Etiqueta.
* Porcentaje, cuando aplique.
* Ayuda breve.
* Estado visual.

---

## 188. Indicador principal

El indicador principal será:

```text
Porcentaje de asignación
```

Fórmula:

```text
Con rutina / (Con rutina + Sin rutina)
```

La interfaz deberá aclarar:

```text
Los socios que no desean rutina se excluyen del cumplimiento.
```

No deberá mostrarse únicamente el porcentaje sin universo.

Ejemplo:

```text
79.1%
182 de 230 socios evaluables
```

---

## 189. Pestañas operativas

Pestañas:

```text
Pendientes
Con rutina
No desean rutina
Incidencias
Todos
```

### Pendientes

Filtro:

```text
current_status = SIN_RUTINA
```

### Con rutina

Filtro:

```text
current_status = CON_RUTINA
```

### No desean rutina

Filtro:

```text
current_status = NO_DESEA_RUTINA
```

### Incidencias

Filtro:

```text
classification_status = INCIDENT
```

Solo visible con capacidad.

### Todos

Incluye estados clasificados y, cuando el usuario tenga permiso, incidencias.

---

## 190. Filtros principales

Filtros visibles:

* Cohorte.
* Sucursal.
* Región.
* Estado.
* Fecha de alta.
* Días sin rutina.
* Instructor.
* Tipo de asignación.
* Fuente.
* Búsqueda.

Los filtros se adaptarán al rol.

### Gerente

No muestra región ni sucursal si no aportan valor.

### Regional

Muestra sucursal.

### Dirección

Muestra región y sucursal.

---

## 191. Filtros rápidos

Chips o botones:

```text
Más de 3 días
Más de 7 días
Más de 15 días
Rutina preexistente
Rutina posterior
Con incidencia
```

Los filtros rápidos deberán reflejarse en la URL o estado de navegación cuando sea viable.

No deberán ocultar filtros activos.

---

## 192. Persistencia de filtros

Durante la sesión, la pantalla conservará:

* Cohorte.
* Pestaña.
* Sucursal.
* Región.
* Búsqueda.
* Orden.
* Página.

Al abrir un detalle y regresar, el usuario volverá al mismo punto.

No será obligatorio conservar filtros después de cerrar sesión en la primera versión.

---

## 193. Tabla operativa

Columnas iniciales:

```text
Socio
Correo
Sucursal
Fecha de alta
Días
Estado
Rutina
Instructor
Última actualización
Acciones
```

Las columnas cambiarán ligeramente según pestaña.

### Pendientes

Prioridad:

```text
Socio
Sucursal
Fecha de alta
Días sin rutina
Correo
Acción
```

### Con rutina

Prioridad:

```text
Socio
Sucursal
Fecha de alta
Primera rutina
Tipo
Instructor
Días para asignación
```

### No desean rutina

Prioridad:

```text
Socio
Sucursal
Fecha de alta
Motivo
Fecha de decisión
Registrado por
```

### Incidencias

Prioridad:

```text
Código
Socio o referencia
Sucursal
Fuente
Severidad
Última detección
Estado
```

---

## 194. Orden de pendientes

Orden predeterminado:

```text
Días sin rutina DESC
Fecha de alta ASC
Nombre ASC
```

Esto coloca primero los casos con mayor atraso.

Los usuarios podrán ordenar por otras columnas permitidas.

---

## 195. Estados visuales

### `SIN_RUTINA`

Etiqueta:

```text
Sin rutina
```

Semántica visual:

```text
Atención requerida
```

### `CON_RUTINA`

Etiqueta:

```text
Con rutina
```

Semántica:

```text
Resuelto
```

### `NO_DESEA_RUTINA`

Etiqueta:

```text
No desea rutina
```

Semántica:

```text
Exclusión registrada
```

### Incidencia

Etiqueta:

```text
Requiere conciliación
```

Los colores deberán respetar accesibilidad y no ser la única señal.

Cada estado tendrá:

* Texto.
* Icono.
* Tooltip.
* Contraste suficiente.

---

## 196. Días sin rutina

Visualización:

```text
1 día
3 días
12 días
```

Semáforo inicial sugerido:

```text
0–2 días: reciente
3–6 días: seguimiento
7 o más: prioritario
```

Los umbrales deberán ser configurables o acordados antes de implementación visual definitiva.

No se cerrarán como regla de negocio en este bloque.

---

## 197. Acciones por fila

Acciones iniciales:

### Socio `SIN_RUTINA`

```text
Ver detalle
Marcar no desea rutina
```

### Socio `CON_RUTINA`

```text
Ver detalle
```

### Socio `NO_DESEA_RUTINA`

```text
Ver detalle
Revertir decisión
```

### Incidencia

```text
Ver detalle
Resolver
```

según capacidades.

No se mostrarán botones deshabilitados sin explicación cuando la acción no exista para el usuario.

---

## 198. Diálogo “No desea rutina”

Componente:

```text
routine-control-decision-dialog
```

Campos:

```text
Motivo
Observación
Confirmación
```

Reglas:

* Motivo obligatorio.
* Observación obligatoria para `OTHER`.
* Mostrar nombre del socio.
* Mostrar sucursal.
* Mostrar cohorte.
* Mostrar consecuencia.

Texto conceptual:

```text
El socio dejará de aparecer como pendiente.
No contará como socio con rutina.
La acción quedará registrada.
```

El diálogo enviará:

```text
expected_status_version
```

---

## 199. Conflicto de versión

Si backend responde:

```text
409 ROUTINE_CONTROL_CONFLICT
```

La interfaz deberá:

1. Informar que el registro cambió.
2. Cerrar o mantener el diálogo de forma segura.
3. Recargar el detalle.
4. Mostrar el estado vigente.
5. No repetir automáticamente la acción.

Mensaje:

```text
Este socio fue actualizado mientras realizabas la acción.
Revisa la información más reciente.
```

---

## 200. Reversión

El diálogo de reversión solicitará:

```text
Motivo de reversión
```

Mostrará:

* Decisión original.
* Usuario original.
* Fecha.
* Motivo.
* Estado probable después de revertir.

El estado final real será el devuelto por backend.

La UI no deberá asumir que volverá siempre a `SIN_RUTINA`, porque podría existir una rutina válida.

---

## 201. Detalle del socio

Podrá abrirse como:

* Página secundaria.
* Drawer lateral.
* Diálogo de pantalla amplia.

Recomendación inicial:

```text
Drawer lateral en escritorio
Página completa en móvil
```

Secciones:

```text
Resumen
Datos del socio
Estado actual
Rutinas
Decisiones
Historial
Incidencias
Información técnica autorizada
```

---

## 202. Resumen del detalle

Mostrará:

```text
Nombre
Estado
Cohorte
Sucursal
Fecha de alta
Correo
Días
Última actualización
```

Además:

```text
Acciones disponibles
```

según capacidades devueltas por API.

---

## 203. Sección de rutinas

Mostrará todas las evidencias válidas autorizadas.

Columnas:

```text
Fecha
Instructor
Fuente
Centro
Primera observación
Última observación
Estado de evidencia
```

La primera rutina se destacará.

Si hay varias:

```text
Primera rutina
Última rutina
Cantidad total
```

---

## 204. Sección de decisiones

Mostrará:

* Decisión.
* Motivo.
* Observación.
* Usuario.
* Fecha.
* Estado activo o revocado.
* Fecha de revocación.
* Motivo de revocación.

Aunque exista una rutina, la declaración histórica seguirá visible.

---

## 205. Historial

Visualización cronológica:

```text
13 jul — Se detectó rutina
10 jul — Marcado como no desea rutina
02 jul — Socio incorporado a cohorte
```

Cada evento mostrará:

* Fecha.
* Tipo.
* Actor.
* Estado anterior.
* Estado nuevo.
* Causa.
* Detalle resumido.

No se mostrará metadata técnica completa salvo permisos administrativos.

---

## 206. Incidencias en detalle

Cuando un socio tenga incidencia:

* Mostrar código legible.
* Mostrar explicación.
* Mostrar fuente.
* Mostrar última detección.
* Mostrar impacto.
* Mostrar acción disponible.

Ejemplo:

```text
Correo duplicado
No se pudo asociar automáticamente la rutina.
```

No mostrar únicamente:

```text
EMAIL_DUPLICADO_GASCA
```

El código técnico podrá aparecer en un tooltip o sección avanzada.

---

## 207. Comparativo regional

Para regionales y dirección se mostrará una tabla o gráfica por sucursal.

Campos:

```text
Sucursal
Total nuevos
Con rutina
Sin rutina
No desean
Cumplimiento
Promedio de días
Incidencias
```

Orden predeterminado:

```text
Cumplimiento ASC
Sin rutina DESC
```

La selección de una fila filtrará la bandeja.

---

## 208. Comparativo nacional

Dirección verá agrupación por región.

Campos:

```text
Región
Sucursales
Total nuevos
Con rutina
Sin rutina
No desean
Cumplimiento
Promedio de días
```

La vista deberá permitir bajar a sucursales.

No se mostrará solamente una gráfica sin acceso a los datos.

---

## 209. Visualizaciones

Visualizaciones iniciales recomendadas:

### Distribución de estados

```text
Con rutina
Sin rutina
No desean
```

### Cumplimiento por sucursal

Ranking o barras horizontales.

### Días para asignación

Distribución o promedio por sucursal.

No son obligatorias para el primer corte si retrasan la bandeja operativa.

Prioridad de implementación:

```text
1. Indicadores
2. Tabla operativa
3. Comparativo por sucursal
4. Gráficas adicionales
```

---

## 210. Regla “show, then drill down”

Cada indicador agregado deberá permitir llegar al detalle.

Ejemplo:

```text
48 sin rutina
    ↓
Lista de 48 socios
```

Ejemplo regional:

```text
Sucursal X — 62% cumplimiento
    ↓
Socios de Sucursal X
```

No se crearán indicadores sin ruta hacia la operación subyacente.

---

## 211. Exportación

Botón:

```text
Exportar
```

Opciones:

```text
Exportar vista actual
Exportar reporte mensual
```

Las opciones dependerán de capacidades y cohorte.

### Vista actual

Indicará:

```text
Se exportarán los filtros actuales
```

### Reporte mensual

Indicará:

```text
Se generará el reporte completo de la cohorte seleccionada
```

---

## 212. Descarga

El frontend:

1. Construirá parámetros desde el estado de filtros.
2. Llamará al endpoint de exportación.
3. Recibirá Blob.
4. Obtendrá nombre desde headers cuando exista.
5. Iniciará descarga.
6. Mostrará resultado.

No generará Excel en Angular.

No enviará listas de IDs para intentar reproducir el filtro.

---

## 213. Nombre de archivo

Formato sugerido:

```text
control_rutinas_<alcance>_<cohorte>_<fecha_corte>.xlsx
```

Ejemplos:

```text
control_rutinas_tec_mxl_2026-07_2026-07-13.xlsx
control_rutinas_region_mexicali_2026-07_2026-07-13.xlsx
control_rutinas_nacional_2026-07_2026-07-13.xlsx
```

Los nombres deberán sanitizarse.

---

## 214. Resumen en Excel

La pestaña `Resumen` deberá reflejar:

* Alcance.
* Cohorte.
* Fecha de corte.
* Fecha de generación.
* Filtros.
* Frescura.
* Total.
* Con rutina.
* Sin rutina.
* No desean.
* Cumplimiento.
* Promedio de días.

El Excel deberá indicar si una fuente estaba desactualizada.

---

## 215. Estados de carga

Cada sección tendrá su propio estado.

Ejemplo:

```text
Indicadores cargando
Tabla cargando
Comparativo cargando
```

La pantalla podrá mostrar indicadores aunque la tabla todavía esté cargando.

No se bloqueará toda la vista con un único spinner cuando no sea necesario.

---

## 216. Errores parciales de UI

Si falla el comparativo, pero el listado funciona:

* Mostrar listado.
* Mostrar error en comparativo.
* Permitir reintentar esa sección.

Si falla el contexto:

* No cargar el módulo.
* Mostrar acceso no disponible o error de configuración.

Si falla la tabla:

* Mantener filtros.
* Permitir reintento.
* No borrar indicadores ya cargados.

---

## 217. Estado vacío

Ejemplos:

### Sin pendientes

```text
No hay socios pendientes con los filtros actuales.
```

### Sin cohortes

```text
Todavía no existen cohortes procesadas.
```

### Sin incidencias

```text
No hay incidencias abiertas.
```

### Sin resultados de búsqueda

```text
No encontramos socios que coincidan con la búsqueda.
```

No se utilizará un único mensaje genérico.

---

## 218. Responsive

### Escritorio

* Tabla completa.
* Drawer lateral.
* Filtros en línea o panel.
* Comparativos visibles.

### Tablet

* Tabla con columnas prioritarias.
* Filtros colapsables.
* Detalle en drawer amplio.

### Móvil

* Lista de tarjetas o tabla simplificada.
* Filtros en bottom sheet o diálogo.
* Detalle como página completa.
* Acciones principales accesibles.
* No mostrar todas las columnas comprimidas.

---

## 219. Columnas móviles

Pendientes:

```text
Socio
Sucursal
Días
Estado
Acción
```

Con rutina:

```text
Socio
Sucursal
Fecha de rutina
Instructor
```

No desean:

```text
Socio
Sucursal
Motivo
```

El resto estará disponible en detalle.

---

## 220. Accesibilidad

La interfaz deberá:

* Tener labels en controles.
* Permitir navegación por teclado.
* Utilizar contraste suficiente.
* No depender solo del color.
* Tener tooltips accesibles.
* Anunciar errores.
* Asociar mensajes de validación.
* Mantener foco después de diálogos.
* Evitar tablas imposibles de leer con zoom.

---

## 221. Estado en URL

Filtros principales recomendados en query params:

```text
cohort
tab
branch
region
search
page
sort
```

Ventajas:

* Regresar desde detalle.
* Compartir una vista autorizada.
* Mantener estado al refrescar.
* Depurar consultas.

El backend seguirá validando todo.

---

## 222. Menú

El menú mostrará:

```text
Control de rutinas
```

solo cuando el usuario tenga capacidad `VIEW`.

Ubicación recomendada:

```text
Operación
```

o grupo equivalente.

No deberá colocarse dentro de Warehouse porque no es un módulo documental.

---

## 223. Notificación de actualización

Cuando la pantalla esté abierta y exista una nueva sincronización:

* Podrá mostrar un aviso.
* No reemplazará filas mientras el usuario esté completando una acción.
* Permitirá recargar.

Primera versión:

```text
Los datos se actualizaron. Recargar vista.
```

No requiere WebSocket inicialmente.

---

## 224. Confirmaciones

Requieren confirmación:

* Marcar no desea.
* Revertir decisión.
* Resolver incidencia.
* Invalidar evidencia.
* Ejecutar pipeline manual.
* Exportación muy grande, cuando aplique.

No requieren confirmación:

* Cambiar filtro.
* Abrir detalle.
* Cambiar cohorte.
* Exportar una vista normal.

---

## 225. Mensajes de éxito

Ejemplos:

```text
El socio fue marcado como “No desea rutina”.
```

```text
La decisión fue revertida.
```

```text
La exportación comenzó.
```

Los mensajes no deberán afirmar un estado que no coincida con la respuesta backend.

---

## 226. Mensajes de error

Ejemplos:

### Conflicto

```text
El registro cambió. Actualiza la información.
```

### Fuera de alcance

```text
Ya no tienes acceso a este socio.
```

### Fuente desactualizada

```text
Trainingym no está actualizado al último corte.
```

### Exportación grande

```text
La exportación supera el límite permitido.
Reduce el rango o los filtros.
```

No se mostrará el mensaje técnico crudo del backend.

---

## 227. Modelos TypeScript

Interfaces iniciales:

```text
RoutineControlContext
RoutineControlCapabilities
RoutineControlMember
RoutineControlMemberDetail
RoutineControlSummary
RoutineControlBreakdownRow
RoutineControlFilters
RoutineControlPagination
RoutineControlEvidence
RoutineControlDecision
RoutineControlStatusEvent
RoutineControlIncident
RoutineControlFreshness
```

Los estados se representarán con unions o enums controlados.

No se utilizará `any` para respuestas principales.

---

## 228. Manejo de fechas

Las fechas de negocio se recibirán como:

```text
YYYY-MM-DD
```

Los timestamps se recibirán como ISO 8601.

La presentación utilizará zona de negocio:

```text
America/Tijuana
```

No se deberán convertir fechas `DATE` a UTC y regresar un día anterior.

El frontend distinguirá:

* Fecha sin hora.
* Timestamp técnico.

---

## 229. Rendimiento frontend

* No guardar miles de socios en memoria.
* No filtrar el histórico completo en navegador.
* No recalcular summary desde filas.
* Cancelar requests obsoletos al cambiar filtros.
* Aplicar debounce a búsqueda.
* No volver a cargar contexto con cada página.
* Reutilizar catálogos.
* Evitar múltiples requests idénticos.

---

## 230. Búsqueda

La búsqueda aplicará debounce.

Valor sugerido:

```text
300–500 ms
```

No ejecutará request con cada tecla de forma inmediata.

Podrá requerir una longitud mínima, excepto cuando se borre el campo.

---

## 231. Paginación

La tabla utilizará:

```text
page
page_size
total_items
```

Cambiar filtros deberá regresar a página 1.

Cambiar orden también regresará a página 1.

El tamaño de página podrá ofrecer:

```text
25
50
100
```

sin superar el máximo backend.

---

## 232. Sincronización entre summary y tabla

Cuando cambie un filtro:

* Actualizar summary.
* Actualizar tabla.
* Actualizar breakdown.

Se utilizará un estado único de filtros para evitar discrepancias.

Si uno de los requests responde tarde con filtros anteriores, no deberá reemplazar resultados actuales.

---

## 233. Pruebas frontend mínimas

### Gerente

* Ve solo su sucursal.
* Pestaña inicial Pendientes.
* Marca no desea.
* Revierte decisión.
* Exporta su vista.
* Regresa de detalle sin perder filtros.

### Regional

* Ve consolidado.
* Filtra sucursal.
* Baja a detalle.
* No puede seleccionar sucursal externa.
* Exporta pool.

### Dirección

* Ve regiones.
* Baja a sucursales.
* Ve consolidado nacional.
* Aplica filtros globales.

### Estados

* Frescura actual.
* Frescura parcial.
* Sin datos.
* Error.
* Conflicto.
* Incidencia.
* Rutina preexistente.

### Responsive

* Escritorio.
* Tablet.
* Móvil.
* Diálogos.
* Tabla reducida.

---

## 234. Decisiones cerradas en este bloque

* La pantalla será una bandeja operativa.
* La vista principal de gerente será Pendientes.
* Regional y dirección tendrán consolidado y drill-down.
* Habrá tres niveles de navegación.
* La frescura será visible.
* La paginación y filtros serán de servidor.
* El resumen no se calculará desde la página visible.
* Las acciones utilizarán capacidades de backend.
* El detalle conservará historial y evidencias.
* La exportación se generará en backend.
* El frontend conservará filtros al abrir detalle.
* La ruta y menú serán neutrales respecto a Trainingym.
* La interfaz será responsive.
* El estado visual no dependerá únicamente del color.
* Las fechas `DATE` se tratarán como fechas de negocio.
* Las gráficas serán secundarias frente a la bandeja operativa.
* Cada indicador deberá permitir bajar al detalle.

---

## 235. Pendientes para bloques posteriores

* Diseño visual final.
* Colores exactos.
* Umbrales de días.
* Rol exacto de dirección.
* Límites de exportación.
* Mockups.
* Migraciones.
* Seeds de permisos.
* Plan de pruebas integral.
* Despliegue.
* Activación gradual.


# Bloque 7: migraciones, pruebas, despliegue y plan de implementación

**Versión:** 1.0
**Estado:** Contrato técnico completo para aprobación
**Dependencias:**

* Bloque 1 — modelo de datos, estados e idempotencia
* Bloque 2 — servicios de dominio y transiciones
* Bloque 3 — providers Gasca y Trainingym
* Bloque 4 — API, permisos y alcance jerárquico
* Bloque 5 — worker, scheduling, backfill y observabilidad
* Bloque 6 — frontend, experiencia operativa y exportación visual

**Alcance:** Migraciones, pruebas, despliegue, activación gradual, rollback y orden de implementación.

---

## 236. Objetivo del bloque

Definir cómo se construirá y activará el módulo sin:

* Modificar producción manualmente.
* Crear tablas fuera de Alembic.
* Mezclar todas las fases en un solo cambio.
* Activar el scheduler antes de validar los datos.
* Exponer el módulo a todos los usuarios antes de probar permisos.
* Perder trazabilidad durante el backfill.
* Depender de Trainingym para validar el dominio.
* Publicar datos incorrectos como oficiales.
* Dejar cambios sin mecanismo de rollback.

---

## 237. Regla de implementación

La implementación se realizará por fases pequeñas.

Cada fase deberá cumplir:

```text
Una responsabilidad principal
Una migración o cambio estructural controlado
Pruebas específicas
Validación manual
Commit independiente
Pull Request
Merge a main
Despliegue desde repositorio
```

No se editará código manualmente en el servidor.

Flujo obligatorio:

```text
Repositorio local
    ↓
Rama
    ↓
Commit
    ↓
Push
    ↓
Pull Request
    ↓
Merge a main
    ↓
Servidor: git pull
    ↓
docker compose up -d --build <servicio>
    ↓
Migraciones, cuando apliquen
    ↓
Validación
```

---

## 238. Rama de implementación

La implementación no se realizará sobre la rama del contrato.

Rama inicial sugerida:

```text
feat/routine-control-foundation
```

Las fases posteriores podrán utilizar ramas separadas:

```text
feat/routine-control-domain
feat/routine-control-providers
feat/routine-control-api
feat/routine-control-frontend
feat/routine-control-worker
```

No es obligatorio usar exactamente esos nombres, pero cada rama deberá tener un alcance delimitado.

---

## 239. Migraciones Alembic

Todos los cambios de base de datos se realizarán mediante Alembic.

No se permitirá:

* `CREATE TABLE` manual en producción.
* Agregar columnas directamente con SQL improvisado.
* Modificar modelos sin migración.
* Crear índices únicamente desde SQLAlchemy sin revisión de Alembic.
* Cambiar constraints sin historial.

Cada migración deberá contener:

* `upgrade()`
* `downgrade()`
* Nombres explícitos de índices.
* Nombres explícitos de constraints.
* FKs.
* Checks.
* Defaults compatibles.
* Revisión de locks.
* Validación de rollback.

---

## 240. Orden recomendado de migraciones

### Migración 1: catálogos y runs

Crear:

```text
routine_control_pipeline_runs
routine_control_provider_runs
```

Objetivo:

* Tener ejecución persistente antes de conectar providers.
* Probar transiciones y heartbeat.
* No depender de estados en memoria.

### Migración 2: miembros y evidencias

Crear:

```text
routine_control_members
routine_assignment_evidences
```

Objetivo:

* Ingestar datos normalizados.
* Probar identidad e idempotencia.

### Migración 3: decisiones, eventos e incidencias

Crear:

```text
routine_control_decisions
routine_control_status_events
routine_control_incidents
```

Objetivo:

* Habilitar reconciliación completa.
* Conservar historial y decisiones manuales.

### Migración 4: permisos y catálogos del módulo

Crear o insertar:

```text
Módulo ROUTINE_CONTROL
Acciones
Route maps
Grants iniciales
Motivos controlados, si se almacenan en DB
```

### Migraciones posteriores

Solo cuando sean necesarias:

* Nuevos índices.
* Nuevas columnas.
* Agregados.
* Modo sombra.
* Retención.
* Correcciones de modelo.

---

## 241. Defaults y nulabilidad

Las tablas se crearán inicialmente vacías.

No se requerirá backfill dentro de la migración.

Regla:

> Las migraciones estructurales no deberán ejecutar navegadores, descargar archivos ni procesar datos externos.

El backfill será una operación separada y controlada.

Para columnas nuevas en tablas ya pobladas:

1. Crear columna nullable.
2. Poblar mediante proceso controlado.
3. Validar.
4. Agregar `NOT NULL` en una migración posterior.

---

## 242. Constraints

Los nombres deberán ser explícitos.

Ejemplos conceptuales:

```text
ck_routine_control_members_current_status
ck_routine_control_members_classification_status
ck_routine_control_members_cohort_first_day
uq_routine_control_members_source_identity
uq_routine_assignment_evidences_provider_identity
uq_routine_control_status_events_event_key
uq_routine_control_active_decision
```

Esto facilita:

* Diagnóstico.
* Rollback.
* Migraciones posteriores.
* Lectura de errores PostgreSQL.

---

## 243. Índices y volumen

Los índices iniciales seguirán el contrato del Bloque 1.

Antes de agregar índices adicionales se deberá revisar:

```text
EXPLAIN ANALYZE
```

sobre:

* Listado de pendientes por sucursal.
* Resumen por cohorte.
* Consulta regional.
* Búsqueda por correo.
* Evidencias por miembro.
* Historial.
* Runs pendientes.

No se crearán índices indiscriminadamente sobre todas las columnas.

---

## 244. Importación de modelos

Los modelos nuevos deberán registrarse en:

```text
backend/app/models/__init__.py
```

antes de generar o aplicar migraciones.

Se verificará:

* Que Alembic detecte las tablas.
* Que no proponga cambios no relacionados.
* Que los nombres sean consistentes.
* Que no existan ciclos de importación.

---

## 245. Pruebas unitarias

Las pruebas unitarias deberán cubrir reglas puras sin requerir navegador.

### Normalización

* Correo con mayúsculas.
* Correo con espacios.
* Correo vacío.
* Fecha válida.
* Fecha inválida.
* Cohorte.
* Hash estable.
* Alias de sucursal.

### Estado

* Sin evidencia ni decisión.
* Evidencia válida.
* Decisión activa.
* Evidencia y decisión.
* Incidencia bloqueante.
* Evidencia invalidada.
* Resolución de incidencia.

### Fechas

* Rutina preexistente.
* Mismo día.
* Posterior.
* Cambio de fecha de venta.
* Fin de mes.
* Cambio de año.
* Zona `America/Tijuana`.

### Idempotencia

* Mismo socio.
* Misma evidencia.
* Mismo evento.
* Misma decisión.
* Mismo archivo.
* Contenido cambiado.

---

## 246. Pruebas de integración con PostgreSQL

Se deberán ejecutar contra una base de prueba.

Casos:

* Constraints.
* Índices.
* Upserts.
* Locks de fila.
* Advisory locks.
* Transacciones.
* Rollback.
* Decisiones concurrentes.
* Reconciliaciones concurrentes.
* FKs.
* Paginación.
* Agregaciones.

No bastarán pruebas con SQLite si el comportamiento depende de:

* PostgreSQL advisory locks.
* Índices parciales.
* JSONB.
* `SELECT FOR UPDATE`.
* Semántica de `TIMESTAMPTZ`.

---

## 247. Pruebas de contrato de providers

Los providers deberán probarse en dos niveles.

### Nivel 1: archivos fixture

Sin navegador.

Fixtures sanitizados de:

* Gasca.
* Trainingym.
* Archivos vacíos.
* Columnas faltantes.
* Duplicados.
* Correos vacíos.
* Rutinas automáticas.
* Múltiples rutinas.

Objetivo:

* Probar parser.
* Probar normalización.
* Probar hashes.
* Probar registros rechazados.

### Nivel 2: proveedor real

Con navegación controlada.

Objetivo:

* Login.
* Failover.
* Selección de centro.
* Fechas.
* Descarga.
* Cierre de navegador.
* Timeouts.
* Artifacts.

---

## 248. Datos sensibles en fixtures

Los fixtures incluidos en el repositorio deberán:

* Estar anonimizados.
* No contener correos reales.
* No contener nombres reales.
* No contener PIN.
* No contener credenciales.
* No contener cookies.
* No contener archivos completos de producción.

Se podrán generar datos sintéticos equivalentes.

---

## 249. Pruebas de API

Se probarán:

* Autenticación.
* Scope.
* Capacidades.
* Listado.
* Filtros.
* Paginación.
* Resumen.
* Detalle.
* Decisiones.
* Reversiones.
* Conflictos.
* Incidencias.
* Exportación.
* Runs manuales.

La prueba deberá comparar:

```text
Resumen
Listado total
Exportación
```

para el mismo usuario y filtros.

Los totales deberán coincidir.

---

## 250. Pruebas de permisos

Matriz mínima:

| Acción              |    Gerente |   Regional | Global lectura | Global administración |
| ------------------- | ---------: | ---------: | -------------: | --------------------: |
| Ver su alcance      |         Sí |         Sí |             Sí |                    Sí |
| Ver otra sucursal   |         No |  Solo pool |             Sí |                    Sí |
| Marcar no desea     |         Sí |         Sí |    Según grant |                    Sí |
| Revertir            |         Sí |         Sí |    Según grant |                    Sí |
| Ver incidencias     | No inicial | No inicial |    Según grant |                    Sí |
| Invalidar evidencia |         No |         No |             No |                    Sí |
| Exportar            |         Sí |         Sí |             Sí |                    Sí |
| Ejecutar pipeline   |         No |         No |             No |                    Sí |

La matriz final se ajustará a los roles reales de producción.

---

## 251. Pruebas de frontend

### Componentes

* Tarjetas.
* Filtros.
* Tabla.
* Frescura.
* Drawer.
* Diálogo.
* Historial.
* Exportación.

### Estados

* Loading.
* Success.
* Empty.
* Partial.
* Stale.
* Failed.
* Conflict.
* Forbidden.
* Not found.

### Jerarquía

* Gerente.
* Regional.
* Dirección.

### Navegación

* Mantener filtros.
* Regresar desde detalle.
* Cambiar cohorte.
* Drill-down.
* Responsive.

---

## 252. Pruebas end-to-end

Flujo mínimo:

```text
1. Provider Gasca incorpora socio.
2. Provider Trainingym no encuentra rutina.
3. Socio aparece SIN_RUTINA.
4. Gerente marca NO_DESEA_RUTINA.
5. Socio sale de pendientes.
6. Ejecución posterior detecta rutina.
7. Socio cambia a CON_RUTINA.
8. Historial conserva decisión.
9. Exportación refleja estado vigente.
```

Segundo flujo:

```text
1. Trainingym falla.
2. Gasca incorpora socios.
3. Pipeline queda PARTIAL.
4. No se crean falsos pendientes confirmados.
5. Frescura aparece desactualizada.
6. Reintento de Trainingym funciona.
7. Se completa reconciliación.
```

---

## 253. Comparación contra el script actual

Antes de reemplazar el flujo manual se deberá comparar un corte conocido.

Validaciones:

* Total de socios Gasca.
* Total de rutinas Trainingym.
* Rutinas automáticas excluidas.
* Correos coincidentes.
* Correos sin coincidencia.
* Con rutina.
* Sin rutina.
* Rutinas preexistentes.
* Rutinas posteriores.
* Totales por sucursal.
* Total nacional.

Las diferencias deberán clasificarse como:

```text
Corrección esperada del nuevo modelo
Error del script anterior
Error del nuevo módulo
Cambio de fuente
Caso ambiguo
```

No se aceptará únicamente que “los números se ven parecidos”.

---

## 254. Backfill inicial

El backfill inicial deberá tener un alcance explícito.

Orden:

```text
1. Un día conocido
2. Una cohorte mensual
3. Dos o tres cohortes
4. Histórico aprobado
```

Antes de cada ampliación se verificará:

* Tiempo.
* Memoria.
* Duplicados.
* Incidencias.
* Totales.
* Scope.
* Exportación.

El histórico completo no se cargará en la primera prueba.

---

## 255. Periodo inicial recomendado

El periodo definitivo se decidirá después de medir Trainingym.

Recomendación preliminar:

```text
Mes actual
+
Uno o dos meses anteriores
```

Objetivo:

* Cubrir pendientes recientes.
* Detectar rutinas posteriores.
* Evitar un backfill excesivo antes de validar.

No representa una decisión funcional cerrada.

---

## 256. Activación por feature flag

El módulo deberá permitir activación controlada.

Variables o configuración provisional:

```text
ROUTINE_CONTROL_ENABLED
ROUTINE_CONTROL_UI_ENABLED
ROUTINE_CONTROL_SCHEDULER_ENABLED
```

Esto permitirá:

* Desplegar tablas y API sin mostrar menú.
* Probar worker sin habilitar usuarios.
* Activar la UI para un grupo beta.
* Desactivar scheduling sin borrar datos.

La protección backend seguirá aplicándose aunque el menú esté oculto.

---

## 257. Fases de rollout

### Fase 0: infraestructura

* Modelos.
* Migraciones.
* Runs.
* Servicios base.
* Sin menú.
* Sin scheduler.

### Fase 1: ingesta manual controlada

* Provider Gasca.
* Provider Trainingym.
* Ejecución manual.
* Validación de datos.
* Sin usuarios operativos.

### Fase 2: dominio y API de lectura

* Reconciliación.
* Listado.
* Resumen.
* Detalle.
* Solo administradores.

### Fase 3: acciones manuales

* `NO_DESEA_RUTINA`.
* Reversión.
* Historial.
* Auditoría.

### Fase 4: frontend beta

Usuarios iniciales:

```text
Administrador responsable
Dirección seleccionada
Uno o dos gerentes piloto
Un regional piloto
```

### Fase 5: scheduler diario

* Activar worker.
* Monitorear.
* Mantener script manual como contingencia temporal.

### Fase 6: rollout general

* Gerentes.
* Regionales.
* Dirección.
* Capacitación.
* Exportación.

### Fase 7: retiro del flujo anterior

Solo después de:

* Varias ejecuciones exitosas.
* Totales conciliados.
* Usuarios operando en Suite.
* Contingencia documentada.

---

## 258. Beta

La beta deberá durar suficientes cortes para observar:

* Inicio de mes.
* Mitad de mes.
* Fin de mes.
* Pase de cortesía cruzando mes.
* Rutina posterior.
* Provider fallido.
* Corrección de datos.

No deberá considerarse validado únicamente con una ejecución exitosa.

---

## 259. Contingencia durante beta

Durante la beta:

* El script actual podrá continuar disponible.
* No será fuente principal de decisiones nuevas.
* Podrá utilizarse para comparación.
* No deberá modificar la base de Suite.
* No deberá publicar resultados que contradigan silenciosamente a Suite.

Si el módulo falla:

* Se puede ejecutar el script manual.
* Se registra la contingencia.
* Se corrige el módulo.
* Se reejecuta el corte.

---

## 260. Despliegue backend

Después del merge:

```powershell
git pull
docker compose up -d --build backend
```

Si hay migración:

```powershell
docker compose exec backend flask db upgrade
```

El orden exacto deberá considerar compatibilidad entre código y esquema.

Estrategia recomendada:

1. Migración compatible hacia adelante.
2. Desplegar backend.
3. Validar.
4. Activar feature flag.

---

## 261. Despliegue frontend

Cuando se habilite la UI:

```powershell
docker compose up -d --build frontend
```

Validar:

* Ruta hash.
* Menú.
* Guards.
* Interceptor JWT.
* API.
* Permisos.
* Responsive.
* Descarga.

---

## 262. Despliegue del worker

Solo después de validar providers manualmente dentro de Docker:

```powershell
docker compose --profile scheduler up -d --build routine-control-scheduler
```

Validar:

```powershell
docker compose ps
docker compose logs --tail=200 routine-control-scheduler
docker compose top routine-control-scheduler
```

El worker no deberá activarse automáticamente antes de que:

* Existan migraciones.
* Exista configuración.
* Existan credenciales.
* Existan mapeos.
* Se haya probado Chromium.

---

## 263. Variables de entorno

Categorías:

### Módulo

```text
ROUTINE_CONTROL_ENABLED
ROUTINE_CONTROL_UI_ENABLED
ROUTINE_CONTROL_SCHEDULER_ENABLED
```

### Providers

```text
ROUTINE_CONTROL_NEW_MEMBERS_PROVIDER
ROUTINE_CONTROL_ROUTINES_PRIMARY_PROVIDER
ROUTINE_CONTROL_ROUTINES_SHADOW_PROVIDER
```

### Trainingym

```text
TRAININGYM_LOGIN_URL
TRAININGYM_WORKOUT_URL
TRAININGYM_USER
TRAININGYM_PASS
TRAININGYM_CENTER_NAME
```

### Scheduling

```text
ROUTINE_CONTROL_DAILY_TIME
ROUTINE_CONTROL_TIMEZONE
ROUTINE_CONTROL_WORKER_POLL_SECONDS
```

### Timeouts y reintentos

```text
ROUTINE_CONTROL_GASCA_TIMEOUT_SECONDS
ROUTINE_CONTROL_TRAININGYM_TIMEOUT_SECONDS
ROUTINE_CONTROL_GASCA_MAX_ATTEMPTS
ROUTINE_CONTROL_TRAININGYM_MAX_ATTEMPTS
```

### Retención

```text
ROUTINE_CONTROL_RAW_RETENTION_DAYS
ROUTINE_CONTROL_DIAGNOSTIC_RETENTION_DAYS
```

Los nombres definitivos se cerrarán al implementar.

---

## 264. Validación de configuración

El worker deberá fallar de forma explícita al inicio si falta configuración crítica.

Ejemplos:

```text
TRAININGYM_USER missing
TRAININGYM_PASS missing
TRAININGYM_CENTER_NAME missing
ROUTINE_CONTROL_TIMEZONE invalid
```

No deberá iniciar un loop infinito fallando cada minuto por una variable inexistente.

Configuración opcional podrá generar advertencias.

---

## 265. Secretos

Los secretos no deberán:

* Quedar en Git.
* Quedar en Dockerfile.
* Quedar en Angular.
* Aparecer en logs.
* Aparecer en screenshots.
* Aparecer en excepciones.
* Aparecer en comandos de proceso.

Se utilizará el mecanismo vigente de variables de entorno o secretos del servidor.

---

## 266. Monitoreo posterior al despliegue

Durante los primeros días se revisará:

* Estado del contenedor.
* Logs.
* Runs.
* Heartbeats.
* Duración.
* Memoria.
* Procesos Chromium.
* Conexiones PostgreSQL.
* Incidencias.
* Totales.
* Frescura.
* Acciones de usuarios.

Se deberán registrar resultados de cada validación.

---

## 267. Validación de backend

Prueba rápida:

```powershell
curl -i --max-time 5 http://127.0.0.1:5000/
```

Un `404` rápido es saludable si Flask respondió.

También validar:

```powershell
docker compose top backend
```

Debe conservar la configuración robusta de Gunicorn.

El worker de rutinas no debe aparecer dentro de los procesos Gunicorn.

---

## 268. Validación de base de datos

Consultas mínimas:

* Runs recientes.
* Runs `RUNNING` huérfanos.
* Provider runs fallidos.
* Miembros por estado.
* Incidencias.
* Decisiones activas.
* Eventos duplicados.
* Evidencias duplicadas.
* Conexiones `idle in transaction`.

La implementación deberá incluir queries operativas documentadas.

---

## 269. Rollback de aplicación

Si la UI presenta errores:

```text
Desactivar ROUTINE_CONTROL_UI_ENABLED
```

Si el scheduler presenta errores:

```text
Desactivar ROUTINE_CONTROL_SCHEDULER_ENABLED
Detener routine-control-scheduler
```

Si el provider Trainingym falla:

* Conservar datos.
* Marcar frescura.
* No borrar estados.
* Reintentar.
* Usar contingencia manual.

No será necesario eliminar tablas para desactivar el módulo.

---

## 270. Rollback de migración

El downgrade deberá probarse en entorno de prueba.

En producción, antes de ejecutar downgrade se deberá revisar:

* Si las tablas contienen datos.
* Si existen FKs.
* Si la aplicación anterior puede operar con el esquema.
* Si se requiere respaldo.

No se hará downgrade destructivo automáticamente después de haber generado información operativa.

La primera opción será:

```text
Desactivar flags
Corregir hacia adelante
```

---

## 271. Respaldo

Antes de migraciones productivas relevantes:

* Verificar respaldo PostgreSQL.
* Verificar espacio.
* Registrar versión actual.
* Registrar migration head.
* Registrar commit desplegado.

Para backfills grandes:

* Validar respaldo.
* Probar con lote pequeño.
* Conservar run IDs.
* Poder identificar filas creadas por ejecución.

---

## 272. Compatibilidad hacia adelante

Las migraciones deberán diseñarse para permitir:

```text
Código anterior + esquema nuevo
```

durante una ventana corta de despliegue, cuando sea posible.

Evitar:

* Renombrar columnas usadas inmediatamente.
* Eliminar columnas en la misma fase.
* Hacer `NOT NULL` antes de poblar.
* Requerir que frontend y backend cambien en el mismo segundo.

---

## 273. Documentación técnica

El repositorio deberá incluir:

```text
Contrato funcional
Contrato técnico
Variables de entorno
Comandos de worker
Runbook de fallos
Queries operativas
Proceso de backfill
Proceso de rollback
```

Archivos sugeridos:

```text
docs/contracts/CONTRATO_CONTROL_ASIGNACION_RUTINAS.md
docs/contracts/CONTRATO_CONTROL_ASIGNACION_RUTINAS_TECNICO.md
docs/runbooks/ROUTINE_CONTROL_RUNBOOK.md
```

---

## 274. Runbook mínimo

El runbook futuro deberá responder:

* Cómo saber si el worker vive.
* Cómo consultar el último run.
* Cómo reintentar un corte.
* Cómo detener scheduling.
* Cómo ejecutar manualmente.
* Cómo revisar artifacts.
* Cómo detectar un challenge.
* Cómo resolver un run huérfano.
* Cómo revisar conexiones.
* Cómo hacer rollback.
* Cómo comparar contra el script anterior.

---

## 275. Orden de implementación recomendado

### Paso 1

Modelos de runs y migración.

Prueba:

* Crear run.
* Transicionar estados.
* Consultar DB.

### Paso 2

Modelos operativos y migración.

Prueba:

* Crear socio.
* Crear evidencia.
* Crear decisión.
* Crear evento.

### Paso 3

Servicios de dominio.

Prueba:

* Transiciones.
* Idempotencia.
* Concurrencia.

### Paso 4

Normalizer Gasca con fixture.

Prueba:

* Archivo local.
* Registros normalizados.

### Paso 5

Normalizer Trainingym con fixture.

Prueba:

* Múltiples rutinas.
* Automáticos excluidos.
* Evidencias.

### Paso 6

Provider Gasca real.

Prueba:

* Un corte manual.

### Paso 7

Provider Trainingym real.

Prueba:

* Login.
* Failover.
* Centro.
* Power BI.
* Descarga.

### Paso 8

Orquestador manual.

Prueba:

* Pipeline completo sin scheduler.

### Paso 9

API de lectura.

Prueba:

* Listado.
* Summary.
* Scope.

### Paso 10

Acciones manuales.

Prueba:

* No desea.
* Reversión.
* Historial.

### Paso 11

Frontend beta.

Prueba:

* Gerente.
* Regional.
* Dirección.

### Paso 12

Exportación.

Prueba:

* Totales iguales a API.

### Paso 13

Worker.

Prueba:

* Run programado.
* Reintento.
* Reinicio.
* Parcial.

### Paso 14

Backfill.

Prueba:

* Cohorte conocida.

### Paso 15

Rollout.

---

## 276. Uso eficiente de Codex

Codex se reservará para tareas que requieran comprender múltiples archivos o relaciones.

Tareas apropiadas:

* Implementar query autorizado.
* Crear worker basado en patrones existentes.
* Adaptar provider Trainingym.
* Revisar permisos.
* Revisar un diff transversal.
* Diagnosticar concurrencia.

Tareas que pueden realizarse mediante scripts:

* Crear archivos base.
* Agregar imports.
* Generar migraciones controladas.
* Aplicar parches mecánicos.
* Ejecutar tests.
* Ejecutar queries.
* Verificar Git.
* Crear ramas y commits.

Cada tarea enviada a Codex deberá incluir:

* Una responsabilidad.
* Archivos permitidos.
* Archivos de referencia.
* Archivos prohibidos.
* Criterios de aceptación.
* Comandos de prueba.
* Prohibición de ampliar alcance.

---

## 277. Criterios de “go live”

El módulo podrá considerarse listo para operación cuando:

1. Las migraciones estén aplicadas.
2. Los providers funcionen dentro de Docker.
3. Trainingym tenga failover validado.
4. El centro se seleccione automáticamente.
5. El pipeline sea idempotente.
6. Los estados coincidan con casos validados.
7. Los permisos estén probados.
8. La exportación coincida con el listado.
9. El worker no bloquee backend.
10. Los runs sean persistentes.
11. La frescura sea visible.
12. Exista contingencia.
13. Exista runbook.
14. La beta haya cubierto cortes suficientes.
15. Dirección apruebe los resultados.

---

## 278. Criterios de suspensión

El rollout deberá detenerse si:

* Aparecen socios de otras sucursales.
* Los permisos filtran incorrectamente.
* Se pierden decisiones manuales.
* Se duplican miembros o evidencias.
* Trainingym genera falsos éxitos.
* El worker deja Chromium huérfano.
* Se bloquea Gunicorn.
* Los totales cambian sin explicación.
* Una extracción fallida genera falsos pendientes.
* Las migraciones producen impacto no previsto.
* La exportación expone datos fuera de scope.

En esos casos:

```text
Detener rollout
Desactivar feature flag
Analizar síntoma
Corregir una causa a la vez
Revalidar
```

---

## 279. Definición de terminado

La implementación no estará terminada únicamente porque la pantalla cargue.

Se considerará terminada cuando existan:

* Datos confiables.
* Estado persistente.
* Decisiones auditadas.
* Permisos backend.
* Worker estable.
* Reintentos.
* Frescura.
* Exportación.
* Pruebas.
* Migraciones.
* Runbook.
* Rollback.
* Validación con usuarios.

---

## 280. Decisiones cerradas del contrato técnico

Quedan aprobadas como base técnica:

* Dominio neutral respecto a Trainingym.
* PostgreSQL como fuente operativa.
* Providers intercambiables.
* Cohortes mensuales.
* Conciliación por correo normalizado.
* Tres estados funcionales.
* Incidencias separadas.
* Decisiones separadas de evidencias.
* Evidencia con prioridad sobre decisión.
* Estado modificado únicamente por reconciliación.
* Historial transaccional.
* Idempotencia multinivel.
* Paginación y filtros de servidor.
* Consulta autorizada compartida.
* Scope gerente, regional y global.
* Worker independiente.
* Runs persistentes.
* Advisory locks.
* Heartbeat.
* Backfill fragmentado.
* Frescura visible.
* Frontend operativo con drill-down.
* Excel bajo demanda.
* Migraciones Alembic.
* Rollout mediante feature flags.
* Activación gradual.
* Rollback sin eliminar datos.

---

## 281. Pendientes que requieren evidencia real

Antes de iniciar determinados pasos deberán confirmarse:

1. Reporte individual definitivo de Gasca.
2. Columnas reales del reporte.
3. ID estable de socio en Gasca.
4. Columnas reales del Workout de Trainingym.
5. ID estable de rutina.
6. Semántica exacta de fecha de rutina.
7. Ventana máxima soportada por Power BI.
8. Catálogo de centros Trainingym.
9. Mapeo centro–sucursal.
10. Casos reales de mismo correo en distintas cohortes.
11. Roles exactos de Dirección.
12. Hora diaria.
13. Lookback de rutinas.
14. Cohortes abiertas.
15. Retención de artifacts.
16. Política de PII.
17. Límite de exportación.
18. Periodo de backfill inicial.

Estos puntos deberán resolverse mediante investigación o pruebas controladas, no mediante suposiciones.

---

## 282. Estado final del documento

Con este bloque, el documento queda en:

```text
Versión: 1.0
Estado: Contrato técnico completo
Siguiente etapa: investigación de datos reales y plan de implementación
```

No deberá iniciarse una migración productiva hasta confirmar los pendientes que afectan identidad e idempotencia.

El primer trabajo técnico recomendado será:

```text
Investigar y documentar la estructura real de los dos archivos fuente:
1. Gasca — socios nuevos individuales.
2. Trainingym — Workout.
```

Después se cerrarán:

* Llaves técnicas.
* Columnas normalizadas.
* Ventanas.
* Mapeos.
* Primer modelo Alembic.


# Bloque 8: validación de fuentes reales y cierre de llaves técnicas

**Versión:** 1.1
**Estado:** Validado con fuentes reales
**Corte analizado:** 1 al 12 de julio de 2026
**Archivos analizados:**

* `gasca_ventas_nuevas_socios.xlsx`
* `tg_workout.xlsx`

---

## 283. Resultado general de la validación

La revisión de los archivos reales permitió cerrar:

* Identidad del socio entre Gasca y Trainingym.
* Fecha oficial de cohorte.
* Regla exacta para reconocer una rutina.
* Identidad de las evidencias Trainingym.
* Uso técnico de `IDFolio`.
* Jerarquía de conciliación.
* Tratamiento de sucursales y centros.
* Reglas de filas no operativas.
* Manejo de correos vacíos o inconsistentes.

---

## 284. Estructura real de Gasca

El archivo contiene 27 columnas.

Campos relevantes:

```text
IDSocio
Pin
Sucursal
Nombre
ApellidoPaterno
ApellidoMaterno
Telefono
Email
FechaCreacion
FechaPago
IDFolio
TotalPagado
```

En el corte analizado:

```text
Registros: 854
IDSocio no nulos: 854
IDSocio distintos: 854
Pin no nulos: 854
Pin distintos: 854
Correos no vacíos: 851
Correos vacíos: 3
Sucursales: 26
```

---

## 285. Fecha de cohorte

La fecha oficial será:

```text
FechaPago
```

`FechaCreacion` no deberá determinar la cohorte.

En el archivo analizado existen cuentas creadas desde 2020 que realizaron una venta nueva en julio de 2026.

Por tanto:

```text
sale_date = DATE(FechaPago en America/Tijuana)
cohort_month = primer día del mes de sale_date
```

Ejemplo:

```text
FechaCreacion = 2020-09-21
FechaPago = 2026-07-01

Cohorte = 2026-07-01
```

---

## 286. Identidad del socio

Gasca `IDSocio` corresponde con Trainingym `Idsocioexterno`.

Se utilizarán los siguientes conceptos:

```text
Gasca.IDSocio
    → external_member_id canónico del provider Gasca

Trainingym.Idsocioexterno
    → referencia al IDSocio de Gasca

Trainingym.id
    → identificador interno del perfil o cuenta Trainingym
```

`Pin` se conservará como metadata operativa, pero no será la llave de conciliación con Trainingym.

---

## 287. Jerarquía de conciliación

La conciliación seguirá esta prioridad:

### Nivel 1: identificador externo

```text
gasca.IDSocio = trainingym.Idsocioexterno
```

Esta será la coincidencia primaria.

### Nivel 2: correo exacto normalizado

Cuando Trainingym no entregue `Idsocioexterno` o no se encuentre el ID:

```text
trim(lower(gasca.Email))
=
trim(lower(trainingym.Email))
```

### Nivel 3: incidencia

Si el ID y el correo apuntan a socios Gasca diferentes:

```text
IDENTITY_CONFLICT
```

No se conciliará automáticamente.

### Resultado del corte validado

```text
Socios con rutina por unión de llaves: 226
Coincidencia por ID: 218
Coincidencia por correo: 218
Coincidencia por ambos: 210
Solo por ID: 8
Solo por correo: 8
Conflictos ID contra correo: 0
```

---

## 288. Correos diferentes entre sistemas

Una diferencia de correo no invalidará una coincidencia por ID.

Casos observados:

```text
Gasca: dmdh2005@gmail.com
TG:    dmvh2005@gmail.com
IDSocio/Idsocioexterno coincidente
```

También existen correos cambiados completamente entre ambos sistemas.

Regla:

```text
Si IDSocio = Idsocioexterno:
    aceptar identidad
    conservar ambos correos
    abrir advertencia EMAIL_DIFFERENCE cuando corresponda
```

La advertencia no será bloqueante para reconocer una rutina.

---

## 289. Correo vacío

El correo vacío no será siempre una incidencia bloqueante.

Reglas:

```text
Correo vacío + coincidencia por ID + rutina válida
    → CON_RUTINA
    → advertencia EMAIL_EMPTY

Correo vacío + sin coincidencia por ID
    → clasificación INCIDENT
    → EMAIL_EMPTY_BLOCKING
```

Esto permite reconocer una rutina cuando existe evidencia inequívoca por identificador externo.

---

## 290. Identidad del registro Gasca

`IDFolio` no es único por socio.

En el corte analizado existen 14 folios compartidos por dos registros. Estos casos corresponden a operaciones donde:

* La sucursal coincide.
* `FechaPago` coincide.
* Un socio normalmente tiene importe pagado.
* Otro socio aparece con importe cero.

Por tanto:

```text
IDFolio
```

no podrá utilizarse por sí solo como `source_record_id`.

### Llave recomendada

```text
source_record_id =
    IDSocio + ":" + IDFolio_raw
```

Llave técnica:

```text
source_identity_key =
    sha256(
        "gasca|new_members|"
        + IDSocio
        + "|"
        + IDFolio_raw
    )
```

### Fallback

Cuando `IDFolio` no esté disponible:

```text
sha256(
    "gasca|new_members|"
    + IDSocio
    + "|"
    + FechaPago normalizada
)
```

### Regla de tipo

`IDFolio` deberá tratarse como texto.

No se convertirá a:

* `float`
* `double`
* entero JavaScript
* número Excel calculado

El archivo actual lo presenta en notación científica y puede superar la precisión numérica segura.

---

## 291. Identidad entre cohortes

`IDSocio` representa a la persona o cuenta, pero no por sí solo el evento de alta.

Una persona podrá aparecer nuevamente en una cohorte posterior.

Por ello:

```text
UNIQUE(IDSocio)
```

no será una restricción válida para la tabla de cohortes.

La identidad del caso utilizará:

```text
IDSocio + IDFolio
```

o su fallback con `FechaPago`.

---

## 292. Estructura real de Trainingym

El archivo contiene 14 columnas:

```text
id
Idsocioexterno
NombreApellidos
Email
Edad
Movil
Sexo
Técnico
NºRutinas
NºPesajes
Total Rutinas-Pesaje
Valoración
Fecha
Centro Origen
```

En el corte analizado:

```text
Filas operativas: 2821
Filas Automático: 1348
Filas con técnico humano: 1473
Filas humanas con rutina: 1472
Filas humanas solo con pesaje: 1
Centros: 25
```

---

## 293. Filas no operativas de Trainingym

El export contiene al final:

* Una fila `Total`.
* Una fila vacía.
* Una fila con el texto `Filtros aplicados`.

El normalizador deberá excluir filas cuando:

```text
id está vacío
id = "Total"
id comienza con "Filtros aplicados:"
Fecha está vacía
Centro Origen está vacío
```

La fila Total no deberá convertirse en una evidencia.

---

## 294. Regla exacta de rutina válida

Una fila será evidencia de rutina únicamente cuando:

```text
id válido
Fecha válida
Técnico no vacío
Técnico no automático
NºRutinas > 0
```

Pseudocódigo:

```python
is_valid_routine = (
    valid_trainingym_id
    and valid_date
    and technician_is_human
    and routine_count > 0
)
```

No será suficiente:

```text
Técnico != Automático
```

porque el reporte también contiene pesajes realizados por técnicos humanos.

---

## 295. Rutinas automáticas

Se excluirán filas donde el técnico normalizado contenga:

```text
automat
```

Ejemplos:

```text
Automático
Automatico
AUTOMATICO
```

Una rutina automática no demostrará acompañamiento humano.

Estas filas se contabilizarán como:

```text
excluded_reason = AUTOMATIC_ROUTINE
```

---

## 296. Pesajes

Las filas con:

```text
NºRutinas vacío o cero
NºPesajes > 0
```

no serán evidencia de rutina.

Podrán conservarse únicamente como metadata o registro rechazado:

```text
excluded_reason = WEIGHING_ONLY
```

No modificarán el estado del socio.

---

## 297. Fecha Trainingym

`Fecha` se entrega como una fecha Excel sin hora.

Se almacenará inicialmente como:

```text
DATE
```

No se inventará un timestamp.

Concepto recomendado:

```text
routine_activity_date
```

El campo representa el día en que el reporte informa actividad de rutina.

`first_routine_at` y `latest_routine_at` podrán implementarse como fechas mientras la fuente no entregue mayor precisión.

---

## 298. Identidad de evidencia Trainingym

Trainingym no entrega un ID individual de rutina en este reporte.

El campo `id` se repite en diferentes fechas, por lo que representa al perfil Trainingym y no a una rutina individual.

En las 1,472 filas válidas, esta combinación fue única:

```text
id
Fecha
Técnico
Centro Origen
```

Llave recomendada:

```text
evidence_identity_key =
    sha256(
        "trainingym|workout|"
        + id
        + "|"
        + Fecha
        + "|"
        + Técnico normalizado
        + "|"
        + Centro Origen normalizado
    )
```

`NºRutinas` no formará parte de la identidad lógica.

Se almacenará como:

```text
routine_count
```

El hash completo de la fila permitirá detectar si el contador fue corregido posteriormente.

---

## 299. Datos de evidencia Trainingym

Mapeo recomendado:

```text
Trainingym.id
    → provider_member_id

Trainingym.Idsocioexterno
    → external_member_id / Gasca IDSocio

Trainingym.Email
    → email_original

Trainingym.Fecha
    → routine_activity_date

Trainingym.Técnico
    → instructor_name

Trainingym.Centro Origen
    → provider_center_key / provider_center_name

Trainingym.NºRutinas
    → routine_count

Trainingym.NºPesajes
    → weighing_count
```

`external_routine_id` permanecerá nulo porque el reporte no lo entrega.

---

## 300. Múltiples evidencias

El mismo socio puede aparecer:

* En varias fechas.
* Con diferentes técnicos.
* Con más de un perfil Trainingym.
* Con varias rutinas.

No se reducirá el archivo a una sola fila por correo antes de persistir.

Cada evidencia válida se conservará.

El dominio calculará:

```text
Primera fecha conocida de rutina
Última fecha conocida de rutina
Instructor más reciente
Cantidad de evidencias
```

---

## 301. Perfiles duplicados Trainingym

Se observaron correos asociados a varios valores de `id`.

Esto coincide con la existencia operativa de cuentas duplicadas en Trainingym.

Reglas:

* `id` se conserva como identificador del perfil TG.
* `Idsocioexterno` tiene prioridad para identificar al socio Gasca.
* Dos perfiles TG podrán relacionarse con el mismo socio.
* No se fusionarán físicamente desde Suite.
* Se podrá abrir una advertencia:

```text
MULTIPLE_TRAININGYM_PROFILES
```

La existencia de varios perfiles no invalida una rutina cuando la identidad externa es inequívoca.

---

## 302. Sucursal operativa y centro de rutina

La sucursal del caso será siempre:

```text
Gasca.Sucursal
```

`Trainingym.Centro Origen` será un atributo de la evidencia.

Se observaron rutinas creadas en un centro diferente de la sucursal de venta.

Por tanto:

```text
Sucursal Gasca != Centro Trainingym
```

no será una incidencia bloqueante.

Podrá registrarse como:

```text
CROSS_BRANCH_ROUTINE
```

para análisis operativo, pero la rutina será válida.

---

## 303. Alias de centros Trainingym

Mapeo validado:

```text
UltraGym & Fitness - Azahares
    → AZAHARES CUL

UltraGym & Fitness - Carrousel
    → CARROUSEL TJ

UltraGym & Fitness - Independencia.
    → INDEPENDENCIA

UltraGym & Fitness - Insurgentes
    → INSURGENTES

UltraGym & Fitness - La Paz
    → PASEO LA PAZ

UltraGym & Fitness - Loma Bonita
    → LOMA BONITA

UltraGym & Fitness - Metepec
    → METEPEC

UltraGym & Fitness - Misión Ensenada
    → MISION ENS

UltraGym & Fitness - Pabellón Rosarito
    → PABELLON RTO

UltraGym & Fitness - Papalote
    → PAPALOTE TJ

UltraGym & Fitness - Paseo 2000
    → PASEO 2000

UltraGym & Fitness - Saltillo Norte
    → SALTILLO VILLALTA

UltraGym & Fitness - San Isidro
    → SAN ISIDRO CUL

UltraGym & Fitness - San Luis RC
    → SAN LUIS

UltraGym & Fitness - Santa Fe
    → SANTA FE

UltraGym & Fitness - Sendero CLN
    → SEND CUL

UltraGym & Fitness - Sendero Chihuahua
    → SEND CHIH

UltraGym & Fitness - Sendero Ixtapaluca
    → IXTAPALUCA

UltraGym & Fitness - Sendero Mexicali
    → SEND MXL

UltraGym & Fitness - Sendero Saltillo Sur
    → SEND SALTILLO

UltraGym & Fitness - Sendero Santa Catarina
    → STA CATARINA

UltraGym & Fitness - Tecnológico
    → TEC MXL

UltraGym & Fitness - Tlalnepantla
    → TLALNEPANTLA

UltraGym & Fitness - Villa Verde
    → VILLA VERDE

UltraGym & Fitness - Villa del Rey
    → VILLAS DEL REY
```

El mapeo deberá almacenarse mediante el servicio canónico de aliases de sucursales, no mediante condicionales dentro del provider.

---

## 304. Serranía

Gasca contiene:

```text
SERRANIA: 32 socios nuevos
```

Trainingym no contiene un centro Serranía en el corte analizado.

Regla:

```text
Si una sucursal Gasca no tiene cobertura en el provider de rutinas:
    no clasificar sus socios como SIN_RUTINA confirmado
    abrir incidencia de cobertura del provider
```

Código recomendado:

```text
ROUTINE_PROVIDER_BRANCH_NOT_CONFIGURED
```

La incidencia podrá ser una incidencia de sucursal asociada a los casos afectados, evitando crear falsos pendientes.

---

## 305. Reglas de conciliación definitivas

Pseudocódigo:

```python
def resolve_member(evidence):
    if evidence.external_member_id:
        member = find_gasca_member_by_idsocio(
            evidence.external_member_id
        )

        if member:
            if (
                evidence.email_normalized
                and member.email_normalized
                and evidence.email_normalized
                    != member.email_normalized
            ):
                create_warning("EMAIL_DIFFERENCE")

            return member

    if evidence.email_normalized:
        candidates = find_gasca_members_by_email(
            evidence.email_normalized
        )

        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            create_incident("EMAIL_MATCH_AMBIGUOUS")
            return None

    create_incident("ROUTINE_MEMBER_NOT_FOUND")
    return None
```

Si la búsqueda por ID y la búsqueda por correo regresan socios diferentes:

```text
IDENTITY_CONFLICT
```

La evidencia no se asociará automáticamente.

---

## 306. Correcciones al contrato anterior

Se reemplaza la decisión:

```text
Conciliación únicamente por correo normalizado
```

por:

```text
Conciliación primaria por IDSocio/Idsocioexterno
con fallback por correo normalizado.
```

También se reemplaza:

```text
Todo correo vacío es una incidencia bloqueante
```

por:

```text
El correo vacío es bloqueante únicamente cuando
no existe una identidad externa suficiente para conciliar.
```

Se agrega como condición obligatoria de evidencia:

```text
NºRutinas > 0
```

---

## 307. Impacto sobre el script anterior

El script anterior:

* Cruza únicamente por correo.
* Ignora `Idsocioexterno`.
* Conserva solo la última fila por correo.
* No valida `NºRutinas`.
* Pierde el historial de evidencias.
* Puede perder coincidencias por correos corregidos.
* Puede interpretar un pesaje humano como rutina.

El nuevo módulo no replicará esas limitaciones.

---

## 308. Pendiente de validación histórica

El corte actual confirma la identidad entre sistemas, pero solo contiene una cohorte mensual.

Antes de aplicar la migración operativa deberá revisarse al menos otro mes de Gasca para confirmar:

* Reaparición de un mismo `IDSocio` en distintas cohortes.
* Cambio de `IDFolio` entre eventos.
* Estabilidad del `IDSocio`.
* Estabilidad de la llave `IDSocio + IDFolio`.
* Casos de alta repetida dentro del mismo mes.

Este pendiente no impide comenzar los modelos de runs y providers, pero deberá cerrarse antes de fijar el constraint definitivo de identidad del caso.


## 309. Validación con exportación directa de junio

Se analizó una exportación descargada directamente desde Gasca:

```text
KpiUnoSociosNuevosDetallado20260713185413.xlsx
```

La ventana contenida corresponde al mes completo de junio de 2026:

```text
FechaPago mínima: 2026-06-01 05:09:41
FechaPago máxima: 2026-06-30 22:20:04
Registros: 2,497
Sucursales: 26
```

El archivo utiliza:

```text
Hoja: Socios
Columnas: 27
```

La estructura coincide con la exportación utilizada para julio.

---

## 310. Unicidad validada en junio

Resultados:

```text
IDSocio no nulos: 2,497
IDSocio distintos: 2,497

IDFolio no nulos: 2,497
IDFolio distintos: 2,466
IDFolio compartidos: 31

Combinaciones IDSocio + IDFolio: 2,497
Combinaciones duplicadas: 0
```

Esto confirma que:

```text
IDSocio
```

es adecuado como identificador externo de la persona o cuenta dentro de Gasca.

También confirma que:

```text
IDSocio + IDFolio
```

es una llave adecuada para identificar el evento de venta nueva.

---

## 311. IDFolio no es una llave individual

En junio existen 31 folios compartidos por dos socios.

La mayoría corresponde al patrón:

```text
Socio principal: TotalPagado = importe de la operación
Socio adicional: TotalPagado = 0
```

También existen folios compartidos entre nombres de sucursal diferentes.

Por tanto, queda prohibido utilizar:

```text
UNIQUE(IDFolio)
```

o:

```text
source_record_id = IDFolio
```

La llave definitiva será:

```text
source_record_id =
    str(IDSocio) + ":" + str(IDFolio)
```

Y:

```text
source_identity_key =
    sha256(
        "gasca|new_members|"
        + str(IDSocio)
        + "|"
        + str(IDFolio)
    )
```

`IDFolio` deberá mantenerse como texto.

---

## 312. PIN no único

En el archivo directo se encontraron PIN repetidos entre personas diferentes.

Ejemplos observados:

```text
PIN 11215 → dos IDSocio diferentes
PIN 8123  → dos IDSocio diferentes
```

Por tanto:

```text
Pin
```

se conservará únicamente como metadata operativa.

No podrá utilizarse para:

* Identidad.
* Constraint único.
* Conciliación con Trainingym.
* Idempotencia.

---

## 313. Validación del correo

Aunque no existen celdas de correo vacías en junio, se encontraron valores que no son correos válidos.

Ejemplo:

```text
Email = "195"
```

aparece en cuatro registros diferentes.

Por tanto, la validación no deberá limitarse a:

```text
email is not null
email != ""
```

También deberá comprobar una estructura mínima de correo.

Reglas:

```text
Correo válido
    → disponible como fallback de conciliación

Correo vacío o con formato inválido
    + IDSocio disponible
    → advertencia no bloqueante

Correo vacío o inválido
    + sin identificador externo conciliable
    → incidencia bloqueante
```

El correo nunca será la identidad principal.

---

## 314. Comparación junio contra julio

Al comparar:

```text
Junio 2026: 2,497 socios
Julio 1–12 de 2026: 854 socios
```

se obtuvo:

```text
IDSocio repetidos entre meses: 0
Correos repetidos entre meses: 0
IDSocio + IDFolio repetidos: 0
```

No se observó en estos dos cortes un mismo socio reapareciendo como venta nueva.

Esto no impide que ocurra históricamente.

El modelo seguirá permitiendo:

```text
Mismo IDSocio
+
Nuevo IDFolio
=
Nuevo evento de venta y nueva cohorte
```

Si se vuelve a observar:

```text
Mismo IDSocio
+
Mismo IDFolio
```

se tratará como la misma venta ya procesada y se aplicará upsert idempotente.

---

## 315. Mapeo técnico definitivo de Gasca

```text
Gasca.IDSocio
    → external_member_id

Gasca.IDFolio
    → external_sale_id

Gasca.IDSocio + ":" + Gasca.IDFolio
    → source_record_id

Gasca.Pin
    → metadata.pin

Gasca.FechaPago
    → sale_datetime_original
    → sale_date
    → cohort_month

Gasca.FechaCreacion
    → source_account_created_at

Gasca.Sucursal
    → external_branch_name

Gasca.Email
    → email_original
    → email_normalized cuando sea válido
```

---

## 316. Formato de fechas

Las fechas del archivo directo se entregan como texto:

```text
dd-mm-yyyy HH:mm:ss
```

El normalizador Gasca deberá analizarlas explícitamente.

Ejemplo:

```text
30-06-2026 22:20:04
```

Resultado:

```text
sale_datetime_original = 2026-06-30 22:20:04 America/Tijuana
sale_date = 2026-06-30
cohort_month = 2026-06-01
```

No se deberá depender de que Excel entregue una fecha nativa.

---

## 317. Decisión final de identidad Gasca

Queda cerrado el contrato:

```text
Identidad externa de persona:
    IDSocio

Identidad del evento de venta nueva:
    IDSocio + IDFolio

Identidad técnica:
    hash(provider + dataset + IDSocio + IDFolio)

Conciliación primaria con rutinas:
    IDSocio = Idsocioexterno

Conciliación secundaria:
    correo normalizado válido
```

Ya no queda pendiente revisar otro mes para definir la llave inicial del modelo.

Una validación histórica posterior podrá descubrir casos especiales, pero no bloquea la creación de los primeros modelos y migraciones.
