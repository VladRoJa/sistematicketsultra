# Suite Ultra — Contact Center V1

**Documento:** Contrato funcional-técnico  
**Versión:** 1.0  
**Fecha:** 22 de septiembre de 2026  
**Estado:** Aprobado funcionalmente; pendiente de implementación

## 1. Objetivo

Crear dentro de Suite Ultra un módulo operativo de **Contact Center** simple de usar, pero suficientemente robusto para conservar seguimiento, trazabilidad y resultados de cada contacto comercial.

El módulo deberá permitir trabajar una cartera proveniente de múltiples fuentes, principalmente:

- contactos CRM visibles en el Funnel de Marketing;
- conversaciones/mensajes atendidos por el equipo de Contact Center;
- campañas de reactivación;
- campañas masivas;
- contactos creados manualmente.

El módulo no sustituye al Funnel.

Principio rector:

> **El Funnel continúa siendo analítico; Contact Center será la capa operativa de seguimiento.**

El flujo objetivo es:

```text
FUENTE
  ↓
CONTACTO
  ↓
CASO
  ↓
INTERACCIONES / SEGUIMIENTO
  ↓
CITA
  ↓
SUCURSAL
  ↓
CIERRE OBLIGATORIO
  ↓
VALIDACIÓN CONTRA VENTA TOTAL
```

La meta es poder responder con evidencia preguntas como:

- ¿qué contactos están pendientes de trabajar?;
- ¿quién los está trabajando?;
- ¿cuándo se les llamó?;
- ¿qué ocurrió en cada intento?;
- ¿a quién hay que volver a llamar?;
- ¿qué citas se generaron?;
- ¿qué citas siguen pendientes de cerrar?;
- ¿qué sucursal recibió la cita?;
- ¿qué citas asistieron?;
- ¿qué contactos terminaron comprando?;
- ¿qué compra fue confirmada por Venta Total?;
- ¿qué agente, fuente, campaña o sucursal produjo el resultado?

---

## 2. Principios de diseño

### 2.1 Simple hacia el usuario, robusto por debajo

El operador no deberá manipular estructuras técnicas ni decenas de estados.

La interfaz deberá reducir la operación diaria a decisiones claras:

- llamar;
- registrar qué pasó;
- programar seguimiento;
- agendar cita;
- cerrar o continuar el caso.

La complejidad de identidad, auditoría, fuentes, validación de compra y permisos deberá resolverse en backend.

### 2.2 Una persona no es un caso

Se separan conceptualmente:

```text
CONTACTO = persona
CASO = motivo por el cual se trabaja a esa persona
INTERACCIÓN = acción realizada
CITA = compromiso con una sucursal
RESULTADO = qué terminó ocurriendo
```

Una persona puede existir una sola vez como contacto y tener múltiples casos históricos.

Ejemplo:

```text
María López
6861234567

Caso 1
CRM
Junio 2026
Cerrado sin compra

Caso 2
Reactivación
Agosto 2026
No localizada

Caso 3
Mensaje
Septiembre 2026
Cita generada
```

### 2.3 Las interacciones son históricas

Registrar un nuevo estado no deberá borrar lo anterior.

Cada llamada, intento, nota, seguimiento o cita deberá conservarse en orden cronológico.

### 2.4 Backend es la autoridad

La UI puede ocultar opciones, pero toda acción deberá validar permisos nuevamente en backend.

### 2.5 Venta Total es la fuente canónica de compra

Un usuario podrá reportar manualmente que una persona compró, pero dicho dato será provisional.

La confirmación canónica deberá provenir de un cruce auditable contra **Venta Total**.

### 2.6 No duplicar identidades existentes de Marketing

Cuando el contacto provenga de iVentas/Funnel, Contact Center deberá enlazarse con la identidad existente y no crear un universo paralelo de “leads Contact Center”.

---

## 3. Relación con Marketing / Funnel actual

Suite Ultra ya persiste contactos iVentas mediante el contrato:

`docs/contratos/contrato_marketing_iventas_leads_v1.md`

y construye el Funnel mediante servicios y rutas de Marketing.

Contact Center deberá consumir dicha información como una posible fuente de origen.

La integración conceptual será:

```text
iVentas / CRM
   ↓
marketing_iventas_contacts
   ↓
Funnel
   ↓
Contacto Contact Center
   ↓
Caso operativo
```

Reglas obligatorias:

1. Un contacto iVentas no se convertirá automáticamente en una identidad nueva si ya existe un contacto equivalente en Contact Center.
2. El identificador externo de iVentas deberá conservarse como referencia.
3. Los campos provenientes de snapshots de Marketing no deberán copiarse como una nueva fuente canónica cuando puedan referenciarse.
4. Contact Center no modificará las reglas canónicas existentes del Funnel.
5. Contact Center podrá exponer desde el Funnel una acción futura tipo **Ver seguimiento CC**, pero no convertirá el Funnel en la pantalla operativa de llamadas.

---

## 4. Fuentes de origen

Cada caso deberá conservar un origen operativo.

Valores técnicos iniciales:

- `CRM`
- `MESSAGE`
- `REACTIVATION`
- `CAMPAIGN`
- `MANUAL`

Etiquetas amigables de UI:

| Técnico | UI |
|---|---|
| `CRM` | CRM |
| `MESSAGE` | Mensaje |
| `REACTIVATION` | Reactivación |
| `CAMPAIGN` | Campaña |
| `MANUAL` | Manual |

El origen describe **por qué nació el caso**, no la identidad completa de la persona.

Cuando exista una referencia externa deberá conservarse, por ejemplo:

- `marketing_iventas_contacts.contact_id`;
- recipient de campaña de reactivación;
- campaña Marketing;
- registro de cartera;
- futura referencia de mensajería.

---

## 5. Contactos

Entidad propuesta:

`contact_center_contacts`

Campos mínimos:

- `id`
- `display_name`
- `primary_phone_raw`
- `phone_mx10`
- `email`
- `preferred_sucursal_id`, nullable
- `is_active`
- `merged_into_contact_id`, nullable
- `created_by_user_id`
- `updated_by_user_id`
- `created_at`
- `updated_at`

### 5.1 Teléfono

`phone_mx10` deberá reutilizar la normalización mexicana vigente cuando sea aplicable.

El teléfono deberá estar indexado.

No se establece una restricción `UNIQUE` rígida sobre teléfono en V1 porque:

- pueden existir teléfonos compartidos;
- puede existir información incompleta;
- un duplicado real debe resolverse mediante merge auditable;
- un contacto puede llegar por fuentes distintas antes de ser conciliado.

### 5.2 Creación manual

La pantalla **Nuevo contacto** deberá pedir únicamente:

- nombre;
- teléfono obligatorio;
- sucursal de interés;
- origen;
- motivo/caso;
- comentario inicial;
- correo opcional.

Antes de guardar deberá ejecutarse búsqueda de posibles duplicados.

---

## 6. Referencias externas

Entidad propuesta:

`contact_center_contact_links`

Objetivo:

Conservar relaciones entre un contacto Contact Center y entidades externas sin duplicar el dato fuente.

Campos mínimos:

- `id`
- `contact_id`
- `source_type`
- `source_key`
- `source_row_id`, nullable
- `source_metadata_json`, nullable
- `created_at`

Ejemplos:

```text
source_type = IVENTAS_CONTACT
source_key  = <contact_id iVentas>
```

```text
source_type = REACTIVATION_RECIPIENT
source_key  = <campaign_recipient_id>
```

La combinación razonable de `source_type + source_key` deberá ser única.

---

## 7. Casos

Entidad propuesta:

`contact_center_cases`

Un caso representa la razón activa o histórica por la que Contact Center trabaja a una persona.

Campos mínimos:

- `id`
- `contact_id`
- `source_type`
- `source_ref`, nullable
- `sucursal_id`, nullable
- `assigned_user_id`
- `status`
- `next_action_at`, nullable
- `opened_at`
- `closed_at`, nullable
- `closed_by_user_id`, nullable
- `created_by_user_id`
- `created_at`
- `updated_at`

Estados internos:

- `NEW`
- `IN_PROGRESS`
- `FOLLOW_UP`
- `APPOINTMENT`
- `CLOSED`

### 7.1 Agente responsable

Todo caso activo deberá poder tener un `assigned_user_id`.

La asignación debe ser por usuario real de Suite.

No se deberán hardcodear nombres de operadores.

