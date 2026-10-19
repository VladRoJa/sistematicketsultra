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
- **La salida siempre tiene `publication_authorized=False`**, incluso si no
  existen descensos. Ante caídas devuelve `BLOCKED_APPROVAL_REQUIRED`.

## Qué no verifica

Un SHA demuestra que el XLSX almacenado coincide con el archivo registrado,
no que Gasca haya aprobado la interpretación de un descenso. Warehouse tiene
auditoría de carga documental, pero no existe en esta implementación una
autoridad KPI que apruebe por sucursal/métrica/par de fechas.

Por ello **no se fabrica una aprobación** a partir de operador de Warehouse,
metadatos XLSX, hashes coincidentes, revisión textual, PR, CI o
`M3BSourceRevisionClaim`. Las 75 disminuciones de octubre siguen bloqueadas
hasta un flujo de aprobación de negocio y revisión formal de procedencia
autorizado separadamente.

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
