# Suite Ultra — Google Ads M6: ingesta automática de reportes programados

**Fecha:** 2026-10-13  
**Estado:** CONTRATO EN REVISIÓN / PR DRAFT. Ninguna ingesta automática, scheduler, credencial de buzón o escritura autorizada.  
**Decisión de fuente (13-oct-2026):** **correo programado Google Ads con CSV/XLSX ahora; Google Ads API después como adaptador intercambiable.** No exigir OAuth/API para completar este camino.

## 1. Objetivo operativo y contexto

Actualizar automáticamente el Funnel de Venta Nueva mediante informes de Google Ads programados para enviarse por correo, sin descargar y subir Excel manualmente. Una vez disponible la API oficial, conectar el adaptador `google_ads_api` a la **misma** validación, Warehouse, snapshots, conciliación, publicación, bitácora y semáforo. Ni el Funnel ni los cálculos deben depender del método de recepción.

**Fuente ya certificada históricamente:** cliente `2739125201`; 24-sep al 08-oct-2026; 645 filas grupo-día, 43 triples y 26 asociaciones provisionales al club (MXN 17,624.73), MXN 1,501.64 no atribuidos, MXN 19,126.37 de cuenta. El XLSX físico `source_upload_id=21499` no se modifica; sus mapeos `APPROVED_PROVISIONAL_XLSX` **expiran el 8 de octubre** y no se extienden silenciosamente.

## 2. Hallazgos en código y limitación de Google Ads

- Existe carga documental/raw y estructurada para `google_ads_campaign_daily` y `google_ads_ad_group_daily`, con parsers **exclusivamente XLSX**:
  - `backend/app/warehouse/services/google_ads_daily_xlsx_parser.py`
  - `backend/app/warehouse/services/google_ads_ad_group_daily_xlsx_parser.py`
  - `backend/app/warehouse/services/google_ads_daily_ingestion_service.py`
  - `backend/app/warehouse/services/google_ads_ad_group_daily_ingestion_service.py`
- El reporte de grupos necesita **Día, Grupo de anuncios, Campaña, Código de moneda, Coste, Clics, Impr., Conversiones, Pase gratis Ads, Compras web Ads y Valor de conv. original**; además de totales diarios reconciliables. El de campañas requiere las columnas equivalentes de su propio contrato.
- La captura de Google Ads muestra un envío programable `Diariamente` a las `8:00` hora del Pacífico, formato **`.csv para Excel`**, segmento **Día**, `Título y período` y `Totales`. Aún no se verificó el archivo real **recibido**, ni si el selector de programación permite `.xlsx`. La disponibilidad de XLSX para descargas manuales NO implica que esté disponible para correos programados.
- Google Ads permite programar informes a usuarios que tengan acceso directo a la cuenta. No usar correos arbitrarios como destinatario ni asumir que el envío soporta direcciones sin permiso. Referencia: https://support.google.com/google-ads/answer/2404176?hl=es .
- Los servicios OAuth/API M1/M2 existen, pero el usuario confirmó que la autorización no se pudo finalizar. **No bloquear ni pedir verificación de la API en M6-correo.**

## 3. Arquitectura: fuente reemplazable, reglas únicas

```text
Google Ads - 2 informes programados (Campañas + Grupos)
  -> buzón autorizado y dedicado (recepción, no envío automático desde Suite)
  -> adaptador google_ads_scheduled_mail  [M6]
  -> archivo raw inmutable + huella SHA-256 + ID de mensaje
  -> parser de formato identificado y validado  [CSV o XLSX]
  -> reconciliación campaña/día vs grupo/día vs totales de cuenta
  -> versionado y aprobación de identidades por sucursal
  -> datos estructurados/snapshots versionados en Warehouse
  -> lectura autorizada por sucursal del Funnel y semáforo
                                ^
Google Ads API (futuro) -> adaptador google_ads_api ---+
```