Esto permitirá:

- cartera por agente;
- reasignación;
- productividad por agente;
- pendientes individuales;
- auditoría.

### 7.2 Casos simultáneos

Por defecto, al intentar abrir un nuevo caso para un contacto con un caso activo, Suite deberá advertirlo.

La UI deberá favorecer:

**Continuar caso existente**

antes de crear otro.

Un supervisor autorizado podrá crear un segundo caso cuando exista una razón de negocio distinta.

---

## 8. Interacciones / bitácora

Entidad propuesta:

`contact_center_interactions`

Campos mínimos:

- `id`
- `case_id`
- `contact_id`
- `interaction_type`
- `outcome`
- `comment`
- `next_action_at`, nullable
- `created_by_user_id`
- `created_at`

La bitácora es append-only a nivel funcional.

No deberá sobrescribirse una interacción anterior para representar una nueva llamada.

### 8.1 Opciones amigables para el operador

La UI deberá presentar inicialmente:

- **No contestó**
- **Volver a llamar**
- **Interesado**
- **Cita**
- **No interesado**
- **Número incorrecto**
- **No contactar**

El backend podrá persistir códigos técnicos estables.

Ejemplo:

| UI | Código |
|---|---|
| No contestó | `NO_ANSWER` |
| Volver a llamar | `CALL_BACK` |
| Interesado | `INTERESTED` |
| Cita | `APPOINTMENT` |
| No interesado | `NOT_INTERESTED` |
| Número incorrecto | `WRONG_NUMBER` |
| No contactar | `DO_NOT_CONTACT` |

### 8.2 Seguimiento

Si el resultado es **Volver a llamar**, deberá solicitarse fecha/hora.

Esa fecha se reflejará en:

`contact_center_cases.next_action_at`

y deberá alimentar las vistas:

- Pendientes de hoy;
- Seguimientos vencidos;
- Próximos seguimientos.

---

## 9. Citas

Entidad propuesta:

`contact_center_appointments`

Campos mínimos:

- `id`
- `case_id`
- `contact_id`
- `sucursal_id`
- `scheduled_at`
- `timezone`
- `status`
- `outcome`, nullable
- `notes`, nullable
- `created_by_user_id`
- `closed_by_user_id`, nullable
- `closed_at`, nullable
- `rescheduled_to_appointment_id`, nullable
- `purchase_reported`
- `purchase_reported_at`, nullable
- `purchase_reported_by_user_id`, nullable
- `purchase_verification_status`
- `venta_total_snapshot_id`, nullable
- `venta_total_snapshot_row_id`, nullable
- `verified_purchase_at`, nullable
- `verified_amount`, nullable
- `verified_tariff`, nullable
- `created_at`
- `updated_at`

La zona horaria operativa será:

`America/Tijuana`

siguiendo la política general de Suite para interacción humana local.

### 9.1 Selección de sucursal

Al agendar, el agente seleccionará la sucursal donde asistirá el contacto.

La sucursal de cita:

- puede ser distinta a la sucursal de origen del caso;
- será la sucursal responsable de atender/cerrar la cita;
- determinará destinatarios de correo y alcance del gerente.

### 9.2 Estados de cita

Estados técnicos:

- `SCHEDULED`
- `CANCELLED`
- `RESCHEDULED`
- `CLOSED`

El estado visual **Cierre pendiente** será derivado cuando:

```text
scheduled_at < ahora
AND status = SCHEDULED
AND outcome IS NULL
```

No será necesario persistir un estado duplicado si puede derivarse correctamente.

---

## 10. Cierre obligatorio de cita

Una cita pasada no deberá desaparecer de la operación.

Toda cita deberá terminar en uno de estos resultados:

- `ATTENDED_PURCHASE_REPORTED`
- `ATTENDED_NO_PURCHASE`
- `NO_SHOW`
- `CANCELLED`
- `RESCHEDULED`

Etiquetas:

- Asistió y compró
- Asistió y no compró
- No asistió
- Cancelada
- Reagendada

### 10.1 Reagendado

Reagendar no deberá sobrescribir silenciosamente la fecha original.

Flujo:

```text
Cita original
status = RESCHEDULED
outcome = RESCHEDULED
        ↓
Nueva cita
status = SCHEDULED
        ↓
rescheduled_to_appointment_id
```

