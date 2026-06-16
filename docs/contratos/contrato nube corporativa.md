# Contrato funcional-técnico final

# Nube Corporativa + Warehouse + Automatizaciones de reportes

# Suite Ultra

## 1. Objetivo general

Diseñar y consolidar la arquitectura documental de Suite Ultra para que exista una separación clara entre:

```text
Warehouse = bóveda técnica, metadata, raw, trazabilidad, auditoría y archivos fuente.

Nube Corporativa = portal gobernado para consulta, descarga y visualización de documentos internos por usuarios finales.
```

La Nube Corporativa será el punto de acceso para documentos internos, reportes publicados, manuales, políticas, formatos, evidencias operativas y archivos generados automáticamente desde procesos del Warehouse.

El Warehouse seguirá siendo la fuente técnica real de archivos, hashes, uploads, metadata, ingestas y trazabilidad.

---

## 2. Principio rector

La arquitectura documental de Suite Ultra seguirá este principio:

```text
Raw first, published later.
```

Todo archivo operativo o automático debe entrar primero al Warehouse o quedar registrado técnicamente en él.

Después, solo si el archivo está listo para consumo de usuarios, se crea una publicación en Nube Corporativa.

Esto evita mezclar archivos técnicos, raw, temporales o de ingesta con documentos visibles para usuarios finales.

---

## 3. Separación conceptual

## 3.1 Warehouse

El Warehouse es la capa técnica.

Responsabilidades:

```text
- Recibir archivos raw.
- Guardar archivos fuente.
- Calcular hash.
- Registrar metadata técnica.
- Registrar origen del archivo.
- Registrar tipo de reporte.
- Registrar periodo del archivo.
- Registrar usuario o proceso que lo creó.
- Mantener auditoría de carga, descarga y archivo.
- Servir como fuente para ingestas estructuradas.
- Conservar trazabilidad de procesos automáticos.
```

El Warehouse puede contener archivos que nunca serán visibles en Nube Corporativa.

Ejemplos:

```text
- Raw descargado desde Gasca.
- Archivos fuente de ingesta.
- Snapshots técnicos.
- Reportes base para Track.
- Archivos auxiliares.
- Archivos generados por jobs antes de validarse.
```

---

## 3.2 Nube Corporativa

La Nube Corporativa es la capa de consumo.

Responsabilidades:

```text
- Mostrar documentos publicados.
- Permitir descarga de documentos autorizados.
- Permitir visualización/preview cuando aplique.
- Administrar categorías documentales.
- Controlar estado documental.
- Controlar confidencialidad.
- Controlar visibilidad por usuario, rol, departamento o sucursal.
- Manejar versión vigente.
- Conservar historial de versiones.
- Registrar auditoría documental.
```

La Nube Corporativa no debe mostrar automáticamente todos los archivos del Warehouse.

Solo debe mostrar documentos publicados o borradores gestionados dentro del módulo documental.

---

## 4. Regla principal de integración Warehouse → Nube

No todo `WarehouseUpload` debe aparecer en Nube.

La regla será:

```text
warehouse_uploads ≠ documentos visibles
internal_documents = documentos visibles/gobernados
```

Un archivo puede existir en Warehouse sin existir en Nube.

Para que un archivo sea visible en Nube, debe existir una publicación documental ligada al upload técnico.

Flujo correcto:

```text
Archivo físico / automático / manual
→ WarehouseUploadORM
→ InternalDocumentORM
→ InternalDocumentVersionORM
→ visibilidad / publicación / permisos
→ Nube Corporativa
```

---

## 5. Tipos de origen documental

La Nube Corporativa deberá soportar documentos de diferentes orígenes.

## 5.1 Carga manual

Flujo:

```text
Usuario autorizado sube archivo desde Nube
→ se registra en Warehouse como internal_documents
→ se crea documento interno
→ queda como borrador
→ usuario configura metadata y visibilidad
→ usuario publica
```

Este flujo aplica para:

```text
- Manuales.
- Políticas.
- Formatos.
- Comunicados internos.
- Evidencias.
- Documentos administrativos.
```

---

## 5.2 Publicación automática desde Warehouse

Flujo:

