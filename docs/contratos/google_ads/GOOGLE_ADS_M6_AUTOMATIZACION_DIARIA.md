# Suite Ultra — Google Ads M6 · Contrato de carga manual temporal

**Estado (14-oct-2026):** integrante del único hito [Issue #888](https://github.com/VladRoJa/sistematicketsultra/issues/888) y [PR #885](https://github.com/VladRoJa/sistematicketsultra/pull/885), ambos abiertos y sin merge. Este archivo conserva su nombre histórico por compatibilidad, pero el contrato anterior de automatización por correo **queda sustituido** por esta decisión. El historial de Git conserva el contrato anterior.

## Decisión de entrada y objetivos
Hasta terminar la API oficial, **el operador descarga manualmente** `Informe de campaña` e `Informe de grupo de anuncios` de Google Ads y los sube en la misma operación de Suite Ultra. No existe lectura programada del buzón, descarga desde enlaces ni scheduler por correo. No pedir contraseñas ni tokens de Gmail/Google Ads al usuario. Google Ads API será un adaptador alternativo futuro sobre las **mismas** validaciones y salidas.

```text
ADMICORP -> cargar campaña.xlsx + grupos.xlsx
         -> PREVIEW sin escrituras (parsers XLSX existentes)
         -> validar fecha cerrada, misma cuenta, 27 campañas, 43 grupos,
            26 pares de identidades aprobadas, MXN y conciliación
         -> confirmar operación con autorización backend
         -> Warehouse RAW ambos, hashes SHA256, fecha, usuario y auditoría
         -> revisión/ingesta estructurada versionada (sin datos parciales)
         -> aprobación/control de continuidad -> Funnel por sucursal
Google Ads API (futuro) -> mismo validador/RAW/ingesta/Funnel
```

## Histórico inmutable y reconciliación
- Cuenta esperada `2739125201`. No confiar en nombre de archivo ni en fechas del navegador.
- M5 histórico: 24-sep..08-oct-2026, fuente grupo upload `21499`, manifiesto `GOOGLE_ADS_M5_IDENTITY_20261012_V1`. No actualizar ni prolongar automáticamente.
- Arranque M6: 09..12-oct-2026, fuentes RAW campañas `21604`, grupos `21605`. 108 filas campaña/día, 172 filas grupo/día, 43 pares históricos y 26 identidades de sucursal a aprobar; inversión cuenta MXN 5,562.11, asignable MXN 5,211.74, no asignada MXN 350.37.
- Los totales de campañas son la única autoridad de gasto de cuenta. Grupos son detalle **no aditivo**. No alterar Metas, CPL, CPT, CAC ni indicadores Meta.
- Aprobación de identidades con versión, JWT ADMICORP y flag `GOOGLE_ADS_M6_APPROVAL_ENABLED` apagado por defecto. La carga manual **no** implica aprobación automática. No inferir nuevos clubes de nombres de campaña/grupo.
- `preflight_daily_pair` es un validador puro sin permisos, persistencia ni publicación; no equivale a finalización de pipeline.
- No permitir que nuevos días aparezcan en Funnel por la mera existencia de los XLSX. El lector M6 actual sigue acotado a 09..12 hasta integrar la procedencia diaria y versión de aprobación de forma segura.

## UX y permisos propuestos
- Sección simple «Google Ads · Carga manual», visible y operable solamente a ADMICORP. Adjuntar ambos XLSX en un mismo formulario, fecha reportada detectada desde sus celdas, no editable como fuente de verdad.
- Botón «Validar» muestra: período, estado, filas, coste cuenta, coste asignado, importe no asignado, diferencias, duplicados y eventual error. **El preview no guarda documentos ni hechos.**
- Botón «Confirmar carga» requiere que la evidencia validada corresponda a los mismos hashes; se debe volver a validar backend antes de persistir. Los errores no se transforman en cero.
- `POST /api/warehouse/uploads` **no puede** usarse como único flujo pareado: su dispatcher opcional intenta ingesta estructurada de un archivo individual inmediatamente. Crear endpoints específicos o una orquestación equivalente, con controles de identidad y sin eludir el preflight.
- La autorización del backend es fuente real: JWT + comprobación vigente del usuario/rol ADMICORP. Las restricciones de menú Angular no conceden permisos.
- Angular: TS para todas las validaciones y acciones, HTML de estructura, CSS separado.

## RAW, reintentos y correcciones
- Antes de guardar, validar ambos XLSX con parsers estrictos existentes: `google_ads_daily_xlsx_parser.py` y `google_ads_ad_group_daily_xlsx_parser.py`. Solo MXN y días cerrados Tijuana, mismas identidades y totales costo/clics/impresiones/conversiones.
- Persistir documentos RAW con `create_warehouse_document_upload`; sus hashes y fechas deben corresponder al preview. Asociar los dos uploads lógicamente al día/operación sin añadir aprobaciones silenciosas.
- Repetir exactamente el mismo par puede reutilizar uploads RAW por hash. Si falla guardar uno, mostrar estado incompleto y exigir reintento/revisión, sin estructurar ni publicar. Archivos tardíos/diferentes para un día ya importado requieren revisión explícita, no `UPDATE` destructivo.
- Estructurada y publicación están separadas de RAW y necesitan controles, trazabilidad, snapshots/canonicalidad y regresión de permisos.

## Gates y despliegue
1. Retirar prototipo de lectura/descarga Gmail y staging RAW acoplado al ID de mensaje.
2. Implementar preflight API sin escrituras para dos archivos y pruebas positivas/negativas.
3. Confirmación ADMICORP e integración RAW pareada con deduplicación y detección de fallos parciales.
4. UI Angular, revisión de accesibilidad y permisos; prueba integrada contra PostgreSQL16.
5. Importación estructurada controlada y extensión del lector M6 a nuevos días con identidad/canonicalidad verificadas.
6. Reconciliar heads Alembic: M6 `b3e7c2d9a104` y main `c13a70e4d82b`, ambas descendientes de `f62a1b9d4c07`. Incorporar main y hacer migración de unión; **nunca** reescribir una migración histórica aplicada.
7. CI global + revisión independiente + un merge autorizado + deploy por git pull/Docker Compose y migración controlada.

**Excluidos:** Gmail/IMAP, autenticación de descarga de enlaces, job/scheduler de correo, ejecución autónoma de correo, reemplazo inmediato por Google Ads API. Los dos mensajes del 14-oct se verificaron solo para diagnóstico: llegaron como enlace directo y no como adjunto, pero no forman parte de M6 manual.

**No desplegado y sin aprobación real:** los tests históricos (hasta 116 PASS del prototipo) no prueban todavía el flujo manual integral.
