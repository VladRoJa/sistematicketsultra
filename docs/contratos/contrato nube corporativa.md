# Suite Ultra — Contrato Técnico Nube Corporativa

## Portal Interno de Documentos Publicados

### Base documental gobernada para Suite Ultra y preparación estratégica para Módulo de Aperturas

---

## 0. Estado actual del módulo

### Estado general

La F1 de Nube Corporativa ya fue implementada y desplegada en producción.

Actualmente el módulo permite:

* crear documentos internos como borrador,
* subir archivos usando flujo Warehouse-first,
* registrar versiones,
* mantener una versión vigente,
* ocultar versiones anteriores para usuarios normales,
* auditar acciones administrativas,
* configurar visibilidad,
* publicar documentos,
* archivar documentos,
* descargar documentos mediante endpoint seguro con JWT,
* usar menú dinámico dentro de Suite Ultra,
* ocultar el menú a roles no administrativos mientras el módulo madura.

### Decisión operativa temporal

El menú de Nube Corporativa queda oculto para gerentes y usuarios no administrativos por ahora.

Motivo:

* el módulo ya funciona,
* pero todavía está en etapa inicial,
* falta pulir UX,
* falta cerrar preview en pantalla,
* falta definir vínculos documentales para aperturas,
* no se quiere generar ruido operativo,
* no se quiere que gerentes empiecen a preguntar antes de cerrar el contrato de uso.

Roles con acceso visible al menú en esta etapa:

* ADMIN
* ADMINISTRADOR
* SUPER_ADMIN
* SISTEMAS

---

## 1. Objetivo técnico

Construir y evolucionar un módulo interno para publicar documentos corporativos dentro de Suite Ultra, usando el Warehouse como bóveda de archivos y trazabilidad, y una capa separada de publicación para usuarios finales.

La Nube Corporativa no debe comportarse como Google Drive.

Debe funcionar como un sistema documental gobernado con:

* metadata obligatoria,
* dueño documental,
* estado documental,
* versión vigente,
* versiones históricas ocultas pero trazables,
* permisos backend,
* auditoría,
* descarga segura,
* preview seguro en pantalla para PDF e imágenes,
* búsqueda y filtros básicos,
* preparación para vincular documentos a proyectos, aperturas, sucursales, tareas y responsables.

---

## 2. Nuevo contexto estratégico: preparación para Aperturas

### Problema real detectado

En aperturas de nuevas sucursales ha ocurrido que:

* cada área maneja versiones distintas de planes,
* hay desfases de fechas,
* personas se dan por no enteradas,
* documentos y planos se pierden en chats,
* acuerdos quedan enterrados en WhatsApp,
* no existe una fuente única de verdad,
* las aperturas cambian constantemente,
* se agregan tareas nuevas sobre la marcha,
* no queda claro cuál documento es el vigente.

### Apertura actual

La apertura actual “Serranía” se coordina con método tradicional mediante grupo de WhatsApp:

```text
Apertura Serranía
```

Esta apertura se usará como observación real para detectar problemas, fricciones y necesidades que después se convertirán en lógica del módulo de Aperturas.

### Siguiente apertura objetivo

La siguiente apertura comprometida será:

```text
Egade
```

Estimación:

```text
aproximadamente 1 mes
```

Objetivo:

Para Egade debe existir una versión robusta del módulo de Aperturas, no como copia de Microsoft Project, pero sí suficientemente fuerte para resolver necesidades reales de coordinación, responsables, tareas, fechas, documentos, versiones y cambios.

---

## 3. Principio rector

La Nube Corporativa debe convertirse en la base documental gobernada de Suite Ultra.

No debe ser un basurero de archivos.

Debe ayudar a responder preguntas como:

* ¿Cuál es el plano vigente?
* ¿Quién subió este documento?
* ¿Quién lo publicó?
* ¿Qué versión reemplazó a cuál?
* ¿A qué apertura pertenece?
* ¿A qué tarea está vinculado?
* ¿Qué área es responsable?
* ¿Este documento es global o sensible?
* ¿Quién puede verlo?
* ¿Quién puede descargarlo?
* ¿Está archivado?
* ¿Hay una versión nueva?
* ¿Dónde está la evidencia oficial?
* ¿Puedo revisar el documento sin descargarlo?

---

## 4. Decisiones cerradas F1

### Arquitectura

Todo archivo entra primero al Warehouse.

Después, el Portal Interno crea una publicación documental ligada a ese upload del Warehouse.

### Publicadores iniciales

En F1 solo publican:

* usuario administrador del sistema,
* Sistemas,
* roles administrativos autorizados.

No hay aprobación formal en F1.

### Menú temporalmente restringido

Por ahora, el menú de Nube Corporativa solo se muestra a roles administrativos/Sistemas.

La ruta puede existir, pero no se expone en menú a gerentes para evitar ruido antes de madurar el módulo.

### Versionado

Al reemplazar una versión:

* la versión nueva queda vigente,
* la versión anterior queda oculta para usuarios normales,
* la versión anterior queda trazable para administradores/auditoría,
* no se sobrescribe físicamente el archivo anterior.

### Descarga

El módulo permite descargar documentos autorizados mediante endpoint backend protegido con JWT.

La descarga no expone rutas internas ni paths del servidor.

### Preview

