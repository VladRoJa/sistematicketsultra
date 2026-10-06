# Contrato — Requisiciones V1 Bridge hacia Tickets V2

Estado: CONTRATO FUNCIONAL-TÉCNICO VIGENTE + EXTENSIÓN E1 POST-APROBACIÓN CONGELADA / LISTA PARA IMPLEMENTACIÓN
Fecha base: 2026-10-02
Última enmienda funcional: 2026-10-06
Alcance: módulo urgente de requisiciones/compras, inicialmente para equipo de gimnasio, diseñado para operar antes de Tickets V2 y migrar 1:1 al modelo V2.
Contrato relacionado: docs/contratos/tickets_v2/CONTRATO_TICKETS_V2_GLOBAL.md

## 0. Regla de trabajo

Este módulo existe para resolver una necesidad urgente de negocio sin seguir acoplando lógica nueva a la tabla legacy de Tickets.

Principio rector:

> Requisiciones se verá integrada en Suite Ultra y podrá convivir visualmente con Tickets, pero tendrá dominio, persistencia, workflow, permisos, historial y adjuntos propios.

Reglas obligatorias:

- No reutilizar Ticket como entidad persistente de requisiciones.
- No agregar estados de requisición al enum legacy estado_ticket_enum.
- No reutilizar por_validar para revisión de Gerencia Deportiva.
- No usar departamento_id legacy como máquina de routing.
- No insertar requisiciones en Maintenance Planner.
- No incluir requisiciones en reportes/KPIs de fallas correctivas.
- No revivir el flujo viejo de preaprobación RRHH.
- No implementar un módulo de Compras general. La extensión E1 solo cubre cotización estructurada, aprobación financiera de la cotización, seguimiento operativo de pago/logística y confirmación de recepción.
- Backend será autoridad de permisos y transiciones.
- Todo dato creado aquí deberá tener mapping explícito hacia Tickets V2.
- No PR, merge ni deploy hasta cerrar cada milestone y autorizarlo explícitamente.

## 1. Objetivo

Permitir que una sucursal cargue una requisición de compra de equipo de gimnasio dentro de Suite Ultra.

Flujo inicial:

    SUCURSAL
       |
       | crea requisición
       v
    PENDING_REVIEW
       |
       v
    GERENCIA DEPORTIVA
       |
       +-- Solicitar información -> NEEDS_INFO
       |
       +-- Rechazar -> REJECTED
       |
       +-- Aprobar -> IN_QUOTATION
                         |
                         v
                    MANTENIMIENTO

La implementación M1+M2 actualmente desplegable termina operativamente en IN_QUOTATION: Mantenimiento recibe una requisición aprobada y puede cargar adjuntos de tipo QUOTE.

La extensión E1 definida en este mismo contrato continúa el ciclo post-aprobación:

    IN_QUOTATION
       |
       | Mantenimiento selecciona cotización
       v
    QUOTE_PENDING_FINANCE_APPROVAL
       |
       | APROBADOR_FINANCIERO aprueba
       v
    PAYMENT_REQUESTED
       |
       v
    SHIPPING_IN_PROGRESS
       |
       v
    IMPORT_IN_PROGRESS          [solo si aplica]
       |
       v
    FINAL_DESTINATION_SHIPMENT
       |
       +-- recibido conforme --------------------> CLOSED
       |
       +-- entrega no conforme -> RECEIPT_ISSUE
                                      |
                                      | Mantenimiento resuelve
                                      | y reanuda logística
                                      v
                               SHIPPING_IN_PROGRESS

Si la cotización financiera se rechaza:

    QUOTE_PENDING_FINANCE_APPROVAL
       |
       | rechazo con motivo
       v
    IN_QUOTATION

El responsable operativo actual de aprobación financiera es Fabián, pero su identidad no se hardcodeará en código, username ni email. La implementación resolverá una capacidad APROBADOR_FINANCIERO configurable.

Esta extensión E1 está congelada contractualmente y lista para implementación M7; todavía no debe considerarse implementada.

## 2. Alcance funcional

La primera versión deberá permitir:

1. crear requisición;
2. seleccionar sucursal;
3. registrar una o más partidas;
4. indicar cantidad por partida;
5. indicar motivo;
6. escribir justificación;
7. definir prioridad;
8. adjuntar evidencia cuando aplique;
9. enviar automáticamente a revisión de Gerencia Deportiva;
10. aprobar;
11. rechazar;
12. solicitar información;
13. permitir al solicitante corregir y reenviar;
14. al aprobar, registrar actor/fecha/comentario y entregar a Mantenimiento;
15. conservar historial auditable;
16. consultar requisiciones según permisos;
17. mostrar claramente estado actual;
18. mantener el módulo aislado de Tickets V1;
19. conservar estructura migrable a Tickets V2.

## 3. Fuera de alcance

No implementar todavía:

- catálogo formal de proveedores;
- maestro corporativo de proveedores;
- órdenes de compra formales/ERP;
- presupuesto;
- centros de costo;
- facturas;
- pagos;
- contabilidad;
- recepción parcial;
- devoluciones parciales;
- inventario automático;
- autorización financiera;
- niveles adicionales de autorización;
- chat;
- menciones;
- Slack interno;
- workflow visual configurable;
- integración ERP.

## 4. Relación con Tickets V1

Requisiciones V1 no será un subtipo persistido en la tabla tickets.

No se agregarán columnas de compra ni nuevos estados al Ticket legacy.

La integración con Tickets V1 será solo de experiencia de usuario cuando convenga:

    Tickets
    ├── Crear ticket
    ├── Ver tickets
    └── Requisiciones

Motivo: Tickets V1 acopla departamento, estado, visibilidad, notificaciones, Planner, reportes y cierre. Meter Requisiciones allí aumentaría la deuda que Tickets V2 busca eliminar.

## 5. Relación con Tickets V2

Este módulo es un bridge pre-V2.

Cuando Tickets V2 exista, cada requisición deberá poder transformarse conceptualmente en:

    Ticket V2
    type = PURCHASE_REQUISITION

con mapping directo de:

- cabecera;
- partidas;
- workflow;
- participantes;
- eventos;
- adjuntos.

No deberá requerirse interpretar semántica legacy de Tickets para migrarlo.

## 6. Entidad principal

Entidad propuesta:

purchase_requisitions

Campos mínimos:

- id
- public_id
- sucursal_id
- created_by_user_id
- category
- reason
- justification
- priority
- status
- approved_by_user_id, nullable
- approved_at, nullable
- approval_comment, nullable
- rejected_at, nullable
- created_at
- updated_at

Los nombres finales deberán alinearse con las convenciones vigentes del repo al implementar.

## 7. Folio

Toda requisición tendrá identificador público independiente del PK.

Formato sugerido:

    RQ-2026-000001

Requisitos:

- único;
- backend-generated;
- estable;
- no editable;
- preservable en V2;
- seguro ante concurrencia.

## 8. Categoría

Campo:

category

Valor inicial:

    GYM_EQUIPMENT

Etiqueta UI:

    Equipo de gimnasio

Aunque inicialmente sea la única categoría, deberá persistirse explícitamente.

No implementar aún otras categorías.

## 9. Partidas

Entidad propuesta:

purchase_requisition_items

Campos mínimos:

- id
- requisition_id
- item_description
- quantity
- notes, nullable
- created_at

Reglas:

- mínimo una partida;
- descripción obligatoria;
- quantity > 0;
- cantidad entera en V1;
- backend valida todas las partidas.

La UI podrá ofrecer:

    Equipo / artículo      Cantidad
    [Caminadora        ]   [2]

    [ + Agregar otro ]

La separación cabecera/partidas evita rediseñar el esquema cuando una solicitud incluya más de un equipo y migra naturalmente a V2.

## 10. Motivo

Valores iniciales:

- REPLACEMENT — Reposición
- NEW_EQUIPMENT — Equipo nuevo
- DAMAGE — Daño
- EXPANSION — Expansión
- OTHER — Otro

Si es OTHER, la justificación debe explicar el contexto.

## 11. Prioridad

Valores:

- NORMAL
- HIGH
- CRITICAL

La prioridad no evita revisión de Gerencia Deportiva.

Incluso CRITICAL no notifica Mantenimiento antes de aprobación.

## 12. Justificación

justification será obligatoria.

No mezclarla con:

- descripción de partida;
- comentario de aprobación;
- rechazo;
- solicitud de información;
- futuras notas de cotización.

## 13. Estados de workflow

Estados vigentes del bridge implementado:

- PENDING_REVIEW
- NEEDS_INFO
- REJECTED
- IN_QUOTATION
- CLOSED

Estados adicionales propuestos por E1:

- QUOTE_PENDING_FINANCE_APPROVAL
- PAYMENT_REQUESTED
- SHIPPING_IN_PROGRESS
- IMPORT_IN_PROGRESS
- FINAL_DESTINATION_SHIPMENT
- RECEIPT_ISSUE

CLOSED representa una requisición recibida conforme por la sucursal.

RECEIPT_ISSUE representa una entrega reportada por la sucursal como no conforme y devuelve ownership operativo a Mantenimiento.

RECEIVED será evento auditable, no estado adicional:

    FINAL_DESTINATION_SHIPMENT -> CLOSED
    event_type = RECEIVED

IMPORT_IN_PROGRESS es un paso opcional. Solo se usa cuando la compra requiere importación.

### 13.1 Creación

    CREATE -> PENDING_REVIEW

Responsable funcional: GERENCIA DEPORTIVA.

Mantenimiento no recibe responsabilidad ni notificación.

### 13.2 Solicitar información

    PENDING_REVIEW -> NEEDS_INFO

Solo Gerencia Deportiva o administrador autorizado.

Comentario obligatorio.

Se notifica al solicitante.

### 13.3 Reenviar

    NEEDS_INFO -> PENDING_REVIEW