La representación interna normalizada debe conservar `account_id`, `source_kind`, `report_type_key`, `business_date`, `campaign_key`, `ad_group_key`, importes/clics/impresiones, conversiones Ads, `source_hash`, `source_message_id`, `ingestion_run_id`, `snapshot_version` y `approval_evidence`. El ID del cliente se **fija en backend/configuración** y se valida contra las evidencias autorizadas; no se obtiene de un remitente o nombre de fichero.

**No añadir montos:** `google_ads_daily_metrics` (campañas) sigue como autoridad de gasto de cuenta; `google_ads_ad_group_daily_metrics` es desglose del mismo gasto, no un segundo ledger. `summary.investment`, `branches[].investment` y CPL/CPT/CAC siguen con base `META_ASSIGNED_ONLY`.

## 4. Configuración recomendada en Google Ads (primer gate manual)

Preparar **dos informes separados**, uno en **Campañas** y otro en **Grupos de anuncios**; ambos con segmentación por **Día** y sin filtrar `Marca` ni `EGADE`, para conservar el gasto total sin asignar.

- Período **dinámico**: preferiblemente `Ayer` o una ventana retrospectiva que cierre en ayer; validar qué opciones ofrece Ads. El informe de 08:00 no debe incluir hoy como día completo. Para conversiones tardías, plantear revisión de 7 días si la programación admite ventana móvil; **no sobrescribir** automáticamente un histórico publicado.
- Incluir `Título y período` y `Totales`; mantener columnas de campaña/grupo, moneda, coste, clics, impresiones y conversiones. En grupos conservar las dos columnas personalizadas `Pase gratis Ads` y `Compras web Ads`.
- En destinatario seleccionar **una cuenta de correo con acceso autorizado a Google Ads** (idealmente buzón operativo administrado por la empresa), no una dirección sin permisos. No compartir contraseñas, claves, mensajes de consentimiento ni tokens.
- Revisar el menú de formatos: si la **programación** ofrece XLSX, probarlo primero (podría reutilizarse el parser). Si solo ofrece `.csv para Excel`, aceptar CSV como raw y construir parser específico validado con muestra real, preservando codificación, delimitador, columnas, subtotales y decimales; **prohibida la conversión ciega CSV→XLSX**.
- Ejecutar una **prueba de recepción** para ambas fuentes antes de crear tablas, cron o buzón automático. Validar si Google envía adjunto real o un enlace de descarga; no asumirlo. Comparar los mismos cortes con los XLSX manuales anteriores cuando sea posible.

**Nota:** el reporte programado puede tener restricciones de tiempo de generación. No considerar `08:00` como hora de llegada garantizada; el worker debe basarse en llegada real y SLA.

## 5. Ingesta de correo segura (a implementar tras gate de muestras)

- Leer un buzón autorizado mediante integración oficial de correo/IMAP o API del proveedor, con **credenciales custodiadas fuera del repo**, permisos mínimos y sin almacenarlas en PostgreSQL plano. La elección concreta se decide tras conocer el proveedor del buzón; no instalar ni conceder acceso por anticipado.
- Lista estricta de reportes esperados y destinatario. Verificar metadatos autenticados/origen (SPF/DKIM/DMARC cuando disponible), tamaño, extensión, MIME, integridad y límites de descompresión. **Un remitente que parece Google Ads no es prueba suficiente.**
- Registrar mensaje, adjunto, `sha256`, fuente, fechas, resultado y correlación. El mismo `message_id + attachment_hash` no produce una segunda ingesta; los reportes duplicados o tardíos quedan auditados.
- Los dos archivos del mismo día se procesan como **par lógico**. Si solo llega uno, `WAITING_SOURCE`; si importes, clics, impresiones, totales o monedas no concilian, `REQUIRES_REVIEW`; jamás publicar total como cero ni recalcular Meta.
- No crear automáticamente sucursales desde un nombre de grupo. Para fechas posteriores al 08-oct, las 26 asociaciones históricas requieren **nueva aprobación explícita de vigencia**, con revisión de identidades y grupos nuevos; `Marca`, `EGADE` y nuevos grupos sin aprobar quedan no asignados. Preferir validación por IDs oficiales cuando la API esté disponible.
- Para capturas retroactivas o cambios de conversiones, registrar revisión inmutable/snapshot versionado; no `UPDATE` silencioso de los datos originales. Raw first, structured after validation, canonicalidad posterior.
- Las acciones de lectura/ingesta se ejecutan **en worker separado de Flask web**, con timeout, cuotas, retries y flags `GOOGLE_ADS_MAIL_PREVIEW_ENABLED` / `GOOGLE_ADS_MAIL_AUTOPUBLISH_ENABLED` (este último `false` hasta autorización expresa). Nunca ejecutar un job largo dentro de Gunicorn.

