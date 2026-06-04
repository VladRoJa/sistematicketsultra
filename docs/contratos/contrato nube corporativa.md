# Suite Ultra — Contrato Técnico Nube Corporativa

## Portal Interno de Documentos Publicados

### Base documental gobernada para Suite Ultra

---

## 0. Separación de contratos

Este documento corresponde únicamente al contrato técnico y funcional de:

```text
Nube Corporativa / Portal Interno de Documentos Publicados
```

El Módulo de Aperturas debe tener un contrato separado.

La Nube Corporativa no existe únicamente para Aperturas. Aperturas será uno de sus principales consumidores futuros, pero la Nube debe servir de forma transversal para:

* manuales,
* reportes,
* políticas,
* formatos,
* procedimientos,
* tutoriales,
* documentación operativa,
* documentación técnica,
* documentos administrativos,
* evidencias,
* archivos internos publicados,
* documentos vinculables a otros módulos de Suite Ultra.

La relación correcta es:

```text
Nube Corporativa = base documental gobernada
Aperturas = módulo operativo que consume y vincula documentos de la Nube
```

---

## 1. Estado actual del módulo

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

### Estado de mejoras posteriores

Además de F1, se trabajaron mejoras locales / de repositorio:

* preview seguro de PDF e imágenes,
* vínculos documentales genéricos,
* UI más premium estilo Suite Ultra v1,
* mejoras UX en formulario de vínculos,
* modal interno para quitar vínculos en lugar de `window.confirm`.

Estas mejoras deben validarse y desplegarse cuando se decida liberar la siguiente versión a producción.

### Decisión operativa temporal

El menú de Nube Corporativa queda oculto para gerentes y usuarios no administrativos por ahora.

Motivo:

* el módulo ya funciona,
* pero todavía se está madurando,
* no se quiere generar ruido operativo,
* no se quiere que gerentes empiecen a preguntar antes de cerrar UX, permisos finos y contrato de uso,
* los primeros documentos cargados serán controlados por Sistemas / administración.

Roles con acceso visible al menú en esta etapa:

* ADMIN
* ADMINISTRADOR
* SUPER_ADMIN
* SISTEMAS

---

## 2. Objetivo técnico

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
* vínculos documentales hacia entidades internas de Suite,
* preparación para integrarse con módulos futuros sin depender de ellos.

---

## 3. Principio rector

La Nube Corporativa debe convertirse en la fuente documental gobernada de Suite Ultra.

No debe ser un basurero de archivos.

Debe ayudar a responder preguntas como:

* ¿Cuál es el documento vigente?
* ¿Quién subió este documento?
* ¿Quién lo publicó?
* ¿Qué versión reemplazó a cuál?
* ¿Quién puede verlo?
* ¿Quién puede descargarlo?
* ¿Está archivado?
* ¿Hay una versión nueva?
* ¿Este documento es sensible?
* ¿A qué proceso, módulo o contexto está vinculado?
* ¿Puedo revisarlo sin descargarlo?

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

El preview seguro de PDF e imágenes es parte de la evolución temprana del módulo.

Debe permitir revisar documentos sin obligar siempre a descargarlos.

Formatos iniciales de preview:

* PDF
* PNG
* JPG
* JPEG

Office docs quedan solo por descarga hasta una fase posterior.

### Búsqueda

F1 incluye búsqueda por metadata.

Búsqueda dentro de PDF queda como pendiente futuro.

### Auditoría

F1 audita acciones administrativas.

Auditoría de descargas queda como pendiente recomendado para documentos sensibles o F2.

### Almacenamiento

F1 usa volumen persistente del servidor.

No se deben guardar archivos en almacenamiento efímero del contenedor.

---

## 5. Relación con otros módulos

La Nube Corporativa debe poder integrarse con otros módulos mediante vínculos documentales.

Módulos consumidores posibles:

* Aperturas,
* PM,
* Tickets,
* Inventario,
* Warehouse,
* Track / BI,
* Planeación Comercial,
* Sistemas,
* Finanzas,
* Operación,
* Recursos Humanos.

La Nube no debe importar lógica específica de cada módulo.

Debe permitir una vinculación genérica mediante:

```text
entity_type
entity_id
entity_key
link_role
```

Ejemplo conceptual:

```text
entity_type = OPENING
entity_key = EGADE
link_role = PLANO
```

A futuro, cuando el módulo consumidor exista formalmente, deberá mandar `entity_id` real.

---