El solicitante autorizado puede modificar:

- partidas;
- motivo;
- justificación;
- prioridad;
- evidencia.

Al reenviar se notifica de nuevo Gerencia Deportiva.

### 13.4 Rechazar

    PENDING_REVIEW -> REJECTED

Solo Gerencia Deportiva o administrador autorizado.

Motivo obligatorio.

REJECTED es terminal en este MVP.

Mantenimiento no recibe notificación.

### 13.5 Aprobar

    PENDING_REVIEW -> IN_QUOTATION

APPROVED es evento auditable, no estado intermedio sin propietario.

En la misma transacción deberán persistirse:

- status = IN_QUOTATION;
- approved_by_user_id;
- approved_at;
- approval_comment;
- evento APPROVED;
- evento ROUTED_TO_MAINTENANCE.

Después del commit se notifica solicitante + Mantenimiento.

### 13.6 Cotizar — E1

Estado:

    IN_QUOTATION

Responsable operativo:

- MANTENIMIENTO;
- SR_MANTENIMIENTO;
- AUX_MANTENIMIENTO;
- ADMINISTRADOR únicamente como respaldo técnico autorizado.

Mantenimiento podrá registrar una o más cotizaciones estructuradas y adjuntar sus archivos.

Reglas E1:

- una requisición puede tener múltiples cotizaciones;
- cada cotización conserva proveedor, monto, moneda, fecha, archivo y observaciones;
- debe existir una cotización seleccionada antes de enviarla a aprobación financiera;
- agregar cotizaciones no cambia el estado;
- agregar una cotización no envía correo por sí mismo;
- no se modifica la requisición base ni sus partidas después de aprobación de Gerencia Deportiva.

Acción:

    Enviar cotización a aprobación financiera

Transición:

    IN_QUOTATION -> QUOTE_PENDING_FINANCE_APPROVAL

Al enviar:

- la cotización seleccionada queda identificada de forma durable;
- se registra evento QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL;
- la cotización no puede sustituirse mientras exista decisión financiera pendiente;
- se notifica al APROBADOR_FINANCIERO configurado.

### 13.7 Aprobación financiera de cotización — E1

Estado:

    QUOTE_PENDING_FINANCE_APPROVAL

Responsable funcional:

    APROBADOR_FINANCIERO

Responsable operativo actual:

    Fabián

Regla técnica obligatoria:

- no hardcodear username, email ni nombre personal en el workflow;
- la capacidad financiera se resolverá mediante la allowlist persistida purchase_requisition_finance_approvers por user_id;
- solo filas is_active=true otorgan can_approve_requisition_quote;
- cambiar al responsable financiero no debe requerir modificar código ni editar manualmente la base de datos en servidor;
- la asignación/desactivación se hará desde una acción administrativa de Suite Ultra.

El aprobador financiero consulta:

- requisición;
- sucursal;
- justificación;
- partidas;
- aprobación previa de Gerencia Deportiva;
- cotización seleccionada;
- proveedor;
- monto;
- moneda;
- archivo de cotización;
- observaciones de cotización.

Acciones:

    [ Aprobar cotización ]
    [ Rechazar cotización ]

Aprobar:

    QUOTE_PENDING_FINANCE_APPROVAL -> PAYMENT_REQUESTED

Efectos:

- evento QUOTE_APPROVED_BY_FINANCE;
- actor y fecha quedan auditados;
- comentario financiero opcional;
- la cotización aprobada queda bloqueada como cotización autorizada;
- ownership operativo regresa a Mantenimiento;
- se notifica a Mantenimiento.

Rechazar:

    QUOTE_PENDING_FINANCE_APPROVAL -> IN_QUOTATION

Reglas:

- comentario/motivo obligatorio;
- evento QUOTE_REJECTED_BY_FINANCE;
- la cotización rechazada queda histórica;
- Mantenimiento puede agregar o seleccionar otra cotización y reenviar;
- se notifica a Mantenimiento.

La aprobación de Gerencia Deportiva autoriza la necesidad. La aprobación financiera posterior autoriza la cotización seleccionada. Son decisiones distintas y ambas quedan auditadas.

### 13.8 Seguimiento de pago y logística por Mantenimiento — E1

Después de aprobación financiera, el owner vuelve a Mantenimiento.

Estados operativos propuestos por Mantenimiento:

    PAYMENT_REQUESTED
        UI: En solicitud de pago

    SHIPPING_IN_PROGRESS
        UI: En proceso de envío

    IMPORT_IN_PROGRESS
        UI: En proceso de importación

    FINAL_DESTINATION_SHIPMENT
        UI: Envío a destino final

Secuencia base:

    PAYMENT_REQUESTED
       |
       v
    SHIPPING_IN_PROGRESS
       |
       v
    IMPORT_IN_PROGRESS
       |
       v
    FINAL_DESTINATION_SHIPMENT

Regla cerrada de importación:

Desde SHIPPING_IN_PROGRESS existen exactamente dos avances válidos:

    SHIPPING_IN_PROGRESS -> IMPORT_IN_PROGRESS

cuando la compra requiere importación;

o:

    SHIPPING_IN_PROGRESS -> FINAL_DESTINATION_SHIPMENT

cuando la compra no requiere importación.

La ruta directa a FINAL_DESTINATION_SHIPMENT no es un salto de estado: es una transición explícitamente válida.

Cuando se use la ruta sin importación, el evento de avance deberá conservar metadata equivalente a:

    import_required = false

Cuando se entre a IMPORT_IN_PROGRESS, el historial hará explícito que la importación sí aplicó.

Mantenimiento decide la ruta operativa al avanzar desde SHIPPING_IN_PROGRESS; backend solo acepta una de esas dos transiciones y conserva la decisión en auditoría.

La UI podrá presentar estos pasos mediante dropdown, pero el dropdown es solo presentación.

Reglas backend:

- no existe PATCH genérico de status;
- Mantenimiento solo puede avanzar por transiciones permitidas;
- no puede saltar arbitrariamente a CLOSED;
- no puede regresar estados desde UI ordinaria;
- cualquier corrección administrativa usa exclusivamente el flujo ADMINISTRATIVE_CORRECTION definido en 13.11;
- cada cambio crea evento auditable con actor, from_status, to_status y created_at.

No enviar correo por cada avance intermedio de pago/logística salvo decisión posterior. El cambio relevante de owner ocurre al llegar a FINAL_DESTINATION_SHIPMENT.

Al cambiar a FINAL_DESTINATION_SHIPMENT:

- termina la responsabilidad operativa de Mantenimiento para E1;
- el expediente pasa a espera de confirmación de la sucursal;
- se notifica a GERENTE(s) autorizados de la sucursal que originó la requisición;
- el gerente obtiene la acción Confirmar recibido;
- Mantenimiento conserva lectura.

### 13.9 Recepción en sucursal — E1

Estado previo:

    FINAL_DESTINATION_SHIPMENT

Responsable:

- GERENTE autorizado de la sucursal que originó la requisición.

El gerente dispone de dos decisiones explícitas:

    [ Confirmar recibido ]
    [ Reportar incidencia ]

#### 13.9.1 Recibido conforme

Transición:

    FINAL_DESTINATION_SHIPMENT -> CLOSED

Evento:

    RECEIVED

Confirmar recibido significa que la requisición completa fue recibida conforme.

Datos:

- actor que confirma, derivado de sesión;
- fecha/hora, definida por servidor;
- observaciones, opcionales;
- evidencia de recepción, opcional.

En la misma transacción:

- se registra RECEIVED;
- from_status = FINAL_DESTINATION_SHIPMENT;
- to_status = CLOSED;
- status = CLOSED.

Después del commit:

- se notifica a Mantenimiento;
- se notifica a Gerencia Deportiva.

#### 13.9.2 Entrega no conforme

Transición:

    FINAL_DESTINATION_SHIPMENT -> RECEIPT_ISSUE

Evento:

    RECEIPT_ISSUE_REPORTED

Tipos iniciales de incidencia:

- DAMAGED: recibido dañado;
- INCOMPLETE: entrega incompleta/faltantes;
- WRONG_ITEM: artículo/equipo incorrecto;
- OTHER: otra no conformidad.

Para reportar incidencia se exige:

- tipo de incidencia;
- descripción/comentario;
- al menos una evidencia adjunta de imagen o PDF.

Efectos:

- la requisición NO se cierra;
- ownership operativo vuelve a Mantenimiento;
- el gerente conserva lectura;
- se notifica a Mantenimiento;
- queda auditado actor, fecha, tipo, comentario y evidencia.

RECEIPT_ISSUE no representa aceptación parcial. Toda la requisición sigue abierta hasta recepción completa conforme.

### 13.10 Resolver incidencia de recepción — E1

Estado:

    RECEIPT_ISSUE

Responsable:

- familia de roles de Mantenimiento.

Acción:

    Reanudar logística

Transición base:

    RECEIPT_ISSUE -> SHIPPING_IN_PROGRESS

Evento:

    RECEIPT_ISSUE_RESOLUTION_STARTED

Para reanudar se exige comentario de resolución/acción tomada.

Después continúa el mismo flujo logístico:

    SHIPPING_IN_PROGRESS
        -> IMPORT_IN_PROGRESS, si aplica
        -> FINAL_DESTINATION_SHIPMENT

Al volver a FINAL_DESTINATION_SHIPMENT se notifica nuevamente al GERENTE de la sucursal para una nueva validación.

El ciclo puede repetirse mientras exista una nueva entrega no conforme.

E1 no permite:

- cerrar desde RECEIPT_ISSUE;
- que Mantenimiento confirme recibido;
- aceptación/cierre parcial;
- eliminar el historial de incidencias anteriores.

### 13.11 Corrección administrativa — E1

Actor autorizado:

- rol ADMINISTRADOR.