El preview de PDF e imágenes sube de prioridad.

Antes estaba contemplado para F2, pero por el nuevo enfoque hacia Aperturas se considera necesario antes o junto con F1.1.

Motivo:

Aperturas requerirá revisar constantemente:

* planos,
* permisos,
* fotos,
* evidencias,
* contratos,
* cotizaciones,
* checklists,
* manuales,
* documentos escaneados.

Obligar a descargar cada archivo haría que la Nube sea lenta y poco práctica.

### Búsqueda

F1 incluye búsqueda por metadata.

Búsqueda dentro de PDF queda como F2 temprano.

### Auditoría

F1 audita acciones administrativas.

Auditoría de descargas queda como pendiente recomendado para documentos sensibles o F2.

### Almacenamiento

F1 usa volumen persistente del servidor.

No se deben guardar archivos en almacenamiento efímero del contenedor.

---

## 5. Módulo backend actual

Blueprint:

```text
backend/app/routes/internal_documents_routes.py
```

Prefijo:

```text
/api/internal-documents
```

Endpoints actuales:

```text
GET    /api/internal-documents/access
GET    /api/internal-documents/categories
GET    /api/internal-documents
POST   /api/internal-documents
GET    /api/internal-documents/<document_id>
PATCH  /api/internal-documents/<document_id>
POST   /api/internal-documents/<document_id>/publish
POST   /api/internal-documents/<document_id>/archive
GET    /api/internal-documents/<document_id>/versions
POST   /api/internal-documents/<document_id>/versions
PUT    /api/internal-documents/<document_id>/visibility
GET    /api/internal-documents/<document_id>/download
GET    /api/internal-documents/<document_id>/versions/<version_id>/download
GET    /api/internal-documents/<document_id>/audit
```

Archivos backend actuales:

```text
backend/app/models/internal_documents.py
backend/app/routes/internal_documents_routes.py
backend/app/utils/internal_documents_access.py
backend/app/warehouse/services/warehouse_document_upload_service.py
backend/migrations/versions/45cb1ba3f367_add_internal_documents_module.py
backend/migrations/versions/f57edbdac964_add_internal_documents_warehouse_report_.py
```

---

## 6. Módulo frontend actual

Ruta actual:

```text
/#/nube-corporativa
```

Carpeta actual:

```text
frontend/src/app/internal-documents/
```

Estructura actual:

```text
internal-documents/
  internal-documents.routes.ts

  models/
    internal-document.model.ts

  services/
    internal-documents.service.ts

  pages/
    internal-documents-home/
      internal-documents-home.component.ts
      internal-documents-home.component.html
      internal-documents-home.component.css
```

Actualmente la pantalla principal concentra:

* listado,
* filtros básicos,
* creación de borrador,
* selección de archivo,
* publicación,
* visibilidad global,
* descarga,
* archivado,
* reemplazo de versión,
* detalle lateral.

Esto es aceptable para F1, pero para F2 conviene separar:

* vista usuario,
* vista admin,
* detalle,
* modal/formulario de publicación,
* configuración de visibilidad,
* historial/auditoría.

---

## 7. Tablas actuales

## 7.1 `internal_document_categories`

Catálogo controlado de categorías.

Campos:

| Campo       | Tipo conceptual | Regla                     |
| ----------- | --------------- | ------------------------- |
| id          | integer         | PK                        |
| key         | string          | único, ejemplo `REPORTES` |
| name        | string          | nombre visible            |
| description | text            | opcional                  |
| is_active   | boolean         | default true              |
| sort_order  | integer         | orden visual              |
| created_at  | datetime        | automático                |
| updated_at  | datetime        | automático                |

Categorías seed F1:

* REPORTES
* MANUALES
* POLITICAS
* FORMATOS
* PROCEDIMIENTOS
* TUTORIALES

---

## 7.2 `internal_documents`

Documento lógico estable.

Un documento puede tener varias versiones.

Campos actuales:

| Campo               | Tipo conceptual | Regla                                        |
| ------------------- | --------------- | -------------------------------------------- |
| id                  | integer         | PK                                           |
| title               | string          | obligatorio                                  |
| description         | text            | obligatorio para publicar                    |
| category_id         | integer         | FK categoría                                 |
| document_type       | string          | opcional/controlado                          |
| owner_user_id       | integer         | FK users, opcional si hay owner_department   |
| owner_department_id | integer         | FK departamentos, opcional si hay owner_user |
| status              | string          | BORRADOR / PUBLICADO / ARCHIVADO             |
| is_sensitive        | boolean         | default false                                |
| current_version_id  | integer         | FK versión vigente                           |
| visibility_mode     | string          | PRIVATE / CUSTOM / GLOBAL                    |
| published_by        | integer         | FK users                                     |
| published_at        | datetime        | nullable                                     |
| archived_by         | integer         | FK users                                     |
| archived_at         | datetime        | nullable                                     |
| created_by          | integer         | FK users                                     |
| updated_by          | integer         | FK users                                     |
| created_at          | datetime        | automático                                   |
| updated_at          | datetime        | automático                                   |

Reglas actuales:

* `title` obligatorio.
* `category_id` obligatorio.
* `status` obligatorio.
* Para publicar, debe existir al menos una versión.
* Para publicar, debe existir dueño documental.
* Para publicar, debe existir visibilidad configurada.
* Si `is_sensitive = true`, no permitir `GLOBAL`.
* Solo documentos `PUBLICADO` aparecen a usuarios normales.
* Documentos `BORRADOR` solo visibles a creador/admin.
* Documentos `ARCHIVADO` solo visibles a admin/auditoría.

---

## 7.3 `internal_document_versions`

Versiones del documento.

Campos actuales:

| Campo                | Tipo conceptual | Regla                           |
| -------------------- | --------------- | ------------------------------- |
| id                   | integer         | PK                              |
| document_id          | integer         | FK internal_documents           |
| warehouse_upload_id  | integer         | FK Warehouse upload             |
| version_label        | string          | ejemplo `1.0`, `1.1`, `2026-06` |
| version_number       | integer         | secuencial                      |
| original_filename    | string          | snapshot del nombre             |
| file_mime_type       | string          | snapshot                        |
| file_size_bytes      | integer         | snapshot                        |
| file_hash_sha256     | string          | snapshot del hash               |
| change_notes         | text            | requerido al reemplazar versión |
| is_current           | boolean         | solo una true por documento     |
| is_hidden_from_users | boolean         | true para versiones anteriores  |
| created_by           | integer         | FK users                        |
| created_at           | datetime        | automático                      |

Reglas:

* Toda versión debe apuntar a un upload del Warehouse.
* No se debe sobrescribir una versión anterior.
* Solo una versión puede tener `is_current = true`.
* Al crear nueva versión vigente:

  * anterior `is_current = false`,
  * anterior `is_hidden_from_users = true`,
  * nueva `is_current = true`,
  * documento `current_version_id` apunta a nueva versión.

---

## 7.4 `internal_document_visibility`

Reglas de acceso por documento.

Campos actuales:

| Campo           | Tipo conceptual | Regla                                        |
| --------------- | --------------- | -------------------------------------------- |
| id              | integer         | PK                                           |
| document_id     | integer         | FK internal_documents                        |
| visibility_type | string          | ROLE / DEPARTMENT / SUCURSAL / USER / GLOBAL |
| role            | string          | nullable                                     |
| department_id   | integer         | nullable                                     |
| sucursal_id     | integer         | nullable                                     |
| user_id         | integer         | nullable                                     |
| can_view        | boolean         | default true                                 |
| can_download    | boolean         | default true                                 |
| is_active       | boolean         | default true                                 |
| created_by      | integer         | FK users                                     |
| created_at      | datetime        | automático                                   |

Reglas:

* Un documento puede tener múltiples reglas de visibilidad.
* El backend resuelve si el usuario puede ver/descargar.
* Para F1, si puede ver normalmente puede descargar.
* `can_download` queda preparado para evolución.
* Visibilidad default al crear documento: privada.
* `GLOBAL` debe usarse con cuidado.
* `GLOBAL` no está permitido para documentos sensibles.

---

## 7.5 `internal_document_audit_logs`

Auditoría documental.

Campos actuales:

| Campo          | Tipo conceptual | Regla                 |
| -------------- | --------------- | --------------------- |
| id             | integer         | PK                    |
| document_id    | integer         | FK internal_documents |
| version_id     | integer         | FK versión, nullable  |
| actor_user_id  | integer         | FK users              |
| action         | string          | tipo de acción        |
| old_value_json | JSON            | snapshot anterior     |
| new_value_json | JSON            | snapshot nuevo        |
| metadata_json  | JSON            | contexto adicional    |
| ip_address     | string          | opcional              |
| user_agent     | text            | opcional              |
| created_at     | datetime        | automático            |

Acciones actuales:

* DOCUMENT_CREATED
* DOCUMENT_METADATA_UPDATED
* DOCUMENT_PUBLISHED
* DOCUMENT_ARCHIVED
* DOCUMENT_VERSION_CREATED
* DOCUMENT_VERSION_REPLACED
* DOCUMENT_VISIBILITY_UPDATED
* DOCUMENT_SENSITIVITY_UPDATED
* DOCUMENT_OWNER_UPDATED

---

## 8. Warehouse

La Nube Corporativa usa Warehouse como bóveda de archivos.

Report type creado:

```text
internal_documents
```

Configuración:

| Campo               | Valor                |
| ------------------- | -------------------- |
| source              | manual               |
| family              | catalogos_auxiliares |
| operational_role    | CATALOGO_AUXILIAR    |
| default_period_type | diario               |
| active              | true                 |

Extensiones permitidas en Warehouse después de F1:

* xlsx
* xls
* csv
* pdf
* txt
* docx
* pptx
* png
* jpg
* jpeg

Límite Warehouse general:

```text
70 MB
```

Límite funcional de Nube Corporativa:

```text
50 MB
```

---

## 9. Permisos actuales

Roles administradores/documentales:

* ADMIN
* ADMINISTRADOR
* SUPER_ADMIN
* SISTEMAS

Estos roles pueden:

* crear documentos,
* editar metadata,
* publicar,
* archivar,
* reemplazar versión,
* configurar visibilidad,
* ver auditoría,
* descargar versiones históricas.

Usuarios normales:

* no ven borradores,
* no ven archivados,
* no ven versiones históricas ocultas,
* solo ven documentos publicados si tienen visibilidad,
* pueden descargar solo si backend lo permite.

