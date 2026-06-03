# Suite Ultra — Contrato Técnico F1.1

## Nube Corporativa / Portal Interno de Documentos Publicados

### Sin código — listo para implementación por fases

## 1. Objetivo técnico

Construir un módulo interno para publicar documentos corporativos dentro de Suite Ultra, usando el Warehouse como bóveda de archivos y trazabilidad, y una capa separada de publicación para usuarios finales.

La Nube Corporativa no debe comportarse como Google Drive. Debe funcionar como un sistema documental gobernado con:

* metadata obligatoria,
* dueño documental,
* estado documental,
* versión vigente,
* versiones históricas ocultas pero trazables,
* permisos backend,
* auditoría,
* descarga segura,
* búsqueda y filtros básicos.

## 2. Decisiones cerradas F1.1

### Arquitectura

Todo archivo entra primero al Warehouse.

Después, el Portal Interno crea una publicación documental ligada a ese upload del Warehouse.

### Publicadores iniciales

En F1 solo publican:

* usuario administrador del sistema,
* Sistemas,
* roles administrativos autorizados.

No hay aprobación formal en F1.

### Versionado

Al reemplazar una versión:

* la versión nueva queda vigente,
* la versión anterior queda oculta para usuarios normales,
* la versión anterior queda trazable para administradores/auditoría,
* no se sobrescribe físicamente el archivo anterior.

### Búsqueda

F1 incluye búsqueda por metadata.

Búsqueda dentro de PDF queda como F1.1 extendido o F2 temprano.

### Auditoría

F1 audita acciones administrativas.

Auditoría de descargas se recomienda dejar lista para documentos sensibles o F2.

### Almacenamiento

F1 usa volumen persistente del servidor.

No se deben guardar archivos en almacenamiento efímero del contenedor.

## 3. Módulo backend sugerido

Crear un blueprint nuevo:

`backend/app/routes/internal_documents_routes.py`

Prefijo sugerido:

`/api/internal-documents`

También puede llamarse:

`/api/corporate-cloud`

Pero para claridad técnica se recomienda:

`/api/internal-documents`

## 4. Módulo frontend sugerido

Ruta de usuario:

`/#/nube-corporativa`

Ruta admin:

`/#/nube-corporativa/admin`

Carpeta sugerida:

`frontend/src/app/internal-documents/`

Componentes separados:

```text
internal-documents/
  internal-documents.routes.ts

  pages/
    internal-documents-home/
      internal-documents-home.component.ts
      internal-documents-home.component.html
      internal-documents-home.component.css

    internal-documents-list/
      internal-documents-list.component.ts
      internal-documents-list.component.html
      internal-documents-list.component.css

    internal-document-detail/
      internal-document-detail.component.ts
      internal-document-detail.component.html
      internal-document-detail.component.css

    internal-documents-admin/
      internal-documents-admin.component.ts
      internal-documents-admin.component.html
      internal-documents-admin.component.css

  services/
    internal-documents.service.ts

  models/
    internal-document.model.ts
```

Regla permanente:

* lógica en `.ts`,
* HTML solo estructura, bindings simples y llamadas a métodos existentes,
* no templates inline,
* no estilos inline.

## 5. Tablas propuestas

## 5.1 `internal_document_categories`

Catálogo controlado de categorías.

Campos conceptuales:

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

## 5.2 `internal_documents`

Documento lógico estable.

Un documento puede tener varias versiones.

Campos conceptuales:

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

Reglas:

* `title` obligatorio.
* `category_id` obligatorio.
* `status` obligatorio.
* `created_by` obligatorio.
* Para publicar, debe existir al menos una versión.
* Para publicar, debe existir dueño documental.
* Para publicar, debe existir visibilidad configurada.
* Si `is_sensitive = true`, no permitir `GLOBAL` abierto sin permiso especial.
* Solo documentos `PUBLICADO` aparecen a usuarios normales.
* Documentos `BORRADOR` solo visibles a creador/admin.
* Documentos `ARCHIVADO` solo visibles a admin/auditoría.

## 5.3 `internal_document_versions`

Versiones del documento.

Campos conceptuales:

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

## 5.4 `internal_document_visibility`

Reglas de acceso por documento.

Campos conceptuales:

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
* El backend debe resolver si el usuario puede ver/descargar.
* Para F1, si puede ver, puede descargar.
* `can_download` queda preparado para evolución.
* Visibilidad default al crear documento: privada para creador/admin.
* `GLOBAL` debe usarse con cuidado.
* `GLOBAL` no debe estar permitido para documentos sensibles salvo permiso especial.

