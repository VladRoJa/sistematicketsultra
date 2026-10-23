# Suite Ultra — Contrato V1: tapizado de múltiples aparatos en un ticket

**Fecha:** 23 de octubre de 2026  
**Alcance:** Tickets V1 / Mantenimiento → Aparatos  
**Estado:** M1 aprobado y aplicado. M2 (API) propuesta para QA; M3 (UI/reportes) pendiente. NO habilitado para usuarios.

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