Menú temporal:

* visible solo para ADMIN / ADMINISTRADOR / SUPER_ADMIN / SISTEMAS.
* oculto para gerentes, regionales y usuarios operativos hasta cerrar UX/contrato de uso.

---

## 10. Reglas de seguridad

1. Todo endpoint requiere JWT.
2. El backend valida permisos en cada endpoint.
3. La descarga no sirve archivos por path público.
4. El endpoint de descarga resuelve archivo desde Warehouse.
5. El backend valida visibilidad antes de entregar archivo.
6. El frontend no es fuente de permisos.
7. No se confía en `role` enviado por frontend.
8. Los documentos sensibles requieren permiso explícito.
9. Los documentos borrador no son visibles para usuarios normales.
10. Los documentos archivados no son visibles en biblioteca normal.
11. El servidor no acepta extensiones peligrosas.
12. El servidor valida tamaño máximo.
13. El servidor normaliza nombres de archivo.
14. No se guardan archivos con nombres originales como path final sin sanitización.
15. No se exponen rutas internas del volumen.
16. La visibilidad global no se permite en documentos sensibles.
17. El preview en pantalla debe usar Blob URL autenticado, no URL pública.
18. El preview no debe exponer `stored_path` ni `stored_filename`.

---

## 11. Reglas de validación de archivo

Formatos permitidos F1:

* PDF
* XLSX
* XLS
* CSV
* TXT
* DOCX
* PNG
* JPG
* JPEG
* PPTX

Bloqueados:

* EXE
* MSI
* BAT
* CMD
* JS
* PHP
* SH
* PS1
* VBS
* SCR
* DLL

Límites:

* Nube Corporativa: 50 MB.
* Warehouse general: 70 MB.

Validar:

* extensión,
* tamaño,
* hash,
* nombre sanitizado,
* archivo vacío,
* ruta segura.

MIME type queda registrado, pero no debe ser la única validación.

---

## 12. Preview seguro de documentos

### Decisión

El preview seguro de PDF e imágenes se mueve de F2 a un bloque previo o paralelo a F1.1.

Nombre sugerido:

```text
F1.0.2 — Preview seguro de PDF e imágenes
```

o:

```text
Prerequisite F1.1 — Document Preview
```

### Objetivo

Permitir que el usuario revise documentos en pantalla sin tener que descargarlos siempre.

Debe conservarse también la opción de descargar.

### Formatos con preview inicial

Soportar inicialmente:

* PDF
* PNG
* JPG
* JPEG

No soportar preview inicial para:

* DOCX
* PPTX
* XLSX
* XLS
* CSV
* TXT

Estos formatos siguen disponibles por descarga.

### Arquitectura recomendada

No crear URL pública.

No servir archivos estáticos directamente.

Usar el endpoint actual protegido:

```text
GET /api/internal-documents/<document_id>/download
```

Flujo:

```text
Angular → request con JWT → backend valida permisos → backend devuelve blob → Angular crea ObjectURL temporal → visor en pantalla
```

### UI recomendada

En el detalle del documento mostrar:

```text
[Ver en pantalla] [Descargar]
```

Reglas UI:

* Si el archivo es PDF o imagen: mostrar `Ver en pantalla`.
* Si el archivo no es previsualizable: ocultar `Ver en pantalla` o mostrar mensaje “Este formato solo está disponible para descarga”.
* Mantener botón `Descargar` siempre que tenga permiso.
* Al cerrar preview, liberar el ObjectURL.

### Riesgos técnicos

* Si no se libera el ObjectURL, puede haber fuga de memoria en navegador.
* Si se usa iframe sin sanitizar URL, Angular puede bloquearlo.
* Si se intenta previsualizar Office sin conversión, mala UX.
* Si se exponen rutas públicas, se rompe el modelo de seguridad.
* Si se abre en nueva pestaña sin token, puede fallar.

### Criterios de aceptación del preview

1. Documento PDF se abre en pantalla.
2. Imagen PNG/JPG/JPEG se abre en pantalla.
3. Documento DOCX/PPTX/XLSX no muestra preview inicial.
4. La opción Descargar se mantiene.
5. El backend sigue validando permisos.
6. No se expone path interno.
7. El ObjectURL se limpia al cerrar.
8. El preview funciona después de F5.
9. Usuario sin permiso no puede previsualizar por request directo.
10. No requiere migración.

---

## 13. Brecha principal para Aperturas

La Nube actual ya resuelve:

* publicación,
* versión vigente,
* versiones históricas,
* auditoría,
* visibilidad,
* descarga,
* sensibilidad,
* dueño documental.

Con el preview seguro resolverá también:

* consulta rápida de PDFs,
* consulta rápida de imágenes,
* revisión visual de planos/evidencias/manuales sin descargar.

Pero todavía no resuelve de forma estructurada:

* vincular documento a una apertura,
* vincular documento a una tarea,
* vincular documento a un proyecto,
* vincular documento a una sucursal como contexto operativo,
* marcar documento como principal/oficial dentro de un contexto,
* clasificar rol del documento dentro de una apertura:

  * plano,
  * contrato,
  * permiso,
  * cotización,
  * checklist,
  * evidencia,
  * manual,
  * financiero,
  * construcción,
  * operación.