```text
Job automático genera archivo
→ archivo se registra en Warehouse
→ sistema crea publicación en Nube
→ documento queda publicado o en borrador según política
```

Este flujo aplica para:

```text
- Reportes automáticos por sucursal.
- Reportes generados desde Gasca.
- Reportes operativos diarios.
- Archivos recurrentes de cobranza.
- Documentos generados por procesos internos.
```

---

## 5.3 Documentos técnicos no publicados

Flujo:

```text
Archivo entra a Warehouse
→ se conserva para trazabilidad
→ no se publica en Nube
```

Este flujo aplica para:

```text
- Raw descargado desde Gasca.
- Archivos fuente de ingesta.
- Archivos canónicos internos.
- Snapshots técnicos.
- Archivos usados únicamente por Track/BI.
```

---

## 6. Estados documentales en Nube

La Nube manejará estados documentales.

Estados mínimos:

```text
BORRADOR
PUBLICADO
ARCHIVADO
```

## 6.1 BORRADOR

Documento creado pero no visible para usuarios finales.

Uso:

```text
- Carga manual pendiente de revisar.
- Documento en preparación.
- Documento confidencial sin reglas de visibilidad completas.
```

---

## 6.2 PUBLICADO

Documento visible para usuarios autorizados según reglas de visibilidad.

Uso:

```text
- Documento oficial disponible.
- Reporte automático listo para descarga.
- Manual vigente.
```

---

## 6.3 ARCHIVADO

Documento retirado de consulta principal.

Uso:

```text
- Documento obsoleto.
- Reporte retirado.
- Archivo sustituido.
```

---

## 7. Visibilidad documental

La visibilidad debe vivir en backend y ser validada ahí.

El frontend solo oculta o guía la UI.

Modos de visibilidad:

```text
PRIVATE
GLOBAL
CUSTOM
```

---

## 7.1 PRIVATE

Documento privado.

Solo visible para administradores/publicadores autorizados.

Uso:

```text
- Borradores.
- Documentos en revisión.
- Documentos confidenciales sin reglas.
- Archivos automáticos pendientes de asignar.
```

---

## 7.2 GLOBAL

Documento visible para todos los usuarios con acceso a Nube Corporativa.

Uso:

```text
- Manuales generales.
- Políticas generales.
- Comunicados globales.
- Formatos de uso general.
```

Regla importante:

```text
Un documento sensible/confidencial no puede ser GLOBAL.
```

---

## 7.3 CUSTOM

Documento visible solo para entidades específicas.

Tipos de regla:

```text
- ROLE
- DEPARTMENT
- SUCURSAL
- USER
- GLOBAL controlado, si el modelo lo requiere
```

Cada regla podrá definir:

```text
can_view
can_download
```

Uso:

```text
- Reportes por sucursal.
- Documentos por departamento.
- Documentos para dirección.
- Reportes confidenciales.
- Archivos exclusivos para usuarios concretos.
```

---

## 8. Confidencialidad

La Nube debe distinguir documentos normales de documentos sensibles.

Campo conceptual:

```text
is_sensitive
```

Reglas:

```text
is_sensitive = true → no puede ser GLOBAL
is_sensitive = true → requiere PRIVATE o CUSTOM
is_sensitive = true → debe respetar can_download
```

Ejemplos de documentos sensibles:

```text
- Cobranza.
- Reportes financieros.
- Reportes por sucursal con datos delicados.
- RH.
- Incidencias confidenciales.
- Auditorías.
```

---

## 9. Categorías documentales

La Nube debe mantener categorías entendibles para usuarios finales.

Categorías sugeridas:

```text
- Manuales
- Políticas
- Formatos
- Reportes
- Evidencia Operativa
- Comunicados
- Recursos Humanos
- Finanzas
- Operaciones
- Sistemas
```

Para el flujo de cobranza recurrente:

```text
Categoría: Reportes
Tipo documental: Reporte operativo
```

Si la tabla actual de categorías todavía no tiene estas categorías, se deben agregar mediante migración o seed controlado, no mediante inserts manuales directos en producción.

---

## 10. Versionado documental

La Nube debe manejar una versión vigente por documento.

Modelo conceptual:

```text
InternalDocumentORM
→ representa el documento lógico

InternalDocumentVersionORM
→ representa cada archivo/version ligado al documento

current_version_id
→ apunta a la versión vigente
```

---

## 10.1 Uso correcto de versiones

Las versiones deben usarse cuando un documento lógico se reemplaza o evoluciona.

Ejemplos:

```text
Manual de apertura v1
Manual de apertura v2
Manual de apertura v3
```

---

## 10.2 Reportes diarios automáticos

Para reportes automáticos diarios por sucursal, no se recomienda usar una sola publicación con muchas versiones diarias, porque cada día representa un corte operativo independiente.

Para la primera fase, cada archivo diario por sucursal será un documento independiente.

Ejemplo:

```text
Cobranza recurrente rechazados - VILLA VERDE - 2026-06-16
Cobranza recurrente rechazados - VILLA VERDE - 2026-06-17
Cobranza recurrente rechazados - SAN LUIS - 2026-06-16
```

Esto facilita búsqueda, descarga, permisos y trazabilidad.

---

## 11. Relación con sucursales

Para documentos por sucursal, la publicación debe poder relacionarse con una sucursal.

Regla deseada:

```text
sucursal_raw → sucursal_canon → sucursal_id
```

Prioridad:

```text
1. Resolver sucursal_raw contra aliases/catálogo.
2. Guardar sucursal_canon en metadata.
3. Crear regla de visibilidad CUSTOM por sucursal_id cuando esté disponible.
```

Si todavía no se puede resolver `sucursal_id`, el documento no debe abrirse globalmente.

Política temporal:

```text
Si no hay sucursal_id confiable:
→ visibility_mode = PRIVATE
→ visible solo para administradores/publicadores
```

---

## 12. Publicaciones automáticas desde Warehouse

La Nube debe soportar publicaciones creadas automáticamente por jobs internos.

Regla:

```text
Un job automático no publica directamente un archivo sin pasar por Warehouse.
```

Flujo obligatorio:

```text
1. Job genera o descarga archivo.
2. Archivo se registra como WarehouseUploadORM.
3. Si el archivo es para consumo, se crea InternalDocumentORM.
4. Se crea InternalDocumentVersionORM ligado al WarehouseUploadORM.
5. Se define estado, categoría, sensibilidad y visibilidad.
6. Se publica o queda como borrador según política.
```

---

## 13. Caso inicial: Cobranza recurrente rechazados

## 13.1 Objetivo

Automatizar el reporte diario de cobranza recurrente rechazada desde Gasca y publicarlo para consulta controlada.

---

## 13.2 Flujo técnico actual

```text
reports-scheduler
→ job cobranza_recurrente_rechazados
→ login Gasca con Playwright
→ genera reporte del día
→ descarga XLSX raw
→ procesa rechazados
→ elimina columna definida por negocio
→ separa XLSX por sucursal
→ registra raw en Warehouse
→ registra XLSX por sucursal en Warehouse
```

---

## 13.3 Flujo final esperado

```text
reports-scheduler
→ descarga Gasca
→ guarda raw en Warehouse
→ genera archivos por sucursal
→ registra archivos por sucursal en Warehouse
→ crea documentos en Nube por sucursal
→ publica o deja privado según política de visibilidad
```

---

## 13.4 Qué se publica en Nube

Sí se publica:

```text
- XLSX procesado por sucursal.
```

No se publica:

```text
- RAW descargado desde Gasca.
```

El raw queda solo en Warehouse.

---

## 13.5 Nombres de documentos en Nube

Formato:

```text
Cobranza recurrente rechazados - {Sucursal} - {YYYY-MM-DD}
```

Ejemplos:

```text
Cobranza recurrente rechazados - VILLA VERDE - 2026-06-16
Cobranza recurrente rechazados - SAN LUIS - 2026-06-16
Cobranza recurrente rechazados - SEND MXL - 2026-06-16
```

---

## 13.6 Metadata esperada

Cada documento automático debe guardar metadata conceptual como:

```json
{
  "origin": "automation",
  "job_key": "cobranza_recurrente_rechazados",
  "source": "gasca_auto",
  "business_date": "2026-06-16",
  "warehouse_upload_id": 123,
  "sucursal_raw": "VILLA VERDE",
  "sucursal_canon": "VILLA_VERDE",
  "rows_count": 12
}
```

