# Suite Ultra — Google Ads M6: ingesta automática de reportes programados

**Fecha:** 2026-10-13  
**Estado:** CONTRATO EN REVISIÓN / PR DRAFT. Dos informes diarios configurados en Google Ads; ninguna recepción por correo, ingesta automática, scheduler ni autopublicación implementados. Sin credenciales de buzón ni escrituras autorizadas por este contrato.  
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
- El operador verificó en Google Ads que la **programación** admite `.xlsx` y configuró dos informes guardados, `Informe de campaña` y `Informe de grupo de anuncios`, ambos `Diariamente (.xlsx)` con rango dinámico `Ayer`, 08:00 hora del Pacífico, segmento `Día`, `Título y período`, `Totales` y destinatario autorizado. Captura de `Informes guardados`: exactamente dos programas. **Aún no se verificó el correo realmente recibido** ni si trae adjunto XLSX o enlace.
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
- **XLSX confirmado y programado para ambos informes.** Validar su formato y contenido *recibido* antes de reutilizar los parsers XLSX existentes. No crear parser CSV en este camino salvo evidencia de cambio real de formato.
- Ejecutar una **prueba de recepción** para ambas fuentes antes de crear tablas, cron o buzón automático. Validar si Google envía adjunto real o un enlace de descarga; no asumirlo. Comparar los mismos cortes con los XLSX manuales anteriores cuando sea posible.

**Nota:** el reporte programado puede tener restricciones de tiempo de generación. No considerar `08:00` como hora de llegada garantizada; el worker debe basarse en llegada real y SLA.

## 5. Ingesta de correo segura (a implementar tras gate de muestras)

- Leer un buzón autorizado mediante integración oficial de correo/IMAP o API del proveedor, con **credenciales custodiadas fuera del repo**, permisos mínimos y sin almacenarlas en PostgreSQL plano. La elección concreta se decide tras conocer el proveedor del buzón; no instalar ni conceder acceso por anticipado.
- Lista estricta de reportes esperados y destinatario. Verificar metadatos autenticados/origen (SPF/DKIM/DMARC cuando disponible), tamaño, extensión, MIME, integridad y límites de descompresión. **Un remitente que parece Google Ads no es prueba suficiente.**
- Registrar mensaje, adjunto, `sha256`, fuente, fechas, resultado y correlación. El mismo `message_id + attachment_hash` no produce una segunda ingesta; los reportes duplicados o tardíos quedan auditados.
- Los dos archivos del mismo día se procesan como **par lógico**. Si solo llega uno, `WAITING_SOURCE`; si importes, clics, impresiones, totales o monedas no concilian, `REQUIRES_REVIEW`; jamás publicar total como cero ni recalcular Meta.
- No crear automáticamente sucursales desde un nombre de grupo. El registro M5 asociado al upload `21499` y al período 24-sep..08-oct permanece **inmutable**; no ampliar el `valid_to` ni cambiar `source_upload_id` de ese registro. Para 09..12-oct se requiere validar las 26 claves exactas contra grupos de `21605` y campañas `21604`, registrar una **nueva evidencia/aprobación de continuidad** y efectuar backfill controlado. `Marca`, `EGADE` y grupos no aprobados permanecen no asignados. Preferir IDs oficiales cuando la API esté disponible.
- **Regla M6 de actualización automática (una vez implementada y habilitada):** aprobar una única vez el conjunto estable de identidad exacta `(customer_id, campaign_key, ad_group_key) -> sucursal_canon` y sus restricciones de vigencia; posteriormente cada día cerrado se publica sin aprobación manual repetida **solo** si llegan ambos reportes, todos los totales diarios y campaña-grupo concilian, se identifica exactamente el mismo conjunto de 26 claves aprobadas y las sucursales siguen operativas/autorizadas. Registrar evidencia por día/archivo/hash y mantener inmutables las fuentes originales. Cualquier nueva clave, cambio de nombre/identidad, identidad ausente, duplicidad, conflicto tardío o descuadre deja el nuevo día en `REQUIRES_REVIEW` (sin asignación implícita); el gasto completo de cuenta sigue siendo su propio ledger. Nunca duplicar gasto sumando grupos a campañas.
- **Cambio de diseño indispensable:** el lector actual `marketing_google_ads_branch_attribution_service.py` fija `HISTORICAL_END=2026-10-08`, `UPLOAD_ID=21499` y cruza `fact.source_upload_id == mapping.source_upload_id`; el modelo `google_ads_branch_identity_mappings` tiene unicidad por identidad y procedencia a un solo upload. Para operar en continuo, separar aprobación estable/versionada de identidad y procedencia diaria del hecho, con esquema y migración **Alembic**, mantener el lector M5 sin regresión y añadir un lector de continuidad que cumpla los mismos controles de scope backend. Prohibido desbloquearlo solo cambiando la constante de fecha.
- Para capturas retroactivas o cambios de conversiones, registrar revisión inmutable/snapshot versionado; no `UPDATE` silencioso de los datos originales. Raw first, structured after validation, canonicalidad posterior.
- Las acciones de lectura/ingesta se ejecutan **en worker separado de Flask web**, con timeout, cuotas, retries y flags `GOOGLE_ADS_MAIL_PREVIEW_ENABLED` / `GOOGLE_ADS_MAIL_AUTOPUBLISH_ENABLED` (este último `false` hasta autorización expresa). Nunca ejecutar un job largo dentro de Gunicorn.