ADMICORP queda cubierto por su rol ADMINISTRADOR; no se hardcodea username.

Objetivo:

Corregir errores operativos de estado o recepción sin borrar, reescribir ni ocultar el historial que realmente ocurrió.

Acción:

    Corrección administrativa

La corrección exige:

- target_status de catálogo cerrado;
- motivo obligatorio;
- comentario explicativo obligatorio;
- actor derivado de sesión;
- timestamp de servidor.

Evento:

    ADMINISTRATIVE_CORRECTION

Debe guardar al menos:

- from_status real;
- to_status corregido;
- actor_user_id;
- reason;
- comment;
- metadata con contexto disponible.

Reglas obligatorias:

- no existe edición directa de status en DB desde UI;
- no existe PATCH genérico de status;
- no se eliminan eventos anteriores;
- no se modifica retroactivamente quién aprobó, rechazó, recibió o reportó incidencia;
- una corrección no crea APPROVED, QUOTE_APPROVED_BY_FINANCE ni RECEIVED falsos;
- una corrección no puede saltarse prerrequisitos de negocio que nunca ocurrieron;
- toda corrección queda visible en historial como acción administrativa;
- el expediente conserva tanto el error original como su corrección.

Prerrequisitos por familia de estados:

- IN_QUOTATION o cualquier estado posterior exige evento APPROVED inicial existente;
- PAYMENT_REQUESTED y estados logísticos posteriores exigen QUOTE_APPROVED_BY_FINANCE existente para la cotización vigente;
- CLOSED no puede ser target directo de ADMINISTRATIVE_CORRECTION: el cierre ordinario requiere RECEIVED por GERENTE autorizado;
- QUOTE_PENDING_FINANCE_APPROVAL exige una cotización seleccionada y un submit financiero vigente.

Catálogo cerrado de correcciones:

| Estado actual | Target permitido | Uso |
| --- | --- | --- |
| NEEDS_INFO | PENDING_REVIEW | deshacer una solicitud de información emitida por error |
| REJECTED | PENDING_REVIEW | reabrir un rechazo inicial equivocado |
| IN_QUOTATION | PENDING_REVIEW | reabrir revisión inicial cuando la aprobación de necesidad fue equivocada |
| QUOTE_PENDING_FINANCE_APPROVAL | IN_QUOTATION | cancelar un envío financiero pendiente y devolver control a Mantenimiento |
| PAYMENT_REQUESTED | QUOTE_PENDING_FINANCE_APPROVAL | reabrir la decisión financiera sobre la misma cotización |
| SHIPPING_IN_PROGRESS | PAYMENT_REQUESTED | corregir avance prematuro a envío |
| IMPORT_IN_PROGRESS | SHIPPING_IN_PROGRESS | corregir entrada prematura/errónea a importación |
| FINAL_DESTINATION_SHIPMENT | IMPORT_IN_PROGRESS | rollback cuando import_required=true |
| FINAL_DESTINATION_SHIPMENT | SHIPPING_IN_PROGRESS | rollback cuando import_required=false |
| RECEIPT_ISSUE | FINAL_DESTINATION_SHIPMENT | deshacer una incidencia de recepción reportada por error |
| CLOSED | FINAL_DESTINATION_SHIPMENT | reabrir una recepción confirmada por error |
| CLOSED | RECEIPT_ISSUE | reabrir cuando posteriormente se determina que la entrega no fue conforme |

No existen otros targets de corrección E1.

En particular:

- PENDING_REVIEW no tiene corrección administrativa de avance; se usa el workflow normal;
- una corrección nunca avanza a un estado posterior que tenga una transición ordinaria disponible;
- REJECTED no se corrige directamente a IN_QUOTATION;
- ningún estado se corrige directamente a CLOSED;
- PAYMENT_REQUESTED no se corrige directamente a IN_QUOTATION; primero se reabre la decisión financiera;
- estados logísticos retroceden como máximo un control operativo por corrección;
- desde FINAL_DESTINATION_SHIPMENT el rollback depende de la decisión auditada import_required;
- si import_required falta por inconsistencia, la corrección debe rechazarse hasta resolver explícitamente esa metadata.

Reconciliación de proyección:

La corrección no borra eventos históricos, pero puede ajustar los campos de proyección actuales para que correspondan al nuevo estado.

IN_QUOTATION -> PENDING_REVIEW:

- conserva el evento APPROVED histórico;
- limpia la proyección vigente approved_by_user_id / approved_at / approval_comment;
- metadata de ADMINISTRATIVE_CORRECTION incluye invalidates_operational_effect = APPROVED;
- una nueva aprobación normal vuelve a poblar la proyección.

QUOTE_PENDING_FINANCE_APPROVAL -> IN_QUOTATION:

- conserva QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL histórico;
- la cotización deja finance_status=PENDING y vuelve a DRAFT/SELECTED según modelo final;
- queda nuevamente editable/seleccionable por Mantenimiento;
- metadata registra cancel_finance_submission=true.

PAYMENT_REQUESTED -> QUOTE_PENDING_FINANCE_APPROVAL:

- conserva QUOTE_APPROVED_BY_FINANCE histórico;
- la cotización vigente vuelve a finance_status=PENDING como proyección actual;
- limpia finance_decided_by_user_id / finance_decided_at / finance_comment de la proyección vigente;
- metadata registra reopen_finance_decision=true;
- Finanzas debe volver a aprobar o rechazar mediante el flujo normal.

RECEIPT_ISSUE -> FINAL_DESTINATION_SHIPMENT:

- conserva RECEIPT_ISSUE_REPORTED histórico;
- metadata registra invalidate_receipt_issue_operational_effect=true;
- el gerente vuelve a tener las acciones de recepción.

Reapertura de CLOSED:

- exige motivo y comentario obligatorio;
- no borra RECEIVED;
- genera ADMINISTRATIVE_CORRECTION;
- marca en metadata que se trata de reopen_after_receipt;
- notifica a Mantenimiento y al GERENTE de la sucursal;
- el histórico debe mostrar que existió un cierre previo y fue corregido.

La corrección administrativa no sustituye los flujos normales. Si el proceso puede resolverse mediante la siguiente transición ordinaria, deberá usarse la transición ordinaria.

Backend implementará este catálogo como estructura cerrada por from_status; no construirá un motor genérico de workflow.

## 14. Matriz de transiciones

| Desde | Acción | Hacia |
| --- | --- | --- |
| — | crear | PENDING_REVIEW |
| PENDING_REVIEW | solicitar información | NEEDS_INFO |
| NEEDS_INFO | reenviar | PENDING_REVIEW |
| PENDING_REVIEW | aprobar necesidad | IN_QUOTATION |
| PENDING_REVIEW | rechazar | REJECTED |
| IN_QUOTATION | enviar cotización a Finanzas | QUOTE_PENDING_FINANCE_APPROVAL |
| QUOTE_PENDING_FINANCE_APPROVAL | aprobar cotización | PAYMENT_REQUESTED |
| QUOTE_PENDING_FINANCE_APPROVAL | rechazar cotización | IN_QUOTATION |
| PAYMENT_REQUESTED | avanzar | SHIPPING_IN_PROGRESS |
| SHIPPING_IN_PROGRESS | avanzar con importación | IMPORT_IN_PROGRESS |
| SHIPPING_IN_PROGRESS | avanzar sin importación | FINAL_DESTINATION_SHIPMENT |
| IMPORT_IN_PROGRESS | avanzar | FINAL_DESTINATION_SHIPMENT |
| FINAL_DESTINATION_SHIPMENT | confirmar recibido conforme | CLOSED |
| FINAL_DESTINATION_SHIPMENT | reportar incidencia | RECEIPT_ISSUE |
| RECEIPT_ISSUE | reanudar logística | SHIPPING_IN_PROGRESS |

Agregar/seleccionar cotizaciones en IN_QUOTATION no cambia status.

El dropdown de Mantenimiento no constituye permiso para saltar estados. Backend valida estrictamente la transición solicitada.

No exponer un PATCH genérico de status que permita saltarse el workflow.

## 15. Eventos / auditoría

Entidad:

    purchase_requisition_events

Campos mínimos:

- id
- requisition_id
- event_type
- actor_user_id, nullable para sistema
- from_status, nullable
- to_status, nullable
- comment, nullable
- metadata_json, nullable
- created_at

Eventos vigentes:

- CREATED
- INFO_REQUESTED
- RESUBMITTED
- APPROVED
- REJECTED
- ROUTED_TO_MAINTENANCE
- ATTACHMENT_ADDED

Eventos E1:

- QUOTE_ADDED
- QUOTE_SELECTED
- QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL
- QUOTE_APPROVED_BY_FINANCE
- QUOTE_REJECTED_BY_FINANCE
- PAYMENT_REQUESTED
- SHIPPING_STARTED
- IMPORT_STARTED
- IMPORT_NOT_APPLICABLE
- FINAL_DESTINATION_SHIPMENT_STARTED
- RECEIVED
- RECEIPT_ISSUE_REPORTED
- RECEIPT_ISSUE_RESOLUTION_STARTED

Los eventos serán append-only funcionalmente.

No permitir editar/borrar eventos desde UI.

## 16. Adjuntos

Entidad propuesta:

purchase_requisition_attachments

Campos mínimos:

- id
- requisition_id
- event_id, nullable
- attachment_type
- original_filename
- storage_key
- mime_type
- size_bytes
- sha256
- uploaded_by_user_id
- created_at
- deleted_at, nullable si la política técnica lo requiere

Tipos iniciales:

- EVIDENCE
- QUOTE
- OTHER

Tipo E1 propuesto:

- RECEIPT_EVIDENCE
- RECEIPT_ISSUE_EVIDENCE

RECEIPT_EVIDENCE será opcional al confirmar recibido conforme.

RECEIPT_ISSUE_EVIDENCE será obligatorio al reportar una entrega no conforme.