## 5.5 `internal_document_audit_logs`

Auditoría documental.

Campos conceptuales:

| Campo          | Tipo conceptual | Regla                 |
| -------------- | --------------- | --------------------- |
| id             | integer         | PK                    |
| document_id    | integer         | FK internal_documents |
| version_id     | integer         | nullable              |
| actor_user_id  | integer         | FK users              |
| action         | string          | acción auditada       |
| old_value_json | json            | nullable              |
| new_value_json | json            | nullable              |
| metadata_json  | json            | nullable              |
| ip_address     | string          | opcional              |
| user_agent     | string          | opcional              |
| created_at     | datetime        | automático            |

Acciones F1:

* DOCUMENT_CREATED
* DOCUMENT_METADATA_UPDATED
* DOCUMENT_PUBLISHED
* DOCUMENT_ARCHIVED
* DOCUMENT_VERSION_CREATED
* DOCUMENT_VERSION_REPLACED
* DOCUMENT_VISIBILITY_UPDATED
* DOCUMENT_SENSITIVITY_UPDATED
* DOCUMENT_OWNER_UPDATED

Acciones F2 posibles:

* DOCUMENT_DOWNLOADED
* DOCUMENT_VIEWED
* DOCUMENT_ACCESS_DENIED

## 6. Relación con Warehouse

F1 debe reutilizar o extender la infraestructura de Warehouse.

Flujo de subida:

1. Usuario admin sube archivo desde Nube Corporativa.
2. Backend valida permiso.
3. Backend valida extensión, MIME type y tamaño.
4. Backend registra archivo en Warehouse.
5. Warehouse guarda archivo en volumen persistente.
6. Warehouse calcula hash.
7. Backend crea `internal_document_versions`.
8. Backend crea o actualiza `internal_documents`.
9. Backend audita acción.

Regla importante:

El Portal no debe guardar archivos propios desligados del Warehouse.

Debe guardar referencia a:

`warehouse_upload_id`

## 7. Endpoints backend propuestos

## 7.1 Categorías

### `GET /api/internal-documents/categories`

Lista categorías activas.

Permiso:

* usuario autenticado.

Respuesta conceptual:

* id
* key
* name
* description
* sort_order

## 7.2 Listar documentos visibles

### `GET /api/internal-documents`

Lista documentos visibles para el usuario autenticado.

Filtros query:

* `q`
* `category_id`
* `status`
* `owner_department_id`
* `is_sensitive`
* `published_from`
* `published_to`
* `page`
* `page_size`

Reglas:

* Usuario normal solo ve `PUBLICADO`.
* Admin puede ver `BORRADOR`, `PUBLICADO`, `ARCHIVADO`.
* Backend aplica permisos de visibilidad.
* No confiar en filtros frontend.

## 7.3 Detalle de documento

### `GET /api/internal-documents/:id`

Devuelve metadata del documento.

Reglas:

* Validar permiso `can_view`.
* Usuario normal solo ve versión vigente.
* Admin puede ver historial básico de versiones.

## 7.4 Crear documento con archivo

### `POST /api/internal-documents`

Crea documento y primera versión.

Payload multipart conceptual:

* file
* title
* description
* category_id
* owner_user_id
* owner_department_id
* is_sensitive
* version_label
* visibility rules opcionales

Reglas:

* Requiere permiso admin/publicador.
* Archivo entra primero a Warehouse.
* Documento nace en `BORRADOR`.
* Visibilidad default privada.
* Auditar `DOCUMENT_CREATED` y `DOCUMENT_VERSION_CREATED`.

## 7.5 Editar metadata

### `PATCH /api/internal-documents/:id`

Permite editar:

* title
* description
* category_id
* owner_user_id
* owner_department_id
* is_sensitive

Reglas:

* Requiere permiso admin/publicador.
* Auditar cambios.
* No cambiar archivo desde este endpoint.

## 7.6 Publicar documento

### `POST /api/internal-documents/:id/publish`

Publica documento.

Reglas:

Antes de publicar validar:

* tiene título,
* tiene descripción,
* tiene categoría,
* tiene dueño documental,
* tiene versión vigente,
* tiene visibilidad configurada,
* si es sensible, no tiene visibilidad global abierta sin permiso.

Efecto:

* status = PUBLICADO
* published_by = usuario actual
* published_at = now
* auditar DOCUMENT_PUBLISHED

## 7.7 Archivar documento

### `POST /api/internal-documents/:id/archive`

Archiva documento.

