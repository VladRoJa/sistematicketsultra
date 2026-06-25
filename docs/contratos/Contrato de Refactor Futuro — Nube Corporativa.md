# Contrato de Refactor Futuro — Nube Corporativa / Documentos Internos

## 1. Contexto

Nube Corporativa ya cuenta con un MVP funcional para gestión documental interna dentro de Suite Ultra. Actualmente permite alta documental, metadata, categorías, búsqueda, filtros, publicación, archivado, descarga, vista previa, versiones, videos externos de Google Drive, asignaciones documentales y acciones operativas mediante cards/modales.

El módulo ya es usable en producción, por lo que esta etapa no busca reconstruirlo de inmediato, sino dejar definido el contrato de pendientes para una refactorización futura cuando existan menos frentes activos.

---

## 2. Principio rector

La Nube Corporativa debe funcionar como un portal gobernado de consumo documental.

Warehouse conserva la lógica de entrada, archivo bruto, trazabilidad técnica y origen documental.

Nube Corporativa debe encargarse de:

* Hacer documentos consumibles por usuarios.
* Controlar permisos reales desde backend.
* Organizar documentos por categorías, asignaciones y contexto operativo.
* Permitir búsqueda y descubrimiento.
* Mantener trazabilidad documental.
* Evitar que formularios operativos ensucien la experiencia de lectura.

---

## 3. Estado actual considerado como base

La refactorización futura parte del estado funcional ya implementado:

* Alta documental desde Suite.
* Metadata básica: título, descripción, categoría, dueño, tipo documental, sensibilidad.
* Estados: borrador, publicado, archivado.
* Vista previa de archivos.
* Descarga de documentos.
* Reemplazo de versión con historial.
* Cards de descubrimiento: Manuales, Tutoriales, Formatos, Comunicados y Reportes.
* Reportes con subnivel de Cobranza recurrente.
* Filtros por categoría, estado, periodo y búsqueda.
* Panel derecho como ficha informativa.
* Acciones operativas movidas a card/modales.
* Videos de apoyo mediante Google Drive.
* Botón Ver video en card.
* Modal de video Drive.
* Modal Asignar a...
* Modal Reemplazar versión.
* Bloqueo de acciones operativas en documentos archivados.
* Capabilities backend para ocultar/permitir acciones en frontend.

---

## 4. Objetivo de la refactorización

Convertir Nube Corporativa de un MVP funcional a un módulo documental gobernado, seguro, mantenible y preparado para escalar.

El objetivo no es agregar pantallas por agregar, sino ordenar la arquitectura para que el módulo soporte:

* Mayor volumen documental.
* Más tipos de documentos.
* Mejor búsqueda.
* Asignaciones más humanas.
* Monitoreo de calidad documental.
* Mayor control de permisos.
* Menor deuda técnica visual y lógica.

---

# 5. Alcance pendiente

## 5.1 Seguridad backend y permisos reales

### Objetivo

Garantizar que el backend sea la fuente real de permisos, no solo el frontend.

### Pendientes

* Revisar todos los endpoints operativos de Nube Corporativa.
* Confirmar que documentos archivados no permitan acciones por API directa.
* Validar que permisos de publicación, archivado, reemplazo, visibilidad, links y recursos externos se rechacen desde backend cuando no correspondan.
* Agregar capabilities faltantes si aplica, por ejemplo:

  * `can_manage_links`
  * `can_manage_external_resources`
  * `can_restore`
  * `can_delete_permanently`, solo si en el futuro se define.
* Unificar la lógica de permisos en helpers backend.
* Evitar reglas duplicadas o contradictorias entre frontend y backend.

### Criterios de aceptación

* Un usuario no puede forzar acciones no permitidas pegando endpoints manualmente.
* Un documento archivado no permite edición, publicación, reemplazo, asignación ni cambio de visibilidad.
* El frontend solo oculta/guía UI; el backend decide realmente.
* Las capabilities devueltas por API coinciden con lo que los endpoints permiten.

---

## 5.2 Definición formal de ciclo de vida documental

### Objetivo

Definir con claridad qué significa cada estado documental y qué acciones permite.

### Estados base

* `BORRADOR`
* `PUBLICADO`
* `ARCHIVADO`

### Pendiente a decidir

Evaluar si se requiere estado adicional:

* `EN_REVISION`
* `RECHAZADO`
* `OBSOLETO`
* `RESTAURADO`