Las cotizaciones continúan usando QUOTE. E1 no define todavía comprobante de pago obligatorio ni una entidad de pago.

Requisitos:

- múltiples adjuntos;
- imágenes;
- PDF;
- acceso privado;
- autorización por requisición;
- no heredar automáticamente la retención de 30 días de ticket_attachments.

Antes de crear almacenamiento nuevo, investigar si los servicios seguros existentes pueden generalizarse sin acoplarse a Ticket.

## 17. Permisos

Backend es autoridad.

No usar únicamente departamento_id para decidir acceso.

### 17.1 Crear

Podrán crear:

- usuarios operativos autorizados que hoy pueden levantar solicitudes/tickets;
- gerentes;
- administradores.

LECTOR_GLOBAL no crea.

Usuario de sucursal crea para su propia sucursal.

Administradores corporativos podrán seleccionar sucursal cuando corresponda.

### 17.2 Ver antes de aprobación

PENDING_REVIEW / NEEDS_INFO:

- creador;
- usuarios autorizados de la misma sucursal según scope;
- Gerencia Deportiva;
- administradores autorizados.

Mantenimiento no adquiere acceso operativo por ser futuro owner.

### 17.3 Aprobar necesidad, rechazar, pedir información

Solo:

- rol GERENCIA DEPORTIVA;
- rol ADMINISTRADOR.

ADMICORP queda cubierto por su rol ADMINISTRADOR; no existe excepción por username.

### 17.4 Cotización y logística

Desde IN_QUOTATION hasta FINAL_DESTINATION_SHIPMENT, según el estado:

Capacidad can_manage_quotation / can_manage_requisition_logistics:

- MANTENIMIENTO;
- SR_MANTENIMIENTO;
- AUX_MANTENIMIENTO;
- ADMINISTRADOR únicamente como respaldo técnico autorizado.

Mantenimiento:

- agrega/selecciona cotizaciones en IN_QUOTATION;
- envía cotización seleccionada a Finanzas;
- no puede modificar cotización mientras QUOTE_PENDING_FINANCE_APPROVAL;
- recupera ownership al aprobarse la cotización;
- avanza desde PAYMENT_REQUESTED a SHIPPING_IN_PROGRESS;
- desde SHIPPING_IN_PROGRESS elige una de dos rutas válidas: IMPORT_IN_PROGRESS cuando aplica, o FINAL_DESTINATION_SHIPMENT cuando no hay importación;
- si entra a IMPORT_IN_PROGRESS, el siguiente paso es FINAL_DESTINATION_SHIPMENT;
- no confirma recepción.

### 17.5 Aprobación financiera de cotización — E1

Capacidad:

    can_approve_requisition_quote

Responsable operativo actual:

    Fabián

Implementación:

- fuente real: purchase_requisition_finance_approvers;
- lookup por user_id del usuario autenticado;
- exigir is_active=true;
- no username hardcodeado;
- no email hardcodeado;
- no depender de que el usuario tenga GERENCIA DEPORTIVA;
- ADMINISTRADOR no obtiene aprobación financiera automáticamente por su rol; debe estar asignado explícitamente si también debe aprobar.

Puede actuar únicamente en QUOTE_PENDING_FINANCE_APPROVAL.

Puede:

- aprobar cotización;
- rechazar cotización con motivo.

No puede:

- alterar requisición base;
- agregar partidas;
- seleccionar otra cotización;
- avanzar estados logísticos.

### 17.6 Recepción en sucursal — E1

En FINAL_DESTINATION_SHIPMENT:

Capacidad normal:

- GERENTE autorizado de la sucursal que originó la requisición.

Puede:

- confirmar recibido conforme;
- reportar incidencia de recepción.

No puede:

- cambiar estados logísticos;
- cerrar una entrega reportada como no conforme.

Mantenimiento no confirma recepción.

Gerencia Deportiva no confirma recepción solo por ser reviewer.

### 17.7 Incidencia de recepción — E1

En RECEIPT_ISSUE:

- Mantenimiento recupera ownership operativo;
- GERENTE de sucursal conserva lectura;
- Gerencia Deportiva conserva lectura;
- APROBADOR_FINANCIERO conserva lectura si su scope general lo permite, pero no decide esta etapa.

Solo Mantenimiento autorizado puede ejecutar Reanudar logística.

### 17.8 Corrección administrativa — E1

Solo rol ADMINISTRADOR puede ejecutar ADMINISTRATIVE_CORRECTION.

ADMICORP queda cubierto por su rol ADMINISTRADOR.

Esta capacidad:

- es global sobre Requisiciones;
- no implica can_approve_requisition_quote;
- no permite falsificar aprobaciones;
- no permite borrar historial;
- sí permite corregir/reabrir estados cuando se cumplen los prerrequisitos contractuales.

Frontend puede ocultar la acción a otros perfiles, pero backend es autoridad.

## 18. No hardcodear usuarios

Prohibido resolver negocio mediante username, email o nombre personal específico.

Esto aplica también al aprobador financiero.

El responsable operativo actual es Fabián, pero la implementación resolverá APROBADOR_FINANCIERO mediante purchase_requisition_finance_approvers por user_id.

Cambiar al responsable financiero no debe requerir deploy, cambio de código ni edición manual de SQL en producción.

La migración crea estructura, no asigna a Fabián buscando username/email. La asignación inicial se realiza mediante la configuración administrativa de Suite después del deploy.

Los destinatarios de Mantenimiento, Gerencia Deportiva y GERENTE de sucursal se resuelven por roles/capacidades/scope vigentes, nunca mediante usernames fijos.

## 19. Notificaciones

Matriz:

| Evento | Destinatario |
| --- | --- |
| CREATED | Gerencia Deportiva |
| INFO_REQUESTED | solicitante |
| RESUBMITTED | Gerencia Deportiva |
| APPROVED | solicitante + Mantenimiento |
| REJECTED | solicitante |
| QUOTE_ADDED / QUOTE_SELECTED | sin correo |
| QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL | APROBADOR_FINANCIERO |
| QUOTE_APPROVED_BY_FINANCE | Mantenimiento |
| QUOTE_REJECTED_BY_FINANCE | Mantenimiento |
| PAYMENT_REQUESTED / SHIPPING_STARTED / IMPORT_STARTED | sin correo |
| FINAL_DESTINATION_SHIPMENT_STARTED | GERENTE(s) autorizados de la sucursal |
| RECEIPT_ISSUE_REPORTED | Mantenimiento |
| RECEIPT_ISSUE_RESOLUTION_STARTED | sin correo |
| FINAL_DESTINATION_SHIPMENT_STARTED después de incidencia | GERENTE(s) autorizados de la sucursal |
| ADMINISTRATIVE_CORRECTION | actores afectados por el nuevo owner; mínimo Mantenimiento o GERENTE cuando aplique |
| RECEIVED / CLOSED | Mantenimiento + Gerencia Deportiva |

Reglas:

- creación no notifica Mantenimiento;
- rechazo inicial no notifica Mantenimiento;
- prioridad crítica no salta el flujo;
- retry no duplica correos;
- falla de email no revierte una transición de negocio confirmada;
- notificaciones se envían después del commit;
- un mismo usuario/email no recibe duplicado si coincide en más de una regla;
- no enviar email en cada paso logístico intermedio;
- reutilizar infraestructura genérica de email;
- no reutilizar targeting legacy de Ticket si obliga a semántica incorrecta.

## 20. UI — entrada

Opción preferida:

    Tickets
    ├── Crear ticket
    ├── Ver tickets
    └── Requisiciones

La ubicación exacta podrá ajustarse al layout vigente.

## 21. UI — creación

Formulario:

    Nueva requisición

    Sucursal
    [ Villa Verde ]

    Categoría
    [ Equipo de gimnasio ]

    Motivo
    [ Reposición ]

    Prioridad
    [ Alta ]

    Partidas
    ---------------------------------
    Equipo / artículo      Cantidad
    [Caminadora        ]   [2]

    [ + Agregar otro ]

    Justificación
    [                               ]

    Evidencia
    [ Adjuntar archivo ]

    [ Enviar a revisión ]

Debe informar que Gerencia Deportiva revisará antes de enviar a Mantenimiento.

## 22. UI — bandeja

Pantalla: Requisiciones.

Columnas mínimas:

- Folio
- Fecha
- Sucursal
- Solicitante
- Resumen / primera partida
- Prioridad
- Estado
- Acción

Filtros mínimos:

- estado;
- sucursal cuando el usuario tenga alcance;
- fecha;
- prioridad.

## 23. UI — detalle

Mostrar siempre:

- folio;
- sucursal;
- creador;
- fecha;
- categoría;
- motivo;
- prioridad;
- justificación;
- partidas;
- adjuntos;
- estado;
- historial.

Gerencia Deportiva o ADMINISTRADOR en PENDING_REVIEW:

    [ Aprobar ]
    [ Solicitar información ]
    [ Rechazar ]

La botonera de decisión debe ser visible en el primer viewport y sticky al scroll vertical.

Solicitante en NEEDS_INFO:

    [ Editar y reenviar ]

Mantenimiento en IN_QUOTATION:

- expediente completo;
- cotizaciones estructuradas;
- agregar cotización;
- seleccionar una cotización;
- CTA Enviar cotización a aprobación financiera.

La cinta de cotización debe ser visible en el primer viewport y sticky.

APROBADOR_FINANCIERO en QUOTE_PENDING_FINANCE_APPROVAL:

- expediente en modo lectura;
- cotización seleccionada destacada;
- proveedor;
- monto;
- moneda;
- archivo;
- observaciones;
- aprobación previa de Gerencia Deportiva;
- botones:

      [ Rechazar cotización ]
      [ Aprobar cotización ]

La botonera financiera debe ser visible en el primer viewport y sticky.

