# M0 — Investigación puntual de Requisiciones V1 Bridge

Estado: COMPLETADO A NIVEL REPOSITORIO; runtime productivo a reconfirmar antes de ejecutar migración
Fecha: 2026-10-02
Contrato: docs/contratos/tickets_v2/CONTRATO_REQUISICIONES_V1_BRIDGE.md
Rama documental: docs/tickets-v2-contract
Base revisada: main @ c8c7852f7237531588c40a3d42fa28b07e276994

## 1. Resultado ejecutivo

No existe actualmente un módulo de requisiciones ni purchase requisitions en el repositorio.

Sí existen las piezas corporativas necesarias para construir el bridge sin tocar Tickets V1:

- UserORM + JWT;
- sucursales;
- roles GERENCIA DEPORTIVA y MANTENIMIENTO;
- rol COMPRAS ya existente para crecimiento futuro;
- blueprints Flask bajo /api;
- Angular standalone + hash routing;
- envío de correo genérico mediante send_email_html;
- patrones modernos de acceso backend-authoritative para publicar módulos en menú;
- patrón seguro de almacenamiento privado de adjuntos de Tickets, aunque su implementación actual está acoplada al namespace tickets.

Conclusión:

> M1 puede implementarse como dominio completamente independiente. No es necesario modificar ticket_model.py, ticket_routes.py, ticket_filters.py, Maintenance Planner ni reportes de Mantenimiento.

## 2. Tickets V1: frontera confirmada

No usar para Requisiciones:

- backend/app/models/ticket_model.py
- backend/app/routes/ticket_routes.py
- backend/app/utils/ticket_filters.py
- backend/app/utils/maintenance_ticket_update_guard.py
- backend/app/maintenance_planner/*
- backend/app/services/mantenimiento_report_service.py
- backend/app/services/mantenimiento_equipos_report_service.py

La requisición no será una fila en tickets.

Esto elimina la necesidad de agregar excepciones para:

- estado por_validar;
- departamento_id = 1;
- doble check de cierre;
- Planner;
- reportes correctivos;
- targeting legacy de correo.

## 3. Roles y usuarios

UserORM persiste:

- id;
- username;
- rol;
- sucursal_id;
- department_id;
- email.

La autorización nueva deberá normalizar rol con trim + upper.

Roles confirmados en el código actual:

- ADMINISTRADOR;
- GERENCIA DEPORTIVA;
- MANTENIMIENTO;
- SR_MANTENIMIENTO;
- AUX_MANTENIMIENTO;
- GERENTE;
- GERENTE_REGIONAL;
- RECEPCIONISTA;
- LECTOR_GLOBAL;
- COMPRAS.

Gerencia Deportiva ya aparece como rol funcional real en varios módulos y Admin Usuarios.

Mantenimiento ya tiene roles especializados.

COMPRAS existe, pero NO participa todavía en el workflow aprobado de Requisiciones V1.

Regla:

- no hardcodear username;
- no depender de IDs históricos de usuarios;
- no usar department_id como única autoridad.

## 4. Sucursales

UserORM conserva sucursal_id y relación M:N mediante usuario_sucursal.

Para V1 bridge:

- usuario ordinario crea para su sucursal autorizada;
- admin corporativo podrá seleccionar sucursal conforme a política actual;
- GERENTE_REGIONAL deberá respetar sucursales_ids si se le permite crear/consultar.

La implementación de permisos deberá reutilizar la semántica existente de alcance por sucursal, pero en helper propio de Requisiciones.

No llamar filtrar_tickets_por_usuario porque opera sobre Ticket ORM.

## 5. Backend / blueprint

Patrón confirmado:

backend/app/__init__.py registra blueprints bajo /api.

Nuevo blueprint propuesto:

    purchase_requisition_bp

prefix:

    /api/purchase-requisitions

Archivo:

    backend/app/routes/purchase_requisition_routes.py

Debe registrarse en backend/app/__init__.py.

## 6. Acceso backend-authoritative

Los módulos nuevos actuales de Suite publican menú después de validar un endpoint backend.

Requisiciones deberá exponer:

    GET /api/purchase-requisitions/access

Respuesta mínima orientativa:

    {
      "allowed": true,
      "can_create": true,
      "can_review": false,
      "can_manage_quotation": false
    }

La forma final del DTO se fija en implementación M1/M2.

Objetivo:

- frontend guía UX;
- backend sigue siendo autoridad en cada operación.

## 7. Modelo de dominio a crear en M1

Archivo recomendado:

    backend/app/models/purchase_requisition.py

Entidades M1:

1. PurchaseRequisitionORM
2. PurchaseRequisitionItemORM
3. PurchaseRequisitionEventORM

Adjuntos NO entran en M1 salvo que se adelante expresamente M5.

Relaciones:

    requisition
      1 -> N items
      1 -> N events

FKs principales:

- sucursal_id -> sucursales.sucursal_id
- created_by_user_id -> users.id
- approved_by_user_id -> users.id nullable
- actor_user_id -> users.id nullable

No FK a tickets.

## 8. Estados M1

Persistir status como string con CheckConstraint o mecanismo equivalente coherente con el repo.

Valores aprobados:

- PENDING_REVIEW
- NEEDS_INFO
- REJECTED
- IN_QUOTATION
- CLOSED

No crear PostgreSQL enum salvo que durante implementación exista una razón fuerte.

Preferencia M0:

> String + CheckConstraint para evitar la rigidez del enum legacy y simplificar evolución/migración V2.

CLOSED podrá existir como valor de dominio pero no tendrá transición pública todavía.

## 9. Categoría, motivo y prioridad

Valores iniciales:

category:
- GYM_EQUIPMENT

reason:
- REPLACEMENT
- NEW_EQUIPMENT
- DAMAGE
- EXPANSION
- OTHER

priority:
- NORMAL
- HIGH
- CRITICAL

Aplicar constraints de DB además de validación de servicio cuando sea práctico.

## 10. Folio

public_id deberá ser UNIQUE.

Formato:

    RQ-YYYY-NNNNNN

No usar max(id)+1 desde aplicación sin protección.

M1 deberá seleccionar estrategia segura.

Opciones válidas a evaluar en implementación:

- sequence PostgreSQL dedicada por folio;
- generar tras flush usando PK, si el formato y estabilidad resultan suficientes.

Preferencia simple:

> Insert/flush -> obtener PK -> construir RQ-YYYY-{id padded} -> flush.

Ventajas:

- sin carrera;
- sin contador separado;
- folio estable;
- suficientemente independiente para conservarse en V2.

El PK sigue siendo interno; public_id es contrato externo.

## 11. Eventos

PurchaseRequisitionEventORM será append-only funcionalmente.

Eventos M1/M3:

- CREATED
- INFO_REQUESTED
- RESUBMITTED
- APPROVED
- REJECTED
- ROUTED_TO_MAINTENANCE

ATTACHMENT_ADDED entra cuando se implemente adjuntos.

No endpoints para editar o borrar eventos.

## 12. Permisos

Crear helper independiente:

    backend/app/utils/purchase_requisition_permissions.py

Capacidades sugeridas:

- can_purchase_requisition_access
- can_purchase_requisition_create
- can_purchase_requisition_review
- can_purchase_requisition_manage_quotation
- can_purchase_requisition_view

Admin roles:

- ADMIN
- ADMINISTRADOR
- SUPER_ADMIN

Reviewer:

- GERENCIA DEPORTIVA
- admin roles

Owner post-aprobación:

- MANTENIMIENTO
- SR_MANTENIMIENTO
- AUX_MANTENIMIENTO
- admin roles

LECTOR_GLOBAL:

- lectura si la política global se confirma;
- jamás write.

No heredar automáticamente permisos PM: el módulo tiene helper propio.

## 13. Email

Infraestructura reusable confirmada:

    backend/app/utils/email_sender.py::send_email_html

No reutilizar:

    backend/app/utils/notify_targets.py::pick_recipients

porque deriva destinatarios desde Ticket.departamento y sucursal.

Crear en M4:

    backend/app/services/purchase_requisition_notification_service.py

Targeting por evento y rol.

Resolver emails mediante UserORM.

No hardcodear cuentas.

## 14. Idempotencia de notificaciones

Contact Center ya tiene un patrón de entidad de notificación persistida.

M4 deberá investigar/reutilizar ese patrón conceptual para impedir duplicados.

No compartir tablas de Contact Center.

Opciones:

- tabla purchase_requisition_notifications;
- delivery marker ligado al event_id;
- mecanismo genérico si para entonces existe uno.

Requisito:

    (event_id, recipient, channel)

o clave equivalente deberá impedir duplicar entrega durante retry.

## 15. Adjuntos

Ticket attachment actual ofrece buenas garantías:

- storage privado;
- UUID;
- path traversal protection;
- escritura atómica;
- no overwrite;
- permisos POSIX cuando aplican;
- metadata/hash.

Pero está acoplado a:

    tickets/<ticket_id>/<uuid.ext>

y valida explícitamente ese patrón.

Conclusión:

> No reutilizar directamente ticket_attachment_storage_service.

M5 deberá elegir entre:

A. extraer primitivas genéricas de private storage preservando Ticket V1;
B. crear purchase_requisition_attachment_storage_service con el mismo patrón de seguridad.

No debilitar el servicio de Tickets para hacerlo genérico rápidamente.

El bridge debe soportar imágenes + PDF y múltiples archivos.

## 16. Frontend

Rutas existentes:

    /main/ver-tickets
    /main/crear-ticket

Layout actual presenta:

    Tickets
      Ver Tickets
      Crear Ticket

Nueva entrada preferida:

    Tickets
      Ver Tickets
      Crear Ticket
      Requisiciones

Ruta propuesta:

    /main/requisiciones

Por consistencia del router hijo real, el path Angular se registrará como:

    requisiciones

dentro de MainComponent.

## 17. Frontend a crear

Carpeta propuesta:

    frontend/src/app/purchase-requisitions/

Archivos iniciales:

- purchase-requisition.models.ts
- purchase-requisition.service.ts
- purchase-requisition-access.guard.ts
- purchase-requisition-list.component.ts
- purchase-requisition-list.component.html
- purchase-requisition-list.component.css
- purchase-requisition-create.component.ts
- purchase-requisition-create.component.html
- purchase-requisition-create.component.css
- purchase-requisition-detail.component.ts
- purchase-requisition-detail.component.html
- purchase-requisition-detail.component.css

Puede reducirse el número de componentes si una pantalla master/detail resulta más simple, pero no usar inline templates/styles.

## 18. Frontend a modificar

- frontend/src/app/app.routes.ts
- frontend/src/app/layout/layout.component.ts

La publicación de menú debe apoyarse en GET /access.

No asumir que menu hidden = authorization.

## 19. Backend a crear

M1:

- backend/app/models/purchase_requisition.py
- backend/app/services/purchase_requisition_service.py
- backend/app/services/purchase_requisition_workflow_service.py
- backend/app/utils/purchase_requisition_permissions.py
- backend/app/routes/purchase_requisition_routes.py
- backend/tests/purchase_requisitions/* o ubicación equivalente según convención
- nueva migración Alembic

M4:

- backend/app/services/purchase_requisition_notification_service.py
- tests de targeting/idempotencia

M5:

- backend/app/models/purchase_requisition_attachment.py si se separa
- backend/app/services/purchase_requisition_attachment_service.py
- backend/app/services/purchase_requisition_attachment_storage_service.py o helper genérico confirmado
- rutas/tests de archivos

## 20. Backend a modificar

M1/M2:

- backend/app/models/__init__.py
- backend/app/__init__.py

No modificar Ticket V1 para habilitar el bridge.

## 21. Alembic

El repositorio mantiene una única línea de migraciones.

Antes de crear la migración M1 se deberá reconfirmar en el checkout de implementación:

    flask db current
    flask db heads

No ejecutar upgrade contra producción durante desarrollo.

El down_revision de M1 será el head real observado al momento de crearla, no un valor copiado de este M0.

## 22. Archivos que explícitamente NO deben tocarse en M1-M4

Salvo hallazgo nuevo:

- backend/app/models/ticket_model.py
- backend/app/routes/ticket_routes.py
- backend/app/utils/ticket_filters.py
- backend/app/utils/maintenance_ticket_update_guard.py
- backend/app/maintenance_planner/*
- backend/app/services/mantenimiento_report_service.py
- backend/app/services/mantenimiento_equipos_report_service.py
- frontend/src/app/pantalla-ver-tickets/*
- frontend/src/app/pantalla-crear-ticket/*

Esto es una ventaja clave del bridge.

## 23. Riesgos confirmados

### Riesgo A — scope de sucursal

No copiar filtrar_tickets_por_usuario porque su query depende de Ticket.

Mitigación:

helper de permisos propio utilizando UserORM.sucursal_id y sucursales_ids.

### Riesgo B — role drift

Hay roles MANTENIMIENTO, SR_MANTENIMIENTO y AUX_MANTENIMIENTO.

Mitigación:

definir conjuntos de capacidades explícitos; no comparar contra un solo rol.

### Riesgo C — storage

El storage seguro actual está namespaced a Tickets.

Mitigación:

extraer primitiva o crear servicio de requisición sin relajar validaciones legacy.

### Riesgo D — correo duplicado

send_email_html no proporciona por sí solo idempotencia de negocio.

Mitigación:

M4 agrega delivery tracking por evento/destinatario.

### Riesgo E — navegación sin auth

Agregar menú directamente por role frontend sería insuficiente.

Mitigación:

GET /access backend-authoritative + guard frontend + checks backend por acción.

## 24. Decisiones cerradas por M0

1. Dominio independiente de Ticket V1.
2. Blueprint /api/purchase-requisitions.
3. Modelos propios.
4. Cabecera + partidas.
5. Event log propio.
6. Permisos propios por capacidad.
7. UserORM/Sucursal se reutilizan.
8. send_email_html se reutiliza como transporte.
9. notify_targets de Ticket no se reutiliza.
10. storage de Ticket no se reutiliza directamente.
11. menu vive bajo Tickets.
12. access endpoint controla publicación.
13. String + CheckConstraint es preferible a enum PostgreSQL para status/catálogos del bridge.
14. Folio puede derivarse del PK después de flush para evitar carrera.
15. Ningún cambio de Planner/reportes/Tickets legacy es necesario.

## 25. Validaciones runtime todavía obligatorias antes de M1 migration

En el checkout donde se implemente M1:

- git status --short;
- git branch --show-current;
- git rev-parse HEAD;
- flask db current;
- flask db heads.

También verificar en base real:

- al menos un usuario GERENCIA DEPORTIVA activo con email cuando se llegue a M4;
- usuarios MANTENIMIENTO activos con email;
- catálogo real de sucursales.

Estas verificaciones no requieren cambiar el contrato de dominio salvo que revelen una diferencia material.

## 26. Criterio de cierre M0

M0 se considera cerrado cuando:

- existe contrato;
- no existe módulo equivalente;
- boundaries V1 están identificados;
- roles necesarios existen en código;
- infraestructura reusable/no reusable está identificada;
- archivos M1 están delimitados;
- estrategia de migración V2 permanece 1:1;
- no se modificó código funcional.

Resultado: LISTO PARA M1.