De esta forma se conserva el historial completo.

---

## 11. Compra reportada vs compra canónica

El gerente podrá indicar:

**Asistió y compró**

Esto persistirá una afirmación operativa:

```text
purchase_reported = true
purchase_reported_at = ...
purchase_reported_by_user_id = ...
purchase_verification_status = REPORTED_PENDING
```

Esto **no es todavía una venta canónica**.

### 11.1 Fuente de verdad

La confirmación deberá cruzarse contra snapshots canónicos de:

- `VentaTotalSnapshotORM`
- `VentaTotalSnapshotRowORM`

La lógica deberá reutilizar resolvers/normalizaciones existentes siempre que sea posible.

No se debe crear un matcher paralelo más débil si ya existe infraestructura probada en Marketing/Warehouse.

### 11.2 Estados de validación

Valores iniciales:

- `NOT_REPORTED`
- `REPORTED_PENDING`
- `VERIFIED`
- `REVIEW`
- `NOT_FOUND_YET`

Solo `VERIFIED` podrá mostrarse como:

**Compra validada**

### 11.3 Evidencia

Cuando exista match canónico se conservará al menos:

- snapshot;
- fila exacta;
- fecha de pago/venta;
- monto;
- tarifa;
- sucursal observada;
- timestamp de validación.

Si el gerente reportó compra y todavía no existe evidencia suficiente, deberá mostrarse:

**Compra reportada · pendiente de validar**

### 11.4 No alterar KPIs corporativos

Contact Center no modificará por sí mismo los KPIs corporativos de Venta Total, Track o Reactivaciones.

Su información servirá para análisis operacional y atribución futura.

---

## 12. Duplicados

La detección de duplicados es parte obligatoria de V1.

Al crear o vincular un contacto, Suite deberá buscar candidatos mediante señales como:

- teléfono normalizado;
- correo;
- identificadores externos;
- coincidencias razonables de nombre + teléfono parcial;
- referencias ya enlazadas.

La existencia de un candidato no deberá fusionar automáticamente.

Debe abrirse un modal de revisión.

Ejemplo:

```text
Posible duplicado

CONTACTO A                 CONTACTO B
Juan Pérez                 Juan Pérez García
6861234567                 6861234567
sin correo                 juan@email.com
Villas del Rey             sin sucursal
CRM                        Reactivación

[Conservar A] [Conservar B]

Nombre:       Juan Pérez García
Teléfono:     6861234567
Correo:       juan@email.com
Sucursal:     Villas del Rey

[Unificar contactos]
```

---

## 13. Merge de contactos

El merge deberá ser explícito y auditable.

Entidad propuesta:

`contact_center_contact_merge_events`

Campos mínimos:

- `id`
- `survivor_contact_id`
- `merged_contact_id`
- `field_resolution_json`
- `merged_by_user_id`
- `created_at`

### 13.1 Reglas

Al fusionar:

1. se selecciona un contacto superviviente;
2. el usuario decide qué valores conservar cuando exista conflicto;
3. los campos vacíos podrán completarse con información del otro contacto;
4. casos deberán reasignarse al superviviente;
5. interacciones deberán conservarse;
6. citas deberán conservarse;
7. referencias externas deberán conservarse;
8. el contacto absorbido quedará marcado con `merged_into_contact_id`;
9. no se realizará hard-delete del contacto absorbido;
10. deberá existir evidencia de quién ejecutó el merge.

### 13.2 Restricciones

No se permitirá merge ciego que provoque:

- pérdida de historial;
- pérdida de referencia externa;
- eliminación de una cita;
- duplicación de una referencia externa única.

---

## 14. Correo de notificación de cita

Cuando se cree una cita, Suite deberá enviar una notificación por correo a la sucursal seleccionada.

Se reutilizará:

`backend/app/utils/email_sender.py::send_email_html`

No se reutilizará directamente:

`pick_recipients(ticket, ...)`

porque dicho helper está acoplado a la entidad `Ticket`.

Se implementará un resolver específico de Contact Center.

### 14.1 Destinatarios

El resolver deberá buscar en backend:

- gerente(s) autorizados de la sucursal destino;
- correos válidos en `UserORM`.

No se deberán hardcodear emails.

