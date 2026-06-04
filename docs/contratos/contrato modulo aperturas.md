# Suite Ultra — Contrato Técnico Módulo de Aperturas

## Centro de control operativo-financiero para aperturas Ultra

---

## 0. Separación de contratos

Este contrato corresponde únicamente al:

```text
Módulo de Aperturas
```

La **Nube Corporativa** tiene contrato separado.

Relación correcta:

```text
Nube Corporativa = base documental gobernada
Aperturas = centro de control operativo-financiero que consume documentos de Nube
```

Aperturas no debe reimplementar almacenamiento documental, versionado, preview ni auditoría documental.

Aperturas debe consumir documentos desde Nube mediante vínculos documentales.

---

## 1. Principio rector

No estamos construyendo una copia de Microsoft Project.

Estamos construyendo un centro de control de aperturas hecho para Ultra.

El módulo debe resolver:

```text
Quién hace qué
Para cuándo
De qué depende
Qué documento lo respalda
Qué partida presupuestal lo paga
Cuánto presupuesto queda
Qué proveedor cobra
Qué factura respalda el pago
Si Finanzas ya recibió/programó/pagó
Qué cambió, quién lo cambió y cuándo
```

Microsoft Project puede ser fuerte en Gantt.

Suite Ultra debe ser fuerte en:

```text
contexto operativo + presupuesto + pagos + documentos + responsables + trazabilidad
```

---

## 2. Objetivo del módulo

Construir un módulo robusto para coordinar aperturas de nuevas sucursales, integrando:

* cronograma,
* fases,
* tareas,
* responsables,
* fechas,
* dependencias,
* presupuesto autorizado,
* partidas,
* solicitudes de pago,
* proveedores,
* facturas,
* documentos oficiales,
* cambios,
* bitácora,
* alertas,
* tablero ejecutivo.

El objetivo no es solo ver tareas.

El objetivo es controlar una apertura completa desde planeación hasta entrega operativa.

---

## 3. Contexto operativo

La apertura actual **Serranía** se está coordinando con el método tradicional, principalmente mediante grupo de WhatsApp y archivos compartidos.

Serranía se usará como caso real para aprender problemas operativos.

La siguiente apertura objetivo es **Egade**, estimada aproximadamente en un mes.

El módulo debe estar pensado para que Egade sea la primera apertura gestionada de forma seria desde Suite Ultra.

---

## 4. Principios UX obligatorios

La UX es requisito de éxito, no cosmético.

Si la pantalla se siente como tabla genérica, Excel web o Project mal copiado, el módulo pierde valor.

### 4.1 Vista ejecutiva primero

Al entrar a una apertura, lo primero debe verse como tablero ejecutivo:

```text
Apertura Egade
Estado general
% avance
Fecha objetivo
Días restantes
Tareas atrasadas
Riesgos abiertos
Presupuesto autorizado
Presupuesto comprometido
Pagos pendientes
Documentos críticos faltantes
```

La vista inicial debe responder en menos de 10 segundos:

```text
¿Cómo va la apertura?
¿Qué está atorado?
Qué urge?
Quién debe moverse?
Qué impacto financiero hay?
```

### 4.2 Detalle después

El detalle debe existir, pero no dominar la primera vista.

El módulo debe permitir bajar de nivel:

```text
Apertura → Fase → Tarea → Pago / Documento / Comentario / Cambio
```

### 4.3 No saturar con tablas

Las tablas son necesarias, pero no deben ser la experiencia principal.

Se deben usar:

* cards ejecutivas,
* timeline por fases,
* lista compacta de pendientes,
* panel lateral de detalle,
* semáforos,
* chips de estado,
* badges de riesgo,
* filtros inteligentes.

### 4.4 Gantt simple, no Project completo

Debe existir una vista de línea de tiempo/Gantt simplificado.

Pero no se busca replicar toda la complejidad de Microsoft Project.

El Gantt debe servir para:

* visualizar fases,
* fechas inicio/fin,
* atrasos,
* dependencias críticas,
* carga por área,
* tareas bloqueadas.

No debe volverse una herramienta pesada de planeación avanzada.

### 4.5 Mobile controlado

Móvil no será para planear toda una apertura.

Móvil debe servir para:

* revisar estado,
* comentar,
* aprobar/rechazar,
* marcar avance rápido,
* ver documentos,
* subir evidencia,
* responder alertas.