### Reglas propuestas

#### Borrador

Permite:

* Editar metadata.
* Cambiar visibilidad.
* Asignar a contexto.
* Agregar video.
* Reemplazar archivo.
* Publicar.
* Archivar.

#### Publicado

Permite:

* Ver.
* Descargar.
* Asignar a contexto.
* Agregar o corregir video.
* Reemplazar versión.
* Cambiar visibilidad.
* Archivar.

#### Archivado

Permite:

* Ver.
* Descargar.
* Consultar historial/auditoría.
* Restaurar, si se implementa en una fase posterior.

No permite:

* Publicar.
* Reemplazar versión.
* Asignar.
* Cambiar visibilidad.
* Agregar video.
* Editar metadata.
* Archivar nuevamente.

### Criterios de aceptación

* Cada estado tiene acciones explícitas.
* Las reglas viven en backend.
* La UI refleja las reglas sin contradicciones.

---

## 5.3 Restauración de documentos archivados

### Objetivo

Definir si archivar significa baja definitiva funcional o si debe existir restauración.

### Pendiente

Implementar, si se decide, una acción:

* `Restaurar documento`

### Reglas sugeridas

* Solo administradores documentales pueden restaurar.
* Restaurar no debe publicar automáticamente.
* Restaurar puede regresar a:

  * `BORRADOR`, opción más segura.
  * `PUBLICADO`, solo si estaba publicado antes y conserva visibilidad válida.
* Debe quedar registro en auditoría.

### Criterios de aceptación

* Un archivado no se edita directamente.
* Para volverlo operativo, primero debe restaurarse.
* La restauración queda auditada.

---

## 5.4 Asignaciones más humanas

### Estado actual

La función existe como “Asignar a...”, pero internamente todavía usa campos técnicos como:

* Entity type.
* Entity key.
* Entity id.
* Link role.
* Label.

### Objetivo

Convertir el modal de asignación en una experiencia entendible para operación.

### Pendientes

* Sustituir campos técnicos por selectores reales cuando existan catálogos.
* Permitir asignar a:

  * Sucursal.
  * Apertura.
  * Área.
  * Proyecto.
  * Tarea.
  * General.
* Mostrar nombres humanos en lugar de keys técnicas.
* Evitar que el usuario tenga que saber IDs.
* Mantener internamente `entity_type`, `entity_id`, `entity_key`, pero ocultar complejidad.

### Diseño deseado

El modal debe presentar algo como:

* ¿A qué quieres asignar este documento?

  * Sucursal
  * Apertura
  * Área
  * Proyecto
  * General

Luego:

* Selecciona sucursal/apertura/área.
* Define rol documental:

  * Manual operativo.
  * Procedimiento.
  * Formato.
  * Comunicado.
  * Reporte.
  * Referencia.
* Etiqueta visible opcional.
* Marcar como principal/oficial.

### Criterios de aceptación

* El usuario no escribe IDs manuales.
* La asignación se entiende sin explicación técnica.
* El backend sigue guardando estructura normalizada.
* La búsqueda y filtros pueden usar esas asignaciones.

---

## 5.5 Índice manual de videos

### Objetivo

Permitir que un video Drive tenga una guía de capítulos o pasos, sin almacenar video en el servidor.

### Contexto

Los videos deben permanecer en Google Drive por estrategia de almacenamiento institucional. Suite Ultra solo debe guardar metadata, enlaces, permisos y guía textual.

### Pendientes

Crear estructura para capítulos manuales:

* Título del capítulo.
* Minuto/segundo aproximado.
* Descripción breve.
* Orden.
* Recurso externo asociado.

Ejemplo:

* `00:00` Introducción.
* `01:35` Cómo entrar a Gasca.
* `03:20` Cómo cancelar contrato.
* `05:45` Errores comunes.

### Limitación aceptada

Como el video vive en Drive, no se garantiza salto exacto dentro del reproductor desde Suite. El índice puede funcionar inicialmente como guía visual.

### Criterios de aceptación

* Un video puede tener capítulos.
* Los capítulos se administran desde Suite.
* Los usuarios pueden consultar la guía mientras ven el video.
* No se almacena video en el servidor.

---

## 5.6 Ventana auxiliar para tutoriales Drive

### Estado

Pendiente. No entra en el MVP actual.

### Objetivo

Permitir que el usuario abra un tutorial en una ventana separada mientras trabaja en Gasca.

### Consideración técnica