### 14.2 Contenido mínimo

Asunto conceptual:

```text
[Contact Center] Nueva cita — Villas del Rey — 24/09/2026 18:00
```

Cuerpo:

- contacto;
- teléfono;
- fecha;
- hora;
- sucursal;
- origen;
- agente que agenda;
- comentario;
- acceso a Suite cuando aplique.

### 14.3 Falla SMTP

Regla obligatoria:

> La cita es el dato principal; el correo es una notificación secundaria.

La creación deberá seguir este orden:

```text
validar
  ↓
guardar cita
  ↓
commit
  ↓
intentar notificación
```

Si SMTP falla:

- la cita no se revierte;
- el error debe quedar registrado/logueado;
- la UI debe poder informar que la cita fue creada aunque el correo no pudiera enviarse.

Para trazabilidad/reintentos se recomienda persistir eventos de notificación mediante una estructura tipo:

`contact_center_notifications`

con:

- appointment_id;
- event_type;
- recipients_json;
- status;
- error;
- sent_at;
- created_at.

---

## 15. Permisos

Se implementará un resolver backend específico, por ejemplo:

`backend/app/utils/contact_center_access.py`

No se deberán hardcodear usuarios particulares.

Roles conceptuales:

### 15.1 Agente Contact Center

Puede:

- ver su cartera;
- crear contactos;
- registrar interacciones;
- programar seguimiento;
- crear citas;
- consultar sus propios casos;
- visualizar posibles duplicados;
- solicitar/ejecutar merge si su permiso lo autoriza.

### 15.2 Supervisor Contact Center

Puede:

- ver cartera completa;
- asignar/reasignar casos;
- ver productividad;
- ver seguimientos vencidos;
- ver todas las citas dentro de su alcance;
- resolver duplicados;
- ejecutar merges;
- consultar reportes.

### 15.3 Gerente

Puede:

- ver citas únicamente de sus sucursales autorizadas;
- usar vista tabla/calendario;
- abrir detalle de cita;
- cerrar cita;
- reagendar cuando corresponda;
- reportar compra.

No obtiene por ello acceso global a la cartera completa del Contact Center.

### 15.4 Administrador

Puede consultar y operar todo el módulo según política general de Suite.

### 15.5 Implementación de acceso

El permiso deberá basarse en atributos reales de usuario/alcance y no únicamente en lo que oculte Angular.

El contrato no fija IDs concretos de departamento o usuarios.

La implementación deberá reutilizar la infraestructura de permisos existente cuando sea adecuada.

---

## 16. Pantallas

### 16.1 Contact Center — Mis contactos

Ruta propuesta:

`/#/contact-center`

Vista principal del operador.

Filtros rápidos:

- Mis pendientes
- Nuevos
- Seguimientos
- Citas
- Todos

Tabla conceptual:

| Contacto | Origen | Sucursal | Estado | Próxima acción |
|---|---|---|---|---|
| María · 686... | CRM | Villas del Rey | Nuevo | Llamar |
| Juan · 686... | Reactivación | Tec Mexicali | Seguimiento | Hoy 17:00 |
| Ana · 686... | Mensaje | Sendero Mexicali | Interesado | Llamar |
| Pedro · 686... | Campaña | Villas del Rey | Cita | Mañana 18:00 |

Acción visible:

**+ Nuevo contacto**

### 16.2 Ficha de contacto

Debe mostrar:

- identidad;
- teléfono;
- email;
- sucursal preferida;
- fuentes enlazadas;
- casos;
- historial cronológico;
- próxima acción;
- citas.

Debajo:

**¿Qué pasó con este contacto?**

con acciones rápidas.

### 16.3 Nuevo contacto

Formulario corto.

Antes de confirmar deberá consultar duplicados.

### 16.4 Modal de duplicados

Debe permitir:

- comparar perfiles;
- visualizar campos diferentes;
- abrir cada historial;
- seleccionar contacto superviviente;
- resolver valor final por campo;
- ejecutar merge.

### 16.5 Reporte Contact Center

Ruta propuesta:

`/#/contact-center/report`

Deberá ofrecer dos representaciones del mismo dataset:

- **Tabla**
- **Calendario**

No se duplicará lógica de negocio entre ambas vistas.

Filtros mínimos:

- rango;
- sucursal;
- región, cuando aplique;
- agente;
- origen;
- estado;
- resultado.

---

## 17. Calendario de citas

El calendario es parte de V1.

Vistas mínimas:

- mes;
- semana;
- día.

Cada evento podrá mostrar:

```text
18:00
Juan Pérez
Villas del Rey
Sandra
CRM
Pendiente
```

Al seleccionar una cita deberá abrirse la misma ficha/modal utilizada desde tabla.

### 17.1 Gerentes

Los gerentes utilizarán este mismo calendario, pero backend filtrará exclusivamente las sucursales permitidas.

No se construirá un calendario paralelo para gerentes.

### 17.2 Estados visuales

El calendario podrá diferenciar:

- programada;
- cierre pendiente;
- cerrada;
- no asistió;
- reagendada;
- cancelada.

La lógica de colores pertenece a frontend; los estados pertenecen al contrato backend.

---

## 18. Métricas operativas

V1 deberá dejar preparada la información para calcular:

- contactos asignados;
- contactos trabajados;
- intentos;
- contactos efectivos;
- seguimientos programados;
- seguimientos vencidos;
- citas generadas;
- citas cerradas;
- citas pendientes de cierre;
- asistencias;
- no-shows;
- compras reportadas;
- compras verificadas;
- conversión contacto → cita;
- conversión cita → asistencia;
- conversión asistencia → compra verificada.

Todo deberá poder desglosarse por:

- agente;
- sucursal;
- origen;
- campaña cuando exista referencia;
- periodo.

Estas métricas son operativas y no reemplazan KPIs corporativos existentes.

---

## 19. API propuesta

Blueprint:

`/api/contact-center`

### 19.1 Contactos

- `GET /api/contact-center/contacts`
- `POST /api/contact-center/contacts`
- `GET /api/contact-center/contacts/<id>`
- `PATCH /api/contact-center/contacts/<id>`
- `GET /api/contact-center/contacts/duplicates`
- `POST /api/contact-center/contacts/merge`

### 19.2 Casos

- `GET /api/contact-center/cases`
- `POST /api/contact-center/cases`
- `GET /api/contact-center/cases/<id>`
- `PATCH /api/contact-center/cases/<id>`
- `POST /api/contact-center/cases/<id>/assign`
- `POST /api/contact-center/cases/<id>/close`

### 19.3 Interacciones

- `GET /api/contact-center/cases/<id>/interactions`
- `POST /api/contact-center/cases/<id>/interactions`

### 19.4 Citas

- `GET /api/contact-center/appointments`
- `POST /api/contact-center/appointments`
- `GET /api/contact-center/appointments/<id>`
- `POST /api/contact-center/appointments/<id>/close`
- `POST /api/contact-center/appointments/<id>/reschedule`

### 19.5 Reporte / calendario

- `GET /api/contact-center/report`
- `GET /api/contact-center/calendar`

Ambos deberán reutilizar la misma capa de consulta/servicio y diferir únicamente en el shape requerido por UI cuando sea necesario.

### 19.6 Validación de compra

- servicio interno de conciliación con Venta Total;
- endpoint administrativo/manual opcional para revalidar;
- automatización posterior permitida.

Todos los endpoints deberán resolver permisos en backend.

---

## 20. Backend propuesto

Archivos tentativos:

```text
backend/app/routes/contact_center_routes.py
backend/app/models/contact_center.py
backend/app/services/contact_center_service.py
backend/app/services/contact_center_identity_service.py
backend/app/services/contact_center_appointment_service.py
backend/app/services/contact_center_purchase_verification_service.py
backend/app/utils/contact_center_access.py
backend/app/utils/contact_center_notify.py
```

La separación exacta podrá ajustarse durante implementación evitando un archivo monolítico.

---

## 21. Frontend propuesto

Estructura tentativa:

```text
frontend/src/app/contact-center/
  contact-center.routes.ts
  contact-center-home.component.ts
  contact-center-home.component.html
  contact-center-home.component.css

  contact-detail/
  contact-create/
  duplicate-merge/
  appointments/
  report/
  services/
  models/
```

Reglas Angular:

- lógica en `.ts`;
- HTML sólo estructura, bindings simples y llamadas a métodos/propiedades;
- estilos en `.css`;
- no templates inline;
- no estilos inline;
- service de dominio consume `environment.apiUrl`.

