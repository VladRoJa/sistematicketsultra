# Contrato — Requisiciones V1 Bridge hacia Tickets V2

Estado: CONTRATO FUNCIONAL-TÉCNICO PARA IMPLEMENTACIÓN POR MILESTONES
Fecha: 2026-10-02
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
- No implementar Compras completo en este contrato.
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

El objetivo de esta primera versión termina cuando Mantenimiento recibe una requisición aprobada y puede comenzar su proceso de cotización.

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

- proveedores;
- catálogo formal de proveedores;
- comparación estructurada de cotizaciones;
- órdenes de compra;
- presupuesto;
- centros de costo;
- facturas;
- pagos;
- contabilidad;
- recepción parcial;
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

Estados V1:

- PENDING_REVIEW
- NEEDS_INFO
- REJECTED
- IN_QUOTATION
- CLOSED

CLOSED queda reservado, pero este contrato no define todavía el flujo posterior a cotización ni un botón de cierre.

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
- evento de routing/handoff cuando aplique.

Después del commit se notifica Mantenimiento.

## 14. Matriz de transiciones

| Desde | Acción | Hacia |
| --- | --- | --- |
| — | crear | PENDING_REVIEW |
| PENDING_REVIEW | solicitar información | NEEDS_INFO |
| NEEDS_INFO | reenviar | PENDING_REVIEW |
| PENDING_REVIEW | aprobar | IN_QUOTATION |
| PENDING_REVIEW | rechazar | REJECTED |

Cualquier transición distinta debe devolver error de negocio.

No exponer un PATCH genérico de status que permita saltarse el workflow.

## 15. Eventos / auditoría

Entidad propuesta:

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

Eventos iniciales:

- CREATED
- INFO_REQUESTED
- RESUBMITTED
- APPROVED
- REJECTED
- ROUTED_TO_MAINTENANCE
- ATTACHMENT_ADDED

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

### 17.3 Aprobar, rechazar, pedir información

Solo:

- GERENCIA DEPORTIVA;
- administradores explícitamente autorizados.

No:

- GERENTE;
- MANTENIMIENTO;
- RECEPCIONISTA;
- LECTOR_GLOBAL;
- creador únicamente por ser creador.

### 17.4 Después de aprobación

IN_QUOTATION:

- creador/sucursal con visibilidad;
- Gerencia Deportiva;
- Mantenimiento;
- administradores autorizados.

## 18. No hardcodear usuarios

Prohibido resolver negocio mediante username específico.

No usar patrones como:

    if username == GERDCORP

o destinatarios únicos como MANTCORP.

Resolver por rol/capacidad.

La implementación deberá verificar en DB la representación vigente de GERENCIA DEPORTIVA y MANTENIMIENTO antes de seedear o codificar permisos.

## 19. Notificaciones

Matriz:

| Evento | Destinatario |
| --- | --- |
| CREATED | Gerencia Deportiva |
| INFO_REQUESTED | solicitante |
| RESUBMITTED | Gerencia Deportiva |
| APPROVED | solicitante + Mantenimiento |
| REJECTED | solicitante |

Reglas:

- creación no notifica Mantenimiento;
- rechazo no notifica Mantenimiento;
- prioridad crítica no salta el flujo;
- retry no duplica correos;
- falla de email no revierte una transición de negocio confirmada;
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

Mostrar:

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

Gerencia Deportiva en PENDING_REVIEW:

    [ Aprobar ]
    [ Solicitar información ]
    [ Rechazar ]

Solicitante en NEEDS_INFO:

    [ Editar y reenviar ]

Mantenimiento en IN_QUOTATION:

- aprobada por;
- fecha;
- comentario;
- expediente completo.

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

Namespace independiente:

    /api/purchase-requisitions

Endpoints iniciales:

    POST /api/purchase-requisitions
    GET  /api/purchase-requisitions
    GET  /api/purchase-requisitions/<id>

    PUT  /api/purchase-requisitions/<id>/requester-edit
    POST /api/purchase-requisitions/<id>/resubmit

    POST /api/purchase-requisitions/<id>/request-info
    POST /api/purchase-requisitions/<id>/approve
    POST /api/purchase-requisitions/<id>/reject

    POST /api/purchase-requisitions/<id>/attachments
    GET  /api/purchase-requisitions/<id>/attachments/<attachment_id>/file

El nombre requester-edit podrá ajustarse durante implementación si existe una convención REST más apropiada.

No exponer un update genérico que pueda cambiar status arbitrariamente.

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