## 6. Caso de uso estratégico: Aperturas

Aperturas es un caso de uso estratégico, pero no es el único propósito de la Nube.

Para Aperturas, la Nube deberá servir como base documental para:

* planos,
* permisos,
* contratos,
* cotizaciones,
* checklists,
* evidencias,
* manuales,
* documentos financieros,
* documentos operativos,
* versiones oficiales.

La lógica de aperturas, tareas, responsables, dependencias, fechas, Gantt simplificado y notificaciones debe vivir en el contrato separado del Módulo de Aperturas.

La Nube solo debe proveer:

* almacenamiento documental,
* versionado,
* preview,
* descarga,
* visibilidad,
* auditoría,
* vínculos documentales.

---

## 7. Módulo backend actual

Blueprint:

```text
backend/app/routes/internal_documents_routes.py
```

Prefijo:

```text
/api/internal-documents
```

Endpoints base:

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

Endpoints de vínculos documentales:

```text
GET    /api/internal-documents/<document_id>/links
POST   /api/internal-documents/<document_id>/links
PATCH  /api/internal-documents/<document_id>/links/<link_id>
DELETE /api/internal-documents/<document_id>/links/<link_id>
GET    /api/internal-documents/by-link
```

Archivos backend actuales:

```text
backend/app/models/internal_documents.py
backend/app/routes/internal_documents_routes.py
backend/app/utils/internal_documents_access.py
backend/app/warehouse/services/warehouse_document_upload_service.py
```

Migraciones principales:

```text
backend/migrations/versions/45cb1ba3f367_add_internal_documents_module.py
backend/migrations/versions/f57edbdac964_add_internal_documents_warehouse_report_.py
backend/migrations/versions/21d6089a97b9_add_internal_document_links.py
```

---

## 8. Módulo frontend actual

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

La pantalla actual contempla:

* header premium,
* resumen visual,
* filtros,
* formulario colapsable,
* lista de documentos,
* detalle documental,
* preview PDF/imágenes,
* descarga,
* publicación,
* archivado,
* reemplazo de versión,
* vínculos documentales,
* modal interno para quitar vínculo.

Pendiente futuro:

* separar vista usuario final y vista admin,
* mover creación/edición a modal o subpantalla dedicada,
* historial/auditoría visual,
* configuración avanzada de permisos.

---

## 9. Tablas actuales

### 9.1 `internal_document_categories`

Catálogo controlado de categorías.

Categorías seed F1:

* REPORTES
* MANUALES
* POLITICAS
* FORMATOS
* PROCEDIMIENTOS
* TUTORIALES

### 9.2 `internal_documents`

Documento lógico estable.

Estados:

* BORRADOR
* PUBLICADO
* ARCHIVADO

Campos principales:

* título,
* descripción,
* categoría,
* tipo documental,
* dueño usuario,
* dueño departamento,
* estado,
* sensibilidad,
* versión vigente,
* visibilidad,
* publicación,
* archivado,
* creado por,
* actualizado por,
* fechas de auditoría.

### 9.3 `internal_document_versions`

Versiones del documento.

Reglas:

* toda versión apunta a Warehouse,
* no se sobrescribe archivo anterior,
* solo una versión vigente,
* versiones anteriores quedan ocultas para usuarios normales,
* versiones anteriores quedan trazables para admin/auditoría.

### 9.4 `internal_document_visibility`

Reglas de acceso por documento.

Tipos:

* GLOBAL
* ROLE
* DEPARTMENT
* SUCURSAL
* USER

### 9.5 `internal_document_audit_logs`

Auditoría documental.

Acciones:

* DOCUMENT_CREATED
* DOCUMENT_METADATA_UPDATED
* DOCUMENT_PUBLISHED
* DOCUMENT_ARCHIVED
* DOCUMENT_VERSION_CREATED
* DOCUMENT_VERSION_REPLACED
* DOCUMENT_VISIBILITY_UPDATED
* DOCUMENT_SENSITIVITY_UPDATED
* DOCUMENT_OWNER_UPDATED
* DOCUMENT_LINK_CREATED
* DOCUMENT_LINK_UPDATED
* DOCUMENT_LINK_DEACTIVATED

### 9.6 `internal_document_links`

Vínculos documentales genéricos.

Objetivo:

Permitir que un documento se relacione con un contexto interno sin depender directamente de otro módulo.

Campos conceptuales:

| Campo       | Uso                                |
| ----------- | ---------------------------------- |
| document_id | Documento vinculado                |
| entity_type | Tipo de entidad                    |
| entity_id   | ID real cuando exista tabla formal |
| entity_key  | Clave legible/snapshot             |
| link_role   | Rol documental                     |
| label       | Etiqueta visible                   |
| is_primary  | Principal/oficial en ese contexto  |
| is_active   | Activo/inactivo                    |
| created_by  | Usuario creador                    |
| updated_by  | Último usuario que editó           |
| created_at  | Fecha creación                     |
| updated_at  | Fecha actualización                |

Tipos de entidad soportados:

* OPENING
* PROJECT
* TASK
* SUCURSAL
* DEPARTMENT
* GENERAL

Roles documentales soportados:

* PLANO
* PERMISO
* CONTRATO
* COTIZACION
* CHECKLIST
* EVIDENCIA
* MANUAL
* FINANCIERO
* CONSTRUCCION
* OPERACION
* OTRO

---

## 10. Warehouse

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

Extensiones permitidas:

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

## 11. Permisos actuales

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
* administrar vínculos,
* descargar versiones históricas.

Usuarios normales:

* no ven borradores,
* no ven archivados,
* no ven versiones históricas ocultas,
* solo ven documentos publicados si tienen visibilidad,
* pueden descargar solo si backend lo permite.

Menú temporal:

* visible solo para ADMIN / ADMINISTRADOR / SUPER_ADMIN / SISTEMAS,
* oculto para gerentes, regionales y usuarios operativos hasta cerrar UX/contrato de uso.

---

## 12. Reglas de seguridad

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
19. Los vínculos documentales deben auditarse.
20. El backend debe validar permisos aunque el frontend oculte botones.

---

## 13. Reglas UX base

A partir de los hallazgos en Nube Corporativa, se adopta esta regla como referencia para Suite Ultra:

### Formularios

Si un campo es obligatorio para ejecutar una acción:

* el botón principal debe permanecer desactivado hasta que se cumpla la condición,
* el usuario debe ver ayuda clara del campo requerido,
* no debe parecer que el botón “no hace nada”.

### Confirmaciones

No usar `alert()` ni `confirm()` del navegador para acciones importantes.

Usar modal interno Suite Ultra para:

* archivar,
* eliminar,
* desactivar vínculos,
* cambios sensibles,
* acciones irreversibles o de trazabilidad.

Pendiente actual:

* reemplazar confirm nativo de archivado por modal interno.
* revisar otros módulos donde aún existan confirm/alert del navegador.

---

## 14. Preview seguro de documentos

### Formatos iniciales con preview

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

### Arquitectura

No crear URL pública.

No servir archivos estáticos directamente.

Usar endpoint protegido:

```text
GET /api/internal-documents/<document_id>/download
```

Flujo:

```text
Angular → request con JWT → backend valida permisos → backend devuelve blob → Angular crea ObjectURL temporal → visor en pantalla
```

### Criterios de aceptación

1. Documento PDF se abre en pantalla.
2. Imagen PNG/JPG/JPEG se abre en pantalla.
3. Documento DOCX/PPTX/XLSX no muestra preview inicial.
4. La opción Descargar se mantiene.
5. El backend sigue validando permisos.
6. No se expone path interno.
7. El ObjectURL se limpia al cerrar.
8. Usuario sin permiso no puede previsualizar por request directo.

---

## 15. Vínculos documentales

### Objetivo

Permitir que un documento pueda vincularse a entidades presentes o futuras sin contaminar la tabla principal `internal_documents`.

### Decisión

No agregar columnas rígidas como:

```text
opening_id
task_id
project_id
```

directamente en `internal_documents`.

Usar tabla puente genérica:

```text
internal_document_links
```

### Uso actual

Actualmente el contexto puede capturarse de forma manual mediante `entity_key`.

Ejemplo:

```text
entity_type = OPENING
entity_key = EGADE
link_role = MANUAL
```

### Decisión futura

Cuando existan catálogos reales, el campo manual debe reemplazarse por selectores/autocomplete.

Para `entity_type = OPENING`:

* mostrar selector de aperturas,
* guardar `entity_id` real,
* conservar `entity_key` como snapshot legible.

Para `entity_type = TASK`:

* mostrar selector de tareas,
* idealmente filtrado por apertura.

Para `entity_type = SUCURSAL`:

* usar catálogo real de sucursales.

Para `entity_type = DEPARTMENT`:

* usar catálogo real de departamentos.

Esto no debe resolverse dentro de Nube hasta que existan los módulos/catálogos correspondientes.

---

## 16. Estados documentales

Estados actuales:

* BORRADOR
* PUBLICADO
* ARCHIVADO

### Sobre REEMPLAZADO

No se recomienda agregar `REEMPLAZADO` como estado de documento.

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

No hacerlo en F1/F1.1.

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

Pendiente:

* indicador visual de oficial/vigente por contexto,
* reglas de documento principal por módulo consumidor.

### Riesgo 4: exponer información sensible

Mitigación actual:

* `is_sensitive`,
* bloqueo de GLOBAL sensible,
* permisos backend.

Pendiente:

* UI más clara para documentos sensibles,
* auditoría de descargas,
* reglas custom más amigables.

### Riesgo 5: acoplar la Nube a otros módulos demasiado pronto

Mitigación:

* usar `internal_document_links`,
* no meter FKs específicas prematuras,
* no duplicar lógica de módulos consumidores.

### Riesgo 6: preview inseguro

Mitigación:

* no exponer rutas públicas,
* usar blob autenticado,
* backend valida permisos,
* limpiar ObjectURL al cerrar,
* no usar URLs internas del servidor en HTML.

---

## 18. Pendientes específicos de Nube Corporativa

### UX / Frontend

* Separar vista admin y vista usuario final.
* Convertir creación de documento en modal o subpantalla dedicada.
* Reemplazar owner user id / owner department id por selector/autollenado.
* Reemplazar confirm nativo de archivado por modal interno Suite.
* Crear vista de auditoría visual.
* Crear vista de versiones históricas más clara.
* Mejorar configuración de visibilidad custom.
* Mostrar indicador visual de documento principal/oficial por contexto.
* Agregar filtros por vínculo documental.
* Agregar filtros por sensible / no sensible.
* Agregar filtros por tipo documental.
* Mejorar responsive después de más uso real.

### Backend

* Auditoría de descargas, especialmente sensibles.
* Validación/alerta de archivos duplicados por hash.
* Endpoint para búsqueda avanzada por vínculo.
* Endpoint para catálogos de contexto cuando existan otros módulos.
* Políticas más finas para descarga histórica.
* Preparar migración futura a almacenamiento externo si volumen crece.

### Búsqueda / IA

* Búsqueda dentro de PDF.
* Extracción de texto para PDFs.
* Indexación interna.
* Catálogo semántico futuro.
* Preguntas sobre documentos publicados, solo cuando permisos estén maduros.

### Integración futura

* Selector de aperturas desde módulo Aperturas.
* Selector de tareas desde módulo Aperturas.
* Selector de sucursales desde catálogo real.
* Selector de departamentos desde catálogo real.
* Consumo de documentos desde PM, Tickets, Inventario, Track y Planeación.

---

## 19. Flujo funcional actual

### Crear borrador

1. Admin entra a Nube Corporativa.
2. Abre formulario Nuevo documento.
3. Sube archivo.
4. Completa metadata mínima.
5. Backend guarda archivo en Warehouse.
6. Backend crea documento en BORRADOR.
7. Backend crea versión 1.
8. Backend audita.

### Configurar visibilidad

1. Admin selecciona documento.
2. Define alcance.
3. Backend guarda reglas.
4. Backend audita.

### Publicar

1. Admin presiona publicar.
2. Backend valida metadata, dueño, versión y visibilidad.
3. Backend cambia estado a PUBLICADO.
4. Documento aparece a usuarios autorizados.

### Descargar

1. Usuario autorizado entra a biblioteca.
2. Backend devuelve solo documentos autorizados.
3. Usuario abre detalle.
4. Usuario descarga.
5. Backend valida permiso.
6. Backend entrega archivo sin exponer ruta real.

### Ver en pantalla

1. Usuario autorizado abre documento.
2. Frontend valida si el formato es previsualizable.
3. Si es PDF/imagen, muestra botón Ver.
4. Frontend solicita archivo al endpoint protegido.
5. Backend valida permisos y entrega blob.
6. Frontend crea ObjectURL temporal.
7. Frontend muestra PDF/imagen en pantalla.
8. Al cerrar, frontend libera ObjectURL.

### Reemplazar versión

1. Admin abre documento.
2. Sube nuevo archivo.
3. Agrega etiqueta de versión y notas de cambio.
4. Backend guarda archivo en Warehouse.
5. Backend oculta versión anterior.
6. Backend marca nueva versión como vigente.
7. Backend audita.