---

## 22. Integración con navegación

Se agregará una entrada principal:

**Contact Center**

La visibilidad del menú deberá depender de acceso.

La ruta siempre deberá estar protegida además por guard frontend y validación backend.

Subvistas:

- Mis contactos
- Citas
- Reporte

Según rol algunas opciones podrán ocultarse.

---

## 23. Importación desde Funnel / CRM

La población del Funnel no deberá convertirse automáticamente completa en casos activos sin una decisión operacional.

V1 deberá soportar seleccionar o cargar a cartera contactos CRM elegibles.

Cuando un contacto del Funnel entre a Contact Center:

1. se identifica referencia iVentas;
2. se intenta resolver contacto existente;
3. si existe, se vincula;
4. si hay candidatos ambiguos, se abre flujo de duplicados;
5. se crea o reutiliza contacto;
6. se crea caso;
7. se asigna agente.

El caso deberá conservar suficiente referencia para volver desde Contact Center al contexto de Marketing cuando aplique.

---

## 24. Reactivaciones y campañas

Contact Center podrá recibir casos originados desde campañas/reac­tivaciones.

La creación del caso no modifica las reglas de atribución definidas en:

`docs/contratos/contrato_reactivaciones_atribuidas_campana_v1.md`

Una reactivación canónica seguirá dependiendo de las fuentes y reglas establecidas por Marketing/Warehouse.

Contact Center aporta:

- llamadas;
- seguimientos;
- citas;
- observaciones;
- evidencia operativa.

No deberá declarar por sí solo una reactivación corporativa canónica.

---

## 25. Auditoría

Todas las entidades operativas deberán conservar:

- usuario creador;
- timestamps;
- usuario que ejecuta acciones críticas.

Acciones críticas mínimas auditables:

- asignación/reasignación;
- creación de cita;
- cierre de cita;
- reagendado;
- reporte manual de compra;
- merge de contactos.

No se deben usar hard-deletes para borrar historial operativo normal.

---

## 26. Fechas y zona horaria

Persistencia:

- timestamps con timezone/UTC según patrón del backend.

Presentación y reglas operativas:

- `America/Tijuana`.

La lógica no deberá mezclar fechas naive con timestamps aware.

---

## 27. Migraciones

Todo cambio de esquema deberá implementarse mediante Alembic.

No se crearán tablas manualmente en producción.

Las migraciones deberán incluir:

- tablas;
- FKs;
- índices;
- constraints;
- enums/check constraints cuando aplique.

El deploy deberá seguir:

```text
repo local
→ commit
→ push / PR / merge
→ servidor git pull
→ docker compose up -d --build backend frontend
→ flask db upgrade cuando aplique
```

---

## 28. Índices mínimos

Se deberán considerar índices para:

- `contact_center_contacts.phone_mx10`;
- casos por `assigned_user_id + status`;
- casos por `contact_id`;
- casos por `next_action_at`;
- interacciones por `case_id + created_at`;
- citas por `sucursal_id + scheduled_at`;
- citas por `status + scheduled_at`;
- citas por `contact_id`;
- links por `source_type + source_key`.

Los índices finales deberán validarse contra consultas reales.

---

## 29. Pruebas mínimas

### 29.1 Backend

Cubrir:

- creación manual;
- detección de duplicado;
- merge sin pérdida de relaciones;
- creación de caso;
- asignación;
- interacción;
- seguimiento;
- cita;
- sucursal distinta al origen;
- cierre obligatorio;
- no-show;
- reagendado;
- compra reportada;
- compra verificada;
- permisos de gerente por sucursal;
- permisos de agente;
- correo después de commit;
- falla SMTP sin rollback.

### 29.2 Frontend

Contratos mínimos:

- rutas;
- guard;
- formulario simple;
- opciones de interacción;
- modal de duplicados;
- tabla;
- calendario;
- cierre de cita;
- estados de compra reportada/verificada.

### 29.3 Regresión

No deberá romper:

- Funnel original;
- Funnel ajustado;
- Marketing/iVentas;
- Reactivaciones;
- Venta Total;
- Tickets;
- permisos existentes.

---

## 30. Criterios de aceptación de V1

