# Contrato — Checklist Diario de Sistemas V1 / M1
## Core backend, persistencia y reglas

Estado: PENDIENTE DE IMPLEMENTACIÓN  
Gate de entrada: contrato global aprobado.  
Gate de salida: backend autoritativo para estado diario, aplazamiento y envío válido.

## 0. Uso de este contrato

Este archivo es autosuficiente para una conversación nueva.

La conversación debe implementar **únicamente M1**.

Está prohibido adelantar:

- UX final mobile-first;
- modal/pantalla obligatoria de M2;
- dashboard BI;
- historial visual;
- integración automática con Tickets V2.

Antes de tocar código:

1. inspeccionar main;
2. revisar sesión/JWT real;
3. revisar modelo de sucursal/usuario;
4. revisar patrón de adjuntos existente;
5. revisar convenciones de rutas, modelos y migraciones;
6. explicar un solo cambio y su prueba.

## 1. Objetivo

Construir el dominio backend y persistencia suficiente para que Suite pueda responder de forma autoritativa:

- si una sucursal ya completó el checklist del día;
- si todavía puede aplazarlo;
- cuándo debe volver a mostrarse;
- si ya entró en estado obligatorio;
- si un payload de respuestas es válido;
- si el estado general es consistente;
- qué incidencias nacen de respuestas NO;
- quién lo realizó y cuándo.

M1 no necesita una UI terminada para demostrar estas reglas.

## 2. Invariantes

- Un checklist oficial por sucursal y business_date.
- Sucursal derivada de sesión/permiso, no confiada al navegador.
- Usuario derivado de JWT/sesión.
- Timestamp generado por backend.
- Todas las preguntas deben tener respuesta.
- Ninguna respuesta preseleccionada es concepto backend.
- Cada NO crea una incidencia propia.
- NO implica descripción obligatoria.
- Evidencia puede quedar preparada para M2.
- NORMAL solo es válido sin NO.
- Con al menos un NO, NORMAL es inválido.
- Máximo dos aplazamientos válidos por día.
- Cada aplazamiento bloquea un nuevo prompt por 5 minutos.
- Después del segundo aplazamiento y al vencer esos 5 minutos, el estado es obligatorio.
- Logout/dispositivo distinto no reinicia aplazamientos.

## 3. Investigación obligatoria

Antes de definir tablas/endpoints, inspeccionar:

- `backend/app/__init__.py`;
- modelos de usuario/sucursal;
- helpers de auth/permisos;
- timezone helpers existentes;
- rutas con business_date;
- almacenamiento de adjuntos reutilizable;
- patrones de auditoría;
- convenciones Alembic;
- cómo se identifica GERENTE y alcance de sucursal;
- si existen usuarios multi-sucursal que puedan requerir tratamiento especial.

Documentar cualquier supuesto que cambie el diseño.

## 4. Modelo conceptual

Se espera una estructura equivalente a:

```text
SystemDailyCheckORM
SystemDailyCheckAnswerORM
SystemDailyCheckIssueORM
SystemDailyCheckIssueAttachmentORM
SystemDailyCheckPromptStateORM   # o equivalente
```

El nombre exacto debe seguir convenciones del repo.

## 5. Checklist diario

Campos conceptuales:

- id;
- branch_id;
- business_date;
- performed_by_user_id;
- general_status;
- created_at;
- submitted_at.

Restricción obligatoria:

```text
UNIQUE(branch_id, business_date)
```

o mecanismo DB equivalente.

No confiar solo en check previo de aplicación.

## 6. Preguntas

Las preguntas deben tener claves estables.

Mínimo:

- COMPUTERS_WORKING;
- PERIPHERALS_WORKING;
- PRINTERS_WORKING;
- BANK_TERMINALS_WORKING;
- INTERNET_WORKING;
- GASCA_WORKING;
- SUITE_ULTRA_WORKING;
- TURNSTILES_WORKING;
- ACCESS_READERS_WORKING;
- TURNSTILE_SCREENS_WORKING;
- AMBIENT_AUDIO_WORKING;
- TV_SCREENS_WORKING;
- CAMERAS_WORKING.