Desktop será para planeación completa.

---

## 5. Pilares funcionales

El módulo se divide en cuatro pilares:

### 5.1 Control operativo

Incluye:

* apertura,
* fases,
* tareas,
* responsables,
* fechas,
* dependencias,
* estados,
* avances,
* comentarios,
* cambios.

### 5.2 Control financiero

Incluye:

* presupuesto autorizado,
* partidas presupuestales,
* solicitudes de pago,
* proveedores,
* cuentas bancarias,
* facturas,
* comprobantes,
* estatus con Finanzas,
* saldos por partida.

### 5.3 Control documental

Incluye:

* documentos vinculados desde Nube,
* planos,
* contratos,
* permisos,
* cotizaciones,
* facturas,
* evidencias,
* checklists,
* manuales.

### 5.4 Control de cambios

Incluye:

* bitácora,
* historial de cambios,
* responsables,
* fecha/hora,
* antes/después,
* comentarios obligatorios en cambios sensibles.

---

## 6. Entidades principales

## 6.1 Sucursal

Ya existe una tabla de sucursales en Suite Ultra.

Aperturas debe reutilizar la base de datos de sucursales.

Pero no se recomienda meter toda la lógica de apertura dentro de la tabla `sucursales`.

### Ajuste recomendado a sucursales

Agregar campo de estado operativo o lifecycle:

```text
PLANEADA
EN_APERTURA
ACTIVA
PAUSADA
CANCELADA
CERRADA
```

El módulo de Aperturas debe mostrar principalmente sucursales en:

```text
EN_APERTURA
```

o equivalentes.

### Regla

```text
Sucursal = entidad física/operativa
Apertura = proyecto temporal para poner esa sucursal en marcha
```

---

## 6.2 Apertura

Tabla propuesta:

```text
openings
```

Representa el proyecto de apertura de una sucursal.

Campos conceptuales:

| Campo                   | Uso                          |
| ----------------------- | ---------------------------- |
| id                      | PK                           |
| sucursal_id             | FK sucursal                  |
| opening_key             | Clave legible, ejemplo EGADE |
| name                    | Nombre visible               |
| description             | Descripción                  |
| status                  | Estado de apertura           |
| planned_start_date      | Fecha planeada de inicio     |
| target_opening_date     | Fecha objetivo de apertura   |
| actual_opening_date     | Fecha real                   |
| general_owner_user_id   | Responsable general          |
| region_id               | Región si aplica             |
| budget_authorized_total | Presupuesto autorizado       |
| budget_currency_id      | Moneda                       |
| created_by              | Usuario creador              |
| updated_by              | Último editor                |
| created_at              | Fecha creación               |
| updated_at              | Fecha actualización          |

Estados sugeridos:

```text
BORRADOR
PLANEADA
EN_EJECUCION
EN_RIESGO
PAUSADA
ABIERTA
CANCELADA
CERRADA
```

---

## 6.3 Fases

Tabla propuesta:

```text
opening_phases
```

Representa bloques grandes de trabajo.

Fases base sugeridas por experiencia de Serranía:

* Preliminares
* Legal
* Finanzas
* Construcción
* Compras
* Sistemas
* Deportivo
* Capital Humano
* Marketing / Preventa
* Operaciones
* Apertura / Entrega

Campos:

| Campo               | Uso                 |
| ------------------- | ------------------- |
| id                  | PK                  |
| opening_id          | FK apertura         |
| name                | Nombre fase         |
| description         | Descripción         |
| sort_order          | Orden               |
| planned_start_date  | Inicio planeado     |
| planned_end_date    | Fin planeado        |
| actual_start_date   | Inicio real         |
| actual_end_date     | Fin real            |
| status              | Estado              |
| owner_department_id | Área responsable    |
| owner_user_id       | Responsable         |
| progress_percent    | Avance              |
| created_at          | Fecha creación      |
| updated_at          | Fecha actualización |

Estados:

```text
NO_INICIADA
EN_PROCESO
BLOQUEADA
EN_RIESGO
COMPLETADA
CANCELADA
```

---

## 6.4 Tareas

Tabla propuesta:

```text
opening_tasks
```

Campos:

| Campo               | Uso                 |
| ------------------- | ------------------- |
| id                  | PK                  |
| opening_id          | FK apertura         |
| phase_id            | FK fase             |
| parent_task_id      | Para subtareas      |
| title               | Título              |
| description         | Descripción         |
| status              | Estado              |
| priority            | Prioridad           |
| owner_user_id       | Responsable         |
| owner_department_id | Área responsable    |
| planned_start_date  | Inicio planeado     |
| planned_due_date    | Fecha compromiso    |
| actual_start_date   | Inicio real         |
| actual_completed_at | Cierre real         |
| progress_percent    | Avance              |
| sort_order          | Orden               |
| requires_document   | Requiere documento  |
| requires_payment    | Requiere pago       |
| created_by          | Usuario creador     |
| updated_by          | Último editor       |
| created_at          | Fecha creación      |
| updated_at          | Fecha actualización |

Estados:

```text
NO_INICIADA
EN_PROCESO
BLOQUEADA
EN_REVISION
COMPLETADA
CANCELADA
```

Prioridades:

```text
BAJA
MEDIA
ALTA
CRITICA
```

---

## 6.5 Dependencias

Tabla propuesta:

```text
opening_task_dependencies
```

Campos:

| Campo              | Uso               |
| ------------------ | ----------------- |
| id                 | PK                |
| task_id            | Tarea dependiente |
| depends_on_task_id | Tarea que bloquea |
| dependency_type    | Tipo              |
| created_by         | Usuario creador   |
| created_at         | Fecha             |

Tipos:

```text
FINISH_TO_START
START_TO_START
FINISH_TO_FINISH
BLOCKER
```

Para F1 puede bastar con:

```text
BLOCKER
```

---

## 6.6 Comentarios / bitácora de tarea

Tabla propuesta:

```text
opening_task_comments
```

Campos:

| Campo           | Uso               |
| --------------- | ----------------- |
| id              | PK                |
| opening_id      | FK apertura       |
| task_id         | FK tarea          |
| comment         | Comentario        |
| created_by      | Usuario           |
| created_at      | Fecha             |
| is_system_event | Evento automático |

Debe servir para:

* acuerdos,
* actualizaciones,
* justificaciones,
* seguimiento,
* evidencia narrativa.

---

## 6.7 Auditoría / eventos

Tabla propuesta:

```text
opening_audit_logs
```

Acciones auditables:

```text
OPENING_CREATED
OPENING_UPDATED
PHASE_CREATED
PHASE_UPDATED
TASK_CREATED
TASK_UPDATED
TASK_STATUS_CHANGED
TASK_DUE_DATE_CHANGED
TASK_OWNER_CHANGED
BUDGET_IMPORTED
BUDGET_ITEM_CREATED
BUDGET_ITEM_UPDATED
PAYMENT_REQUEST_CREATED
PAYMENT_REQUEST_SUBMITTED
PAYMENT_REQUEST_STATUS_CHANGED
DOCUMENT_LINKED
DOCUMENT_UNLINKED
```

Campos:

| Campo          | Uso                                       |
| -------------- | ----------------------------------------- |
| id             | PK                                        |
| opening_id     | FK apertura                               |
| entity_type    | OPENING / PHASE / TASK / PAYMENT / BUDGET |
| entity_id      | ID relacionado                            |
| action         | Acción                                    |
| old_value_json | Antes                                     |
| new_value_json | Después                                   |
| metadata_json  | Contexto                                  |
| actor_user_id  | Usuario                                   |
| created_at     | Fecha                                     |

---

# 7. Presupuesto

## 7.1 Presupuesto autorizado

Tabla propuesta:

```text
opening_budgets
```

Campos:

| Campo              | Uso                                 |
| ------------------ | ----------------------------------- |
| id                 | PK                                  |
| opening_id         | FK apertura                         |
| version_label      | Versión                             |
| status             | BORRADOR / AUTORIZADO / REEMPLAZADO |
| currency_id        | Moneda                              |
| authorized_total   | Total autorizado                    |
| source_document_id | Documento Nube                      |
| created_by         | Usuario                             |
| authorized_by      | Usuario autorizador                 |
| authorized_at      | Fecha autorización                  |
| created_at         | Fecha creación                      |

Regla:

El presupuesto autorizado no debe sobrescribirse silenciosamente.

Si cambia, debe crearse nueva versión o evento auditado.

---

## 7.2 Partidas presupuestales

Tabla propuesta:

```text
opening_budget_items
```

La columna B del archivo de presupuesto actual corresponde conceptualmente a las partidas.

Campos:

| Campo             | Uso                |
| ----------------- | ------------------ |
| id                | PK                 |
| opening_budget_id | FK presupuesto     |
| opening_id        | FK apertura        |
| area_key          | Área               |
| item_key          | Clave normalizada  |
| name              | Nombre de partida  |
| description       | Descripción        |
| authorized_amount | Monto autorizado   |
| committed_amount  | Monto comprometido |
| paid_amount       | Monto pagado       |
| currency_id       | Moneda             |
| status            | Estado             |
| created_by        | Usuario            |
| updated_by        | Usuario            |
| created_at        | Fecha              |
| updated_at        | Fecha              |

Estados:

```text
ACTIVA
PROPUESTA
APROBADA
RECHAZADA
CANCELADA
```

### Regla de nuevas partidas

Se pueden agregar partidas nuevas, pero no como texto libre silencioso.

Si una partida no existe:

* puede proponerse,
* debe auditarse,
* puede requerir aprobación si implica incremento presupuestal.

---

## 7.3 Control de saldo

Cada partida debe mostrar:

```text
presupuesto autorizado
monto solicitado
monto programado
monto pagado
saldo disponible
```

Fórmula conceptual:

```text
saldo disponible = autorizado - comprometido - pagado
```

Donde:

```text
comprometido = solicitudes enviadas/programadas no pagadas
pagado = pagos confirmados por Finanzas
```

---

# 8. Solicitudes de pago a proveedores

## 8.1 Objetivo

Convertir el formato Excel de solicitud de pago a proveedores en un flujo dentro de Suite Ultra.

El MVP no leerá automáticamente facturas.

El MVP debe estructurar correctamente:

```text
apertura → partida → proveedor → factura → solicitud de pago → Finanzas
```

---

## 8.2 Tabla propuesta

```text
opening_payment_requests
```

Campos:

| Campo                    | Uso                      |
| ------------------------ | ------------------------ |
| id                       | PK                       |
| opening_id               | FK apertura              |
| budget_item_id           | FK partida               |
| requested_by             | Usuario solicitante      |
| provider_id              | FK proveedor             |
| provider_bank_account_id | FK cuenta bancaria       |
| concept                  | Concepto                 |
| invoice_date             | Fecha factura            |
| requested_payment_date   | Fecha solicitud          |
| subtotal                 | Subtotal                 |
| tax_amount               | IVA                      |
| tax_rate                 | Tasa IVA                 |
| total_amount             | Total con IVA incluido   |
| currency_id              | Moneda                   |
| fiscal_uuid              | Folio fiscal             |
| invoice_number           | Número/factura           |
| notes                    | Notas                    |
| status                   | Estado                   |
| finance_reviewed_by      | Usuario Finanzas         |
| finance_reviewed_at      | Fecha revisión           |
| scheduled_payment_date   | Fecha programada         |
| paid_at                  | Fecha pago               |
| proof_document_id        | Comprobante pago en Nube |
| invoice_document_id      | Factura en Nube          |
| created_at               | Fecha creación           |
| updated_at               | Fecha actualización      |

---

## 8.3 Estados de solicitud

Estados propuestos:

```text
BORRADOR
ENVIADA
EN_REVISION_FINANZAS
PROGRAMADA
PAGADA
RECHAZADA
CANCELADA
```

### Reglas

BORRADOR:

* editable por solicitante/admin.

ENVIADA:

* ya no debería editarse libremente.
* queda en espera de revisión.

EN_REVISION_FINANZAS:

* Finanzas está validando.

PROGRAMADA:

* Finanzas ya definió fecha o intención de pago.

PAGADA:

* pago liberado.
* debe poder anexarse comprobante.

RECHAZADA:

* requiere motivo.

CANCELADA:

* no debe afectar saldo activo.

---

## 8.4 Campos obligatorios para enviar a Finanzas

Para pasar de BORRADOR a ENVIADA:

* apertura,
* partida,
* proveedor,
* cuenta bancaria/CLABE,
* concepto,
* total con IVA incluido,
* moneda,
* folio fiscal,
* número/factura cuando aplique,
* factura adjunta,
* notas si hay condición especial.

---

## 8.5 Factura adjunta

La factura debe adjuntarse obligatoriamente para enviar a Finanzas.

La factura debe vivir en Nube Corporativa.

La solicitud de pago debe guardar referencia:

```text
invoice_document_id
```

La Nube debe mantener:

* archivo,
* versión,
* preview,
* descarga,
* auditoría documental.

Aperturas solo referencia el documento.

---

## 8.6 Folio fiscal

El folio fiscal es obligatorio.

Regla mínima:

```text
No permitir folio fiscal duplicado dentro de la misma apertura.
```

Regla recomendada:

```text
No permitir folio fiscal duplicado globalmente en solicitudes activas.
```

Esto evita riesgo de doble pago.

---

## 8.7 IVA

La UI F1 debe pedir:

```text
Total con IVA incluido
```

Debe permitir calcular como apoyo:

```text
subtotal = total / (1 + tax_rate)
iva = total - subtotal
```

Default:

```text
tax_rate = 16%
```

Pero debe poder ajustarse a:

```text
0%
8%
16%
otro
```

No asumir que todas las facturas siempre tendrán 16%.

---

# 9. Proveedores

## 9.1 Catálogo de proveedores

Tabla propuesta:

```text
providers
```

Campos:

| Campo             | Uso              |
| ----------------- | ---------------- |
| id                | PK               |
| legal_name        | Razón social     |
| trade_name        | Nombre comercial |
| rfc               | RFC              |
| provider_area_key | Área/categoría   |
| status            | Activo/Inactivo  |
| notes             | Notas            |
| created_by        | Usuario          |
| updated_by        | Usuario          |
| created_at        | Fecha            |
| updated_at        | Fecha            |

Áreas/categorías sugeridas:

```text
SISTEMAS
MANTENIMIENTO
RH
CONSTRUCCION
COMPRAS
MARKETING
LEGAL
DEPORTIVO
OPERACION
FINANZAS
OTRO
```

---

## 9.2 Cuentas bancarias de proveedores

Tabla propuesta:

```text
provider_bank_accounts
```

Campos:

| Campo          | Uso            |
| -------------- | -------------- |
| id             | PK             |
| provider_id    | FK proveedor   |
| bank_name      | Banco          |
| clabe          | CLABE          |
| account_holder | Titular        |
| currency_id    | Moneda         |
| is_default     | Cuenta default |
| is_active      | Activa         |
| created_at     | Fecha          |
| updated_at     | Fecha          |

Regla:

La CLABE debe buscarse/seleccionarse desde cuenta bancaria del proveedor.

No debe capturarse como texto libre principal en cada solicitud.

### Seguridad

Datos bancarios de proveedores son sensibles.

Deben tener permisos más estrictos que catálogos simples.

---

# 10. Monedas

No mezclar monedas con unidades de medida.

Crear catálogo propio:

```text
currencies
```

Campos:

| Campo     | Uso                   |
| --------- | --------------------- |
| id        | PK                    |
| code      | MXN / USD             |
| name      | Peso mexicano / Dólar |
| symbol    | $ / US$               |
| decimals  | 2                     |
| is_active | Activa                |

Monedas iniciales:

```text
MXN
USD
```

---

# 11. Documentos vinculados desde Nube

Aperturas debe consumir documentos desde Nube Corporativa mediante:

```text
internal_document_links
```

Ejemplos:

```text
OPENING / EGADE / PLANO
OPENING / EGADE / CONTRATO
OPENING / EGADE / PERMISO
OPENING / EGADE / FACTURA
TASK / EGADE-ELECTRICO-001 / EVIDENCIA
```

### Ajuste requerido a Nube

Agregar roles documentales adicionales:

```text
FACTURA
COMPROBANTE_PAGO
PRESUPUESTO
CRONOGRAMA
```

Esto puede hacerse cuando inicie la integración formal.

---

# 12. UX objetivo del módulo

## 12.1 Pantalla inicial: listado de aperturas

Debe mostrar cards de aperturas:

```text
Egade
Serranía
Estado
Fecha objetivo
Avance %
Presupuesto autorizado
Pagos pendientes
Tareas atrasadas
Riesgos
```

Filtros:

* estado,
* región,
* responsable,
* fecha objetivo,
* riesgo,
* avance.

---

## 12.2 Dashboard de apertura

Al entrar a una apertura:

### Header

```text
Apertura Egade
Estado: En ejecución
Fecha objetivo: dd/mm/yyyy
Días restantes
Responsable general
```

### KPIs principales

* avance general,
* tareas completadas,
* tareas atrasadas,
* tareas bloqueadas,
* presupuesto autorizado,
* comprometido,
* pagado,
* saldo disponible,
* pagos pendientes,
* documentos críticos faltantes.