Mantenimiento después de aprobación financiera:

Estados UI:

- En solicitud de pago;
- En proceso de envío;
- En proceso de importación;
- Envío a destino final.

Se presentarán mediante un control de avance/dropdown de seguimiento.

Reglas UX:

- mostrar claramente estado actual;
- puede mostrarse la secuencia completa;
- solo el siguiente estado permitido puede seleccionarse;
- no habilitar saltos;
- no habilitar retrocesos ordinarios;
- el control permanece sticky mientras Mantenimiento sea owner;
- IMPORT_IN_PROGRESS es opcional;
- estando en SHIPPING_IN_PROGRESS, el control ofrece como siguiente paso En proceso de importación o Envío a destino final;
- seleccionar Envío a destino final directamente registra que la importación no aplica;
- después de entrar a IMPORT_IN_PROGRESS, el único siguiente estado logístico ordinario es Envío a destino final.

Al llegar a Envío a destino final:

- la acción de Mantenimiento desaparece;
- aparece para GERENTE autorizado de la sucursal una cinta sticky con:

      [ Reportar incidencia ]
      [ Confirmar recibido ]

Confirmar recibido es la acción principal positiva.

Reportar incidencia abre captura de:

- tipo de incidencia;
- descripción;
- evidencia obligatoria.

En RECEIPT_ISSUE:

- la cinta sticky vuelve a Mantenimiento;
- muestra resumen visible de la incidencia reportada;
- acción principal:

      [ Reanudar logística ]

- exige comentario de resolución/acción tomada;
- al reanudar pasa a SHIPPING_IN_PROGRESS.

El historial debe conservar cada ciclo de incidencia/resolución.

ADMINISTRADOR:

- ve una acción secundaria Corrección administrativa;
- la acción no debe competir visualmente con el CTA normal del owner;
- abre un diálogo separado;
- muestra estado actual;
- permite seleccionar únicamente target_status contractualmente válidos para corrección;
- exige motivo y comentario;
- muestra advertencia explícita de que la corrección quedará auditada;
- para reabrir CLOSED debe mostrar una confirmación reforzada.

El nombre de sucursal mostrado en expediente se resuelve contra catálogo de sucursales y no degrada a Sucursal #<id> solo porque el viewer no tenga scope de creación sobre esa sucursal.

No mostrar acciones genéricas de Tickets V1 como En progreso, Finalizar, Cierre gerente o Fecha solución.

## 24. Mapping 1:1 hacia Tickets V2

### 24.1 Cabecera

purchase_requisitions.id -> source reference V2

public_id -> Ticket V2 public_id

category -> tipo/subtipo V2

Semántica inicial:

    type = PURCHASE_REQUISITION
    subtype = GYM_EQUIPMENT

### 24.2 Estado

Los estados V1 del bridge se traducen a:

    Ticket V2 global status
    +
    workflow stage

No es obligatorio conservar los mismos strings, pero la semántica debe ser inequívoca.

### 24.3 Partidas

purchase_requisition_items -> line items/detalle de workflow V2.

### 24.4 Eventos

purchase_requisition_events -> ticket_v2_events o adapter equivalente.

### 24.5 Adjuntos

purchase_requisition_attachments -> expediente V2.

Preferir link/reuso de storage sobre copiar blobs.

### 24.6 Participantes

Semántica:

    created_by -> REQUESTER
    GERENCIA DEPORTIVA -> REVIEWER
    MANTENIMIENTO -> OWNER después de APPROVED

El bridge no necesita implementar el futuro modelo completo de participantes si puede derivarlo sin ambigüedad.

## 25. API propuesta

Namespace:

    /api/purchase-requisitions

Vigentes:

    GET  /access
    POST /
    GET  /
    GET  /<id>
    PUT  /<id>/requester-edit
    POST /<id>/resubmit
    POST /<id>/request-info
    POST /<id>/approve
    POST /<id>/reject
    POST /<id>/attachments
    GET  /<id>/attachments/<attachment_id>/file

Extensión E1, nombres semánticos propuestos:

    POST /<id>/quotes
    POST /<id>/quotes/<quote_id>/select
    POST /<id>/submit-quote-for-finance
    POST /<id>/finance/approve-quote
    POST /<id>/finance/reject-quote
    POST /<id>/advance-logistics
    POST /<id>/confirm-receipt
    POST /<id>/report-receipt-issue
    POST /<id>/resume-logistics
    POST /<id>/administrative-correction

confirm-receipt recibe:

- comment, opcional;
- evidence_attachment_ids, opcional; todos deben ser RECEIPT_EVIDENCE de la misma requisición.

report-receipt-issue recibe:

- issue_type;
- comment obligatorio;
- evidence_attachment_ids obligatorio y no vacío; todos deben ser RECEIPT_ISSUE_EVIDENCE de la misma requisición.

resume-logistics recibe:

- comment obligatorio.

administrative-correction recibe:

- target_status;
- reason;
- comment.

Solo ADMINISTRADOR.

advance-logistics recibirá un target_status de un catálogo cerrado y backend validará que sea exactamente una transición permitida desde el estado actual.

administrative-correction tampoco es un PATCH genérico: backend valida target_status, estado actual y prerrequisitos históricos antes de persistir.

No es un PATCH genérico de status.

GET /access deberá poder exponer, cuando E1 se implemente, capacidades equivalentes a:

- can_manage_quotation;
- can_approve_requisition_quote;
- can_manage_requisition_logistics;
- can_confirm_receipt;
- can_admin_correct_requisition.

Los nombres finales podrán ajustarse durante investigación previa a implementación, conservando la semántica.

## 26. Backend

Separar responsabilidades.

Estructura orientativa:

    models/
      purchase_requisition*.py

    routes/
      purchase_requisition_routes.py

    services/
      purchase_requisition_service.py
      purchase_requisition_workflow_service.py
      purchase_requisition_attachment_service.py
      purchase_requisition_notification_service.py

    utils/
      purchase_requisition_permissions.py

Los nombres pueden adaptarse a convenciones reales del repo.

Sí es obligatorio evitar una ruta monolítica con toda la lógica incrustada.

## 27. Transacciones

Creación y revisión inicial conservan las garantías vigentes.

E1 requiere atomicidad adicional.

Enviar cotización a Finanzas:

- validar IN_QUOTATION;
- validar actor de Mantenimiento;
- validar cotización seleccionada;
- marcar decisión financiera pendiente;
- mover a QUOTE_PENDING_FINANCE_APPROVAL;
- registrar QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL.

Aprobar cotización:

- validar APROBADOR_FINANCIERO;
- validar QUOTE_PENDING_FINANCE_APPROVAL;
- validar que la cotización pendiente siga siendo la misma;
- registrar decisión;
- mover a PAYMENT_REQUESTED;
- registrar QUOTE_APPROVED_BY_FINANCE y PAYMENT_REQUESTED.

Rechazar cotización:

- validar APROBADOR_FINANCIERO;
- validar QUOTE_PENDING_FINANCE_APPROVAL;
- registrar motivo;
- marcar cotización como rechazada;
- mover a IN_QUOTATION;
- registrar QUOTE_REJECTED_BY_FINANCE.

Avance logístico:

- validar actor de Mantenimiento;
- validar estado actual;
- validar next state permitido;
- persistir status;
- registrar evento correspondiente.

Confirmar recibido:

- validar GERENTE y scope de sucursal;
- validar FINAL_DESTINATION_SHIPMENT;
- registrar RECEIVED;
- mover a CLOSED.

Corrección administrativa:

- validar rol ADMINISTRADOR;
- bloquear requisición para concurrencia;
- validar target_status contra catálogo cerrado;
- validar prerrequisitos históricos;
- exigir reason y comment;
- registrar ADMINISTRATIVE_CORRECTION;
- persistir nuevo status;
- nunca borrar/modificar eventos previos.

Reportar incidencia:

- validar GERENTE y scope de sucursal;
- validar FINAL_DESTINATION_SHIPMENT;
- validar tipo/comentario/evidencia;
- registrar RECEIPT_ISSUE_REPORTED;
- mover a RECEIPT_ISSUE.

Reanudar logística:

- validar Mantenimiento;
- validar RECEIPT_ISSUE;
- validar comentario de resolución;
- registrar RECEIPT_ISSUE_RESOLUTION_STARTED;
- mover a SHIPPING_IN_PROGRESS.

Notificaciones siempre después del commit o mediante mecanismo durable compatible.

## 28. Concurrencia

Debe impedirse:

- doble aprobación inicial;
- approve/reject inicial simultáneo;
- doble resubmit;
- edición tardía después de aprobación;
- selección concurrente incompatible de cotizaciones;
- cambiar cotización mientras existe aprobación financiera pendiente;
- doble submit de cotización a Finanzas;
- approve/reject financiero simultáneo;
- decisión financiera sobre una cotización distinta a la pendiente;
- doble avance logístico;
- saltos de estado por requests simultáneos;
- doble confirmación de recibido;
- confirmar recibido simultáneamente con reportar incidencia;
- doble reporte de incidencia;
- doble reanudación de logística desde RECEIPT_ISSUE;
- corrección administrativa simultánea con transición ordinaria;
- dos correcciones administrativas concurrentes;
- reapertura de CLOSED simultánea con otra acción.

Estrategias aceptables:

- row lock;
- compare-and-set por estado;
- versionado;
- equivalente seguro en PostgreSQL/SQLAlchemy.

Si llegan dos acciones incompatibles, exactamente una gana y la otra recibe conflicto de negocio.

## 29. Edición

No implementar DRAFT en V1.

La creación entra directamente a PENDING_REVIEW.

En NEEDS_INFO, solicitante autorizado puede editar:

- motivo;
- prioridad;
- justificación;
- partidas;
- evidencia.

No puede editar:

- folio;
- creador;
- historial;
- aprobación.