Creación atómica para:

- requisición;
- partidas;
- evento CREATED;
- metadata inicial.

Aprobación atómica para:

- validar actor;
- validar estado;
- registrar aprobación;
- mover a IN_QUOTATION;
- registrar APPROVED;
- registrar handoff.

Notificación después de commit o mediante mecanismo durable compatible.

No enviar correo antes de persistir la aprobación.

## 28. Concurrencia

Debe impedirse:

- doble aprobación;
- approve/reject simultáneos;
- doble resubmit;
- edición tardía después de aprobación.

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

Al aprobar:

- aparece en bandeja permitida para Mantenimiento;
- Mantenimiento recibe notificación;
- puede consultar expediente;
- no aparece en Maintenance Planner correctivo;
- no incrementa KPIs de fallas;
- no entra a reporte ejecutivo de fallas;
- no usa fecha_solucion legacy;
- no usa doble check de cierre de Tickets V1.

La futura gestión de cotizaciones se construirá sobre Requisiciones.

## 34. Integración Gerencia Deportiva

Gerencia Deportiva tendrá bandeja clara de pendientes de revisión.

Acciones:

- aprobar;
- solicitar información;
- rechazar.

Backend valida rol y estado en cada acción.

Ver una requisición no equivale automáticamente a poder aprobarla.

## 35. Integración sucursal

El creador podrá:

- ver requisiciones;
- consultar estado;
- responder NEEDS_INFO;
- consultar aprobación/rechazo;
- consultar expediente permitido.

El alcance de otros usuarios de la misma sucursal deberá seguir política Suite y probarse explícitamente.

## 36. Observabilidad

Logs estructurados para:

- creación;
- aprobación;
- rechazo;
- request-info;
- resubmit;
- adjuntos;
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

Backend:

1. creación válida;
2. mínimo una partida;
3. quantity > 0;
4. scope de sucursal;
5. estado inicial PENDING_REVIEW;
6. evento CREATED;
7. Mantenimiento no recibe routing inicial;
8. Gerencia Deportiva puede aprobar;
9. usuario no autorizado no aprueba;
10. aprobación guarda actor/fecha/comentario;
11. aprobación deja IN_QUOTATION;
12. handoff a Mantenimiento una sola vez;
13. rechazo exige motivo;
14. rechazo no notifica Mantenimiento;
15. request-info exige comentario;
16. resubmit desde NEEDS_INFO;
17. transición inválida rechazada;
18. concurrencia evita doble decisión;
19. scope de lectura;
20. LECTOR_GLOBAL no escribe;
21. adjunto privado respeta scope;
22. Ticket V1 normal continúa funcionando.

Frontend:

- formulario;
- múltiples partidas;
- bandeja;
- detalle;
- acciones por rol;
- request-info/resubmit;
- approve/reject.

No crear matriz combinatoria innecesaria.

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

## 42. Primera extensión prevista: cotizaciones

Fuera de implementación de este contrato.

La base deberá permitir que un contrato posterior agregue una entidad hija de cotizaciones con:

- proveedor;
- monto;
- moneda;
- archivo;
- fecha;
- seleccionado/no seleccionado;
- observaciones.

No agregar columnas quote_1, quote_2, quote_3 a la requisición.

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

R3. Gerencia Deportiva es reviewer funcional inicial.

R4. Mantenimiento no recibe requisición antes de aprobación.

R5. Aprobar mueve directamente a IN_QUOTATION; APPROVED es evento.

R6. REJECTED es terminal en MVP.

R7. NEEDS_INFO vuelve a PENDING_REVIEW mediante resubmit.

R8. Toda transición se valida en backend.

R9. Historial de eventos es append-only funcionalmente.

R10. No borrar requisiciones enviadas.

R11. No contaminar Planner/KPIs/reportes correctivos.

R12. Adjuntos no heredan reglas legacy por implicación.

R13. No hardcodear usernames.

R14. No notificar Mantenimiento en creación, rechazo o request-info.

R15. El bridge conserva mapping explícito a Tickets V2.

## 45. Decisiones pospuestas

No decidir aquí:

- workflow posterior a IN_QUOTATION;
- quién autoriza cotización;
- Compras vs Mantenimiento como comprador final;
- proveedor seleccionado;
- presupuesto;
- orden de compra;
- recepción;
- factura;
- pago;
- inventario;
- SLA;
- recordatorios;
- chat;
- integración nativa con Tickets V2 antes de M0 V2.

No inventar estos procesos durante implementación.

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