### Vincular documento

1. Admin selecciona documento.
2. Selecciona tipo de entidad.
3. Captura contexto temporal o selecciona catálogo futuro.
4. Selecciona rol documental.
5. Marca si es principal/oficial.
6. Backend crea vínculo.
7. Backend audita.

### Quitar vínculo

1. Admin presiona quitar.
2. Suite muestra modal interno.
3. Admin confirma.
4. Backend desactiva vínculo.
5. Backend audita.
6. El vínculo deja de aparecer como activo.

---

## 20. QA actual

### Seguridad

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

### Versionado

* Crear primera versión funciona.
* Reemplazar versión crea nuevo registro.
* Versión anterior queda no vigente.
* Versión anterior queda oculta para usuario normal.
* Admin puede ver historial.
* Documento apunta a versión vigente correcta.

### Warehouse

* Archivo se registra en Warehouse.
* Archivo tiene hash.
* Archivo queda en volumen persistente.
* Portal guarda referencia a `warehouse_upload_id`.
* Descarga resuelve desde Warehouse.
* Archivo sobrevive reinicio/rebuild.

### Auditoría

* Crear documento audita.
* Editar metadata audita.
* Publicar audita.
* Archivar audita.
* Reemplazar versión audita.
* Cambiar visibilidad audita.
* Cambiar sensibilidad audita.
* Crear vínculo audita.
* Actualizar vínculo audita.
* Desactivar vínculo audita.

### Frontend

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

## 21. Criterio de cierre Nube Corporativa v1

Nube Corporativa v1 se considera suficientemente cerrada cuando:

1. Un admin sube un archivo y este entra al Warehouse.
2. El Portal crea documento ligado a ese archivo.
3. El documento nace como borrador.
4. El admin puede configurar metadata.
5. El admin puede configurar visibilidad.
6. El admin puede publicar.
7. El usuario autorizado lo ve.
8. El usuario autorizado lo descarga.
9. El usuario autorizado puede previsualizar PDF/imagen.
10. El usuario no autorizado no lo ve.
11. El usuario no autorizado no lo descarga por URL directa.
12. El admin puede reemplazar versión.
13. La versión anterior queda oculta y trazable.
14. El admin puede archivar.
15. El admin puede vincular documento a contexto.
16. El admin puede quitar vínculo con modal interno.
17. Todo cambio administrativo queda auditado.
18. Los archivos sobreviven reinicio/rebuild por volumen persistente.
19. No se exponen rutas internas ni Warehouse al usuario final.
20. El menú queda controlado para evitar exposición prematura.

Estado:

```text
Nube Corporativa v1 funcional.
Pendiente validación final local y decisión de deploy.
```

---

## 22. No incluido en este contrato

Este contrato no define:

* tareas de apertura,
* Gantt,
* dependencias,
* responsables por apertura,
* fechas compromiso de apertura,
* presupuesto de apertura,
* notificaciones de apertura,
* tablero de avance de apertura,
* flujo de cambios de apertura.

Todo eso pertenece al contrato separado:

```text
Módulo de Aperturas
```

La Nube solo provee la capa documental para que Aperturas pueda consumir documentos oficiales y trazables.

---

## 23. Siguiente contrato separado: Módulo de Aperturas

El contrato de Aperturas deberá definir:

* qué es una apertura,
* fases de apertura,
* áreas involucradas,
* responsables,
* tareas,
* fechas,
* dependencias,
* cambios,
* historial,
* tablero de avance,
* notificaciones,
* permisos,
* documentos requeridos por fase,
* relación con Nube Corporativa,
* relación con sucursales,
* relación con finanzas/construcción/operación/sistemas.

La integración con Nube deberá consumir:

```text
internal_document_links
```

pero no debe reimplementar almacenamiento documental.

---

## 24. Pendientes futuros para Nube

* Auditoría de descargas.
* Búsqueda dentro de PDFs.
* Preview Office si realmente se justifica.
* Selector real de owner user / owner department.
* Selector real de contexto por módulo.
* Historial visual de auditoría.
* Reglas de visibilidad avanzadas.
* Firma de recibido.
* Vigencias / vencimientos.
* Notificaciones por documento vencido.
* Documentos destacados.
* Documentos favoritos.
* Publicación automática de reportes confiables.
* Migración futura a S3/R2/MinIO si el volumen crece.
