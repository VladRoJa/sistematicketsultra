# Issue #856 — Modalidad de límites operativos sin saldo Meta (propuesta)

Estado: DRAFT — revisión y QA aislado, NO DEPLOY.

## Decisión de producto

**Nunca exigir ni inventar “mensajes restantes” cuando el proveedor no publica ese saldo.**
El límite nominal de iVentas (por ejemplo 100,000 mensajes/día) no es el saldo disponible.
La modalidad operativa representa solamente el riesgo que Suite Ultra puede controlar.

Se mantienen los registros históricos de atestaciones, el contrato de aprobaciones
antiguas, los bloqueos reales del proveedor y los kill switches duales.

## Registro de política

Operador con privilegios globales registra una revisión append-only por canal con:

- identidad exacta de canal y clave de portafolio compartido;
- máximo **interno** positivo por canal en 24 h (explícito, no un default ficticio);
- máximo **interno** positivo para el portafolio en la misma ventana (idéntico para los canales asociados);
- límite nominal comunicado por el proveedor como **referencia opcional**;
- cuenta/número alias, zona horaria de referencia, fuente/criterio y auditoría.

La configuración no consulta ni modifica Meta; no activa envíos.

## Contabilidad y aprobación

- Contador móvil de 24 h en UTC: intentos V2 registrados por Suite en estado
  SUBMITTING, SUBMITTED, SCHEDULED, RECONCILIATION_REQUIRED, RETRY_ELIGIBLE,
  RETRY_EXHAUSTED o PROVIDER_ERROR (excepto NOT_CREATED_CONFIRMED).
- Los intentos ambiguos sin timestamp / sin reconciliar fuera de ventana bloquean,
  y los consumos externos a Suite son desconocidos.
- Se incluyen reservas activas del mismo canal o portafolio; pueden
  sobreestimarse mientras un intento y su reserva coinciden (conservador).
- Agrupación por claves de portafolio; límites inconsistentes entre canales
  del mismo portafolio o cambios de mapeo en ventana bloquean.
- No se incluye la propia reserva al revisar el mismo plan autorizado.
- HOLD por insuficiencia; no hay deduplicación nueva entre campañas comerciales.
- Reserva serializada con advisory locks por ámbito, aprobación 15 min,
  costo confirmado en MXN, manifest y digest inmutables.
- El nuevo manifest usa `basis=SUITE_OPERATOR_ROLLING_24H_V1`, sin
  attestation_id (NULL permitido tras migración); registra revision_id y límites
  aceptados para detectar cambios antes de materialización y ejecución.
- Aprobaciones legacy mantienen `OPERATOR_ATTESTED_NOT_META_VERIFIED`
  y los IDs de evidencia original sin backfill ni cambios retrospectivos.

## Límites de alcance / garantías

**No** asegura el cupo actual Meta, la calidad de cuenta ni que el proveedor
acepte el POST. **No** detecta envíos directos en iVentas, Meta ni fuera de
los caminos V2 instrumentados. Un cambio externo puede rechazar el mensaje;
en ese caso se registra el estado real y se exige conciliación si es ambiguo.

El balance operador **nunca se llama cuota Meta restante**.
El cálculo usa ventana móvil UTC, no un calendario local ni reinicio Meta supuesto.

## Aceptación

- Pruebas sintéticas: modalidad legacy sigue, limites por canal/portafolio,
  actividad ajena dentro del portafolio, reserva concurrente, HOLD, errores
  ambiguos, NULL en attestation solo para nuevo manifest, rechazo de caps
  inconsistentes y protección de liberación HELD.
- Migración Alembic de e856d3c21013 → f856opcap1013 probada en PostgreSQL 16
  aislado, sin borrado/backfill, downgrade protegido con datos nuevos.
- Angular build, pruebas de rutas/permisos y kill switches OFF.
- Sin merge, despliegue ni POST provider antes de revisión explícita.

## Prueba QA 26 sucursales

La validación de 26 canales se maneja separadamente como 26 campañas internas
QA_MANUAL (un contacto por sucursal), preflight y autorización por lote;
el envío de cada lote requiere confirmación explícita **en esa ejecución**.
El presente contrato no autoriza enviar ni levantar kill switches.