Reglas:

* No borra archivo.
* No borra versiones.
* Deja de aparecer en biblioteca normal.
* Auditar DOCUMENT_ARCHIVED.

## 7.8 Reemplazar versión

### `POST /api/internal-documents/:id/versions`

Sube nueva versión.

Payload multipart conceptual:

* file
* version_label
* change_notes

Reglas:

* Requiere permiso admin/publicador.
* Archivo entra primero a Warehouse.
* Versión anterior queda oculta para usuarios normales.
* Nueva versión queda vigente.
* Auditar DOCUMENT_VERSION_REPLACED.

## 7.9 Listar versiones

### `GET /api/internal-documents/:id/versions`

Reglas:

* Admin ve todas.
* Usuario normal no ve versiones ocultas.
* Usuario normal puede ver solo versión vigente si tiene permiso al documento.

## 7.10 Descargar versión vigente

### `GET /api/internal-documents/:id/download`

Reglas:

* Validar `can_download`.
* Validar documento publicado, salvo admin.
* Descargar versión vigente.
* No exponer path real del servidor.
* No permitir acceso directo por URL pública al archivo.
* Opcional F1: auditar solo si `is_sensitive = true`.
* F2: auditar todas las descargas.

## 7.11 Descargar versión específica admin

### `GET /api/internal-documents/:id/versions/:version_id/download`

Reglas:

* Solo admin/publicador/auditor.
* Permite descargar versión histórica.
* Auditar si documento sensible.

## 7.12 Actualizar visibilidad

### `PUT /api/internal-documents/:id/visibility`

Payload conceptual:

Lista de reglas:

* visibility_type
* role
* department_id
* sucursal_id
* user_id
* can_view
* can_download

Reglas:

* Requiere permiso admin/publicador.
* Reemplaza o actualiza reglas activas.
* Auditar DOCUMENT_VISIBILITY_UPDATED.
* Si documento sensible, bloquear GLOBAL salvo permiso especial.

## 7.13 Auditoría de documento

### `GET /api/internal-documents/:id/audit`

Reglas:

* Solo admin/publicador/auditor.
* Devuelve historial de acciones administrativas.

## 8. Permisos backend

## 8.1 Permisos conceptuales

Permisos necesarios:

* `internal_documents.view`
* `internal_documents.download`
* `internal_documents.upload`
* `internal_documents.create`
* `internal_documents.edit`
* `internal_documents.publish`
* `internal_documents.archive`
* `internal_documents.replace_version`
* `internal_documents.manage_visibility`
* `internal_documents.view_sensitive`
* `internal_documents.view_audit`
* `internal_documents.download_historical_versions`

## 8.2 Roles iniciales sugeridos

F1 puede mapear contra roles existentes.

Roles con administración completa:

* ADMIN
* ADMINISTRADOR
* SUPER_ADMIN
* SISTEMAS

Roles con lectura según visibilidad:

* GERENTE
* GERENTE_REGIONAL
* LECTOR_GLOBAL
* GERENCIA_DEPORTIVA
* otros roles autenticados según reglas del documento

Regla:

No basta con rol. También se evalúa visibilidad del documento.

## 8.3 Matriz F1

| Acción                             | Admin/Sistemas |          Publicador | Usuario autorizado | Usuario no autorizado |
| ---------------------------------- | -------------: | ------------------: | -----------------: | --------------------: |
| Ver biblioteca                     |             Sí |                  Sí |                 Sí |                    No |
| Ver documento publicado autorizado |             Sí |                  Sí |                 Sí |                    No |
| Descargar documento autorizado     |             Sí |                  Sí |                 Sí |                    No |
| Ver borradores                     |             Sí |   Sí, si es creador |                 No |                    No |
| Subir documento                    |             Sí |                  Sí |                 No |                    No |
| Editar metadata                    |             Sí |                  Sí |                 No |                    No |
| Publicar                           |             Sí |                  Sí |                 No |                    No |
| Archivar                           |             Sí |                  Sí |                 No |                    No |
| Reemplazar versión                 |             Sí |                  Sí |                 No |                    No |
| Ver versiones históricas           |             Sí |                  Sí |                 No |                    No |
| Ver auditoría                      |             Sí |            Opcional |                 No |                    No |
| Ver sensible                       |             Sí | Sí si tiene permiso | Solo si autorizado |                    No |

## 9. Reglas de seguridad

