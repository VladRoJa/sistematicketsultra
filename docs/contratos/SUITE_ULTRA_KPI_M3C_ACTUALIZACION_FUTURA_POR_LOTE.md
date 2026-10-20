# Suite Ultra — KPI M3-C: contrato de actualizaciones FUTURAS por lote

**Estado:** propuesta de diseño, sin implementación ni ejecución productiva.
**Fecha:** 2026-10-20.
**Antecedente operativo declarado por el usuario:** la actualización histórica
de KPI Desempeño **1–15 de octubre de 2026 ya fue ejecutada**. NO se incluye
como tarea pendiente, no se programa su repetición y no se propone backfill
retroactivo automático. Este documento no certifica el resultado de esa
ejecución ni sustituye su auditoría de cierre.

## Propósito y autoridad de la fuente

Cuando un operador autorizado de Suite Ultra solicita **una nueva actualización**
de KPI Desempeño, la intención es adoptar los últimos datos oficiales disponibles
de Gasca para las fechas solicitadas. Una disminución de un acumulado MTD no
constituye por sí sola un error ni requiere un aprobador extra: debe concordar
con la fuente original verificada. Errores de identidad, fecha, ausencia de
archivos, duplicaciones contradictorias, bytes/SHA, integralidad y trazabilidad
sí deben detener la ejecución.

Warehouse verifica los **bytes almacenados**; un evento `UPLOAD` o un SHA,
aisladamente, no demuestra que el documento proceda del servicio oficial de
Gasca. La adquisición de archivos oficiales es una responsabilidad de
integración separada, con fuente y usuario/cuenta de servicio confiables.

## Inventario existente (NO reemplazar por implementaciones duplicadas)

| Componente | Responsabilidad real actual | Límite |
| --- | --- | --- |
| `backend/app/warehouse/backfill/import_fuentes_extraidas.py` | Importar archivo/inventario histórico; `--commit` explícito; JSONL | Opera por registro/día; `--skip-existing-snapshots` impediría aplicar revisiones a fechas existentes; no es ejecutor transaccional de lote |
| `backend/app/warehouse/services/kpi_desempeno_staging_service.py::stage_kpi_desempeno_upload()` | Validar XLSX, comparar M1 y guardar candidato no canónico | Candidato por día; no publica |
| `backend/app/warehouse/services/kpi_desempeno_m3b_provenance_audit.py::audit_kpi_desempeno_m3b_provenance()` | Releer archivo, verificar SHA/bytes/snapshot, serie mensual y revisiones | Solo lectura; `publication_authorized=False` |
| `backend/app/warehouse/services/kpi_desempeno_m3b_verified_plan.py::plan_kpi_desempeno_verified_source_impact()` | Clasificar cambios F3 en fuente verificable y determinar bloqueos | Planificación, `READY_FOR_PROCESSING` no publica |
| `backend/app/warehouse/services/kpi_desempeno_repository.py::persist_kpi_desempeno_snapshot()` | Ingesta con canonicalidad del snapshot por fecha | Hace `db.session.commit()` por llamada; no publica lote atómico |
| `backend/app/warehouse/backfill/rebuild_track_from_sources.py` | Refresh de fuentes y mart históricos con `--commit`, JSONL | Confirma refresh de fuentes antes de versión/mart; no garantiza atomicidad entre fechas; dry-run no calcula todo |
| `backend/app/warehouse/services/track_daily_pipeline_service.py::run_track_daily_pipeline_for_date()` | Flujo diario que **también descarga y reingesta Gasca** | NO llamarlo sin control en un replay histórico: descargaría de nuevo y afectaría otras fuentes |
| `backend/app/warehouse/services/track_daily_query_version_service.py` | Lectores prefieren cierres efectivos | Blindaje de candidatos M3-C1 ya integrado; conservar esta invisibilidad |

## Contrato de una futura solicitud

Entrada de un comando autenticado, con permisos de backend:
- `scope`: fechas de negocio exactas (ejemplo: inicio/fin del corte), mismo mes
  o división explícita entre meses.
- Identificador inequívoco del **lote oficial de Gasca** y evidencia de
  adquisición autenticada (no un SHA/manual claims por sí solos).
- Mapa inmutable `fecha -> upload_id / SHA-256 / candidate_snapshot_id`,
  junto con la versión canónica esperada para cada fecha.
- Política explícita de modos: `preview` por defecto; un comando de
  `execute` futuro exige autorización del operador, preflight aprobado y
  verificación de que los snapshot IDs no cambiaron.