Si el modelo actual no tiene `metadata_json` en Nube, esta metadata podrá vivir inicialmente en auditoría o en vínculos documentales, pero deberá considerarse como necesidad estructural futura.

---

## 13.7 Estado inicial

Recomendación para producción:

```text
PUBLICADO si ya existe visibilidad por sucursal confiable.
PRIVATE si aún no existe visibilidad fina por sucursal.
```

Mientras Nube no esté liberada para usuarios, puede crearse como:

```text
PUBLICADO + PRIVATE
```

Así el documento queda listo en Nube pero no visible para usuarios finales.

Cuando se cierre la capa de permisos por sucursal:

```text
PUBLICADO + CUSTOM por sucursal
```

---

## 13.8 Sensibilidad

El reporte de cobranza recurrente rechazados debe considerarse sensible.

Configuración:

```text
is_sensitive = true
visibility_mode = PRIVATE o CUSTOM
```

No debe ser GLOBAL.

---

## 14. Scheduler de reportes

Se crea un scheduler independiente del scheduler de Track.

Servicio:

```text
reports-scheduler
```

Responsabilidad:

```text
- Automatizaciones de reportes.
- Descargas externas con Playwright.
- Procesamiento de archivos.
- Publicación en Warehouse.
- Publicación posterior en Nube Corporativa.
```

No debe mezclarse con:

```text
track-scheduler
```

---

## 14.1 Track scheduler

Responsabilidad:

```text
- Track Daily Mart.
- Integraciones Track.
- Cierres canónicos.
- Snapshots operativos.
- Procesos BI propios de Track.
```

---

## 14.2 Reports scheduler

Responsabilidad:

```text
- Reportes externos.
- Reportes automáticos.
- Descargas Gasca.
- Archivos para Nube.
- Jobs documentales.
```

Motivo de separación:

```text
Si Gasca, Playwright o un reporte externo falla, no debe afectar Track.
```

---

## 15. Variables de entorno

El scheduler reutiliza `.env.docker`.

Variables base:

```env
REPORTS_SCHEDULER_ENABLED=true
REPORTS_SCHEDULER_TZ=America/Tijuana
REPORTS_SCHEDULER_SLEEP_SECONDS=60

COBRANZA_RECURRENTE_ENABLED=true
COBRANZA_RECURRENTE_RUN_HOUR=07
COBRANZA_RECURRENTE_RUN_MINUTE=10

GASCA_USER=...
GASCA_PASS=...
GASCA_LOGIN_URL=...
GASCA_REPORTES_URL=...

WAREHOUSE_AUTOMATION_USER_ID=47
```

Regla:

```text
No hardcodear credenciales.
No hardcodear user_id técnico.
No crear .env separado para reports-scheduler.
```

---

## 16. Docker

Nuevo servicio:

```yaml
reports-scheduler:
  build:
    context: ./backend
  depends_on:
    - db
  env_file:
    - .env.docker
  environment:
    APP_ENV: "prod"
  command: python -m app.warehouse.scheduler.reports_scheduler_worker
  restart: unless-stopped
  init: true
  stop_grace_period: 120s
  networks:
    - backend-net
  volumes:
    - /home/adminrdp/sistematicketsultra/uploads:/uploads
  profiles:
    - scheduler
```

El servicio debe compartir el volumen `/uploads` con backend/frontend para que los archivos registrados puedan descargarse.

---

## 17. Reglas de almacenamiento

## 17.1 Local / pruebas

Los archivos generados localmente no deben commitearse.

Ignorar:

```gitignore
backend/storage/
uploads/
```

---

## 17.2 Producción

En producción, los archivos deben guardarse bajo el volumen persistente:

```text
/uploads
```

No se deben guardar archivos críticos únicamente dentro del filesystem efímero del contenedor.

---

## 18. Auditoría

## 18.1 Warehouse

Debe auditar:

```text
- UPLOAD
- DOWNLOAD
- ARCHIVE
```

Para automatizaciones, `audit_details` debe incluir:

```json
{
  "upload_origin": "reports_scheduler",
  "job_key": "cobranza_recurrente_rechazados",
  "artifact_kind": "sucursal",
  "business_date": "2026-06-16",
  "source": "gasca_auto"
}
```

---

## 18.2 Nube Corporativa

Debe auditar:

```text
- DOCUMENT_CREATED
- DOCUMENT_PUBLISHED
- DOCUMENT_UPDATED
- DOCUMENT_ARCHIVED
- DOCUMENT_VISIBILITY_UPDATED
- VERSION_CREATED
- VERSION_DOWNLOADED
```

Si las acciones exactas ya existen con otros nombres, se reutilizan.

---

## 19. Descarga de documentos

La descarga desde Nube no debe bajar directamente desde rutas públicas sin validación.

Debe pasar por backend:

```text
/api/internal-documents/<document_id>/download
```

El backend debe validar:

```text
- Documento existe.
- Documento está publicado, salvo administrador.
- Usuario tiene permiso de vista.
- Usuario tiene permiso de descarga.
- Documento no está archivado.
```

---

## 20. Preview

La Nube puede mostrar preview cuando el tipo de archivo lo permita.

Tipos con preview deseado:

```text
- PDF
- Imágenes
```

Para XLSX, la primera fase puede limitarse a descarga.

No es obligatorio renderizar Excel en pantalla en esta fase.

---

## 21. Permisos

La fuente real de permisos debe ser backend.

El frontend puede ocultar botones, pero no sustituye permisos.

Reglas:

```text
- Backend valida acceso a Nube.
- Backend valida descarga.
- Backend valida publicación.
- Backend valida visibilidad.
- Backend valida documentos sensibles.
```

---

## 22. Roles administrativos

Usuarios administradores/publicadores pueden:

```text
- Crear documentos.
- Editar metadata.
- Publicar.
- Archivar.
- Ver documentos privados.
- Administrar visibilidad.
- Descargar versiones históricas.
```

Usuarios normales solo pueden:

```text
- Ver documentos publicados a los que tienen acceso.
- Descargar documentos si can_download = true.
```

---

## 23. Política inicial de liberación

Como la Nube todavía no está en uso por usuarios finales, se permitirá ajustar estructura, modelos y flujos antes de liberar.

Prioridad actual:

```text
1. Definir arquitectura correcta.
2. Evitar hacks.
3. Evitar que Warehouse se convierta en portal de usuario.
4. Evitar que Nube se llene de archivos técnicos.
5. Preparar visibilidad confidencial/global desde el inicio.
```

---

## 24. Cambios estructurales permitidos antes de liberar Nube

Como Nube aún no está productiva para usuarios finales, se permite:

```text
- Ajustar modelos.
- Agregar campos.
- Agregar migraciones.
- Ajustar rutas.
- Ajustar componentes frontend.
- Cambiar categorías.
- Mejorar permisos.
- Cambiar UX de publicación.
```

Siempre con migraciones Alembic cuando implique DB.

---

## 25. Modelo conceptual ideal

```text
WarehouseUploadORM
- Archivo físico
- Hash
- Tipo técnico
- Periodo
- Fuente
- Auditoría técnica

InternalDocumentORM
- Título
- Descripción
- Categoría
- Estado
- Sensibilidad
- Visibilidad
- Publicación

InternalDocumentVersionORM
- Versión
- warehouse_upload_id
- Archivo vigente
- Notas de versión

InternalDocumentVisibilityORM
- Reglas por rol/departamento/sucursal/usuario
- can_view
- can_download

InternalDocumentAuditORM
- Auditoría documental
```

---

## 26. Criterios de aceptación de Nube

La Nube se considera correctamente alineada cuando:

```text
1. No muestra todos los uploads técnicos del Warehouse.
2. Solo muestra documentos gobernados.
3. Permite documentos globales.
4. Permite documentos confidenciales.
5. Impide documentos sensibles globales.
6. Permite visibilidad por sucursal.
7. Permite descarga validada por backend.
8. Permite publicación manual.
9. Permite publicación automática desde Warehouse.
10. Conserva versión vigente.
11. Conserva historial de versiones.
12. Conserva auditoría documental.
```

---