1. Todo endpoint requiere JWT.
2. El backend valida permisos en cada endpoint.
3. La descarga no debe servir archivos por path público.
4. El endpoint de descarga debe resolver archivo desde Warehouse.
5. El backend debe validar visibilidad antes de entregar archivo.
6. El frontend no debe ser fuente de permisos.
7. No se debe confiar en `role` enviado por frontend.
8. Los documentos sensibles requieren permiso explícito.
9. Los documentos borrador no son visibles para usuarios normales.
10. Los documentos archivados no son visibles en biblioteca normal.
11. El servidor no debe aceptar extensiones peligrosas.
12. El servidor debe validar tamaño máximo.
13. El servidor debe normalizar nombres de archivo.
14. No guardar archivos con nombres originales como path final sin sanitización.
15. No exponer rutas internas del volumen.

## 10. Reglas de validación de archivo

Formatos permitidos F1:

* PDF
* XLSX
* CSV
* DOCX
* PNG
* JPG
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

* documentos normales: 25 MB
* reportes Excel pesados: 50 MB
* mayor a 50 MB requiere decisión posterior

Validar:

* extensión,
* MIME type,
* tamaño,
* hash,
* nombre sanitizado.

## 11. Pantallas Angular F1

## 11.1 Home — Nube Corporativa

Ruta:

`/#/nube-corporativa`

Elementos:

* buscador principal,
* tarjetas por categoría,
* últimos publicados,
* accesos rápidos,
* botón admin si tiene permiso.

## 11.2 Lista de documentos

Elementos:

* tabla/lista,
* filtros:

  * categoría,
  * área/dueño,
  * estado si admin,
  * sensible si admin,
  * fecha publicación,
* acciones:

  * ver detalle,
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
* acciones.

## 11.3 Detalle de documento

Elementos:

* metadata,
* descripción,
* categoría,
* dueño documental,
* versión vigente,
* fecha de publicación,
* estado,
* sensibilidad,
* botón descargar,
* historial básico si admin.

## 11.4 Admin de documentos

Ruta:

`/#/nube-corporativa/admin`

Elementos:

* listado admin,
* crear documento,
* subir archivo,
* editar metadata,
* configurar visibilidad,
* publicar,
* archivar,
* reemplazar versión,
* ver auditoría.

## 12. Servicio Angular

Servicio sugerido:

`internal-documents.service.ts`

Métodos conceptuales:

* `getCategories()`
* `listDocuments(filters)`
* `getDocument(id)`
* `createDocument(payload)`
* `updateDocument(id, payload)`
* `publishDocument(id)`
* `archiveDocument(id)`
* `replaceVersion(id, payload)`
* `getVersions(id)`
* `downloadDocument(id)`
* `updateVisibility(id, payload)`
* `getAudit(id)`

Reglas:

* Usar `environment.apiUrl`.
* No hardcodear URLs.
* No mezclar lógica de permisos compleja en HTML.
* Las capacidades de UI deben venir idealmente del backend o de métodos del componente.

## 13. Respuestas API recomendadas

Cada documento listado debe incluir capacidades calculadas por backend:

```text
permissions/capabilities:
- can_view
- can_download
- can_edit
- can_publish
- can_archive
- can_replace_version
- can_manage_visibility
- can_view_audit
```

Esto evita duplicar demasiada lógica en Angular.

El frontend puede ocultar botones con esas capacidades, pero el backend debe volver a validar al ejecutar la acción.

## 14. Flujo funcional F1

## 14.1 Crear borrador

1. Admin entra a Nube Corporativa Admin.
2. Sube archivo.
3. Completa metadata mínima.
4. Backend guarda archivo en Warehouse.
5. Backend crea documento en BORRADOR.
6. Backend crea versión 1.
7. Backend audita.

## 14.2 Configurar visibilidad

1. Admin selecciona documento.
2. Define alcance:

   * global,
   * rol,
   * departamento,
   * sucursal,
   * usuario específico.
3. Backend guarda reglas.
4. Backend audita.

## 14.3 Publicar

1. Admin presiona publicar.
2. Backend valida metadata, dueño, versión y visibilidad.
3. Backend cambia estado a PUBLICADO.
4. Documento aparece a usuarios autorizados.

## 14.4 Descargar

1. Usuario entra a biblioteca.
2. Backend devuelve solo documentos autorizados.
3. Usuario abre detalle.
4. Usuario descarga.
5. Backend valida permiso.
6. Backend entrega archivo sin exponer ruta real.

## 14.5 Reemplazar versión

1. Admin abre documento.
2. Sube nuevo archivo.
3. Agrega etiqueta de versión y notas de cambio.
4. Backend guarda archivo en Warehouse.
5. Backend oculta versión anterior.
6. Backend marca nueva versión como vigente.
7. Backend audita.