## 6. Scheduler, observabilidad, permisos y QA

Crear un job real `marketing.google_ads_mail_ingestion` en Control de Automatizaciones **solo cuando exista código y corrida auditada**. Mostrar ejecuciones, hash/referencias, fechas de negocio, último error saneado, permisos ADMICORP y botón de ejecución manual únicamente cuando esté autorizado. El semáforo del bloque Google Ads es propio y depende de fecha de negocio completa y SLA, no del último correo recibido. Zona de operación `America/Tijuana`.

Casos negativos obligatorios: falta uno de los dos informes, múltiples adjuntos, enlace en vez de adjunto, correo no autorizado, CSV con columnas o delimitador distintos, moneda errónea, día actual, totales inconsistentes, archivo corrupto, identidad nueva/renombrada, grupos `Marca`/`EGADE`, reenvío duplicado, conversiones tardías y caída del proveedor de email.

Cambios a tablas/estados de aprobación, runs y snapshots requieren **Alembic + PostgreSQL 16 real**, pruebas backend y Angular; despliegue desde repo local/PR/main (sin editar código en servidor). Los controles técnicos se validan en backend aunque Angular esconda botones.

## 7. Secuencia por fases (sin saltarse gates)

**M6-E1 — Configuración concluida; recepción pendiente.** Los dos informes ya están programados a diario como XLSX, `Ayer`, 08:00 Pacífico y destinatario autorizado. Los archivos descargados manualmente del **09..12-oct** (`21604` campañas, `21605` grupos) concilian: **108 campañas/día, 172 grupos/día, 5,562.11 MXN, 2,130 clics, 21,072 impresiones, 29 conversiones Ads**, con 0.00 diferencia. Funnel ya muestra acumulado de cuenta al 12-oct, **16,515.31 MXN** (10,953.20 anterior + 5,562.11 nuevo), pero la atribución sigue acotada al 08-oct. Aún hay que recibir un correo de cada informe y confirmar adjunto vs enlace, columnas, metadatos y rango.

**M6-E2 — Parser/normalizador de correo.** Añadir adaptador CSV si hace falta, pruebas con muestras despersonalizadas (cuenta/campañas de trabajo, sin credenciales). Reutilizar validaciones estrictas de XLSX y asegurar cero regresiones.

**M6-E3 — Captura raw e ingesta estructurada versionada.** Implementar lector de buzón en un proceso aislado, almacenamiento/auditoría, deduplicación y pares diarios. Migraciones Alembic, simulación sin escritura y PG16.

**M6-E4 — Backfill aprobado y continuidad automática protegida.** Preparar aprobación nueva para 09..12-oct respaldada por `21604`/`21605` y cotejo exacto de las 26 identidades; no mutar M5. Implementar modelo Alembic de identidad aprobada versionada más evidencia/procedencia diaria, y lector de continuidad por fecha autorizada. Una vez habilitado, días posteriores conservan automáticamente las mismas 26 relaciones si superan todas las validaciones diarias; nuevas/ambiguas no se asignan y requieren revisión. Publicar solo días completos conciliados. Mantener el gasto de cuenta y CPL/CPT/CAC independientes de la atribución.

**M6-E5 — Scheduler opt-in + UI de frescura.** Hora basada en llegada real del reporte; retries seguros, observabilidad, diagnóstico, semáforo y run manual controlado.

**M6-API — Sustitución posterior del adaptador, NO prerequisito de E1–E5.** Al resolver acceso a API, crear `google_ads_api` con IDs oficiales y acciones de conversión verificadas. Publicar por la **misma** capa de conciliación/snapshots/branch scope. Modo de transición con validación paralela correo vs API; una única fuente canónica por cuenta/día, sin conteo doble.

## 8. Primer paso solicitado al operador

**Siguiente gate operativo:** recibir los dos primeros correos del ciclo diario y confirmar adjunto XLSX vs enlace. **Siguiente gate de desarrollo:** migración/versionado de continuidad M6-E4 y backfill controlado del 09..12-oct, con pruebas, antes de habilitar autopublicación. No pedir configurar Google Ads de nuevo; ambos informes ya constan programados.