Después de aprobación, datos base bloqueados para solicitante.

## 30. Borrado

No implementar borrado físico desde UI.

Una requisición enviada entra al histórico.

REJECTED conserva evidencia y auditoría.

Si se requiere CANCELLED en el futuro, deberá ser una transición explícita.

## 31. Fechas y timezone

Persistencia en UTC con timestamps timezone-aware cuando corresponda.

Presentación humana en America/Tijuana.

No persistir strings locales ambiguos como fuente canónica.

## 32. Seguridad de adjuntos

Requisitos:

- archivo privado;
- no URL pública permanente;
- validar tipo real usando infraestructura disponible;
- nombre físico no controlado por usuario;
- límites de tamaño;
- autorización de descarga;
- hash;
- protección contra traversal.

No ampliar alcance a servicios externos de escaneo si Suite no los usa actualmente, salvo decisión posterior.

## 33. Integración Mantenimiento

Al aprobar Gerencia Deportiva:

- la requisición entra a IN_QUOTATION;
- aparece en bandeja de Mantenimiento;
- Mantenimiento recibe notificación;
- puede consultar expediente;
- puede registrar y seleccionar cotizaciones;
- puede enviar la cotización seleccionada a aprobación financiera;
- no aparece en Maintenance Planner correctivo;
- no incrementa KPIs de fallas;
- no entra a reporte ejecutivo de fallas;
- no usa fecha_solucion legacy;
- no usa doble check de cierre de Tickets V1.

Mientras QUOTE_PENDING_FINANCE_APPROVAL:

- Mantenimiento conserva lectura;
- no puede sustituir la cotización pendiente;
- espera decisión financiera.

Si Finanzas rechaza:

- vuelve a IN_QUOTATION;
- Mantenimiento recibe motivo;
- puede preparar/seleccionar otra cotización.

Si Finanzas aprueba:

- estado = PAYMENT_REQUESTED;
- ownership vuelve a Mantenimiento;
- avanza secuencialmente pago/logística;
- al marcar FINAL_DESTINATION_SHIPMENT termina su responsabilidad activa en E1;
- conserva lectura hasta CLOSED.

## 34. Integración Gerencia Deportiva

Gerencia Deportiva:

- revisa la necesidad en PENDING_REVIEW;
- aprueba/rechaza/pide información;
- no selecciona cotización;
- no sustituye al aprobador financiero;
- conserva lectura de la trazabilidad posterior;
- recibe notificación al cierre.

La aprobación de necesidad y la aprobación financiera de cotización son controles separados.

## 35. Integración Finanzas y sucursal

### 35.1 APROBADOR_FINANCIERO

Responsable operativo actual: Fabián.

Funciones:

- recibe la cotización seleccionada;
- aprueba o rechaza;
- rechazo exige motivo;
- no modifica requisición/cotización;
- no gestiona logística.

La identidad se resuelve mediante capacidad configurable, nunca username hardcodeado.

### 35.2 GERENTE de sucursal

Cuando Mantenimiento marca FINAL_DESTINATION_SHIPMENT:

- GERENTE(s) autorizados de la sucursal reciben notificación;
- consultan expediente y trazabilidad;
- pueden confirmar recibido conforme;
- o reportar una entrega no conforme.

Si confirman:

- se crea RECEIVED;
- la requisición cierra.

Si reportan incidencia:

- se crea RECEIPT_ISSUE_REPORTED;
- status = RECEIPT_ISSUE;
- ownership vuelve a Mantenimiento;
- Mantenimiento reanuda logística después de registrar la acción tomada.

E1 modela daño, faltantes/entrega incompleta, artículo incorrecto y OTHER como incidencia de recepción.

No existe cierre parcial: una entrega incompleta mantiene abierta toda la requisición.

## 36. Observabilidad

Logs estructurados para:

- creación;
- aprobación;
- rechazo;
- request-info;
- resubmit;
- adjuntos;
- cotización agregada/seleccionada, E1;
- compra registrada, E1;
- recepción/cierre, E1;
- corrección administrativa, E1;
- errores de notificación.

Debe poder rastrearse por:

- requisition_id;
- public_id;
- actor;
- event_type.

No registrar contenido completo de archivos ni información innecesaria.

## 37. Migraciones

Usar Alembic.

Reglas:

- un solo head;
- validar flask db current;
- validar flask db heads;
- upgrade;
- downgrade;
- no editar migraciones históricas;
- no asumir IDs mágicos de roles/departamentos.

## 38. Compatibilidad con Tickets V1

La regresión deberá verificar que no se altera:

- creación Tickets V1;
- listado;
- filtros;
- cierre;
- Maintenance Planner;
- reporte Mantenimiento;
- adjuntos Ticket V1;
- validation-summary;
- permisos V1.

El nuevo módulo puede agregar navegación sin cambiar semántica de tickets existentes.

## 39. Tests mínimos

Se conservan todos los tests vigentes de M1/M2.

E1 agrega como mínimo:

1. Mantenimiento puede crear múltiples cotizaciones solo en IN_QUOTATION;
2. cotización requiere proveedor, monto > 0, moneda, fecha y archivo;
3. solo una cotización activa seleccionada;
4. enviar a Finanzas exige cotización seleccionada;
5. submit deja QUOTE_PENDING_FINANCE_APPROVAL;
6. submit notifica al APROBADOR_FINANCIERO;
7. usuario sin capacidad financiera no aprueba/rechaza cotización;
8. fila activa en purchase_requisition_finance_approvers otorga can_approve_requisition_quote;
9. fila inactiva no otorga capacidad;
10. ADMINISTRADOR sin asignación financiera no aprueba cotización por ser admin;
11. GERENCIA DEPORTIVA sin asignación financiera no aprueba cotización por ser reviewer inicial;
12. solo ADMINISTRADOR puede administrar finance approvers;
13. alta de aprobador usa user_id existente;
14. alta duplicada no crea segunda fila;
15. desactivar conserva fila/historial y revoca capacidad;
16. reactivar recupera capacidad sobre la misma asignación;
17. sin aprobadores activos no se puede enviar cotización a Finanzas;
18. aprobador financiero puede leer expediente pendiente;
19. aprobar cotización deja PAYMENT_REQUESTED;
20. aprobar cotización notifica Mantenimiento;
21. rechazar cotización exige motivo;
22. rechazar cotización vuelve a IN_QUOTATION;
23. cotización rechazada permanece histórica;
24. mientras está pendiente no puede sustituirse cotización;
25. Mantenimiento no puede saltar PAYMENT_REQUESTED directamente a FINAL_DESTINATION_SHIPMENT;
26. PAYMENT_REQUESTED -> SHIPPING_IN_PROGRESS válido;
27. SHIPPING_IN_PROGRESS -> IMPORT_IN_PROGRESS válido cuando aplica;
28. IMPORT_IN_PROGRESS -> FINAL_DESTINATION_SHIPMENT válido;
29. SHIPPING_IN_PROGRESS -> FINAL_DESTINATION_SHIPMENT es válido cuando Mantenimiento indica que la importación no aplica y queda auditado;
30. la ruta sin importación registra IMPORT_NOT_APPLICABLE o metadata equivalente import_required=false;
31. cada avance crea evento auditable;
32. avances logísticos intermedios no generan correo;
33. FINAL_DESTINATION_SHIPMENT notifica GERENTE(s) de sucursal;
34. Mantenimiento no puede confirmar recibido;
35. GERENTE de otra sucursal no puede confirmar;
36. GERENTE de sucursal origen puede confirmar;
37. confirmar recibido deja CLOSED y crea RECEIVED;
38. GERENTE de sucursal origen puede reportar incidencia;
39. reportar incidencia exige tipo, comentario y evidencia;
40. reportar incidencia deja RECEIPT_ISSUE;
41. RECEIPT_ISSUE notifica Mantenimiento;
42. Mantenimiento puede reanudar logística desde RECEIPT_ISSUE;
43. reanudar logística deja SHIPPING_IN_PROGRESS;
44. Mantenimiento no puede cerrar RECEIPT_ISSUE;
45. confirmar y reportar incidencia simultáneamente produce un único ganador;
46. doble confirmación produce conflicto;
47. no se puede retroceder estado desde UI/API ordinaria;
48. no se puede usar endpoint de avance como PATCH arbitrario;
49. E1 no contamina Planner/reportes/Tickets V1;
50. ADMINISTRADOR puede ejecutar corrección administrativa;
51. usuario no ADMINISTRADOR recibe 403;
52. corrección exige motivo y comentario;
53. target_status fuera de catálogo se rechaza;
54. NEEDS_INFO -> PENDING_REVIEW administrativo es válido;
55. REJECTED -> PENDING_REVIEW administrativo es válido;
56. IN_QUOTATION -> PENDING_REVIEW conserva APPROVED histórico y limpia proyección vigente;
57. QUOTE_PENDING_FINANCE_APPROVAL -> IN_QUOTATION cancela el pending financiero;
58. PAYMENT_REQUESTED -> QUOTE_PENDING_FINANCE_APPROVAL reabre decisión financiera sin borrar aprobación histórica;
59. SHIPPING_IN_PROGRESS -> PAYMENT_REQUESTED es válido;
60. IMPORT_IN_PROGRESS -> SHIPPING_IN_PROGRESS es válido;
61. FINAL_DESTINATION_SHIPMENT -> IMPORT_IN_PROGRESS exige import_required=true;
62. FINAL_DESTINATION_SHIPMENT -> SHIPPING_IN_PROGRESS exige import_required=false;
63. FINAL_DESTINATION_SHIPMENT sin metadata import_required rechaza corrección logística;
64. RECEIPT_ISSUE -> FINAL_DESTINATION_SHIPMENT es válido y conserva incidencia histórica;
65. reabrir CLOSED conserva evento RECEIVED original;
66. CLOSED -> FINAL_DESTINATION_SHIPMENT es válido;
67. CLOSED -> RECEIPT_ISSUE es válido;
68. corrección no puede crear PAYMENT_REQUESTED sin decisión financiera normal;
69. corrección no puede cerrar directamente;
70. corrección concurrente con transición ordinaria produce un único ganador;
71. historial conserva error original + corrección.