## 14.6 Archivar

1. Admin archiva documento.
2. Backend cambia estado a ARCHIVADO.
3. Documento desaparece de biblioteca normal.
4. Historial queda disponible para admin.

## 15. Checklist QA F1

## 15.1 Seguridad

* Usuario sin token no accede.
* Usuario no autorizado no ve documento.
* Usuario no autorizado no descarga por URL directa.
* Usuario autorizado sí descarga.
* Usuario normal no ve borradores.
* Usuario normal no ve archivados.
* Usuario normal no ve versiones ocultas.
* Documento sensible no se publica globalmente por error.
* Frontend oculta botones, pero backend bloquea aunque se fuerce request.

## 15.2 Versionado

* Crear primera versión funciona.
* Reemplazar versión crea nuevo registro.
* Versión anterior queda no vigente.
* Versión anterior queda oculta para usuario normal.
* Admin puede ver historial.
* Documento apunta a versión vigente correcta.

## 15.3 Warehouse

* Archivo se registra en Warehouse.
* Archivo tiene hash.
* Archivo queda en volumen persistente.
* Portal guarda referencia a `warehouse_upload_id`.
* Descarga resuelve desde Warehouse.

## 15.4 Auditoría

* Crear documento audita.
* Editar metadata audita.
* Publicar audita.
* Archivar audita.
* Reemplazar versión audita.
* Cambiar visibilidad audita.
* Cambiar sensibilidad audita.

## 15.5 Frontend

* Lista carga documentos autorizados.
* Filtros funcionan.
* Buscador por metadata funciona.
* Detalle muestra metadata correcta.
* Botón descargar funciona.
* Botones admin solo aparecen si hay permisos.
* F5 en ruta hash mantiene pantalla correcta.
* Responsive básico funciona.

## 16. Orden de implementación recomendado

## Rama 1 — DB/Migrations

Nombre sugerido:

`feature/f1-internal-documents-db`

Objetivo:

Crear tablas y catálogos base.

Incluye:

* modelos ORM,
* migración Alembic,
* seed de categorías,
* relaciones con users/departments/sucursales/Warehouse.

No incluye endpoints completos ni frontend.

## Rama 2 — Backend base

Nombre sugerido:

`feature/f1-internal-documents-backend`

Objetivo:

Crear blueprint y endpoints base.

Incluye:

* listar categorías,
* listar documentos,
* detalle,
* crear documento,
* subir archivo vía Warehouse,
* publicar,
* archivar,
* reemplazar versión,
* descarga segura,
* auditoría.

## Rama 3 — Permisos y seguridad

Nombre sugerido:

`feature/f1-internal-documents-permissions`

Objetivo:

Endurecer permisos backend.

Incluye:

* helpers de permisos,
* validación por rol,
* validación por visibilidad,
* documentos sensibles,
* pruebas manuales por rol.

Puede combinarse con backend si el cambio no crece demasiado, pero idealmente separarlo.

## Rama 4 — Frontend admin

Nombre sugerido:

`feature/f1-internal-documents-admin-ui`

Objetivo:

Crear pantallas administrativas.

Incluye:

* ruta admin,
* formulario subir/crear,
* editar metadata,
* publicar,
* archivar,
* reemplazar versión,
* configurar visibilidad.

## Rama 5 — Frontend usuario

Nombre sugerido:

`feature/f1-internal-documents-user-ui`

Objetivo:

Crear biblioteca para usuarios.

Incluye:

* home,
* lista,
* filtros,
* detalle,
* descarga.

## Rama 6 — QA/Integración

Nombre sugerido:

`feature/f1-internal-documents-qa`

Objetivo:

Pruebas finales, limpieza e integración.

Incluye:

* checklist QA,
* pruebas por rol,
* pruebas por visibilidad,
* pruebas de versión,
* pruebas de descarga directa,
* revisión visual,
* documentación interna.

## 17. Criterio de cierre F1

F1 se puede cerrar cuando:

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

## 18. Pendientes para F2

* Búsqueda dentro de PDFs.
* Auditoría de descargas.
* Destacados.
* Vigencias y alertas.
* Publicación automática de reportes confiables.
* Responsables por área.
* Aprobación documental.
* Firma de recibido.
* Preview de PDF.
* Integración con notificaciones.
* Dashboard de documentos vencidos/no revisados.
* Migración futura a S3/R2/MinIO si el volumen crece.
