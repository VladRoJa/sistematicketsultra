# CONTRATO — Nube Corporativa Fase 2

## Centro de conocimiento interno, videos embebidos y búsqueda por contenido

## 1. Contexto

Nube Corporativa ya funciona como biblioteca documental gobernada dentro de Suite Ultra.

Actualmente permite:

* Publicar documentos.
* Consultar documentos disponibles.
* Buscar por metadata.
* Filtrar por periodo, categoría y estado.
* Ver detalle documental.
* Descargar archivos.
* Previsualizar PDFs e imágenes.
* Administrar visibilidad, vínculos, versiones y auditoría para perfiles autorizados.

La Fase 1 resolvió el almacenamiento, visibilidad y consulta básica.

La Fase 2 debe resolver el siguiente problema: una biblioteca funciona cuando el usuario sabe qué buscar, pero no ayuda suficiente cuando el usuario no sabe qué documentos existen.

La evolución deseada es convertir Nube Corporativa en un centro de conocimiento interno.

---

## 2. Objetivo de producto

Convertir Nube Corporativa de una biblioteca documental a una experiencia guiada de consulta, aprendizaje y descubrimiento.

La Fase 2 debe permitir que el usuario:

* Entre a Nube y entienda rápidamente qué puede consultar.
* Acceda por cards a tipos de documentos.
* Vea videos/tutoriales dentro de Suite sin salir a Drive.
* Consulte índices manuales de videos.
* Busque no solo por título, sino también dentro del contenido de documentos.
* Encuentre capítulos de videos por texto.
* Acceda solo a contenido permitido según permisos backend.

---

## 3. Principios de diseño

### 3.1 Backend como fuente real de permisos

El frontend puede mostrar u ocultar secciones, pero la autorización real siempre debe permanecer en backend.

Toda búsqueda, preview, descarga, video embebido o capítulo debe respetar:

* `can_view_internal_document`
* `can_download_internal_document`
* reglas de visibilidad
* estado del documento
* sensibilidad
* vínculos documentales
* permisos especiales por rol/sucursal si aplican

### 3.2 No duplicar lógica de permisos

La búsqueda interna no debe crear un sistema paralelo de permisos.

El índice puede contener texto de todos los documentos, pero los resultados visibles deben filtrarse por los documentos que el usuario realmente puede ver.

### 3.3 Descubrimiento antes que complejidad

La pantalla inicial debe ser fácil de entender para usuarios no técnicos.

Primero se deben mostrar caminos claros:

* Cobranza
* Manuales
* Tutoriales
* Formatos
* Comunicados
* Reportes

La biblioteca completa debe seguir existiendo para búsquedas avanzadas.

### 3.4 Índice, no lectura en vivo

El backend no debe abrir PDFs, Excels o documentos cada vez que alguien escribe en el buscador.

La extracción de texto debe hacerse al publicar, subir o actualizar una versión.

El buscador debe consultar una tabla de índice.

### 3.5 Drive como proveedor externo controlado

Los videos de Google Drive pueden embeberse, pero no deben permitir iframes arbitrarios.

El backend debe validar el proveedor y extraer el ID del archivo.

---

## 4. Alcance funcional Fase 2

La Fase 2 se divide en cuatro bloques.

---

# F2.1 — Home guiado con cards

## 4.1 Objetivo

Agregar una portada dentro de Nube Corporativa que ayude al usuario a descubrir contenido sin depender del buscador.

## 4.2 Experiencia esperada

Al entrar a Nube, el usuario verá una sección tipo:

```text
¿Qué necesitas consultar?

[ Cobranza ]
Archivos diarios por sucursal.

[ Manuales ]
Procesos, instructivos y documentos operativos.

[ Tutoriales ]
Videos y guías paso a paso.

[ Formatos ]
Plantillas, checklists y documentos descargables.

[ Comunicados ]
Información interna publicada.

[ Reportes ]
Archivos operativos y administrativos.
```

## 4.3 Comportamiento de las cards

Cada card aplicará filtros preconfigurados.

Ejemplos:

```text
Cobranza
- periodo: Hoy
- búsqueda: Cobranza recurrente rechazados
- categoría/tipo: Reportes financieros u operativo definido
```

```text
Manuales
- periodo: Todo
- categoría: Manuales
```

```text
Tutoriales
- periodo: Todo
- categoría: Tutoriales
- tipo de contenido: Video / guía
```

```text
Formatos
- periodo: Todo
- categoría: Formatos
```

## 4.4 Regla de visibilidad

Las cards no deben prometer acceso a documentos no visibles para el usuario.

Si una card no tiene documentos visibles para el usuario, puede:

