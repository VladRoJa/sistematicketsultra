# M1-F6 / Etapa 1 — Evidencia histórica del universo Track (schema only)

Estado: propuesta implementada en PR, **sin captura automática, sin lectura de certificación y sin despliegue**.

## Problema

La comparación de `track_daily_mart` con el catálogo *actual* de
`track_branch_catalog` no prueba qué sucursales estaban autorizadas en el día
de negocio D. En producción, para 2026-10-13, base #4466 y cierre #4471
coincidieron en 26/26 con cero faltantes o sobrantes, pero esa coincidencia
**no prueba** vigencia histórica ni puntualidad.

## Contrato de persistencia

- `track_version_roster_snapshots`: una cabecera por
  `track_daily_versions.id`, con fecha D, captura timestamp del servidor,
  conteo esperado, digest SHA-256 y sello único opcional.
- `track_version_roster_members`: conjunto exacto de sucursales esperadas
  (`version_id` + `sucursal_canon` PK); se conserva el
  `sucursal_id_at_capture` como valor escalar sin FK al catálogo mutable.
- Fuente de captura inicial permitida:
  `LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE`. Es evidencia contemporánea de
  **generación de versión**, NO prueba de que el catálogo tenía vigencia en D.
- `historical_roster_verified` es **FALSE obligatorio por DB** en esta etapa.
  Cambiarlo necesita un contrato posterior que demuestre vigencia y linaje.
- Una cabecera solo puede crearse para versión `running` con
  `started_at_utc` y fecha D idéntica. La DB fija
  `captured_at_utc`; versiones ya `success` como #4466/#4471 no se pueden
  reconstruir retrospectivamente mediante este mecanismo.
- Escribir miembros mientras el snapshot está abierto; el sellado requiere
  `expected_branch_count` filas, bloquea nuevas inserciones y es irreversible.
  Los triggers bloquean UPDATE/DELETE de miembros y cualquier mutación posterior
  de la cabecera. El FK a Track es RESTRICT; no borrar versiones con evidencia.
- Hash: 64 caracteres hexadecimales minúsculos en esta etapa. Todavía no se
  computa ni coteja con los miembros; eso pertenece a la Etapa 2 y es otro
  motivo para **no certificar** por mera existencia de un snapshot sellado.
- La migración crea tablas vacías y rechaza downgrade si hay registros. No
  genera seeds, historiales ficticios ni backfill.

## Gates siguientes

1. **Etapa 2 / Captura transaccional**: construir listado Track no-demo,
   normalizarlo y producir hash reproducible; capturarlo dentro del ciclo real
   antes de construir el mart; sellar solo si la versión y el conteo coinciden,
   con fallos de captura tratados sin estados verdes. Revisar todos los flujos
   de versión: base, preview, cierre pedido y backfill. Nunca inferir vigencia
   retroactiva.
2. **Etapa 3 / Vigencia histórica**: definir fuente autorizada para altas,
   bajas y correcciones efectivas por día/sucursal y su gobierno/auditoría.
   No usar solo `captured_at_utc` como fecha de vigencia.
3. **Etapa 4 / Lectura SLA**: comparar roster efectivo verificado y miembros
   sellados contra filas exactas del mart, validar hash, éxito de versión,
   horario de publicación (base 02:00/03:00 D+1); separar cierre canónico y
   conservar `UNKNOWN` en cualquier ausencia/ambigüedad.

## Validaciones mínimas

En PostgreSQL 15 y 16 con datos sintéticos:
- migration Alembic `f6roster1014` (único parent `c856map1014`);
- integridad de FK, versión `running`, fecha D, checksum formato, unicidad;
- impedir versión histórica `success` y sello con cardinalidad incorrecta;
- append-only de miembros, sello irreversible y bloqueo de deletes;
- no cambiar `historical_roster_verified` ni eliminar la evidencia por downgrade.

**No cambia** cálculos Track, Funnel, Warehouse, permisos, schedules, endpoints,
semáforos ni producción en esta etapa.