Gasca suele requerir Firefox. Por eso no debe prometerse Picture-in-Picture avanzado basado en Document Picture-in-Picture, ya que no es una base confiable para Firefox con iframe de Drive.

### Solución futura sugerida

Agregar botón:

* `Abrir auxiliar`

Comportamiento:

* Intenta abrir una ventana pequeña con `window.open`.
* Carga la URL de preview de Drive.
* Si el navegador bloquea popup, abre en pestaña nueva.
* No promete always-on-top.

### Criterios de aceptación

* El usuario puede ver el tutorial fuera de la pestaña principal de Suite.
* Funciona razonablemente en Firefox.
* No rompe el flujo actual de modal interno.
* No duplica almacenamiento de video.

---

## 5.7 Búsqueda interna por contenido

### Estado actual

La búsqueda funciona por metadata visible:

* Título.
* Descripción.
* Categoría.
* Estado.
* Periodo.

### Objetivo

Permitir búsqueda por texto dentro del documento.

### Pendientes

* Extraer texto de PDFs y documentos compatibles.
* Guardar índice textual en base de datos o motor de búsqueda.
* Relacionar texto extraído con versión documental.
* Permitir reindexar documentos.
* Considerar documentos escaneados sin texto.
* Definir si OCR entra o queda fuera.

### Posibles campos

* `document_id`
* `version_id`
* `indexed_text`
* `indexed_at`
* `index_status`
* `index_error`
* `language`
* `page_count`

### Estados de indexación

* `PENDING`
* `INDEXED`
* `FAILED`
* `SKIPPED`

### Criterios de aceptación

* El usuario puede encontrar un documento aunque la palabra solo exista dentro del archivo.
* El índice respeta permisos de visibilidad.
* Si un documento no se puede indexar, queda trazabilidad del error.
* El sistema no bloquea el backend web durante indexaciones largas.

---

## 5.8 Reindex y monitoreo documental

### Objetivo

Crear herramientas para detectar problemas de calidad documental.

### Pendientes

Panel o endpoint de monitoreo que detecte:

* Documentos sin dueño.
* Documentos sin descripción.
* Documentos sin categoría.
* Documentos publicados sin visibilidad válida.
* Documentos sensibles con visibilidad global.
* Documentos sin versión vigente.
* Documentos con links Drive inválidos.
* Videos Drive sin preview.
* Asignaciones huérfanas.
* Documentos archivados con capabilities operativas.
* Documentos con archivos faltantes o Warehouse upload inválido.
* Recursos externos inactivos.
* Duplicados por hash.
* Duplicados por título.

### Criterios de aceptación

* Sistemas/Admin puede ver salud documental.
* Se pueden detectar problemas antes de que los usuarios los reporten.
* No se corrigen automáticamente sin confirmación.
* Cada alerta tiene causa y acción sugerida.

---

## 5.9 Pulido visual y experiencia de usuario

### Objetivo

Reducir fricción visual y mejorar claridad operacional.

### Pendientes

* Ordenar jerarquía de botones en card.
* Separar acciones primarias/secundarias/peligrosas.
* Agregar badges:

  * Tiene video.
  * Publicado.
  * Borrador.
  * Archivado.
  * Confidencial.
  * Global.
  * Asignado.
* Agregar tooltips breves.
* Mejorar responsive móvil.
* Limpiar CSS obsoleto.
* Revisar textos:

  * “Asignar a...” en lugar de “Contexto documental”.
  * “Ver archivo” en lugar de solo “Ver”, si ayuda.
  * “Reemplazar versión” solo visible si aplica.
* Evitar saturación de cards con demasiados botones.

### Criterios de aceptación

* El módulo se entiende sin explicación.
* El panel derecho se mantiene como ficha informativa.
* Los formularios viven en modales.
* Las cards no se ven saturadas en desktop ni móvil.

---

## 5.10 Limpieza técnica frontend

### Objetivo

Reducir deuda técnica acumulada en el componente principal.

### Estado actual

`internal-documents-home.component.ts/html/css` concentra demasiada lógica:

* Listado.
* Filtros.
* Alta documental.
* Preview.
* Videos.
* Asignaciones.
* Reemplazo de versión.
* Confirmaciones.
* Panel derecho.
* Modales.

### Pendientes

Separar en componentes Angular standalone:

* `InternalDocumentsListComponent`
* `InternalDocumentCardComponent`
* `InternalDocumentDetailPanelComponent`
* `InternalDocumentCreateModalComponent`
* `InternalDocumentPreviewModalComponent`
* `InternalDocumentAssignModalComponent`
* `InternalDocumentReplaceVersionModalComponent`
* `InternalDocumentFiltersComponent`

### Reglas

* Cada componente debe tener `.ts`, `.html`, `.css`.
* No usar templates inline.
* No mover lógica al HTML.
* Los servicios siguen centralizados en `InternalDocumentsService`.
* El componente contenedor coordina estado global y filtros.

### Criterios de aceptación

* El HTML principal se reduce significativamente.
* Cada modal tiene responsabilidad clara.
* Las acciones siguen funcionando igual.
* No se cambia backend durante esta limpieza salvo necesidad justificada.

---

## 5.11 Limpieza técnica backend

### Objetivo

Reducir concentración de lógica en `internal_documents_routes.py`.

### Pendientes

Separar lógica en servicios:

* `internal_documents_service.py`
* `internal_document_visibility_service.py`
* `internal_document_links_service.py`
* `internal_document_external_resources_service.py`
* `internal_document_indexing_service.py`
* `internal_document_health_service.py`

Mantener rutas como capa delgada:

* Validar request.
* Llamar servicio.
* Serializar respuesta.
* Manejar errores.

### Criterios de aceptación

* Las rutas no contienen lógica de negocio pesada.
* Permisos se mantienen en utils/guards claros.
* Servicios son testeables.
* Serializadores se vuelven reutilizables.

---

## 6. Exclusiones explícitas

Esta refactorización no incluye de inicio:

* Almacenar videos en servidor Suite.
* Sustituir Google Drive como repositorio de videos.
* IA generativa para responder preguntas sobre documentos.
* OCR avanzado obligatorio.
* Eliminación física definitiva de documentos.
* Firma electrónica.
* Flujos de aprobación documental complejos.
* Sincronización bidireccional con Google Drive.

Estas exclusiones pueden convertirse en fases futuras, pero no forman parte del alcance base de refactor.

---

## 7. Orden recomendado de ejecución futura

### Fase R1 — Seguridad y coherencia

1. Revisar endpoints operativos contra documentos archivados.
2. Completar capabilities faltantes.
3. Definir ciclo de vida documental.
4. Decidir restauración de archivados.

### Fase R2 — UX operacional

1. Pulir cards.
2. Mejorar modales.
3. Hacer asignaciones más humanas.
4. Limpiar panel derecho.
5. Mejorar responsive.

### Fase R3 — Refactor frontend

1. Separar componentes.
2. Reducir HTML principal.
3. Ordenar CSS.
4. Mantener servicios por dominio.

### Fase R4 — Refactor backend

1. Separar services.
2. Adelgazar rutas.
3. Centralizar serializadores.
4. Endurecer permisos.

### Fase R5 — Búsqueda avanzada

1. Indexación textual.
2. Reindex.
3. Estados de indexación.
4. Búsqueda por contenido.

### Fase R6 — Monitoreo documental

1. Salud documental.
2. Alertas de problemas.
3. Links Drive inválidos.
4. Documentos incompletos o huérfanos.

### Fase R7 — Videos avanzados

1. Índice manual de videos.
2. Ventana auxiliar.
3. Mejor metadata para tutoriales.
4. Validación periódica de previews Drive.

---

## 8. Definición de terminado

La refactorización futura se considera terminada cuando:

* Backend controla permisos reales para todas las acciones.
* El frontend solo guía la experiencia y no es la única barrera.
* El panel derecho queda estrictamente informativo.
* Las cards concentran acciones principales.
* Los modales concentran formularios.
* Las asignaciones son entendibles para usuarios no técnicos.
* El módulo tiene monitoreo básico de calidad documental.
* La búsqueda puede evolucionar hacia contenido interno.
* El código frontend está dividido en componentes.
* El backend está dividido en servicios.
* No se rompe el flujo actual de operación.
* No se almacena video pesado en el servidor.
* Drive se mantiene como proveedor externo de videos.

---

## 9. Nota de prioridad

Este contrato queda como backlog documentado. No requiere ejecución inmediata porque el módulo actual ya es funcional en producción.

La prioridad inmediata de Suite Ultra puede continuar en otros frentes. Este contrato debe retomarse cuando se busque estabilizar, escalar o limpiar formalmente Nube Corporativa.