M1 debe decidir, según patrones del repo, si el catálogo de preguntas vive en:

- tabla versionable;
- seed controlado;
- definición backend estable.

La decisión debe preservar histórico aunque cambie el label visible.

## 7. Respuestas

Valores canónicos:

- YES;
- NO;
- NA.

Cada respuesta debe pertenecer a un checklist y question_key estable.

No aceptar claves desconocidas.

No aceptar preguntas faltantes.

No aceptar duplicados.

## 8. Incidencias

Cada NO debe tener una incidencia correspondiente.

Campos conceptuales:

- id;
- answer_id;
- affected_scope nullable;
- reported_to_support;
- description;
- created_at.

Reglas:

- description obligatoria para NO;
- affected_scope solo obligatorio cuando la pregunta lo requiera;
- reported_to_support obligatorio para NO;
- YES/NA no deben persistir incidencia activa asociada.

No pedir ni modelar diagnóstico técnico.

## 9. Affected scope

Valores:

- ONE;
- MULTIPLE.

M1 debe definir de forma explícita qué question_keys requieren este dato.

No aplicar mecánicamente a preguntas donde “uno o varios equipos” no tenga sentido.

## 10. Estado general

Valores:

- NORMAL;
- MINOR_FAILURE;
- OPERATIONAL_IMPACT.

Validación:

```text
si NO count == 0:
    general_status == NORMAL

si NO count > 0:
    general_status in {MINOR_FAILURE, OPERATIONAL_IMPACT}
```

Backend es autoridad.

## 11. Prompt state / aplazamientos

Debe existir persistencia durable de la regla de aplazamiento.

Campos conceptuales:

- branch_id;
- business_date;
- postpone_count;
- last_postponed_at;
- next_prompt_at;
- mandatory_from_at nullable;
- completed_at nullable;
- updated_at.

Puede integrarse en otra entidad si queda semánticamente limpio.

## 12. Regla de aplazamiento

Estado inicial:

```text
postpone_count = 0
```

Primer aplazamiento válido:

```text
postpone_count = 1
next_prompt_at = now + 5 min
```

Segundo aplazamiento válido:

```text
postpone_count = 2
next_prompt_at = now + 5 min
mandatory_from_at = next_prompt_at
```

Antes de `next_prompt_at`:

- no debe exigirse nuevamente;
- un endpoint de estado debe indicarlo.

Desde `mandatory_from_at`:

- `can_postpone = false`;
- `mandatory = true`.

No debe existir tercer aplazamiento.

## 13. Concurrencia de aplazamiento

Dos solicitudes concurrentes no deben permitir superar el límite ni consumir estados inconsistentes.

M1 debe proteger:

- doble click;
- dos pestañas;
- dos dispositivos.

Usar transacción/locking/constraint apropiado al patrón del repo.

## 14. Business date

La business_date debe resolverse en backend con la política temporal vigente.

No confiar en fecha enviada por navegador.

Debe quedar probado el comportamiento alrededor de medianoche local.

## 15. Permisos

M1 debe definir quién puede:

- consultar estado diario propio;
- aplazar;
- enviar checklist;
- consultar un checklist específico si se requiere para pruebas/admin.

Mínimo:

- GERENTE con alcance válido puede llenar para su sucursal;
- ADMINISTRADOR puede tener acceso especial si el producto lo requiere;
- ningún usuario puede falsificar otra sucursal desde payload.

No hardcodear username.

## 16. Endpoints mínimos conceptuales

La forma exacta debe seguir convenciones del repo.

Capacidades mínimas:

### Estado diario

`GET /api/system-daily-checks/today/status`

Output conceptual:

```json
{
  "business_date": "2026-10-07",
  "completed": false,
  "postpone_count": 1,
  "can_postpone": true,
  "next_prompt_at": "...",
  "mandatory": false
}
```

### Aplazar

`POST /api/system-daily-checks/today/postpone`

Sin branch_id arbitrario como autoridad.

### Enviar

`POST /api/system-daily-checks/today/submit`

Payload conceptual:

- answers[];
- issue detail para respuestas NO;
- general_status.

Sucursal/usuario/fecha no son autoridad del body.

## 17. Idempotencia / duplicados

M1 debe definir comportamiento para:

- submit repetido;
- retry por timeout;
- dos submits concurrentes.

No crear dos checklists para la misma sucursal/fecha.

Preferencia:

- conflicto explícito o respuesta idempotente;
- nunca duplicación silenciosa.

## 18. Adjuntos

M1 debe investigar infraestructura existente y definir frontera.

Puede:

- crear modelo/relación necesaria;
- dejar carga física para M2.

No duplicar un sistema de archivos si existe uno seguro reutilizable.

## 19. Catálogo de Tickets V2

M1 puede persistir una referencia general opcional por question_key.

No debe:

- exigir subcategoría técnica;
- exigir insumo;
- crear ticket;
- resolver diagnóstico.

Gasca y Suite Ultra pueden permanecer sin binding definitivo si el catálogo no los representa limpiamente.

## 20. Migraciones

Todo cambio DB mediante Alembic.

Acceptance exige:

- upgrade limpio;
- downgrade si la política del repo lo requiere;
- modelo ORM alineado con schema;
- no depender de columnas inexistentes.

## 21. Pruebas mínimas

### Unicidad

- no permite dos checklists misma sucursal/fecha;
- sí permite fechas distintas;
- sí permite sucursales distintas.

### Respuestas

- rechaza pregunta faltante;
- rechaza question_key inválida;
- rechaza duplicada;
- acepta YES/NO/NA válidos.

### Incidencias

- NO exige detalle;
- YES/NA no lo exigen;
- múltiples NO generan múltiples incidencias.

### Estado general

- todo YES/NA + NORMAL acepta;
- todo YES/NA + MINOR/IMPACT rechaza si se adopta regla estricta;
- NO + NORMAL rechaza;
- NO + MINOR acepta;
- NO + IMPACT acepta.

### Aplazamiento

- primer postpone -> count 1;
- antes de 5 min no vuelve a ser elegible;
- segundo postpone -> count 2;
- antes del segundo +5 min todavía no obligatorio;
- al vencer -> mandatory true;
- tercer postpone rechazado;
- logout no reinicia;
- otra sesión/dispositivo observa mismo estado;
- concurrencia no supera 2.

### Permisos

- usuario autorizado funciona;
- sucursal falsificada se ignora/rechaza;
- usuario sin permiso rechaza.

### Timezone

- business_date consistente en America/Tijuana según estándar vigente.

## 22. Observabilidad

Errores deben ser diagnosticables sin loggear datos sensibles innecesarios.

No loggear:

- tokens;
- evidencia binaria;
- payload completo si contiene datos sensibles.

## 23. Fuera de alcance M1

- UI final;
- modal bloqueante;
- router guard definitivo;
- cámara móvil;
- dashboard;
- historial visual;
- BI;
- ticket automático;
- diagnóstico técnico.

## 24. Gate de salida

M1 queda ACCEPTED solo si:

1. migraciones aplican correctamente;
2. tests backend están verdes;
3. status diario funciona;
4. postpone funciona con máximo 2;
5. regla de 5 minutos funciona;
6. mandatory se deriva correctamente;
7. submit válido persiste checklist/respuestas/incidencias;
8. duplicados/concurrencia están protegidos;
9. permisos backend están probados;
10. no existe dependencia de localStorage para autoridad.

## 25. Estado final esperado

```text
M1 — ACCEPTED
M2 — DESBLOQUEADO
M3 — BLOQUEADO POR M2
```
