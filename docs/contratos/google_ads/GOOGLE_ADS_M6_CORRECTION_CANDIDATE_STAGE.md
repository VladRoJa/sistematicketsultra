# M6 correcciones tardías — fase 2 (candidato, servicio interno)

Este servicio es intencionalmente **inaccesible por HTTP**. No tiene endpoint,
menú, RAW uploader excepcional ni conexión al lector Funnel. La bandera
`GOOGLE_ADS_M6_CORRECTION_CANDIDATE_ENABLED` está **OFF** por defecto.

`stage_m6_correction_candidate` exige identidad real ADMICORP vía JWT +
consulta a `users`, autorización de operador Warehouse `can_upload` vigente,
dos archivos RAW nuevos con `upload_origin=google_ads_correction_pair` y
`correction_case_intent=CANDIDATE_ONLY`, par 27/43 y catálogo M5/M6
aprobado. La evidencia previa del día es obligatoria, incluso si fue
archivada. El staging guarda expediente, 27/43 hechos y dos auditorías en
una sola transacción. La repetición exacta valida filas y auditorías.

No existe todavía un mecanismo productivo de carga que emita esa procedencia,
por lo tanto **no se puede usar este servicio para reemplazar los RAW
21654/21655**. Una futura fase debe desarrollar un upload por caso con
autorización independiente, comparativa, promoción atómica e integración del
lector con la revisión. Nada de esto habilita la publicación.
