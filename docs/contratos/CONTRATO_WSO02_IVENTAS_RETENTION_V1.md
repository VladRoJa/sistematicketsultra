# WSO-02 — Optimización de almacenamiento iVentas (contrato de paquete)

Fecha: 2026-11-02. Estado: **análisis sobre main; sin cambios en producción**.

## Objetivo
Reducir tamaño y crecimiento de iVentas Marketing sin romper el Funnel Original o Histórico, Contact Center, campañas, automatización, integridad de cortes ni KPI comerciales.

## Alcance previsto
1. Diagnóstico read-only: espacio real PostgreSQL desglosado en heap/índices/TOAST para `marketing_iventas_sync_runs`, `marketing_iventas_raw_pages`, `marketing_iventas_contacts`, `marketing_iventas_contact_tags` y `marketing_iventas_branch_failures`.
2. Retención consciente de consumidores: construir una vista previa de candidatos con criterios explicables y alcance de filas/bytes; comprobar referencias y probar paridad del Funnel por fechas.
3. Ejecución controlada, solo cuando exista evidencia suficiente y autorización de borrado real; conservar auditoría de resultados agregados, y no improvisar DELETE sobre millones de contactos.
4. Verificar liberación física y KPI/Track/Marketing después de operar.

Archivos principales:
- `backend/app/models/marketing.py` — ORM actual de sync runs, páginas RAW, contactos, tags.
- `backend/app/services/marketing_sales_funnel_service.py` — lector de runs canónicos.
- `backend/app/services/marketing_sales_funnel_cutoff_service.py` — lector de cortes históricos exactos.
- `backend/app/services/marketing_iventas_run_lifecycle_service.py` — canonicalidad.
- `backend/app/services/automation_control/job_read_service.py` — historial operativo por sync run.
- `backend/scripts/ops/wso02_iventas_storage_diagnostic.sql` — diagnóstico seguro.

## Hallazgo fundamental del código
- Funnel general usa runs **canónicos COMPLETED** para el mes y ventana histórica de atribución.
- Funnel histórico de corte exacto **NO usa solo is_canonical**: en `_select_exact_iventas_run()` busca el `COMPLETED` con mayor `id` para `(period_key,date_from,date_to)`. Por tanto, runs no canónicos de cortes anteriores son datos requeridos.
- `marketing_iventas_raw_pages.payload_json` contiene carga RAW; los contactos normalizados y tags pueden derivarse de la misma corrida, pero no son automáticamente borrables si la corrida sigue siendo legible.
- Automatización inspecciona historial de `marketing_iventas_sync_runs` incluso para corridas no canónicas. No eliminar metadata de runs sin decidir qué información histórica conservar.
- FKs del modelo: páginas, contactos y fallos apuntan a run, tags a identidad compuesta de contacto. **No confiar en cascadas** para decidir protección.
- No existe autorización para borrar parte de las corridas activas ni los contactos históricos necesarios para los cortes.

## Hipótesis y gates
**H1 (por medir):** existen múltiples `COMPLETED` con idéntico `period_key/date_from/date_to`; solo uno es el seleccionado por el lector de corte. Incluso si es desplazado para Funnel, puede conservar valor operativo/auditable.

**H2 (por medir):** la distribución de 12 GB se concentra en contactos repetidos, índices, TOAST del RAW o combinación; la estrategia depende del desglose real, no de la cantidad de corridas.

No implementar todavía un job de borrado ni una migración: primero resolver la distribución del almacenamiento, retención por cortes, FKs, reader contract y política para datos de auditoría.

### Criterios de aceptación
- Preview exhaustivo por periodo, estado y lector con candidatos NO destructivos.
- Cero pérdida de cortes disponibles y salidas KPI verificadas con datos sintéticos y caso real controlado.
- No perder evidencia vigente de Contact Center, campañas, Track o automatización.
- Sin DELETE de tablas completas, sin CASCADE implícito, sin cambio de canonicalidad ni scopes.
- Distinción explícita: propuesto / probado / merged / desplegado / ejecutado en producción.

## Referencia histórica (no reconfirmada en este diagnóstico)
Se estimaron ~12 GB para iVentas, 5 corridas canónicas y 359 no canónicas; esos números deben validarse contra PostgreSQL actual antes de cualquier conclusión sobre ahorro.

## Diagnóstico productivo de solo lectura — 2026-11-02

Resultados comunicados del SQL WSO-02, sin modificaciones:

| Tabla | Total | Heap | Índices | TOAST y otros |
|---|---:|---:|---:|---:|
| `marketing_iventas_contacts` | **12 GB** | 7,394 MB | **4,855 MB** | 2,104 kB |
| `marketing_iventas_raw_pages` | 1,024 MB | 49 MB | 18 MB | 957 MB |
| `marketing_iventas_contact_tags` | 628 MB | 339 MB | 289 MB | 128 kB |
| `marketing_iventas_sync_runs` | 192 kB | 64 kB | 96 kB | 32 kB |
| `marketing_iventas_branch_failures` | 8,192 bytes | 0 bytes | 8,192 bytes | 0 |

Las ~16,948,868 filas de contactos reportadas por `pg_class.reltuples` son una **estimación de estadísticas**. El inventario de 365 corridas es exacto:

- 5 canónicas, con suma de contador `contacts_unique` de 414,324.
- 69 últimas completadas por corte (excluyendo las canónicas), con contador 3,424,420.
- 216 `COMPLETED` desplazadas para la misma clave de corte; contador 11,038,412.
- 75 `FAILED/PARTIAL`; contador 2,213,736.
- Canónicos actuales: `IVENTAS-2026-07` hasta `IVENTAS-2026-11`, una corrida por mes.
- Solo cuatro FKs internas: tags → contacts, raw pages/contacts/branch failures → sync runs. **Esto NO demuestra ausencia de referencias lógicas.**

### Referencia lógica encontrada que exige protección

`contact_center_contact_links` guarda `source_type='IVENTAS_CONTACT'` y `source_row_id` sin FK hacia `marketing_iventas_contacts.id`; `contact_center_iventas_reconciliation_service.py` escribe esos IDs. Además `contact_center_service.py` puede consultar contactos por ID puntual. El borrado de contactos con vínculos así podría dejar identidades de CRM incongruentes aun sin error SQL. El diagnóstico ampliado 7 clasifica **`PROTECTED_CONTACT_CENTER`** para toda corrida que contenga alguna referencia lógica vigente.

Los 216 `SUPERSEDED_COMPLETED_REVIEW` son **candidatos de análisis**, no todavía autorización de `DELETE`. El conteo exacto de filas persistidas por bucket y la dimensión de referencias lógicas se obtendrán del diagnóstico ampliado. Las 75 incompletas se mantienen en revisión separada para no borrar evidencia de fallos operativos.

### Espacio físico: advertencia operativa

Eliminar filas de PostgreSQL por `DELETE` **no equivale a liberar inmediatamente bytes a `df -h`**. `VACUUM` normal recupera espacio *internamente* para reutilizar; reducir archivos físicos de la tabla y sus índices requiere una estrategia adicional como reescritura controlada (`VACUUM FULL` con bloqueo fuerte) u otra opción respaldada por extensiones. No programar estas acciones sin medición, plan de bloqueo, espacio temporal y compatibilidad. WSO-02 no debe prometer recuperar 12 GB solo por eliminar 216 corridas.
