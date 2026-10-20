# Suite Ultra — M3-B / Auditoría autoritativa de fuentes KPI (solo lectura)

**Alcance:** verificar procedencia documental de KPI Desempeño mediante Warehouse y
comparar las dos series MTD para identificar descensos. No es un sistema de
aprobación ni un permiso para promover snapshots o escribir Track.

## Fuente verificable

`audit_kpi_desempeno_m3b_provenance(candidate_snapshot_ids, canonical_snapshot_ids, expected_branch_count=26)`
se ejecuta solo dentro de un contexto Flask autorizado. Recibe mapas explícitos
`date -> snapshot_id`; no elige versiones por mayor ID ni por fecha de carga.

- Exige fechas contiguas desde el primer día de un único mes.
- Revalida que cada baseline es el único canónico de su fecha y que cada
  candidato distinto del baseline permanece no canónico.
- Exige report_type KPI, snapshot_kind daily, 26 sucursales por fecha
  (configurable únicamente para tests sintéticos), sin rechazo de filas.
- Exige evento de auditoría `UPLOAD` con mismo `uploaded_by_user_id`, pero
  **no lo interpreta como aprobación de una corrección de negocio**.
- Usa `_read_parsed()` de M3-A, que verifica archivo almacenado, SHA-256,
  tamaño, formato de hoja, período y fecha embebida, sin alterar bytes.
- Comprueba que las **tres métricas F3** (`reactivaciones`, `bajas`,
  `socios_activos_del_mes`) y la identidad de cada sucursal coincidan
  exactamente entre XLSX y filas ORM. No presume equivalencia de aliases.
- Rechaza un roster distinto entre fechas o frente a cada canónico anterior.
- Calcula descensos por sucursal y métrica entre fechas consecutivas, con
  snapshot ID, upload ID y SHA de ambos extremos.
- Compara contra la serie canónica previa y reporta
  `shared_declines`, `new_declines` y `removed_declines`.
- **La salida siempre tiene `publication_authorized=False`**: la auditoría
  nunca ejecuta ni autoriza por sí misma una publicación. Ante descensos,
  devuelve `SOURCE_VERIFIED_WITH_MTD_REVISIONS` y anota cada disminución
  como `FUENTE_VERIFICADA_REVISION_MTD`; sin descensos, `SOURCE_VERIFIED`.
  La caída del acumulado no constituye por sí sola una inconsistencia.

## Autoridad de datos y separación entre auditoría y ejecución

**Gasca es la fuente de verdad de KPI Desempeño.** Cuando un operador de Suite
Ultra autorizado ejecuta el flujo de actualización, está solicitando que el
sistema use los últimos archivos oficiales disponibles de Gasca. No se requiere
que un tercero apruebe individualmente una disminución MTD confirmada por los
archivos originales.

La auditoría verifica integridad técnica de los datos **almacenados**: bytes,
tamaño y SHA-256 frente al registro Warehouse, fecha/identidad y concordancia
entre XLSX y snapshot. El evento UPLOAD documenta una carga; por sí solo no
demuestra que un documento provenga externamente de Gasca. El flujo operativo
deberá restringir fuentes/cargadores confiables y verificar que el lote seleccionado
corresponda al corte más reciente y completo. No debe confiar en un hash,
nombre de archivo o solicitud externa para declarar fuente oficial.

**Frontera de ejecución:** este módulo solo reporta procedencia y diferencias;
no contiene permisos de usuario, transacciones de promoción, reconstrucción,
rollback ni revalidación del estado actual de Warehouse justo antes de escribir.
`publication_authorized=False` significa que no tiene esa capacidad, **no**
que se necesite una aprobación humana adicional por cada descenso. La
publicación, canonicalidad y reconstrucción quedan en un flujo posterior que
debe validar un lote completo e impedir lecturas mixtas.

## Caso octubre 2026 (solo referencia, no credencial de ejecución)

La auditoría manual previa identificó 15 fechas (1–15/oct), 14 candidatos no
canónicos y una fecha sin diferencias (15/oct). Sus resultados reportaron
75 disminuciones en la serie propuesta de bajas; 59 compartidas con la serie
anterior, 16 nuevas y seis desaparecidas. La función debe poder reproducir esa
comparación usando IDs exactos desde Warehouse **sin escribir producción**,
pero estas cifras no reemplazan una ejecución auditada del nuevo servicio.

## Límites

No rutas HTTP nuevas, no scheduler, no migraciones, no permisos nuevos,
no nuevas tablas, no mutaciones Warehouse/Track, sin carga de datos reales en CI,
sin promoción, sin reconciliación/autorización de publicación. La CI sintética
valida el contrato de origen y rechaza alteraciones de bytes, drift DB,
auditoría faltante, discontinuidad de fechas, cambios de canónico y roster.