Por eso el siguiente ajuste estratégico no debe rehacer `internal_documents`.

Debe agregar una capa de vinculación.

---

## 14. Propuesta F1.1 real: documentos vinculables

### Objetivo

Permitir que un documento publicado o en borrador pueda vincularse a entidades futuras o existentes sin amarrar todavía la Nube al módulo completo de Aperturas.

### Tabla propuesta

```text
internal_document_links
```

### Campos conceptuales

| Campo       | Tipo conceptual | Regla                                                       |
| ----------- | --------------- | ----------------------------------------------------------- |
| id          | integer         | PK                                                          |
| document_id | integer         | FK internal_documents                                       |
| entity_type | string          | PROJECT / OPENING / TASK / SUCURSAL / DEPARTMENT / GENERAL  |
| entity_id   | integer         | nullable, cuando exista entidad formal                      |
| entity_key  | string          | nullable, ejemplo `EGADE`, `SERRANIA`, `SUCURSAL_12`        |
| link_role   | string          | PLANO / PERMISO / CONTRATO / CHECKLIST / EVIDENCIA / MANUAL |
| label       | string          | nombre visible opcional                                     |
| is_primary  | boolean         | marca documento principal/oficial en ese contexto           |
| is_active   | boolean         | default true                                                |
| created_by  | integer         | FK users                                                    |
| created_at  | datetime        | automático                                                  |
| updated_at  | datetime        | automático                                                  |

### Ejemplos

Documento vinculado a apertura futura:

```text
document_id: 15
entity_type: OPENING
entity_key: EGADE
link_role: PLANO
is_primary: true
```

Documento vinculado a tarea futura:

```text
document_id: 22
entity_type: TASK
entity_key: EGADE-ELECTRICO-001
link_role: EVIDENCIA
is_primary: false
```

Documento vinculado a sucursal:

```text
document_id: 30
entity_type: SUCURSAL
entity_id: 12
entity_key: INSURGENTES
link_role: CONTRATO
is_primary: true
```

### Ventaja

Esta tabla permite preparar la base documental para Aperturas sin construir todavía:

* tabla de aperturas,
* tabla de tareas,
* Gantt,
* dependencias,
* notificaciones,
* responsables por tarea.

Cuando existan esas tablas, `entity_id` podrá apuntar a registros reales o se podrá migrar a FKs específicas.

---

## 15. Metadata útil para Aperturas

La metadata actual cubre:

| Requisito               | Estado actual                        |
| ----------------------- | ------------------------------------ |
| título                  | cubierto                             |
| descripción             | cubierto                             |
| categoría               | cubierto                             |
| área/departamento       | parcialmente cubierto por owner      |
| sucursal                | cubierto en visibilidad, no contexto |
| alcance                 | no cubierto formalmente              |
| propietario/responsable | parcialmente cubierto por owner      |
| estado                  | cubierto                             |
| vigencia                | no cubierto                          |
| versión                 | cubierto                             |
| fecha publicación       | cubierto                             |
| archivo asociado        | cubierto vía Warehouse               |
| usuario que subió       | cubierto en Warehouse/version        |
| usuario que publicó     | cubierto                             |
| proyecto/apertura       | no cubierto                          |
| tarea vinculada         | no cubierto                          |
| preview                 | pendiente F1.0.2                     |

### Ajuste mínimo recomendado

No agregar todas estas columnas directo a `internal_documents`.

Orden recomendado:

1. Agregar preview seguro para PDF/imágenes.
2. Agregar `internal_document_links`.
3. Dejar para F2:

   * vigencia,
   * vencimiento,
   * revisión periódica,
   * responsable operativo distinto al dueño documental,
   * aprobación documental,
   * firma de recibido.

---

## 16. Estados documentales

Estados actuales:

* BORRADOR
* PUBLICADO
* ARCHIVADO

### Sobre REEMPLAZADO

No se recomienda agregar `REEMPLAZADO` todavía como estado de documento.

Motivo:

* el reemplazo actual ocurre a nivel de versión,
* una versión anterior ya queda `is_current = false`,
* una versión anterior ya queda `is_hidden_from_users = true`,
* el documento lógico sigue vivo.

Si en el futuro un documento completo reemplaza a otro documento completo, conviene manejarlo con una relación nueva:

```text
internal_document_replacements
```

o un campo:

```text
replaced_by_document_id
```

No hacerlo en F1.1.

---

## 17. Riesgos

### Riesgo 1: que se vuelva basurero documental

Mitigación:

* metadata obligatoria,
* dueño documental,
* categoría,
* tipo documental,
* visibilidad,
* vínculos contextuales,
* auditoría,
* filtros,
* eventualmente vigencia/revisión.

### Riesgo 2: documentos duplicados

Mitigación actual:

* hash en Warehouse,
* versiones lógicas,
* auditoría.

Pendiente:

* alertar si se sube archivo duplicado,
* sugerir reemplazar versión en lugar de crear documento nuevo,
* usar `is_primary` por contexto para evitar múltiples “oficiales”.

### Riesgo 3: no saber cuál es vigente

Mitigación actual:

* `current_version_id`,
* `is_current`,
* `version_number`,
* `version_label`.

Pendiente F1.1/F2:

* `is_primary` en vínculo contextual,
* indicadores visuales de “oficial/vigente”.

### Riesgo 4: exponer información sensible

Mitigación actual:

* `is_sensitive`,
* bloqueo de GLOBAL sensible,
* permisos backend.

Pendiente:

* UI más clara para documentos sensibles,
* auditoría de descargas,
* reglas custom más amigables.

### Riesgo 5: amarrar la Nube a Aperturas demasiado pronto

Mitigación:

* usar tabla genérica `internal_document_links`,
* no meter `opening_id` directo en `internal_documents`,
* no crear lógica de tareas hasta que exista contrato de Aperturas.

### Riesgo 6: mezclar Warehouse con portal público

Mitigación actual:

* Warehouse guarda archivo,
* Nube publica documento lógico,
* usuario nunca ve path interno,
* descarga pasa por backend.

### Riesgo 7: preview inseguro

Mitigación:

* no exponer rutas públicas,
* usar blob autenticado,
* backend valida permisos,
* limpiar ObjectURL al cerrar,
* no usar URLs internas del servidor en HTML.

---

## 18. Pendientes UX detectados en producción

Pendientes inmediatos ya detectados:

1. Ocultar botón “Global” cuando el documento ya tiene `visibility_mode = GLOBAL`.
2. Ocultar botón “Global” para documentos sensibles.
3. Corregir descarga para conservar extensión original del archivo.
4. Formatear `published_at`, `created_at`, `updated_at` en UI.
5. Cambiar `Owner user id` y `Owner department id` por selector o autollenado.
6. Hacer formulario de creación colapsable.
7. Separar vista admin y vista usuario.
8. Mejorar etiqueta del botón “Global” a “Hacer visible globalmente”.
9. Mostrar mejor el estado “Sensible”.
10. Agregar confirmación visual al publicar.
11. Agregar preview en pantalla para PDF e imágenes.

### Bug conocido: descarga sin extensión

Problema:

El frontend construía fallback de descarga con:

```text
document.title + version
```

Eso podía perder `.pdf`, `.docx`, etc.

Solución recomendada:

Usar primero:

```text
document.current_version.original_filename
```

Si no existe, construir fallback con extensión por MIME type.

---

## 19. Pantallas Angular objetivo

## 19.1 Home — Nube Corporativa

Ruta:

```text
/#/nube-corporativa
```

Elementos objetivo:

* buscador principal,
* tarjetas por categoría,
* últimos publicados,
* accesos rápidos,
* vista limpia para usuario final,
* sin formulario admin visible por defecto.

## 19.2 Lista de documentos

Elementos:

* tabla/lista,
* filtros:

  * categoría,
  * área/dueño,
  * estado si admin,
  * sensible si admin,
  * fecha publicación,
  * vínculo futuro a apertura/proyecto,
* acciones:

  * ver detalle,
  * ver en pantalla si aplica,
  * descargar,
  * editar si admin,
  * archivar si admin.

Columnas:

* título,
* categoría,
* dueño,
* versión,
* fecha publicación,
* estado,
* sensible,
* vínculo/contexto,
* acciones.

## 19.3 Detalle de documento

Elementos:

* metadata,
* descripción,
* categoría,
* dueño documental,
* versión vigente,
* fecha de publicación,
* estado,
* sensibilidad,
* vínculos contextuales,
* botón ver en pantalla,
* botón descargar,
* historial básico si admin.

## 19.4 Admin de documentos

Ruta futura:

```text
/#/nube-corporativa/admin
```

Elementos:

* listado admin,
* crear documento,
* subir archivo,
* editar metadata,
* configurar visibilidad,
* publicar,
* archivar,
* reemplazar versión,
* ver auditoría,
* administrar vínculos contextuales.

---

## 20. Servicio Angular actual

Servicio:

```text
frontend/src/app/internal-documents/services/internal-documents.service.ts
```

Métodos actuales:

* `getAccess()`
* `getCategories()`
* `listDocuments(filters)`
* `getDocument(id)`
* `createDocument(payload)`
* `updateDocument(id, payload)`
* `publishDocument(id)`
* `archiveDocument(id)`
* `replaceVersion(id, payload)`
* `getVersions(id)`
* `downloadCurrentDocument(id)`
* `downloadHistoricalVersion(id, versionId)`
* `updateVisibility(id, payload)`
* `getAudit(id)`
* `triggerBrowserDownload(response, fallbackName)`

Métodos recomendados F1.0.2 Preview:

* `openPreview(document)`
* `closePreview()`
* `canPreviewDocument(document)`
* `resolvePreviewType(document)`
* `createPreviewObjectUrl(response)`
* `revokePreviewObjectUrl()`

Estos métodos deben vivir en `.ts`, no en HTML.

Métodos futuros F1.1:

* `getDocumentLinks(documentId)`
* `upsertDocumentLink(documentId, payload)`
* `deleteDocumentLink(documentId, linkId)`
* `listDocumentsByEntity(entityType, entityKey/entityId)`

---

## 21. Respuestas API recomendadas

Cada documento listado debe incluir capacidades calculadas por backend:

```text
capabilities:
- can_view
- can_download
- can_edit
- can_publish
- can_archive
- can_replace_version
- can_manage_visibility
- can_view_audit
- can_download_historical_versions
```

