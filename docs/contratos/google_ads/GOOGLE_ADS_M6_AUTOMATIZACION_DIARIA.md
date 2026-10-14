# Suite Ultra — Google Ads M6 · Contrato de carga manual y lectura canónica

**Actualizado 14-oct-2026.** [Issue #888](https://github.com/VladRoJa/sistematicketsultra/issues/888) · [PR #885](https://github.com/VladRoJa/sistematicketsultra/pull/885). El nombre de este documento se conserva por compatibilidad histórica: el transporte por Gmail y sus schedulers **no forman parte de M6**. La futura Google Ads API deberá sustituir únicamente el adaptador de entrada, no las reglas de ingesta, trazabilidad ni permisos.

**Estado del código:** flujo manual desarrollado en la rama, no desplegado. Las banderas de escritura/aprobación están **OFF por defecto**. El último gate de código anterior al corte documental aprobó 138 tests PostgreSQL 16 más TypeScript y build Angular; no sustituye QA visual ni revisión independiente. Ninguna aprobación, importación o publicación productiva se infiere del CI.

## 1. Alcance e invariantes

- Cuenta `2739125201`; fechas y MXN validadas por backend a partir del XLSX y de sus datos, nunca a partir del nombre del archivo.
- M5 del 24-sep al 08-oct-2026 es inmutable; fuente grupo `21499` y manifiesto `GOOGLE_ADS_M5_IDENTITY_20261012_V1`.
- M6 histórico del 09 al 12-oct: RAW campaña `21604`, grupos `21605`; 108 filas campañas/día, 172 grupos/día en total por el período, costo cuenta MXN 5,562.11, costo asignado MXN 5,211.74 y no asignado MXN 350.37. La continuidad de 26 identidades exige aprobación inicial versionada, nunca implícita.
- Desde el **13-oct-2026** el día solo alimenta Funnel tras publicación canónica explícita de exactamente 27 campañas y 43 grupos conciliados, con 26 asociaciones aprobadas, auditoría y hashes exactos.
- Campañas constituyen el ledger único de inversión. Grupos detallan atribución a sucursal y **no** se suman nuevamente al gasto. No modificar Meta ni métricas CPL/CPT/CAC existentes.
- Para gerente/regional, las consultas de grupos se acotan por SQL a sus sucursales y a los uploads publicados; no se devuelve gasto global ni no asignado. Fechas sin publicación no equivalen a costo cero.

## 2. Flujo implementado en la rama M6

| Etapa | Endpoint | Efecto y barrera |
| --- | --- | --- |
| 1. Preview | `POST /api/integrations/google-ads/manual/preview` | Dos XLSX, JWT + ADMICORP vigente, preflight sin escrituras, ticket vinculado a hashes/actor con 15 minutos |
| 2. RAW | `POST /api/integrations/google-ads/manual/confirm` | Ticket y archivos idénticos, permiso Warehouse upload, revalidación y dos uploads RAW auditados; `PARTIAL_RAW` no ingesta/publica |
| 3. Estructurada | `POST /api/integrations/google-ads/manual/ingest` | Confirmación explícita, JWT/ADMICORP+Warehouse, bandera separada; 27+43 facts y dos auditorías en transacción PG16 |
| 4. Canónica | `POST /api/integrations/google-ads/manual/publish` | Confirmación explícita, JWT/ADMICORP+Warehouse, bandera separada; hashes, identidades, hechos y auditorías revalidados, publicación revisionada y dos auditorías atómicas |
| Diagnóstico | `GET /api/integrations/google-ads/manual/correction-status?day=YYYY-MM-DD` | ADMICORP + Warehouse view, transacción de solo lectura; RAW, facts, auditorías, revisiones y bloqueos del día |
| Aprobación M6 inicial | `POST /api/integrations/google-ads/continuity/approve` | Aprobación explícita con JWT, identidad real ADMICORP y comprobación histórica; bandera apagada por defecto |

Las rutas pertenecen al blueprint `backend/app/routes/google_ads_m6_continuity_routes.py`. El frontend se integra en Google Ads · Administración, con componente standalone TS/HTML/CSS y service REST separado. Angular guía, pero **el backend autoriza**.

Banderas de operación (apagadas hasta autorización productiva):
- `GOOGLE_ADS_M6_APPROVAL_ENABLED`
- `GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED`
- `GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED`

La carga RAW y el preflight no equivalen a aprobación ni publicación. La confirmación de RAW no llama a la ingesta; la ingesta no llama a publicación. No se debe usar `POST /api/warehouse/uploads` genérico como sustituto del proceso pareado: podría despachar ingesta individual sin sus gates.

## 3. Consistencia, fallos e idempotencia

- Los RAW conservan SHA256, periodo y actor. Una pareja idéntica puede ser reintentada sin duplicación; ante fallo de segunda carga, la primera evidencia puede persistir y el estado debe reflejar `PARTIAL_RAW`, sin representar atomicidad que Warehouse no provee.
- La transacción estructurada contiene **ambas tablas y auditorías**; ante fallo del segundo insert no queda publicación ni mitad de la pareja.
- Publicar exige hechos equivalentes a RAW, ambos import audits, estado ACTIVE, identidad M6 aprobada y autorización actual. La publicación inicial y las dos auditorías forman una única transacción.
- La tabla `google_ads_m6_daily_publications` admite revisiones con índice parcial único para el único canónico por día. La implementación **aún no almacena hechos alternativos por revisión** y, por seguridad, rechaza sustituciones de días publicados.
- Una publicación exacta puede repetirse idempotentemente; una distinta produce conflicto. RAW archivados o con hash distinto son evidencia, no permiso para reemplazo.
- Correcciones históricas y el caso de RAW `21654`/`21655`: [protocolo separado de correcciones tardías](GOOGLE_ADS_M6_CORRECCIONES_TARDIAS.md). Está **propuesto y en HOLD**; no autoriza archivar, borrar, sustituir ni publicar datos reales.

## 4. Almacenamiento, migraciones y lectores

- Migraciones M6 `b3e7c2d9a104` (continuidad/identidades) y `d7f2a09c8b61` (publicaciones).
- El `main` integrado en la rama culmina en `c856map1014`; la migración **de unión** `a4c85d6e9f20` declara ambos padres, sin DDL, DML ni backfill. La prueba Alembic comprueba un solo head. No implica que migraciones se hayan aplicado en producción.
- El lector de atribución nuevo para fechas 13-oct+ se ubica en `backend/app/services/marketing_google_ads_m6_daily_attribution_service.py`; se combina con la historia 09–12 sin modificar M5. El lector global verifica campañas y grupos pero contabiliza solo gasto de campañas.
- Si existen huecos entre el inicio del tramo diario y la última publicación canónica, la lectura falla cerrada (`requires_review`) en lugar de aparentar cobertura completa.

## 5. Evidencia y condiciones previas al merge/despliegue

En el HEAD de código `a69c65ab` los workflows M6 [push](https://github.com/VladRoJa/sistematicketsultra/actions/runs/38636448972) y [PR](https://github.com/VladRoJa/sistematicketsultra/actions/runs/38636454373) terminaron SUCCESS: **138/138 pruebas** backend/PG16, comprobación TypeScript y build Angular PASS. El E2E sintético usa rutas Flask/JWT, Warehouse/PG16 real, publicación y SQL restringido por sucursal; no prueba datos productivos ni pixel-perfect UI.

**Pendiente:** QA visual en navegador con perfiles reales y mensajes de error; revisión de seguridad/código independiente; aceptación productiva de identidades M6; procedimiento separado de correcciones versionadas si se decide incluirlo; plan de migración, rollback, único merge autorizado y despliegue posterior siguiendo repo → servidor git pull → Docker Compose → Alembic. No desplegar ni habilitar flags desde un test exitoso.

**No hacer:** reactivar Gmail/IMAP, descargar reportes desde enlaces de correo, crear jobs de buzón, editar código directamente en servidor, borrar RAW históricos, actualizar hechos M5 o hacer publicación automática tras upload.