## 27. Criterios de aceptación del flujo Cobranza recurrente

El flujo se considera correcto cuando:

```text
1. reports-scheduler corre separado de track-scheduler.
2. El job entra a Gasca automáticamente.
3. Descarga el XLSX raw.
4. Guarda raw en Warehouse.
5. Procesa rechazados.
6. Genera archivos por sucursal.
7. Registra los archivos por sucursal en Warehouse.
8. Publica documentos por sucursal en Nube.
9. El raw no aparece en Nube.
10. Los documentos de sucursal quedan sensibles.
11. Los documentos no son globales.
12. Se pueden descargar desde Nube con permisos.
13. El job no duplica resultados de forma descontrolada.
14. Si falla Gasca, no afecta Track.
```

---

## 28. Orden de implementación recomendado

## Fase 1 — Scheduler y job automático

Estado: implementado y validado.

```text
- Crear reports-scheduler.
- Crear job cobranza recurrente.
- Descargar Gasca.
- Procesar XLSX.
- Generar archivos por sucursal.
```

---

## Fase 2 — Publicación en Warehouse

Estado: implementado y validado.

```text
- Registrar raw en Warehouse.
- Registrar sucursales en Warehouse.
- Validar report_type_key.
- Validar WAREHOUSE_AUTOMATION_USER_ID.
```

---

## Fase 3 — Rediseño/ajuste Nube antes de liberación

Estado: pendiente.

Objetivo:

```text
- Confirmar modelo de Nube.
- Confirmar campos obligatorios.
- Confirmar categorías.
- Confirmar visibilidad.
- Confirmar reglas confidenciales.
- Confirmar vínculo con WarehouseUploadORM.
```

---

## Fase 4 — Publicación automática en Nube

Estado: pendiente.

Objetivo:

```text
- Crear documentos en Nube desde uploads de Warehouse.
- Publicar cada archivo por sucursal.
- Definir sensibilidad.
- Definir visibilidad inicial.
- Dejar raw solo en Warehouse.
```

---

## Fase 5 — UX final de Nube

Estado: pendiente.

Objetivo:

```text
- Mejorar exploración por categoría.
- Mejorar búsqueda.
- Mejorar filtros por estado.
- Mejorar filtros por sucursal/departamento si aplica.
- Mejorar mensajes de confidencialidad.
- Preparar vista para usuarios finales.
```

---

## 29. Reglas de trabajo

No editar código manualmente en servidor.

Flujo correcto:

```text
repo local
→ branch
→ cambios paso a paso
→ prueba local/contenedor
→ commit
→ push
→ pull servidor
→ docker compose up -d --build servicio
→ migraciones si aplica
→ validar logs
→ validar UI
```

Toda modificación de DB debe ir con migración Alembic.

En Angular:

```text
- Lógica en .ts.
- HTML solo estructura, bindings simples y llamadas a métodos existentes.
- Componentes separados en .ts, .html y .css.
- No templates inline.
- No estilos inline.
```

---

## 30. Regla de cierre por PR

Cada bloque de implementación debe terminar con:

```text
- Commit limpio.
- Push de rama.
- Descripción lista para Pull Request.
```

La PR debe incluir:

```text
- Qué se agregó.
- Qué se modificó.
- Qué se probó.
- Riesgos.
- Variables de entorno nuevas.
- Migraciones.
- Comandos de despliegue.
```

---

## 31. Resumen ejecutivo

Suite Ultra tendrá dos capas documentales claramente separadas.

El Warehouse será la bóveda técnica: conserva archivos raw, metadata, hashes, auditoría e ingestas.

La Nube Corporativa será el portal gobernado: muestra únicamente documentos publicados o gestionados, con permisos, visibilidad, confidencialidad y versión vigente.

Los reportes automáticos, como Cobranza recurrente rechazados, entrarán primero al Warehouse y después crearán publicaciones en Nube solo para los archivos destinados a usuarios finales.

El raw queda en Warehouse.
Los archivos limpios por sucursal se publican en Nube.
La visibilidad se define por permisos, no por frontend.

Este diseño permite documentos globales, confidenciales, por sucursal, por departamento y generados automáticamente, sin contaminar la Nube con archivos técnicos.