Esto ya existe.

Para F1.1 se agregaría:

```text
links:
- id
- entity_type
- entity_id
- entity_key
- link_role
- label
- is_primary
- is_active
```

El frontend puede ocultar botones con capacidades, pero el backend debe volver a validar al ejecutar la acción.

---

## 22. Flujo funcional actual F1

## 22.1 Crear borrador

1. Admin entra a Nube Corporativa.
2. Sube archivo.
3. Completa metadata mínima.
4. Backend guarda archivo en Warehouse.
5. Backend crea documento en BORRADOR.
6. Backend crea versión 1.
7. Backend audita.

## 22.2 Configurar visibilidad

1. Admin selecciona documento.
2. Define alcance:

   * global,
   * rol,
   * departamento,
   * sucursal,
   * usuario específico.
3. Backend guarda reglas.
4. Backend audita.

## 22.3 Publicar

1. Admin presiona publicar.
2. Backend valida metadata, dueño, versión y visibilidad.
3. Backend cambia estado a PUBLICADO.
4. Documento aparece a usuarios autorizados.

## 22.4 Descargar

1. Usuario autorizado entra a biblioteca.
2. Backend devuelve solo documentos autorizados.
3. Usuario abre detalle.
4. Usuario descarga.
5. Backend valida permiso.
6. Backend entrega archivo sin exponer ruta real.

## 22.5 Ver en pantalla

1. Usuario autorizado abre documento.
2. Frontend valida si el formato es previsualizable.
3. Si es PDF/imagen, muestra botón `Ver en pantalla`.
4. Frontend solicita archivo al endpoint protegido.
5. Backend valida permisos y entrega blob.
6. Frontend crea ObjectURL temporal.
7. Frontend muestra PDF/imagen en pantalla.
8. Al cerrar, frontend libera ObjectURL.

## 22.6 Reemplazar versión

1. Admin abre documento.
2. Sube nuevo archivo.
3. Agrega etiqueta de versión y notas de cambio.
4. Backend guarda archivo en Warehouse.
5. Backend oculta versión anterior.
6. Backend marca nueva versión como vigente.
7. Backend audita.

## 22.7 Archivar

1. Admin archiva documento.
2. Backend cambia estado a ARCHIVADO.
3. Documento desaparece de biblioteca normal.
4. Historial queda disponible para admin.

---

## 23. Flujo futuro F1.1: vincular documento a apertura

1. Admin crea o selecciona documento.
2. Admin abre sección “Vinculación”.
3. Selecciona tipo de entidad:

```text
OPENING
```

4. Selecciona o captura clave:

```text
EGADE
```

5. Selecciona rol del documento:

```text
PLANO
```

6. Marca si es principal/oficial:

```text
is_primary = true
```

7. Backend crea `internal_document_links`.
8. Backend audita.
9. Futuro módulo de Aperturas podrá consultar documentos por apertura.

---

## 24. Checklist QA actual F1

## 24.1 Seguridad

* Usuario sin token no accede.
* Usuario no autorizado no ve documento.
* Usuario no autorizado no descarga por URL directa.
* Usuario autorizado sí descarga.
* Usuario normal no ve borradores.
* Usuario normal no ve archivados.
* Usuario normal no ve versiones ocultas.
* Documento sensible no se publica globalmente.
* Frontend oculta botones, pero backend bloquea aunque se fuerce request.
* Menú oculto a gerentes mientras el módulo está en beta.

## 24.2 Versionado

* Crear primera versión funciona.
* Reemplazar versión crea nuevo registro.
* Versión anterior queda no vigente.
* Versión anterior queda oculta para usuario normal.
* Admin puede ver historial.
* Documento apunta a versión vigente correcta.

## 24.3 Warehouse

* Archivo se registra en Warehouse.
* Archivo tiene hash.
* Archivo queda en volumen persistente.
* Portal guarda referencia a `warehouse_upload_id`.
* Descarga resuelve desde Warehouse.
* Archivo sobrevive reinicio/rebuild.

## 24.4 Auditoría

* Crear documento audita.
* Editar metadata audita.
* Publicar audita.
* Archivar audita.
* Reemplazar versión audita.
* Cambiar visibilidad audita.
* Cambiar sensibilidad audita.

## 24.5 Frontend

* Lista carga documentos autorizados.
* Filtros funcionan.
* Buscador por metadata funciona.
* Detalle muestra metadata correcta.
* Botón descargar funciona.
* Preview PDF funciona.
* Preview imagen funciona.
* Botones admin solo aparecen si hay permisos.
* F5 en ruta hash mantiene pantalla correcta.
* Responsive básico funciona.

---

## 25. QA pendiente inmediato en producción

Antes de abrirlo a más usuarios, validar:

1. Usuario no admin:

   * no ve menú,
   * si accede manualmente, backend no expone acciones admin,
   * no ve borradores,
   * no ve archivados.

2. Documento sensible:

   * crear sensible,
   * intentar hacerlo global,
   * backend debe rechazar.

3. Persistencia:

   * reiniciar backend/frontend,
   * descargar documento publicado,
   * confirmar que el archivo sigue disponible.

4. Descarga:

   * confirmar que conserva extensión,
   * confirmar que Windows reconoce el archivo.