Frontend:

- cinta sticky de revisión inicial;
- cinta sticky de cotización para Mantenimiento;
- cinta sticky de aprobación financiera;
- dropdown/stepper logístico secuencial para Mantenimiento;
- cinta sticky de Confirmar recibido para GERENTE;
- diálogo de Corrección administrativa solo para ADMINISTRADOR;
- confirmación reforzada para reapertura de CLOSED;
- Configuración -> Aprobación financiera solo para ADMINISTRADOR;
- búsqueda de usuario por catálogo y alta por user_id;
- activar/desactivar aprobadores sin borrado físico;
- nombre real de sucursal independiente del scope de creación.

## 40. Criterios de aceptación

La primera entrega queda funcional cuando:

1. una sucursal crea una requisición real;
2. Gerencia Deportiva la ve;
3. Mantenimiento no la recibe antes de aprobación;
4. Gerencia Deportiva puede aprobar/rechazar/pedir información;
5. solicitante puede responder NEEDS_INFO;
6. aprobación llega a Mantenimiento;
7. existe historial auditable;
8. documentos/evidencias son privados;
9. no contamina Planner ni reportes de fallas;
10. Tickets V1 sigue funcionando;
11. mapping a V2 queda documentado.

### 40.1 Aceptación E1 post-aprobación

E1 queda funcional cuando:

1. Mantenimiento recibe una requisición aprobada en IN_QUOTATION;
2. registra múltiples cotizaciones estructuradas;
3. selecciona una cotización;
4. la envía a APROBADOR_FINANCIERO;
5. ADMINISTRADOR puede configurar aprobadores financieros desde Requisiciones sin SQL manual;
6. el responsable financiero actual puede aprobar/rechazar sin estar hardcodeado;
7. sin aprobador financiero activo no puede enviarse una cotización a aprobación;
8. rechazo vuelve a Mantenimiento/IN_QUOTATION con motivo;
9. aprobación financiera deja PAYMENT_REQUESTED y devuelve ownership a Mantenimiento;
10. Mantenimiento avanza paso a paso sin saltos;
11. importación funciona como etapa opcional y ambas rutas desde SHIPPING_IN_PROGRESS quedan auditadas;
12. al llegar a FINAL_DESTINATION_SHIPMENT la responsabilidad pasa al GERENTE de sucursal;
13. GERENTE puede confirmar conforme o reportar incidencia;
14. confirmar recibido crea RECEIVED y CLOSED;
15. reportar incidencia crea RECEIPT_ISSUE y devuelve ownership a Mantenimiento;
16. Mantenimiento puede reanudar logística y volver a entregar;
17. el ciclo incidencia -> resolución -> nueva entrega puede repetirse sin perder historial;
18. notificaciones respetan cambios de owner sin spam intermedio;
19. toda decisión/avance es auditable;
20. ADMINISTRADOR puede corregir errores operativos mediante ADMINISTRATIVE_CORRECTION sin borrar historial ni fabricar aprobaciones;
21. CLOSED puede reabrirse administrativamente conservando RECEIVED previo;
22. no contamina Tickets V1, Planner ni reportes correctivos.

## 41. Milestones

### M0 — Boundary e investigación puntual

Antes de implementar:

- verificar HEAD;
- verificar Alembic head;
- localizar navegación vigente;
- verificar roles GERENCIA DEPORTIVA, MANTENIMIENTO, ADMIN, GERENTE, LECTOR_GLOBAL;
- revisar storage reusable;
- revisar infraestructura de email;
- confirmar que no existe módulo equivalente;
- confirmar convenciones de modelos/routes/services.

Entregable:

reporte corto de investigación y lista exacta de archivos a crear/modificar.

Sin código funcional todavía.

### M1 — Persistencia y dominio

- modelos;
- migración;
- estados;
- partidas;
- eventos;
- permisos base;
- serialización.

Criterios:

- upgrade/downgrade;
- tests de dominio;
- un solo Alembic head.

### M2 — Creación y consulta

- create;
- list;
- detail;
- scopes;
- frontend creación;
- bandeja;
- detalle.

Criterio clave:

Gerencia Deportiva la ve y Mantenimiento todavía no la recibe.

### M3 — Revisión Gerencia Deportiva

- request-info;
- resubmit;
- approve;
- reject;
- auditoría;
- concurrencia;
- UI.

### M4 — Handoff Mantenimiento + notificaciones

- targeting;
- email;
- visibilidad post-aprobación;
- evento routing;
- bandeja Mantenimiento.

Criterios:

- aprobación llega una vez;
- creación no llega;
- rechazo no llega.

### M5 — Adjuntos

- storage reusable/generalizado;
- múltiples adjuntos;
- imágenes/PDF;
- permisos;
- UI.

Si evidencia es imprescindible desde el primer día, M5 podrá adelantarse dentro de M2 sin alterar el modelo contractual.

### M6 — Hardening y regresión

- Tickets V1;
- Planner;
- reportes;
- permisos;
- smoke con perfiles reales;
- documentación.

No merge/deploy hasta aceptación.

### M7 / E1 — Cotización, aprobación financiera, logística y recepción

Estado: E1 CONGELADA / LISTA PARA IMPLEMENTACIÓN M7.

Incluye:

- cotizaciones estructuradas;
- selección de cotización;
- envío a aprobación financiera;
- capacidad configurable APROBADOR_FINANCIERO;
- approve/reject financiero;
- estados PAYMENT_REQUESTED, SHIPPING_IN_PROGRESS, IMPORT_IN_PROGRESS y FINAL_DESTINATION_SHIPMENT;
- dropdown/stepper secuencial de Mantenimiento;
- handoff a GERENTE de sucursal;
- corrección administrativa auditada para ADMINISTRADOR;
- reapertura controlada de CLOSED;
- evento RECEIVED;
- cierre por recepción;
- nuevas notificaciones;
- migración Alembic;
- regresión completa.

Antes de código:

- validar que el nuevo modelo/tabla no colisione con otro head de Alembic;
- confirmar targeting técnico de GERENTE(s) de sucursal contra los helpers vigentes;
- implementar el catálogo cerrado de ADMINISTRATIVE_CORRECTION definido en 13.11;
- implementar la configuración Aprobación financiera dentro de Requisiciones conforme a 42.2.

## 42. Extensión E1 — modelo de cotizaciones y aprobación financiera

### 42.1 Cotizaciones

Entidad hija propuesta:

    purchase_requisition_quotes

Campos base:

- id;
- requisition_id;
- supplier_name;
- amount;
- currency;
- quote_date;
- attachment_id;
- notes, nullable;
- created_by_user_id;
- created_at.

Selección:

- is_selected;
- selected_by_user_id, nullable;
- selected_at, nullable.

Aprobación financiera:

- finance_status: DRAFT | PENDING | APPROVED | REJECTED;
- finance_submitted_by_user_id, nullable;
- finance_submitted_at, nullable;
- finance_decided_by_user_id, nullable;
- finance_decided_at, nullable;
- finance_comment, nullable.

Reglas:

- múltiples cotizaciones por requisición;
- una sola selección activa;
- no usar quote_1, quote_2, quote_3;
- proveedor es snapshot/texto E1; no existe catálogo formal;
- solo IN_QUOTATION permite seleccionar/enviar;
- submit financiero exige una selección;
- al submit finance_status = PENDING;
- mientras PENDING no se cambia selección;
- approve deja finance_status = APPROVED;
- reject deja finance_status = REJECTED y libera la requisición para nueva selección;
- cada decisión además genera evento append-only;
- una cotización aprobada no puede sustituirse durante el flujo logístico ordinario.

### 42.2 Aprobador financiero

Capacidad:

    can_approve_requisition_quote

Responsable operativo inicial:

    Fabián

Patrón elegido para E1:

    purchase_requisition_finance_approvers

Motivo de la decisión:

- sigue el patrón runtime real de operadores por user_id ya usado en Suite Ultra;
- permite cambiar responsable sin tocar código;
- evita hardcodear username/email;
- mantiene el dominio de Requisiciones aislado;
- permission_grants no será fuente de enforcement de E1 mientras el catálogo global continúe en modo observabilidad/compatibilidad y no sustituya los guards reales.

Campos mínimos:

- id;
- user_id, unique, FK users.id;
- is_active;
- added_by_user_id, FK users.id;
- notes, nullable;
- created_at;
- updated_at.

Reglas:

- una fila activa otorga can_approve_requisition_quote;
- una fila inexistente o inactiva no otorga la capacidad;
- el lookup se hace por user_id autenticado;
- rol ADMINISTRADOR no implica can_approve_requisition_quote;
- rol GERENCIA DEPORTIVA no implica can_approve_requisition_quote;
- el aprobador puede tener cualquier rol compatible con autenticación mientras tenga asignación activa;
- E1 permitirá una o más filas activas técnicamente, aunque la política inicial tendrá a Fabián como responsable principal;
- si existen múltiples aprobadores activos, todos reciben la notificación y la primera decisión válida gana mediante control de concurrencia;
- nunca usar username, email o nombre como llave de autorización.

Administración:

- solo ADMINISTRADOR puede listar, activar o desactivar aprobadores financieros;
- la administración debe ocurrir mediante API/UI de Suite Ultra;
- no editar filas manualmente en servidor;
- toda alta debe guardar added_by_user_id;
- toda modificación conserva updated_at y notes para contexto administrativo.

UX administrativa E1:

La configuración vive dentro del dominio Requisiciones, no dentro de Permisos globales.

