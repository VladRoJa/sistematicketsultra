# Google Ads M6 — Contrato propuesto de correcciones históricas versionadas

**14-oct-2026 · Diseño sujeto a aprobación, NO implementado.** Aplica al Issue #888 / PR #885. Este documento **no autoriza** editar datos productivos, sustituir RAW, activar flags, aplicar migraciones, publicar o hacer merge. El protocolo de publicación actual admite únicamente primera publicación e idempotencia exacta.

## 1. Estado demostrado y restricción principal

- **RAW son evidencia inmutable.** El estado ARCHIVED no borra la evidencia ni elimina conflictos por período: el detector del flujo pareado incluye RAW ACTIVE y ARCHIVED.
- **Hechos estructurados actuales no están versionados por revisión.** Las tablas de campañas y grupos no permiten almacenar sin colisión dos variantes completas para el mismo cliente, clave y día. No corregir mediante UPDATE/DELETE sobre esos hechos.
- La tabla `google_ads_m6_daily_publications` ya permite revisiones y un solo `is_canonical=true` por cliente/día, pero por sí sola **no versiona los hechos**. Cambiar solo el puntero de publicación **no** sería una corrección íntegra.
- `publish_manual_daily_pair()` bloquea deliberadamente sustituciones con `PUBLISHED_DAY_CONFLICT`. `confirm_google_ads_m6_manual_pair()` bloquea conflictos por fecha/RAW, incluso archivados. `inspect_m6_day_for_correction()` es solo lectura, nunca una autorización.
- El ledger de campañas es la fuente de costo de cuenta. Grupos son detalle no aditivo; no duplicar campaña+grupo ni cargar como cero una fecha faltante.

## 2. Evidencia histórica conocida, no instrucciones de actuación

El diagnóstico operativo reportado para **2026-10-13** identificó RAW `21654` (grupo) y `21655` (campaña), inicialmente ACTIVE, sin métricas estructuradas ni auditoría de importación. El parser de campañas rechazó el contenido de `21655` con `No es un Informe de campaña Google Ads`.

Esto **no** prueba que ambos archivos sean válidos, que deban borrarse o que estén todavía en idéntico estado. Antes de actuar, ADMICORP debe consultar `GET /api/integrations/google-ads/manual/correction-status?day=2026-10-13`, revisar la evidencia y documentar los hashes, fecha, actores, reportes y resultado del preflight actualizado. No ejecutar archive/delete/reingesta manual sobre esos IDs como atajo.

## 3. Decisión por estado del día

| Estado consultado | Significado | Acción permitida hoy |
| --- | --- | --- |
| `NO_RECORDS` | Sin RAW ni hechos ni publicación | Flujo normal preview → RAW → ingesta → publicación, sujeto a gates |
| `RAW_ONLY_UNPUBLISHED` | Evidencia RAW previa, sin hechos | Diagnóstico y expediente de incidente; no reemplazar aunque se archive |
| `STRUCTURED_INCONSISTENT` | Filas incompletas o incoherentes | Bloquear toda publicación, auditar causa; no completar mediante insert ad hoc |
| `STRUCTURED_UNPUBLISHED` | Hechos presentes sin publicación | Verificar pareja, procedencia y auditorías; solo flujo actual si cumple todos los controles |
| `PUBLICATION_REVIEW_REQUIRED` | Revision(es) sin canonicalidad activa | Congelar; investigación y reconstrucción auditada |
| `CANONICAL_PUBLISHED` | Una revisión visible en Funnel | Solo reintento exacto actualmente; sustitución requiere nuevo protocolo |

No tomar `replacement_authorized=false`, `can_delete_existing_raw=false` o `can_auto_republish=false` como campos a modificar para habilitar reemplazos: expresan **bloqueos de seguridad**.

## 4. Protocolo mínimo para futura implementación (no autorizado)

### 4.1 Apertura de caso

Expediente inmutable por cliente/día con ID de caso, motivo, solicitante, revisor, fecha Tijuana/UTC, referencias de uploads anteriores, hashes, publicaciones y snapshots de métricas previas. Guardar diferencia entre costos, clics, impresiones y conversiones, así como 27 campañas, 43 grupos y 26 identidades aprobadas. Cualquier cambio de identidad requiere su propio proceso de aprobación: nunca reasignar desde el nombre del archivo.

### 4.2 Nuevas fuentes y facts versionados