5. Preview:

   * abrir PDF en pantalla,
   * abrir imagen en pantalla,
   * confirmar que Office docs siguen solo por descarga,
   * confirmar que al cerrar se libera el visor.

---

## 26. Orden recomendado de siguientes trabajos

## F1.0.2 — Preview seguro de PDF e imágenes

Rama sugerida:

```text
feature/internal-documents-preview
```

Incluye:

* botón `Ver en pantalla`,
* visor PDF,
* visor imagen,
* mantener botón Descargar,
* ObjectURL temporal,
* limpieza de ObjectURL al cerrar,
* mensaje para formato no previsualizable.

No requiere migración.

No debería requerir backend.

## Hotfix UX adicional

Rama sugerida:

```text
hotfix/internal-documents-ux-polish
```

Incluye:

* ocultar botón Global cuando ya está en GLOBAL,
* ocultar botón Global si documento sensible,
* corregir nombre de descarga con extensión original,
* formatear fecha publicada.

No requiere migración.

## F1.1 — Documentos vinculables

Rama sugerida:

```text
feature/f1-1-internal-document-links
```

Incluye:

* modelo `InternalDocumentLinkORM`,
* migración Alembic,
* endpoints para listar/crear/desactivar vínculos,
* serializer de vínculos,
* UI mínima admin para capturar vínculo,
* filtros por entity_type/entity_key,
* auditoría de vínculos.

## F2 — Nube Corporativa madura

Incluye:

* búsqueda dentro de PDF,
* auditoría de descargas,
* preview Office vía conversión o servicio externo si aplica,
* documentos destacados,
* vigencias y alertas,
* publicación automática de reportes confiables,
* responsables por área,
* aprobación documental,
* firma de recibido,
* selector de dueños,
* reglas de visibilidad amigables,
* separación UI admin/usuario.

## Aperturas — Módulo separado

Debe construirse después de cerrar F1.1 documental.

Incluirá:

* apertura,
* tareas,
* responsables,
* fechas,
* dependencias,
* cambios,
* historial,
* documentos vinculados,
* notificaciones,
* vista tipo Gantt simplificada,
* tablero de avance,
* control por área.

---

## 27. Criterio de cierre F1

F1 se considera cerrada cuando:

1. Un admin sube un archivo y este entra al Warehouse.
2. El Portal crea documento ligado a ese archivo.
3. El documento nace como borrador.
4. El admin puede configurar metadata.
5. El admin puede configurar visibilidad.
6. El admin puede publicar.
7. El usuario autorizado lo ve.
8. El usuario autorizado lo descarga.
9. El usuario no autorizado no lo ve.
10. El usuario no autorizado no lo descarga por URL directa.
11. El admin puede reemplazar versión.
12. La versión anterior queda oculta y trazable.
13. El admin puede archivar.
14. Todo cambio administrativo queda auditado.
15. Los archivos sobreviven reinicio/rebuild por volumen persistente.
16. No se exponen rutas internas ni Warehouse al usuario final.
17. El menú queda controlado para evitar exposición prematura.

Estado:

```text
F1 funcional en producción.
Pendiente QA final por roles.
```

---

## 28. Criterio de cierre F1.0.2 Preview

F1.0.2 se puede cerrar cuando:

1. Documento PDF se puede ver en pantalla.
2. Imagen PNG/JPG/JPEG se puede ver en pantalla.
3. Opción Descargar sigue disponible.
4. Office docs no intentan preview inicial.
5. El preview usa endpoint autenticado.
6. No se exponen rutas internas.
7. El ObjectURL se limpia al cerrar.
8. Usuario no autorizado no puede previsualizar.
9. Build frontend pasa.
10. No requiere migración.
11. No rompe flujo actual de descarga.

---

## 29. Criterio de cierre F1.1

F1.1 se puede cerrar cuando:

1. Existe tabla de vínculos documentales.
2. Un documento puede vincularse a una entidad genérica.
3. Se soportan al menos estos `entity_type`:

```text
OPENING
PROJECT
TASK
SUCURSAL
DEPARTMENT
GENERAL
```

4. Se soportan al menos estos `link_role`:

```text
PLANO
PERMISO
CONTRATO
COTIZACION
CHECKLIST
EVIDENCIA
MANUAL
FINANCIERO
CONSTRUCCION
OPERACION
OTRO
```

5. Se puede marcar un documento como principal/oficial en un contexto.
6. Se puede consultar documentos por `entity_type` + `entity_key`.
7. La UI permite ver vínculos básicos.
8. El backend valida permisos.
9. Los cambios de vínculos se auditan.
10. No se rompe el flujo actual de F1.
11. No se crean dependencias directas prematuras con tablas de Aperturas que aún no existen.

---

## 30. Pendientes para F2

* Búsqueda dentro de PDFs.
* Auditoría de descargas.
* Destacados.
* Vigencias y alertas.
* Publicación automática de reportes confiables.
* Responsables por área.
* Aprobación documental.
* Firma de recibido.
* Preview Office vía conversión si aplica.
* Integración con notificaciones.
* Dashboard de documentos vencidos/no revisados.
* Selector de usuarios/departamentos/sucursales.
* Visibilidad avanzada por proyecto/apertura.
* Relación formal con módulo de Aperturas.
* Migración futura a S3/R2/MinIO si el volumen crece.