- Identificador de operación idempotente, estable para los mismos archivos,
  fechas, sucursales y modo. Una solicitud repetida sin nueva fuente debe ser
  un **no-op**; si ya se ejecutó, devolver los IDs/resultados existentes.
  **Nunca** usar el reloj de descarga como criterio de cambio de valores.

### Preflight obligatorio: solo lectura

1. Confirmar que el lote entrante es íntegro, oficial y más reciente para el
   corte elegido; sin suponer que el nombre del archivo prueba procedencia.
2. Leer canónicos actuales y comparar con los `expected_snapshot_ids`.
   Si ya coinciden con la fuente más reciente, `ALREADY_CURRENT`: sin rebuild.
3. Verificar fechas contiguas, 26 identidades esperadas o el roster oficial
   controlado, hashes, uploads y F3 contra XLSX, mediante #955 y #952.
4. Calcular por día/sucursal métricas y derivados D / D+1. Las reducciones
   respaldadas por ambos archivos oficiales son revisiones válidas.
5. Detectar dependencia de otras fuentes (agregadoras, Venta Total, cierre
   diario) y política por periodo antes de tocar mart o informes.
6. Emitir un **plan persistible y auditable** que indique versiones anteriores,
   candidatas, cambios, días/lectores/reportes dependientes, conflictos y
   razón de no-op. El preflight no cambia tablas ni ejecuta schedulers.

## Publicación y reconciliación: implementación POSTERIOR

**No usar como atajo el commit por día de scripts existentes.** El patrón
propuesto es preparar snapshots y versiones derivados de forma invisible,
validar el lote completo y definir una frontera de publicación consistente:

- Bloqueo lógico/advisory por familia de reporte y rango/mes, con comprobación
  compare-and-swap de todos los canónicos esperados. Evitar dos actualizaciones
  solapadas. No asumir que los advisory locks de otro servicio cubren todo el
  rango automáticamente.
- Preparar versiones candidatas de Track sin `is_current=true` y sin exposición
  a lectores. Reutilizar los builders existentes separando cómputo de
  `commit()` donde sea necesario; toda refactorización requiere QA aislado.
- Publicar canonicalidad Warehouse y punteros Track visibles únicamente
  después de revalidar preparación completa. Si no es posible un commit SQL
  único para las tablas implicadas, **no declarar atomicidad**: se requiere
  una estrategia explícita de estado de lote, gate de lectores, compensación
  o replay seguro antes de habilitar la función.
- Los reportes derivados deben regenerarse desde versiones publicadas,
  con tracking independiente de estados/errores y reconciliación verificable.
  Un email/archivo externo emitido no forma parte de una transacción SQL.
- Registrar en auditoría quién solicitó, fuente oficial, hashes, canónicos
  antes/después, versiones Track y reportes regenerados; rechazo y motivo.
- `FAILED` nunca equivale a actualización concluida. Reintentar con la MISMA
  identidad de lote debe continuar sin duplicar ni volver a elegir archivos.

Cualquier tabla adicional de operación/versionado exige **migración Alembic**.
Scheduler y endpoints productivos permanecen fuera de alcance hasta autorización
y tests de carreras, rollback y observabilidad.

## Criterios de aceptación del futuro ejecutor

1. Lote idéntico a canónicos actuales: no-op, **cero** cambios/scheduler.
2. Corrección descendente Gasca verificable: no bloquear por signo;
   preservar exactamente nuevo valor, fecha y evidencia.
3. Cambio de hash, identidad, fecha, roster, baseline concurrente o archivo
   oficial incompleto: bloqueo **antes** de publicar.
4. Corte hasta día 15: no exigir 16 si está fuera de la serie oficial.
   Falta de un día **interno** del corte: bloqueo.
5. Candidato Track incompleto o error en cálculo: ningún nuevo dato visible.
6. Error después del límite de publicación: estado `RECONCILIATION_REQUIRED`
   y recuperación idempotente, no éxito ficticio.
7. Lectores Track no ven versiones candidatas; validación de dashboard y
   reportes por fecha después de reconciliar.
8. Pruebas en PostgreSQL real sintético: doble ejecución, colisiones,
   concurrencia, reinicio entre fases, versión ya publicada y el no-op de
   intervalos históricos **sin tocar información productiva**.

## Situación operativa hoy

- **Octubre 1–15:** actualizado previamente según confirmación del usuario;
  ningún paso de esta propuesta debe volver a procesarlo automáticamente.
- **#955 y #952:** código de auditoría/planificación integrado, no un ejecutor
  de publicación.
- **Este cambio:** solo diseño. No scripts lanzados, no reingestas, no commits
  en DB, no canonicalidad modificada, no pipeline Track ni migraciones.