V1 se considera funcional cuando:

1. un agente puede crear un contacto manual;
2. puede trabajar un contacto proveniente de CRM/Funnel;
3. puede registrar múltiples llamadas sin perder historial;
4. puede programar seguimiento;
5. puede agendar una cita en cualquier sucursal permitida;
6. la sucursal recibe notificación por correo;
7. el gerente ve la cita en tabla/calendario;
8. el gerente sólo ve sucursales autorizadas;
9. una cita pasada queda visible hasta cerrarse;
10. el gerente puede cerrarla con resultado;
11. si reporta compra, queda como provisional;
12. el sistema puede validar la compra contra Venta Total y conservar evidencia;
13. duplicados pueden revisarse en modal;
14. un merge conserva datos, historial, casos, citas y referencias;
15. el supervisor puede filtrar actividad por agente, sucursal, origen y periodo;
16. toda autorización sensible se vuelve a validar en backend.

---

## 31. Fuera de alcance V1

No forma parte obligatoria de esta fase:

- marcador telefónico integrado;
- grabación de llamadas;
- telefonía VoIP;
- envío automático de WhatsApp;
- lectura automática de conversaciones iVentas en tiempo real;
- IA para resumir llamadas;
- scoring automático de leads;
- distribución automática avanzada de cartera;
- SLA sofisticado;
- atribución financiera definitiva de campañas basada únicamente en Contact Center;
- sustitución de KPIs corporativos;
- automatización de recordatorios recurrentes por scheduler.

La arquitectura deberá permitir incorporar estas capacidades después sin reconstruir la identidad base.

---

## 32. Orden recomendado de implementación

Para respetar desarrollo incremental:

### Paso 1

Migración + modelos base:

- contactos;
- links;
- casos;
- interacciones.

### Paso 2

Permisos backend + endpoints básicos.

### Paso 3

Pantalla **Mis contactos** + ficha + captura manual.

### Paso 4

Seguimientos y `next_action_at`.

### Paso 5

Citas + cierre obligatorio.

### Paso 6

Notificación por correo.

### Paso 7

Vista tabla/calendario para CC y gerentes.

### Paso 8

Detección/merge de duplicados.

### Paso 9

Integración controlada con Funnel/iVentas.

### Paso 10

Validación contra Venta Total.

### Paso 11

Reporte y métricas.

Cada paso deberá validarse antes de introducir el siguiente.

---

## 33. Decisiones cerradas por este contrato

Quedan acordadas:

- Contact Center será módulo propio.
- Funnel seguirá siendo analítico.
- El contacto representa a la persona.
- El caso representa la razón de seguimiento.
- Habrá asignación por usuario.
- Se podrán crear contactos manuales.
- Los contactos CRM/Funnel podrán incorporarse sin duplicar identidad.
- Se soportarán orígenes CRM, mensajes, reactivaciones, campañas y manual.
- Las interacciones conservarán historial.
- Habrá seguimiento con fecha/hora.
- El agente seleccionará sucursal de cita.
- La sucursal puede diferir de la sucursal origen.
- Se reutilizará el sender SMTP existente.
- La cita se guarda antes de intentar correo.
- Los gerentes verán sólo sus sucursales.
- Toda cita pasada deberá cerrarse.
- Reagendar conservará la cita anterior.
- “Compró” manual será provisional.
- Venta Total será la fuente canónica de compra.
- Existirá detección de duplicados.
- Existirá modal de comparación.
- El merge será auditable y no destructivo.
- Reporte tendrá tabla y calendario.
- El calendario será compartido por CC y gerentes bajo distintos permisos.
- Los permisos reales estarán en backend.
- Todo cambio de DB usará Alembic.

---

## 34. Resultado esperado

Contact Center deberá convertirse en la capa operativa que conecte:

```text
Marketing / CRM
        +
Reactivaciones / Campañas
        +
Mensajes / Captura manual
        ↓
CONTACT CENTER
        ↓
seguimiento humano trazable
        ↓
citas
        ↓
sucursales
        ↓
resultado
        ↓
Venta Total
        ↓
evidencia comercial
```

La experiencia diaria debe seguir siendo sencilla para el operador, mientras Suite conserva una estructura capaz de medir y auditar el recorrido completo de cada contacto.