Ruta/UI propuesta:

    Requisiciones
      -> Configuración
         -> Aprobación financiera

Acceso:

- visible solo para ADMINISTRADOR;
- backend valida ADMINISTRADOR aunque frontend oculte la entrada.

Contenido mínimo:

1. encabezado:
   - título Aprobación financiera;
   - texto breve indicando que estos usuarios pueden aprobar/rechazar cotizaciones;
   - contador de aprobadores activos;

2. bloque Agregar aprobador:
   - buscador por nombre, username, correo o ID;
   - resultados de usuarios existentes;
   - selección por user_id;
   - campo notes opcional;
   - CTA Agregar aprobador;

3. tabla/lista de asignaciones:
   - usuario;
   - email;
   - rol actual;
   - estado Activo/Inactivo;
   - fecha de alta;
   - agregado por;
   - notes;
   - acción Activar/Desactivar;

4. feedback:
   - confirmación visible al activar/desactivar;
   - error claro si el usuario ya existe en la allowlist;
   - advertencia si se intenta desactivar al último aprobador activo.

Reglas UX:

- no permitir capturar username/email manualmente como llave;
- el usuario se selecciona desde resultados del catálogo y se envía user_id;
- desactivar no borra la fila ni su historial;
- reactivar reutiliza la misma fila;
- no mostrar permisos globales ni permission_grants dentro de esta pantalla;
- no mezclar esta configuración con Gerencia Deportiva, Mantenimiento o recepción.

Regla operativa para cero aprobadores activos:

- backend permite que la configuración quede temporalmente sin aprobadores;
- mientras no exista ninguno activo, no se puede ejecutar Enviar cotización a aprobación financiera;
- UI de Mantenimiento muestra mensaje: No hay aprobador financiero activo configurado;
- no mover la requisición a QUOTE_PENDING_FINANCE_APPROVAL si no existe destinatario activo.

API administrativa propuesta:

    GET  /api/purchase-requisitions/config/finance-approvers
    POST /api/purchase-requisitions/config/finance-approvers
    PUT  /api/purchase-requisitions/config/finance-approvers/<user_id>

El POST recibe user_id, no username/email.

El PUT permitirá al menos activar/desactivar y editar notes.

El endpoint funcional:

    GET /api/purchase-requisitions/access

expondrá:

    can_approve_requisition_quote

calculado desde esta allowlist activa.

Notificaciones:

QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL resolverá destinatarios consultando todos los aprobadores financieros activos con email válido, con dedupe por email.

Despliegue inicial:

1. migración crea purchase_requisition_finance_approvers;
2. deploy normal;
3. ADMINISTRADOR entra a configuración de Requisiciones;
4. selecciona al usuario de Fabián por user_id desde catálogo de usuarios;
5. activa la asignación;
6. desde ese momento recibe y puede decidir cotizaciones pendientes.

No seedear a Fabián por username, nombre, email ni ID mágico en Alembic.

### 42.3 Seguimiento logístico

No se crea una tabla de compra completa en E1 solo para representar el flujo propuesto.

La fuente operativa inmediata será:

- purchase_requisitions.status;
- eventos append-only por cada avance;
- cotización aprobada como referencia financiera.

Si durante investigación se detectan datos logísticos adicionales indispensables, deberán agregarse explícitamente al contrato antes de crear columnas.

### 42.4 Recepción e incidencias

E1 no requiere una entidad RECEIVED independiente si el evento conserva:

- actor_user_id;
- created_at;
- observaciones;
- evidencia opcional mediante attachment_id/metadata.

La confirmación completa crea RECEIVED y mueve:

    FINAL_DESTINATION_SHIPMENT -> CLOSED

Una entrega no conforme crea RECEIPT_ISSUE_REPORTED y mueve:

    FINAL_DESTINATION_SHIPMENT -> RECEIPT_ISSUE

Metadata mínima de incidencia:

- issue_type;
- comment;
- evidence_attachment_ids.

Desde RECEIPT_ISSUE, Mantenimiento registra la acción tomada mediante comentario y crea RECEIPT_ISSUE_RESOLUTION_STARTED:

    RECEIPT_ISSUE -> SHIPPING_IN_PROGRESS

No se acepta recepción parcial como cierre. Una entrega incompleta se trata como incidencia y mantiene abierta toda la requisición.

## 43. Extensión futura a Compras general

Cuando se extienda fuera de equipo de gimnasio podrán existir:

- nuevas categorías;
- reviewer distinto;
- owner distinto;
- Compras como owner;
- autorizaciones adicionales.

V1 urgente tendrá una sola política activa:

    GYM_EQUIPMENT
    -> GERENCIA DEPORTIVA
    -> MANTENIMIENTO

La lógica deberá quedar encapsulada para sustituir esta política después sin reescribir todo el módulo.

No construir todavía un motor genérico de reglas.

## 44. Invariantes

R1. Una requisición no es un Ticket V1.

R2. Toda requisición nace PENDING_REVIEW.

R3. Gerencia Deportiva y ADMINISTRADOR son reviewers iniciales autorizados.

R4. Mantenimiento no recibe requisición antes de aprobación inicial.

R5. Aprobar necesidad mueve directamente a IN_QUOTATION; APPROVED es evento.

R6. REJECTED inicial es terminal.

R7. NEEDS_INFO vuelve a PENDING_REVIEW mediante resubmit.

R8. Toda transición se valida en backend.

R9. Historial de eventos es append-only funcionalmente.

R10. No borrar requisiciones enviadas.

R11. No contaminar Planner/KPIs/reportes correctivos.

R12. Adjuntos no heredan reglas legacy por implicación.

R13. No hardcodear usernames, emails ni nombres personales.

R14. No notificar Mantenimiento en creación, rechazo inicial o request-info.

R15. El bridge conserva mapping explícito a Tickets V2.

R16. Gerencia Deportiva autoriza la necesidad; Finanzas autoriza la cotización. Son decisiones distintas.

R17. APROBADOR_FINANCIERO se resuelve exclusivamente desde purchase_requisition_finance_approvers activo por user_id; el responsable operativo actual no se codifica en fuente.

R18. Enviar cotización a Finanzas mueve IN_QUOTATION -> QUOTE_PENDING_FINANCE_APPROVAL.

R19. Finanzas rechaza -> IN_QUOTATION; aprueba -> PAYMENT_REQUESTED.

R20. Mientras exista decisión financiera pendiente, Mantenimiento no sustituye la cotización.

R21. Mantenimiento avanza estados logísticos mediante transiciones cerradas; el dropdown no permite saltos arbitrarios.

R21.1. IMPORT_IN_PROGRESS es opcional. Desde SHIPPING_IN_PROGRESS son válidas exactamente dos rutas: IMPORT_IN_PROGRESS si requiere importación, o FINAL_DESTINATION_SHIPMENT si no aplica importación.

R22. Mantenimiento termina ownership activo en FINAL_DESTINATION_SHIPMENT.

R23. Solo GERENTE autorizado de la sucursal decide la recepción en el flujo normal E1.

R24. RECEIVED es evento y produce FINAL_DESTINATION_SHIPMENT -> CLOSED.

R25. Entrega no conforme produce FINAL_DESTINATION_SHIPMENT -> RECEIPT_ISSUE y nunca cierra.

R26. RECEIPT_ISSUE devuelve ownership a Mantenimiento.

R27. Reanudar logística produce RECEIPT_ISSUE -> SHIPPING_IN_PROGRESS.

R28. E1 no permite cierre parcial; entrega incompleta mantiene toda la requisición abierta.

R29. No enviar correos por cada avance logístico intermedio.

R30. Cotizaciones son entidad hija estructurada; nunca quote_1/quote_2/quote_3.

R31. ADMINISTRADOR puede corregir estados mediante ADMINISTRATIVE_CORRECTION; ningún otro rol obtiene esa capacidad por defecto.

R32. Corrección administrativa nunca borra eventos ni fabrica aprobaciones/recepciones inexistentes.

R33. CLOSED puede reabrirse por ADMINISTRADOR, conservando RECEIVED original y registrando el motivo de reapertura.

R34. ADMINISTRATIVE_CORRECTION está sujeto a prerrequisitos históricos y catálogo cerrado de targets; no es PATCH libre de status.

R35. El catálogo de correcciones de 13.11 es exhaustivo en E1; cualquier par from_status/to_status no listado se rechaza.

R36. Una corrección puede cambiar la proyección vigente, pero nunca elimina el evento histórico cuya consecuencia está corrigiendo.

## 45. Decisiones pospuestas

No quedan decisiones funcionales abiertas que bloqueen M7/E1.

Siguen fuera de E1:

- catálogo corporativo de proveedores;
- presupuesto y disponibilidad presupuestal;
- orden de compra formal/ERP;
- ejecución real del pago;
- forma de pago;
- factura fiscal;
- contabilidad;
- inventario automático;
- devoluciones/cambios;
- múltiples compras parciales para una requisición;
- SLA;
- recordatorios;
- chat;
- integración nativa con Tickets V2 antes de M0 V2.

No inventar estos procesos durante implementación. Cualquier necesidad requiere enmienda contractual previa.

## 46. Definición de éxito arquitectónico

El bridge habrá cumplido su propósito si, cuando Tickets V2 esté listo, puede migrarse esencialmente así:

    purchase_requisition
        -> TicketV2
           source = PURCHASE_REQUISITIONS_V1
           source_id = requisition.id
           public_id = requisition.public_id
           type = PURCHASE_REQUISITION
           subtype = requisition.category

        -> items
        -> events
        -> attachments
        -> participants derivados

sin depender de:

- departamento_id legacy;
- por_validar;
- correos para reconstruir aprobación;
- texto libre para descubrir responsable;
- separar requisiciones mezcladas con fallas de Mantenimiento.

Ese criterio protege la inversión del módulo urgente.