- Crear por **migración Alembic** un almacenamiento candidato de hechos campaña/día y grupo/día **asociados a revision/case ID**, que permita coexistencia con revisión previa. No reescribir la tabla histórica M5 ni reusar su ledger para sobrescribir fechas.
- Importar cada nuevo par XLSX como **nuevos RAW append-only** con hash, procedencia, actor, fechas, audiencias y auditoría. Resolver explícitamente la excepción por período en un endpoint de corrección independiente; el uploader genérico y el flujo normal permanecen bloqueantes.
- Parser y preflight idénticos al flujo normal, más comparación lado a lado de la revisión anterior y candidata; mantener hechos y evidencia antiguos consultables. Si falla un archivo o una auditoría, no crear revisión visible.
- Un candidato no es canónico. No aparece en lectura global ni regional y no cuenta como nuevo gasto mientras esté en revisión.

### 4.3 Autorización y promoción atómica

- ADMICORP real verificado en JWT **y base de datos** + permiso Warehouse; solicitud explícita vinculada al expediente, doble confirmación y kill switch de correcciones separado, **OFF** inicialmente. Evaluar aprobación independiente de quien subió los RAW antes de habilitar producción.
- Revalidar bajo transacción PG16 + advisory lock del cliente/día: hashes de bytes RAW, procedencia, idempotencia, hechos 27/43, 26 identidades versionadas, moneda MXN, fecha cerrada, auditorías, versión vigente y expected canonical publication/revision para prevenir carreras.
- **En una transacción:** marcar la publicación anterior no canónica, insertar la revisión nueva como única canónica, escribir auditorías de supersesión y publicación con `previous_publication_id` y `new_publication_id`. En cualquier error hacer rollback de **toda** la promoción. No borrado ni mutación de hechos anteriores.
- Idempotencia estricta: mismo caso, revisión y hashes devuelve mismo resultado; otro contenido/actor/versión debe producir conflicto, nunca sobrescritura silenciosa.

### 4.4 Lector y continuidad

- El lector global debe contar **una sola revisión canónica** por día desde 13-oct-2026; inversión solo del ledger de campañas de esa revisión y jamás sumar grupos.
- El lector regional debe seleccionar **hechos de grupo pertenecientes exactamente a esa revisión y a los uploads aprobados**, con filtro SQL de sucursales autorizadas. No traer gasto de cuenta/no asignado al usuario restringido.
- Si el candidato, fuente, hash, auditoría o canonicalidad son inconsistentes, devolver `requires_review` o cobertura incompleta sin gasto inventado. M5 (24-sep–08-oct) y M6 (09–12-oct) permanecen inmutables.
- Preferir trazabilidad mediante `revision_id`/source ID en resultados administrativos; no exponer hashes completos ni detalles de cuenta a gerentes.

## 5. Pruebas y gates obligatorios antes de abrir escritura

1. PostgreSQL 16: dos versiones de campaña/grupo del mismo día coexisten, FK+unicidad de revisión, máximo un canónico, integridad de auditorías; `alembic upgrade head` sobre ambas historias reconciliadas.
2. Flujo real sintético: caso inicial RAW_ONLY como 21654/21655; RAW previo archivado permanece localizable; archivo incorrecto no autoriza excepción; segundo par se valida sin alterar el primero.
3. Transacción: falla de segunda auditoría, hash desalineado o conflicto concurrente revierte toda promoción; lectores permanecen en revisión previa.
4. SQL real: tras revisión 2 solo cuenta revisión 2, con suma única de campañas; gerente/regional solo ven sus sucursales y fuentes, scope vacío no ejecuta SQL global. Replay exacto no duplica costo.
5. Seguridad: usuario distinto, JWT vencido, falta permiso Warehouse, flag OFF, cambio de actor o de revisión esperada bloqueados; no hay UPDATE/DELETE destructivos sobre RAW/histórico.
6. Regresión: lector histórico M5/M6 09–12, backend, permisos negativos, frontend TypeScript/build, QA visual de mensajes y dictamen independiente.
7. Operación: backup verificado, plan de rollback hacia canónico anterior **sin borrar evidencia**, bitácora de autorización del usuario y ventana de despliegue por commit/merge y migración separada.

## 6. Decisión actual

**HOLD sobre correcciones tardías.** PR #885 puede seguir validándose para primera publicación canónica y lectura, pero **no** puede usarse para corregir/reemplazar RAW 21654/21655 ni días ya publicados. Cualquier habilitación requiere implementación de hechos versionados, endpoint separado, evidencia E2E y aprobación explícita previa.

**Queda fuera de este cambio:** ejecutar corrección real, editar Warehouse, crear migración de hechos alternativos, cambiar switches y modificar Funnel en producción.