* ocultarse,
* mostrarse deshabilitada,
* mostrarse con contador 0.

La decisión visual se definirá en diseño, pero backend debe devolver información filtrada por permisos.

## 4.5 Entregable funcional

* Nueva sección superior en Nube.
* Cards por tipo de documento.
* Acciones rápidas que aplican filtros.
* Contador de documentos visibles por card.
* Biblioteca actual permanece disponible debajo o en pestaña secundaria.

---

# F2.2 — Videos externos embebidos desde Google Drive

## 5.1 Objetivo

Permitir que documentos tipo tutorial/video se visualicen dentro de Suite Ultra sin obligar al usuario a abrir Drive manualmente.

## 5.2 Caso base

Un administrador registra un recurso de video con URL de Drive:

```text
https://drive.google.com/file/d/<file_id>/view
```

Suite lo transforma internamente en URL de preview:

```text
https://drive.google.com/file/d/<file_id>/preview
```

Y lo presenta dentro de Nube con un visor embebido.

## 5.3 Reglas

Solo se aceptan URLs de proveedores permitidos.

Proveedor inicial:

```text
GOOGLE_DRIVE
```

No se aceptan iframes arbitrarios ni URLs no controladas.

## 5.4 Permisos

El permiso de ver el video dentro de Suite depende de Nube.

Sin embargo, Drive puede tener sus propios permisos.

Si Drive bloquea el video, Suite debe mostrar fallback:

```text
No se pudo cargar el video embebido.
Puedes abrirlo directamente en Drive.
```

Y mostrar botón:

```text
Abrir en Drive
```

## 5.5 Alcance MVP

El MVP no descargará ni copiará videos de Drive al servidor.

Solo guardará metadata del recurso externo y mostrará el embed.

## 5.6 Futuro

Más adelante se podrá permitir video nativo subido a Suite:

* MP4 cargado en Warehouse/Nube.
* Reproductor HTML5 propio.
* Saltos exactos por timestamp.
* Control total por permisos Suite.

---

# F2.3 — Índice manual de videos

## 6.1 Objetivo

Permitir que un video tenga capítulos manuales para que los usuarios encuentren partes importantes sin ver el video completo.

## 6.2 Ejemplo

```text
00:00 — Introducción
00:42 — Tornillería
02:15 — Registro de evidencia
04:30 — Cierre del proceso
```

## 6.3 Experiencia esperada

En el detalle del video se mostrará:

```text
Índice del video

00:00 Introducción
00:42 Tornillería
02:15 Registro de evidencia
04:30 Cierre del proceso
```

## 6.4 Click en capítulo

Para videos de Drive:

* Se intentará abrir el video embebido o Drive en el tiempo indicado si el proveedor lo soporta.
* Si Drive no permite salto confiable, el índice funcionará como guía manual.

Para videos nativos de Suite:

* El click debe saltar exactamente al tiempo usando el reproductor HTML5.

## 6.5 Captura inicial

La captura de capítulos puede iniciar manualmente por administrador.

Campos mínimos:

```text
Título del capítulo
Tiempo en segundos
Descripción opcional
Orden
```

## 6.6 Búsqueda

Los capítulos deben integrarse al buscador.

Si el usuario busca:

```text
tornillería
```

Debe poder aparecer:

```text
Tutorial de mantenimiento preventivo
Coincidencia en video:
00:42 — Tornillería
```

---

# F2.4 — Búsqueda interna por contenido

## 7.1 Objetivo

Ampliar el buscador para que encuentre documentos por su contenido interno, no solo por título o descripción.

## 7.2 Problema que resuelve

Hoy el usuario necesita saber cómo se llama el documento.

Con búsqueda por contenido, puede buscar términos como:

```text
tornillería
cancelación
evidencia
mantenimiento
manual de cobro
```

y Suite debe encontrar archivos donde aparezcan esos términos.

## 7.3 Fuentes indexables MVP

El MVP debe indexar:

* Título.
* Descripción.
* Categoría.
* Tipo documental.
* Texto interno de PDF con texto seleccionable.
* Texto interno de DOCX.
* Texto interno de XLSX.
* Texto interno de CSV/TXT.
* Índice manual de videos.
* Descripción/transcripción manual de videos si existe.

## 7.4 Fuera del MVP

No entra inicialmente:

* OCR para PDFs escaneados.
* OCR para imágenes.
* Transcripción automática de video.
* IA generativa para resumir documentos.
* Vector search.
* Chatbot sobre documentos.

Estas capacidades pueden quedar para una Fase 3.

## 7.5 Regla técnica

El texto se extrae e indexa cuando:

* se crea un documento,
* se publica,
* se reemplaza versión,
* se registra/reemplaza recurso externo,
* se actualizan capítulos del video.

No se debe extraer texto durante cada búsqueda.

---

## 8. Modelo de datos propuesto

La Fase 2 debe evitar romper el modelo actual de Nube.

Se recomienda agregar tablas auxiliares.

---

## 8.1 Tabla: `internal_document_external_resources`

Representa videos o recursos externos asociados a un documento.

Campos sugeridos:

```text
id
document_id
provider
resource_kind
original_url
external_file_id
preview_url
title
description
is_active
created_by
created_at
updated_by
updated_at
```

Valores iniciales:

```text
provider:
- GOOGLE_DRIVE

resource_kind:
- VIDEO
- FOLDER
- LINK
```

Reglas:

* Un documento puede tener cero o más recursos externos.
* Para Fase 2, lo normal será un recurso externo principal por documento.
* Solo administradores de Nube pueden crear/editar recursos externos.

---

## 8.2 Tabla: `internal_document_video_chapters`

Representa capítulos manuales de video.

Campos sugeridos:

```text
id
document_id
external_resource_id
time_seconds
label
description
sort_order
is_active
created_by
created_at
updated_by
updated_at
```

Reglas:

* `time_seconds` debe ser entero mayor o igual a 0.
* `label` es obligatorio.
* Se ordena por `time_seconds` y `sort_order`.
* Los capítulos inactivos no aparecen a usuarios finales.
* Los capítulos activos se indexan para búsqueda.

---

## 8.3 Tabla: `internal_document_search_index`

Representa texto extraído o registrado para búsqueda.

Campos sugeridos:

```text
id
document_id
version_id
external_resource_id
chapter_id
source_kind
content_text
normalized_text
language
created_at
updated_at
```

Valores de `source_kind`:

```text
METADATA
FILE_CONTENT
VIDEO_CHAPTER
VIDEO_DESCRIPTION
MANUAL_TRANSCRIPT
EXTERNAL_RESOURCE
```

Reglas:

* Un documento puede tener múltiples entradas de índice.
* El índice puede contener contenido de documentos sensibles, pero los resultados siempre se filtran por permisos.
* El índice debe actualizarse al reemplazar versiones o editar capítulos.

---

## 8.4 Opcional futuro: `internal_document_discovery_cards`

Si las cards se quieren administrar dinámicamente desde UI, se puede agregar:

```text
id
key
title
description
icon
category_id
document_type
default_period
default_query
sort_order
is_active
visibility_mode
created_at
updated_at
```

Para el MVP, las cards pueden estar hardcodeadas en frontend o definidas por endpoint backend simple.

---

## 9. Backend propuesto

## 9.1 Endpoints nuevos

### Home / cards

```text
GET /api/internal-documents/discovery
```

Respuesta esperada:

```json
{
  "cards": [
    {
      "key": "manuales",
      "title": "Manuales",
      "description": "Procesos e instructivos operativos.",
      "count": 12,
      "filters": {
        "period": "all",
        "category_key": "MANUALES"
      }
    }
  ]
}
```

Los contadores deben respetar permisos del usuario.

---

### Crear recurso externo

```text
POST /api/internal-documents/<document_id>/external-resources
```

Payload:

```json
{
  "provider": "GOOGLE_DRIVE",
  "resource_kind": "VIDEO",
  "original_url": "https://drive.google.com/file/d/abc/view",
  "title": "Tutorial de ejemplo",
  "description": "Video de apoyo operativo"
}
```

Backend debe:

* validar provider,
* extraer `external_file_id`,
* construir `preview_url`,
* guardar metadata,
* registrar auditoría.

---

### Listar recursos externos

```text
GET /api/internal-documents/<document_id>/external-resources
```

Devuelve recursos visibles para el documento.

---

### Crear/editar capítulos

```text
POST /api/internal-documents/<document_id>/video-chapters
PUT /api/internal-documents/<document_id>/video-chapters/<chapter_id>
DELETE /api/internal-documents/<document_id>/video-chapters/<chapter_id>
```

`DELETE` debe ser baja lógica con `is_active=false`.

---

### Buscar

Opción A: extender listado actual:

```text
GET /api/internal-documents?q=texto&search_scope=all
```

Opción B: endpoint dedicado:

```text
GET /api/internal-documents/search?q=texto
```

Recomendación: endpoint dedicado para Fase 2.4.

Respuesta esperada:

```json
{
  "items": [
    {
      "document": {},
      "matches": [
        {
          "source_kind": "VIDEO_CHAPTER",
          "label": "00:42 — Tornillería",
          "snippet": "Capítulo relacionado con tornillería...",
          "time_seconds": 42
        }
      ]
    }
  ]
}
```

