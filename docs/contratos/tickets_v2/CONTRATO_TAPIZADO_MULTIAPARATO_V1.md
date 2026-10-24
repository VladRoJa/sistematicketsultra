# Suite Ultra — Contrato V1: tapizado de múltiples aparatos en un ticket

**Fecha:** 23 de octubre de 2026  
**Alcance:** Tickets V1 / Mantenimiento → Aparatos  
**Estado:** M1 y M2 integrados; M3 (interfaz, historiales y reportes) implementado en PR pendiente de CI/QA. El backend permanece deshabilitado por defecto para escritura multiaparato.

## Necesidad funcional

Una intervención de tapizado puede afectar dos o más aparatos de una misma sucursal. Debe registrarse como **un ticket operativo**, con responsable, prioridad, compromiso y validación compartidos, pero con trazabilidad individual desde todos los aparatos intervenidos.

La regla existente (PR #1096) que requiere un aparato para Mantenimiento → Aparatos se mantiene. En tapizado, «obligatorio» significará **al menos uno** del inventario, y se permitirá seleccionar varios.

Este contrato **no altera** la programación de preventivos: el contrato de Preventivo mantiene un ticket por equipo programado en lote. Tampoco sustituye el contrato global de Tickets V2; el puente debe poder proyectarse a V2.

## Autoridad y compatibilidad

- **Ticket operativo**: la fila de `tickets` sigue siendo la unidad de trabajo. Su estado, cierre, compromiso, responsable y costos NO se duplican por aparato.
- **Aparato principal legacy**: `tickets.aparato_id` continúa representando un aparato principal y sigue siendo legible por los clientes actuales. No se elimina ni se modifica en M1.
- **Conjunto de aparatos**: nueva tabla `ticket_aparatos`, una fila única por (`ticket_id`, `inventario_id`). En nuevos trabajos múltiples, el aparato principal también tendrá su fila en esta tabla.
- **M1 no sincroniza datos ni cambia lecturas**: la tabla queda vacía inicialmente; no se crea ningún vínculo nuevo hasta aprobar M2. Las consultas actuales a `tickets.aparato_id` siguen funcionando sin cambios. Un backfill histórico, si se autoriza, será una operación posterior, idempotente y simulable.
- **Auditoría**: `vinculado_en_utc` es el momento de creación del vínculo (timestamptz). M2 deberá registrar en el historial del ticket el actor, IDs y motivo de cada adición/remoción de aparatos dentro de la **misma transacción**. No presentar una simple fecha como auditoría completa.
- **Borrado y trazabilidad**: la FK a `inventario_general` es RESTRICT (sin borrado de equipos relacionados). La FK a `tickets` usa CASCADE para respetar el ciclo de vida legacy del ticket; cualquier eliminación de ticket requiere sus permisos y política existentes.

## Contrato de datos aprobado en M1

```text
tickets [existente]
  id                     PK
  aparato_id              FK → inventario_general.id (principal legacy)
  familia_equipo_id       snapshot de familia del aparato principal
  estado, fechas, ...     operativa única del ticket

ticket_aparatos [nueva]
  ticket_id               FK → tickets.id, parte de PK
  inventario_id           FK → inventario_general.id, parte de PK
  vinculado_en_utc        timestamptz NOT NULL
  PK (ticket_id, inventario_id)
  INDEX (inventario_id, ticket_id)
```

M1 no añadió `tipo_trabajo` ni estados. M2 agrega `tickets.tipo_trabajo` (nullable, `TAPIZADO` o NULL) mediante migración Alembic `l23c10202623`, sin cambiar los estados principales. No inferir tapizado solo porque haya más de un aparato; podrían existir otros trabajos colectivos en el futuro.

## M2 — Creación y lectura (implementación propuesta / QA pendiente)

1. Añadir un identificador de tipo de trabajo (p. ej. `TAPIZADO`) y aceptar `aparatos_ids` **solo** en la ruta explícita Mantenimiento → Aparatos. El formato exacto será definido y probado.
2. Validar **cada** ID: entero positivo, único, aparato real, sucursal destino autorizada y vínculo vigente en `inventario_sucursal`. Nunca usar IDs enviados por UI como fuente de permisos; el backend valida sucursal y actor.
3. Rechazar solicitudes sin aparatos, aparatos de otra sucursal, duplicados o mezclas inválidas, antes de cualquier escritura. Sin creaciones parciales.
4. Elegir explícitamente el aparato principal (por ejemplo, primer seleccionado), poblar `tickets.aparato_id` y la tabla `ticket_aparatos` con **todos** los IDs, incluido el principal, en una sola transacción con el ticket y sus adjuntos.
5. Guardar actor/motivo/antes-después en historial auditable. Las ediciones posteriores requerirán control de permisos, validación e historial.
6. Leer conjuntos mediante la unión lógica de `tickets.aparato_id` y los vínculos de `ticket_aparatos`, deduplicados, para incluir tickets legacy. No sustituir lecturas históricas sin QA y medición.

## Contrato de API M2

**Endpoint existente:** `POST /api/tickets/create`, `application/json` o `multipart/form-data` con `payload` JSON y archivo `image` opcional. Usa el JWT y scope actuales.

Ejemplo de body (ilustrativo; **aún no activar desde el frontend**):

```json
{
  "descripcion": "Tapizar respaldos de tres equipos",
  "departamento_id": 1,
  "clasificacion_id": 487,
  "sucursal_id_destino": 4,
  "criticidad": 3,
  "tipo_trabajo": "TAPIZADO",
  "aparatos_ids": [431, 432, 433]
}
```

- `aparatos_ids`: obligatorio al declarar `TAPIZADO`, lista de 1 a 50 IDs distintos (enteros positivos o cadenas decimales enteras); se rechaza `bool`, float, nulos, duplicados y listas fuera del límite.
- `aparato_id`: opcional; si llega, **debe coincidir con el primero** de `aparatos_ids`. El backend decide y persiste el principal.
- `tipo_trabajo`: **exactamente** `TAPIZADO` (mayúsculas). En tickets existentes se omite o queda NULL. Se rechaza `aparatos_ids` si no se especificó el tipo.
- **Activación:** `TICKETS_TAPIZADO_MULTI_ENABLED=false` por defecto. Hasta completar M3 y QA, cualquier solicitud `TAPIZADO` devuelve HTTP 409 sin escrituras. Los tickets V1 normales no dependen del flag.
- Solo admite la ruta real de catálogo Mantenimiento → Aparatos (487 y descendientes); Edificio y Sistemas no pueden declararse como tapizado.
- Para cada ID comprueba que existe en Inventarios, `tipo=aparatos` y vinculación a la sucursal destino. Se aplican las reglas actuales de usuario administrador, sucursal y jefe regional.
- Si un ID falla, devuelve HTTP 400, sin insertar ningún ticket, vínculo, evento ni adjunto.
- En caso válido, crea un ticket único con `aparato_id` principal, `tipo_trabajo=TAPIZADO`, un vínculo por equipo en `ticket_aparatos` y evento de creación `ticket_aparatos_vinculados_v1` con actor, timestamp, lista, principal y motivo.
- Se usa `commit=False` para el ticket hasta que estén registrados todos los vínculos y auditoría. Sin imagen la ruta confirma; con imagen confirma el servicio de adjuntos, **en una sola transacción**.
- La respuesta 201 agrega `tipo_trabajo`, `aparato_id`, `aparatos_ids`; otras respuestas permanecen compatibles.
- `Ticket.to_dict()` agrega `tipo_trabajo`, `aparatos_ids` y, para TAPIZADO, `aparatos` con ID/nombre/código/familia. Para históricos V1 `aparatos_ids` retorna el `aparato_id` único cuando exista, sin consultar la tabla de vínculos.
- M2 no habilita edición/retirada de vínculos. Cualquier mutación futura requiere control de permisos, trazabilidad y transacción independiente.
- M2 NO modifica todavía los endpoints de historial por aparato ni los reportes; ambos se integran en M3. **No habilitar selección múltiple en producción hasta M3 y QA de lectura.**

## M3 — UI, historiales y BI (pendiente)

- Opción **Trabajo de tapizado**, selector múltiple por sucursal, chips/códigos visibles y mínimo un equipo obligatorio. Resto de flujos mantiene el selector sencillo y la validación actual.
- Los historiales por aparato en Tickets e Inventarios deben incluir tickets donde el aparato sea principal **o** esté en `ticket_aparatos`, sin duplicados; respetar filtros de sucursal, roles y visibilidad.
- En Reporte equipos / Todo el total de tickets cuenta **una vez por `ticket.id`**; para visualizar aparatos se listan los códigos relacionados. En familia, `tickets.familia_equipo_id` continúa como snapshot principal legacy; al analizar trabajo con distintas familias debe añadirse un desglose por aparatos afectados, sin sumar falsamente tickets entre familias.
- Un cierre/validación de tapizado es único por ticket; no se fabrican cierres por cada aparato.
- Datos históricos #941, #2301, #2831 y #3191–#3194 no se vinculan automáticamente. Exigen identificación fiable de equipos y una corrección auditada futura.

## M1 — Criterios de aceptación

- Migración Alembic única y reversible: crea tabla e índice sin copiar registros, alterar `tickets` ni `inventario_general`.
- Modelo SQLAlchemy registrado, sin mutación automática ni endpoints nuevos.
- Restricciones DB de unicidad y FK; transacción histórica intacta.
- CI y pruebas ORM/migraciones aprobadas antes de aplicar `flask db upgrade heads`.
- No habilitar nuevas opciones en Angular ni abrir rutas de escritura hasta concluir M2 y M3.

## Riesgos que deben revisarse antes de M2

- Endpoints `/api/tickets/historial-por-equipo`, `/api/tickets/historial/<aparato_id>`, `/api/inventario/.../historial`, consultas de filtrado en Tickets y reporte de mantenimiento actualmente dependen de `tickets.aparato_id`.
- Hay equipos en Inventarios sin familia asignada: no inventar familia ni forzar una sola para un ticket mixto.
- Cambios de sucursal y traslados históricos: exigir asignación correcta al momento de creación y conservar evidencia de vínculo si en el futuro un aparato se mueve de sucursal.
- No introducir código específico de tapizado en M1 que impida después otros trabajos multiaparato.

## M3 — Implementación y QA para despliegue

### Captura

- El subformulario Mantenimiento → Aparatos consulta `GET /api/tickets/tapizado-disponible` bajo JWT. Si devuelve `habilitado:false`, la opción de Tapizado **no aparece**; M2 rechaza peticiones manuales con HTTP 409.
- Con el flag habilitado, el operador marca **Trabajo de tapizado · varios aparatos**. Se conserva la opción original (un solo aparato, obligatorio) sin afectar Sistemas/Edificio.
- Los aparatos disponibles se consultan en la sucursal destino; el componente cancela consultas anteriores al cambiar de sucursal y elimina la selección previa.
- Selector múltiple: búsqueda por nombre, código y marca; filtros combinables por categoría y familia; resumen de seleccionados, quitar uno, tope 50 y mínimo 1.
- El primer aparato seleccionado queda como principal en `aparato_id`; la lista completa llega en `aparatos_ids` exclusivamente cuando `tipo_trabajo=TAPIZADO`. El backend vuelve a validar cada aparato, usuario y sucursal.

### Lecturas e informes

- `/api/tickets/historial-equipo/<id>`, `/api/tickets/historial-por-equipo/<id>`, `/api/tickets/historial/<id>` y `/api/inventario/<id>/historial` incluyen tickets vinculados como principales o secundarios.
- `/api/inventario/equipos-historial` y los filtros por aparato de la bandeja utilizan ambas relaciones.
- El filtro SQL emplea `EXISTS` sobre `ticket_aparatos`, sin multiplicar filas al encontrar un ticket con varios equipos. Se aplica `filtrar_tickets_por_usuario` a los resultados, incluido el alcance regional y el acceso solo asignados.
- En la bandeja se muestra `Tapizado · N aparatos`; el tooltip enumera nombres y códigos.
- El reporte mixto de mantenimiento y el reporte Equipos imprimen nombres/códigos vinculados dentro de la **misma fila del ticket**. Los conteos de tickets y los estados no se multiplican. La familia snapshot del ticket sigue representando el aparato principal: no se interpreta como resultado de una sumatoria de familias secundarias.
- Ticket V1 normal y tickets históricos sin vínculos secundarios mantienen su ruta de lectura anterior.

### Activación y límites

1. Aprobar CI completo (pruebas específicas backend/Angular, regresión de mantenimiento, permisos e Inventarios).
2. Integrar PR y desplegar **backend + frontend** con `TICKETS_TAPIZADO_MULTI_ENABLED=false`; confirmar que Crear Ticket → Aparatos continúe sin opción Tapizado y botón inactivo sin aparato.
3. Confirmar `flask db current` alineado con `l23c10202623`. M3 **no añade migraciones**.
4. Preparar QA autorizado en ULTRA DEMO. Para activación posterior al QA, cambiar configuración operativa `.env.docker` a `TICKETS_TAPIZADO_MULTI_ENABLED=true` y recrear backend mediante Docker Compose (sin editar el código fuente en el servidor). El endpoint autenticado debe devolver `habilitado:true`. Nunca activar sin verificación de scopes.
5. Crear un solo ticket de prueba con 2–3 aparatos reales de ULTRA DEMO, probar que aparece una sola vez en lista, historia individual de cada aparato y una vez en reporte.
6. Probar error por cambio de sucursal, lista vacía, retirar todos los seleccionados, falla de servidor y multipart con imagen.
7. Revertir el flag a false si aparece discrepancia; los tickets previamente creados permanecen en DB y deben seguir siendo consultables.

**Históricos #941/#2301/#2831/#3191–#3194:** no se editan ni vinculan automáticamente. La corrección requerirá inventario exacto y autorización específica.

## M4 — Recepción parcial por aparato (2026-10-23)

**Problema:** el ticket #3209 demuestra que seis equipos pueden salir a tapizarse y regresar en entregas parciales. El estado global y el cierre no pueden sustituir la recepción individual.

### Persistencia y trazabilidad
- Alembic `m23c10202623` agrega a `ticket_aparatos` `recibido_en_utc` y `recibido_por`, ambos opcionales y vinculados por CHECK. **NULL** implica pendiente.
- Los tickets M3 existentes, incluido #3209, inician con sus equipos **pendientes**; ningún backfill de recepciones ni reasignación automática.
- Cada check confirma recepción con actor y timestamp UTC. Reversión exige motivo (máximo 500 caracteres) y deja evento `tapizado_recepcion_aparato_v1` en `tickets.historial_fechas`, con equipo/código, estado previo/nuevo y usuario.
- Cambiar estado individual no modifica la existencia, familia, sucursal, código ni stock del aparato. No modifica automáticamente el estado global del ticket.
- `avance_tapizado` se calcula por lecturas de registros vinculados: `total`, `recibidos`, `pendientes`, `porcentaje`, `parcial` y `completo`. **No se persiste porcentaje**.

### API y permisos
- `GET /api/tickets/tapizado/<ticket_id>/avance`: requiere JWT, lectura scoped con `filtrar_tickets_por_usuario`. Devuelve equipos, progreso, autorización de edición e historial.
- `PATCH /api/tickets/tapizado/<ticket_id>/aparatos/<inventario_id>/recepcion`, JSON `{"recibido":true}` o `{"recibido":false,"motivo":"corrección"}`: requiere JWT, scope del ticket, permiso específico y lock de ticket. No se aceptan operaciones sobre equipos ajenos, cambios duplicados ni edición después de `por_validar` o `finalizado`.
- Editan solo administradores, gerente de la sucursal destino, coordinación autorizada con scope, jefe regional explícito en su alcance, o técnico de mantenimiento asignado al ticket. Ser lector o tener acceso de lectura no concede edición.
- Flag de despliegue independiente `TICKETS_TAPIZADO_RECEPCION_ENABLED` (default `false`). La creación multiaparato conserva `TICKETS_TAPIZADO_MULTI_ENABLED`, sin dependencia de M4.

### Cierre y presentación
- Con 0/6, 3/6 o 5/6 recepciones, se bloquea `cierre/solicitar`, `cierre/gerente-desde-cero` y `cierre/aceptar-creador` con HTTP 409. Con 6/6 puede continuar el flujo normal según rol, atención y validaciones de Mantenimiento; **no se cierra automáticamente**.
- En bandeja: `Tapizado · 3/6 recibidos` y tooltip por equipo con nombre/código y pendiente/recibido.
- Modal de resumen: seis equipos, check individual, progreso porcentual, actor, fecha/hora, historial con código, corrección auditada con motivo. Si falla el GET, la interfaz conserva lectura pero no permite escritura.
- Al cerrar el modal después de cambios, la bandeja refresca preservando filtros.

### Despliegue en orden
1. Aprobar CI e integrar PR. M4 requiere migración antes de iniciar código nuevo, para evitar que el ORM lea columnas inexistentes.
2. En servidor: `git pull` → `docker compose build backend frontend` → `docker compose run --rm --no-deps backend flask db upgrade heads` → `docker compose up -d --no-build backend frontend`.
3. Con `TICKETS_TAPIZADO_RECEPCION_ENABLED=false`, confirmar visualmente el detalle de #3209 en solo lectura y la migración aplicada.
4. Habilitar flag M4 y recrear backend. Sin cambiar el flag M3 (ya activo). Probar **sin marcar todos** una recepción y ver contador 1/6; verificar motivo en reversión y regresar a 0/6. No cerrar el ticket #3209 durante QA si se usa como referencia.
5. Confirmar en API que un usuario sin permisos de mantenimiento/gerencia recibe 403/404, y un ticket parcial recibe 409 al intentar solicitar cierre.
6. Si aparece discrepancia, apagar **solo** `TICKETS_TAPIZADO_RECEPCION_ENABLED`; no borrar columnas ni recepciones.

### Límite funcional
`Recibido` se refiere a entrega física de tapicería; no implica instalado o listo para uso. No existe entrega automática por lotes ni progresión de ticket por porcentaje. El cierre sigue siendo explícito y validado.