## 6. Scheduler, observabilidad, permisos y QA

Crear un job real `marketing.google_ads_mail_ingestion` en Control de Automatizaciones **solo cuando exista código y corrida auditada**. Mostrar ejecuciones, hash/referencias, fechas de negocio, último error saneado, permisos ADMICORP y botón de ejecución manual únicamente cuando esté autorizado. El semáforo del bloque Google Ads es propio y depende de fecha de negocio completa y SLA, no del último correo recibido. Zona de operación `America/Tijuana`.

Casos negativos obligatorios: falta uno de los dos informes, múltiples adjuntos, enlace en vez de adjunto, correo no autorizado, CSV con columnas o delimitador distintos, moneda errónea, día actual, totales inconsistentes, archivo corrupto, identidad nueva/renombrada, grupos `Marca`/`EGADE`, reenvío duplicado, conversiones tardías y caída del proveedor de email.

Cambios a tablas/estados de aprobación, runs y snapshots requieren **Alembic + PostgreSQL 16 real**, pruebas backend y Angular; despliegue desde repo local/PR/main (sin editar código en servidor). Los controles técnicos se validan en backend aunque Angular esconda botones.

## 7. Secuencia por fases (sin saltarse gates)

**M6-E1 — Muestras de correo (ahora; sin desarrollo ni credenciales).** Probar una programación de Campañas y otra de Grupos, decidir CSV o XLSX según el selector real. Recibir un ejemplar y contrastar contra los parsers; determinar destinatario autorizado y si el correo tiene adjunto o enlace. Un solo ensayo antes de automatizar.

**M6-E2 — Parser/normalizador de correo.** Añadir adaptador CSV si hace falta, pruebas con muestras despersonalizadas (cuenta/campañas de trabajo, sin credenciales). Reutilizar validaciones estrictas de XLSX y asegurar cero regresiones.

**M6-E3 — Captura raw e ingesta estructurada versionada.** Implementar lector de buzón en un proceso aislado, almacenamiento/auditoría, deduplicación y pares diarios. Migraciones Alembic, simulación sin escritura y PG16.

**M6-E4 — Mapeo de vigencia futura y publicación.** Revisar 26 aprobaciones históricas/identidades nuevas, extender mediante proceso explícito y publicar solo fechas conciliadas. Sin extender automáticamente M5.

**M6-E5 — Scheduler opt-in + UI de frescura.** Hora basada en llegada real del reporte; retries seguros, observabilidad, diagnóstico, semáforo y run manual controlado.

**M6-API — Sustitución posterior del adaptador, NO prerequisito de E1–E5.** Al resolver acceso a API, crear `google_ads_api` con IDs oficiales y acciones de conversión verificadas. Publicar por la **misma** capa de conciliación/snapshots/branch scope. Modo de transición con validación paralela correo vs API; una única fuente canónica por cuenta/día, sin conteo doble.

## 8. Primer paso solicitado al operador

En la ventana **Programar** de Google Ads, desplegar el selector que ahora dice **«.csv para Excel»** y comprobar si incluye **XLSX**. No hace falta programar envío todavía ni compartir dirección de correo. Este único dato determina si M6-E2 puede reutilizar el parser XLSX o necesita CSV.