### Secciones principales

* Timeline / fases
* Tareas
* Presupuesto
* Solicitudes de pago
* Documentos
* Cambios / bitácora

---

## 12.3 Timeline / Gantt simple

Debe mostrar fases con barras.

Cada fase puede expandirse a tareas.

Debe resaltar:

* atrasos,
* bloqueos,
* dependencias,
* tareas críticas.

No debe intentar copiar Project completo.

---

## 12.4 Panel lateral de tarea

Al seleccionar tarea:

* título,
* estado,
* prioridad,
* responsable,
* área,
* fecha compromiso,
* dependencias,
* documentos vinculados,
* partida presupuestal,
* solicitudes de pago relacionadas,
* comentarios,
* historial.

---

## 12.5 Vista financiera

Debe mostrar:

* presupuesto por área,
* partidas,
* autorizado,
* comprometido,
* pagado,
* saldo,
* solicitudes pendientes,
* alertas de sobrepresupuesto.

Debe permitir navegar:

```text
Partida → solicitudes de pago → factura → proveedor
```

---

## 12.6 Vista solicitudes de pago

Debe mostrar:

* folio interno,
* proveedor,
* partida,
* concepto,
* total,
* moneda,
* folio fiscal,
* estado,
* fecha solicitud,
* fecha programada,
* comprobante.

Acciones:

* crear borrador,
* enviar a Finanzas,
* revisar,
* programar,
* marcar pagada,
* rechazar,
* cancelar.

---

# 13. Permisos

Roles sugeridos:

```text
APERTURAS_ADMIN
APERTURAS_MANAGER
APERTURAS_COLABORADOR
APERTURAS_FINANZAS
APERTURAS_LECTOR
SISTEMAS
ADMIN
SUPER_ADMIN
```

### Capacidades

ADMIN / SUPER_ADMIN / SISTEMAS:

* todo.

APERTURAS_ADMIN:

* crear apertura,
* editar fases/tareas,
* asignar responsables,
* administrar presupuesto,
* ver pagos,
* gestionar documentos.

APERTURAS_MANAGER:

* editar tareas asignadas,
* comentar,
* subir evidencia,
* crear solicitudes de pago si aplica.

APERTURAS_FINANZAS:

* revisar solicitudes,
* programar pago,
* marcar pagado,
* rechazar,
* adjuntar comprobantes.

APERTURAS_COLABORADOR:

* ver tareas asignadas,
* actualizar avance,
* comentar,
* subir evidencia.

APERTURAS_LECTOR:

* solo consulta.

---

# 14. Notificaciones

Eventos notificables:

* tarea asignada,
* tarea próxima a vencer,
* tarea atrasada,
* tarea bloqueada,
* cambio de fecha,
* cambio de responsable,
* solicitud de pago enviada,
* solicitud rechazada,
* pago programado,
* pago liberado,
* presupuesto excedido,
* documento crítico faltante,
* apertura cambia de estado.

Canales posibles:

* notificación interna Suite,
* correo,
* Telegram futuro,
* WhatsApp no directo en F1.

---

# 15. Roadmap

## F0 — Contrato y diseño

* cerrar contrato,
* revisar Serranía,
* extraer fases/tareas reales,
* mapear presupuesto,
* definir UX inicial.

## F1 — Base de Aperturas

Incluye:

* tabla `openings`,
* relación con sucursales,
* estados de apertura,
* fases,
* tareas,
* responsables,
* fechas,
* dependencias simples,
* dashboard básico,
* timeline simple.

No incluye aún pagos complejos.

## F2 — Presupuesto y partidas

Incluye:

* presupuesto de apertura,
* partidas,
* carga manual o importación base,
* saldos,
* avance financiero por partida.

## F3 — Solicitudes de pago

Incluye:

* proveedores,
* cuentas bancarias,
* monedas,
* solicitudes de pago,
* factura adjunta,
* estados con Finanzas,
* folio fiscal obligatorio,
* validación de duplicados.

## F4 — Integración documental completa

Incluye:

* documentos requeridos por fase/tarea,
* consumo avanzado de Nube,
* roles documentales FACTURA, COMPROBANTE_PAGO, PRESUPUESTO, CRONOGRAMA,
* documentos críticos faltantes.

## F5 — Notificaciones y control de cambios

Incluye:

* alertas,
* bitácora visual,
* cambios sensibles con motivo,
* recordatorios.

## F6 — Automatización inteligente

Incluye:

* lectura de XML/PDF de facturas,
* autollenado proveedor/folio/total,
* detección avanzada de duplicados,
* sugerencias de partida,
* reportes ejecutivos automáticos.

---

# 16. MVP robusto para Egade

El MVP para Egade debe incluir mínimo:

```text
1. Crear apertura Egade vinculada a sucursal en estado EN_APERTURA.
2. Crear fases base.
3. Crear tareas con responsable, área y fecha.
4. Ver dashboard ejecutivo.
5. Ver timeline simple.
6. Registrar presupuesto base.
7. Registrar partidas.
8. Crear solicitud de pago contra partida.
9. Seleccionar proveedor.
10. Seleccionar cuenta bancaria.
11. Capturar total con IVA.
12. Capturar folio fiscal.
13. Adjuntar factura desde Nube.
14. Enviar solicitud a Finanzas.
15. Cambiar estados de pago.
16. Ver documentos vinculados.
17. Ver bitácora de cambios.
```

Esto ya sería suficientemente fuerte para demostrar valor real.

---

# 17. Riesgos

### Riesgo 1: copiar Project y perder diferenciación

Mitigación:

* UX ejecutiva primero,
* integración financiera/documental,
* Gantt simple,
* contexto Ultra.

### Riesgo 2: volverse otro Excel

Mitigación:

* catálogos,
* estados,
* permisos,
* validaciones,
* trazabilidad,
* dashboards.

### Riesgo 3: sobreconstruir antes de Egade

Mitigación:

* F1 operativo,
* F2 financiero,
* F3 pagos,
* no meter OCR ni automatización fiscal al inicio.

### Riesgo 4: pagos sin control

Mitigación:

* partida obligatoria,
* factura obligatoria,
* folio fiscal obligatorio,
* proveedor/cuenta bancaria por catálogo,
* auditoría.

### Riesgo 5: presupuesto se vuelve flexible sin control

Mitigación:

* presupuesto versionado,
* partidas nuevas auditadas,
* incrementos con aprobación,
* saldos por partida.

### Riesgo 6: UX pesada

Mitigación:

* dashboard primero,
* panel lateral,
* acciones rápidas,
* móvil limitado,
* no saturar con tablas.

---

# 18. Criterios de aceptación F1

F1 se considera completo cuando:

1. Se puede crear una apertura.
2. Se puede vincular a sucursal.
3. Se pueden crear fases.
4. Se pueden crear tareas.
5. Las tareas tienen responsable, área, estado y fecha.
6. Se pueden marcar tareas como completadas/bloqueadas.
7. Se puede ver dashboard ejecutivo.
8. Se puede ver timeline simple.
9. Se puede consultar detalle de tarea.
10. Se puede comentar en tarea.
11. Se auditan cambios importantes.
12. El backend valida permisos.
13. La UI se siente como centro de control, no como tabla MVP.

---

# 19. Criterios de aceptación F3 pagos

F3 se considera completo cuando:

1. Se puede crear proveedor.
2. Se puede registrar cuenta bancaria.
3. Se puede crear solicitud de pago.
4. La solicitud exige apertura.
5. La solicitud exige partida.
6. La solicitud exige proveedor.
7. La solicitud exige total.
8. La solicitud exige folio fiscal.
9. La solicitud exige factura adjunta.
10. Se valida duplicado de folio fiscal.
11. Se puede enviar a Finanzas.
12. Finanzas puede revisar/programar/pagar/rechazar.
13. Se actualizan saldos de partida.
14. Se auditan cambios.
15. Se puede consultar por apertura, proveedor, partida y estado.

---

# 20. No incluido en MVP

No incluir inicialmente:

* OCR automático,
* validación SAT,
* integración bancaria,
* Project avanzado,
* WhatsApp automático,
* IA sobre documentos,
* firma digital,
* aprobaciones complejas multi-nivel,
* forecast financiero avanzado.

---

# 21. Próximo paso

Después de cerrar este contrato:

1. Crear rama documental.
2. Guardar contrato en:

```text
docs/contratos/contrato modulo aperturas.md
```

3. Revisarlo.
4. Crear F1 de implementación con contrato micro:

```text
F1 — Base de Aperturas
```

5. Implementar paso a paso:

```text
DB → Backend → Frontend → QA
```