---

## 10. Extracción de texto

## 10.1 Archivos soportados MVP

```text
PDF con texto
DOCX
XLSX
CSV
TXT
```

## 10.2 Librerías sugeridas

Python:

```text
pypdf o pdfplumber para PDF con texto
python-docx para DOCX
openpyxl para XLSX
csv / texto plano para CSV/TXT
```

OCR queda fuera del MVP.

## 10.3 Flujo de indexación

Cuando se sube o reemplaza una versión:

```text
1. Se guarda el archivo en Warehouse/Nube.
2. Se crea o actualiza InternalDocumentVersion.
3. Se dispara extracción de texto.
4. Se borra índice anterior de esa versión.
5. Se inserta nuevo índice.
6. Si falla extracción, el documento sigue funcionando pero queda con estado de indexación fallido.
```

## 10.4 Estado de indexación

Se recomienda agregar campos o tabla para monitoreo:

```text
index_status:
- PENDING
- INDEXED
- FAILED
- SKIPPED_UNSUPPORTED
```

Puede vivir en `internal_document_versions` o en una tabla auxiliar.

Para no alterar demasiado, se recomienda tabla auxiliar:

```text
internal_document_index_jobs
```

solo si se requiere trazabilidad.

---

## 11. Frontend propuesto

## 11.1 Home guiado

Agregar sección superior en:

```text
frontend/src/app/internal-documents/pages/internal-documents-home/
```

Componentes futuros sugeridos:

```text
internal-documents-discovery-cards.component.ts
internal-documents-discovery-cards.component.html
internal-documents-discovery-cards.component.css
```

No meter todo en el componente actual si empieza a crecer demasiado.

## 11.2 Preview de video

Actualmente el preview soporta PDF e imagen.

Se debe extender a:

```text
previewType: 'pdf' | 'image' | 'external-video'
```

El modal debe mostrar:

```text
iframe para Google Drive preview
índice de capítulos
botón Abrir en Drive
botón Descargar si aplica
```

## 11.3 Índice de video

Agregar panel dentro del detalle:

```text
Índice del video
00:00 Introducción
00:42 Tornillería
02:15 Evidencia
```

Para usuarios normales:

* solo lectura,
* clic para intentar abrir/saltar.

Para administradores:

* crear capítulo,
* editar capítulo,
* desactivar capítulo.

## 11.4 Búsqueda por contenido

El buscador actual debe poder mostrar resultados enriquecidos.

Ejemplo:

```text
Manual de mantenimiento básico
Coincidencia en PDF:
"... revisar tornillería antes de cerrar la orden ..."

Tutorial de mantenimiento
Coincidencia en video:
00:42 — Tornillería
```

---

## 12. Permisos y seguridad

## 12.1 Permisos de administración

Solo administradores de Nube pueden:

* crear recursos externos,
* editar recursos externos,
* eliminar/desactivar recursos externos,
* crear capítulos,
* editar capítulos,
* desactivar capítulos,
* reindexar documentos manualmente.

Regla actual de administración:

```text
ADMICORP
SISTEMAS
```

## 12.2 Permisos de lectura

Un usuario puede ver video, capítulos y resultados de búsqueda solo si puede ver el documento padre.

## 12.3 Seguridad de iframes

Solo se deben permitir providers validados.

Para Google Drive:

```text
drive.google.com/file/d/<id>/view
drive.google.com/file/d/<id>/preview
```

Backend extrae `<id>` y genera el preview.

Frontend solo recibe una URL segura generada por backend.

## 12.4 Riesgo Drive

Drive conserva sus propios permisos.

Suite puede mostrar el iframe, pero si Drive bloquea el archivo, el usuario verá error de Drive.

Por eso debe existir fallback:

```text
Abrir en Drive
```

---

## 13. Auditoría

Agregar eventos de auditoría para:

```text
EXTERNAL_RESOURCE_CREATED
EXTERNAL_RESOURCE_UPDATED
EXTERNAL_RESOURCE_DEACTIVATED
VIDEO_CHAPTER_CREATED
VIDEO_CHAPTER_UPDATED
VIDEO_CHAPTER_DEACTIVATED
DOCUMENT_INDEXED
DOCUMENT_INDEX_FAILED
```

Si no se desea ampliar todavía `InternalDocumentAuditAction`, se puede registrar como metadata en eventos existentes, pero se recomienda ampliar auditoría con migración.

---

## 14. Fases de implementación

## F2.1 — Home guiado con cards

Cambios:

* Endpoint discovery.
* Cards visibles por permisos.
* Cards aplican filtros.
* UI responsive.
* Sin cambios pesados de DB si se hardcodea configuración inicial.

Prioridad: Alta.

---

## F2.2 — Videos externos de Drive

Cambios:

* Modelo para recursos externos.
* Validación de URL Drive.
* Preview embebido en modal.
* Botón Abrir en Drive.
* Tipo de contenido video externo.

Prioridad: Alta.

---

## F2.3 — Índice manual de videos

Cambios:

* Modelo de capítulos.
* CRUD admin de capítulos.
* Visualización para usuarios.
* Integración básica con buscador por metadata.

Prioridad: Media-Alta.

---

## F2.4 — Búsqueda por contenido

Cambios:

* Tabla de índice.
* Extractores de texto.
* Job de indexación.
* Endpoint de búsqueda enriquecida.
* Resultados con snippets.
* Indexar capítulos de video.

Prioridad: Media-Alta.

---

## F2.5 — Reindexación y monitoreo

Cambios:

* Botón admin “Reindexar”.
* Estado de indexación.
* Logs de errores.
* Vista admin de documentos sin índice.

Prioridad: Media.

---

## 15. Fuera de alcance de Fase 2

No entra en esta fase:

* OCR de imágenes.
* OCR de PDFs escaneados.
* Transcripción automática de videos.
* IA para resumir documentos.
* Chatbot documental.
* Vector search.
* Control total de permisos de Drive.
* Streaming nativo optimizado para videos grandes.
* Edición global de permisos desde Centro de Permisos.

---

## 16. Riesgos técnicos

## 16.1 Archivos pesados

PDFs o XLSX grandes pueden tardar en indexarse.

Mitigación:

* indexar en job o proceso controlado,
* no bloquear la carga del usuario,
* guardar estado de indexación.

## 16.2 Drive no permite control total

Google Drive puede no permitir salto exacto por timestamp o puede pedir permisos externos.

Mitigación:

* fallback Abrir en Drive,
* índice como guía,
* videos nativos Suite en fase futura.

## 16.3 Búsqueda mostrando datos no permitidos

El índice podría contener texto sensible.

Mitigación:

* filtrar siempre resultados por permisos del documento padre,
* nunca devolver snippets de documentos no visibles.

## 16.4 Componente actual muy grande

La pantalla actual de Nube ya concentra mucha lógica.

Mitigación:

* separar cards, video preview, capítulos y búsqueda avanzada en subcomponentes.

## 16.5 Extracción de texto imperfecta

PDFs escaneados o archivos mal formateados pueden no producir texto.

Mitigación:

* marcar como `SKIPPED_UNSUPPORTED`,
* dejar OCR para fase posterior.

---

## 17. Criterios de aceptación

## Home guiado

* El usuario ve cards de acceso rápido.
* Cada card muestra contador de documentos visibles.
* Al hacer clic, se aplican filtros automáticamente.
* La biblioteca completa sigue disponible.
* No se muestran documentos no permitidos.

## Videos Drive

* Un admin puede registrar un link de Drive válido.
* Suite genera preview embebido.
* El usuario autorizado puede reproducirlo dentro de Nube.
* Existe botón Abrir en Drive.
* Si Drive bloquea el preview, Suite muestra mensaje claro.

## Índice de video

* Un admin puede crear capítulos con minuto y título.
* El usuario ve el índice en el detalle del video.
* El índice se muestra ordenado.
* El índice puede buscarse por texto.
* Los capítulos inactivos no aparecen al usuario final.

## Búsqueda por contenido

* El buscador encuentra coincidencias en metadata.
* El buscador encuentra coincidencias en contenido indexado.
* El buscador encuentra coincidencias en capítulos de video.
* Los resultados muestran origen de coincidencia.
* Los resultados respetan permisos del documento.
* No se lee el archivo en vivo por cada búsqueda.

---

## 18. Resultado esperado

Al finalizar Fase 2, Nube Corporativa debe sentirse como:

```text
Centro de conocimiento interno
```

y no solo como:

```text
Repositorio de archivos
```

El usuario podrá entrar, descubrir contenido por cards, ver tutoriales dentro de Suite, consultar índices de video y buscar dentro de documentos aunque no recuerde el nombre exacto del archivo.

---

## 19. Nombre sugerido de fase

```text
Nube Corporativa Fase 2 — Descubrimiento, tutoriales y búsqueda interna
```

## 20. Entregables recomendados

```text
F2.1 Home guiado con cards
F2.2 Videos Drive embebidos
F2.3 Índice manual de videos
F2.4 Índice de búsqueda por contenido
F2.5 Reindexación y monitoreo
```
