# Campañas V2 — Fase 1 — Progreso

Última actualización: 2026-09-30

## Base de trabajo

- Repositorio: `VladRoJa/sistematicketsultra`
- Base de este milestone: `main` en `54f0c2c72ac11ba3d98dfc6600d526992d77217d`
- Rama: `feat/campaign-v2-tariff-catalog`
- Contrato rector: `docs/contratos/campanas_v2/CONTRATO_CAMPANAS_V2_FASE_1.md`

## Decisiones consolidadas

1. Campañas V2 usa un mapping de tarifas separado del catálogo legacy de Reactivaciones.
2. `MarketingReactivationTariffORM`, `reactivation_group` y las categorías legacy no se modifican.
3. V2 conserva su propia `categoria_tarifa` y `audience_family`.
4. La identidad textual usa exactamente la normalización vigente de `tarifa_key`: NFKC, trim, uppercase y colapso de whitespace.
5. Los siete valores observados de `audience_family` son:
   - `DOMICILIADO`
   - `TRIMESTRAL`
   - `CONVENIO`
   - `SEMESTRE`
   - `ESTUDIANTE`
   - `MES`
   - `OUT_OF_SEGMENT`
6. `MES` se almacena, pero no está aprobado como sexta familia comercial seleccionable.
7. `OUT_OF_SEGMENT` es una clasificación comercial y no equivale a una exclusión técnica.
8. El snapshot del catálogo es un artefacto inmutable. No se edita en sitio; cualquier cambio futuro debe producir un nuevo artefacto versionado y su migración correspondiente.

## Cruce aprobado previo al Milestone 1

- Catálogo V2: 166 filas / 166 `tarifa_key` únicas.
- Legacy efectivo: 190 `tarifa_key` únicas.
- Coincidencias: 153.
- Sólo V2: 13.
- Sólo legacy: 37.
- Colisiones de normalización: 0.
- Coincidencias con misma `categoria_tarifa`: 151.
- Coincidencias con categoría distinta: 2:
  - `CONVENIO DOMICILIADO $549`: legacy `Domiciliado`; V2 `Convenio`.
  - `MEMBRESIA LM`: legacy `Membresía`; V2 `Convenio`.

Las 13 tarifas exclusivas de V2 son:

- `$349 ATLETA CAR/COBACH ROSARITO`
- `3 MESES PROPORCIONAL`
- `50% 1ER MES 60+ 12 MESES`
- `ANUALIDAD EN LINEA`
- `MISION ZOE ENS`
- `PAGO EN LÍNEA ANUALIDAD X 4999`
- `PAGO EN LINEA CIERRE ABRIL`
- `PROMO 14 FEB`
- `PROMO DIA DE LA MUJER`
- `SEMANA INSTRUCTOR PERSONALIZADO EXTERNO $900`
- `SEMESTRAL $2,999 + 1 MES GRATIS`
- `TRES MESES POR 1,490`
- `ULTRA FIT KIDS SIN PLAZO $399`

## Milestone 1 — Catálogo Campañas V2

Estado: **completado y mergeado a `main` en `8d9279e893e12a8ae351392ab2e7fbffbc6f73d1`**.

### Modelo

Nuevo ORM: `MarketingCampaignV2TariffORM`

Tabla: `marketing_campaign_v2_tariffs`

Campos:

- `id`
- `tarifa_key`
- `tarifa_raw`
- `categoria_tarifa`
- `audience_family`

No contiene `reactivation_group` ni depende de `MarketingReactivationTariffORM`.

### Snapshot inmutable

Archivo:

`backend/data/reference/marketing_campaign_v2_tariffs_2026-09-30.json`

- Filas: 166
- Política: `immutable`
- SHA-256 esperado de los bytes UTF-8 del archivo:

`00b9475ea8bdfbaf3c9d1d3571d630035ff315ab8cd374fb0339e18589162bae`

La migración y la prueba de integridad validan este checksum antes de aceptar el catálogo.

Distribución aprobada:

| audience_family | filas |
| --- | ---: |
| DOMICILIADO | 102 |
| TRIMESTRAL | 21 |
| CONVENIO | 12 |
| SEMESTRE | 10 |
| OUT_OF_SEGMENT | 10 |
| ESTUDIANTE | 6 |
| MES | 5 |
| **Total** | **166** |

### Migración

Revisión: `c3a7e1f5b9d2`

Parent: `e2c4a6b8d0f1`

La migración:

- crea exclusivamente `marketing_campaign_v2_tariffs`;
- valida SHA-256 del snapshot;
- valida metadata, 166 filas, normalización, unicidad y familias;
- valida la distribución exacta;
- inserta las 166 filas;
- crea UNIQUE de `tarifa_key`;
- crea CHECK de los siete valores de `audience_family`;
- crea índice por `audience_family`;
- no escribe sobre `marketing_reactivation_tariffs`;
- en downgrade elimina sólo índice y tabla V2.

### Pruebas de integridad

Archivo:

`backend/tests/marketing/test_marketing_campaign_v2_tariff_catalog.py`

Cobertura:

- contrato del ORM y ausencia de `reactivation_group`;
- SHA-256 exacto del snapshot;
- detección de cualquier cambio de bytes;
- 166 filas;
- 166 `tarifa_key` únicas;
- cero colisiones;
- equivalencia con la normalización vigente;
- distribución 102/21/12/10/10/6/5;
- presencia de las 13 tarifas exclusivas V2;
- coexistencia de las dos categorías conflictivas sin alterar legacy;
- UNIQUE de `tarifa_key`;
- CHECK de `audience_family`;
- upgrade;
- downgrade conservando legacy.

Resultado del harness específico del milestone:

`6 passed`

### Hardening previo a PR

- Se agregó una regla específica en `.gitattributes`:
  `backend/data/reference/marketing_campaign_v2_tariffs_2026-09-30.json -text`.
  Esto impide conversiones automáticas de finales de línea o normalización de texto por Git, protegiendo el SHA-256 exacto del artefacto también en clones sobre Windows.
- `MarketingCampaignV2TariffORM` se exporta oficialmente desde `backend/app/models/__init__.py`, tanto en el import de `.marketing` como en `__all__`.
- La prueba específica importa el ORM V2 desde `app.models`, por lo que el export queda cubierto por la suite del milestone.
- El snapshot permanece sin cambios y conserva SHA-256 `00b9475ea8bdfbaf3c9d1d3571d630035ff315ab8cd374fb0339e18589162bae`.

## Fuera de alcance del Milestone 1

No se agregaron:

- endpoints;
- Angular;
- Campaign V2;
- Recipient V2;
- integración iVentas;
- cambios a Reactivaciones legacy.

## Milestone 2 — Persistencia base Campaign V2 + Recipient V2

Estado: **completado y mergeado vía PR #752 a `main` en `b949817eff87d3d82a0c2ff0f540576c028ded4c`**.

### Base y rama

- Base SHA: `8d9279e893e12a8ae351392ab2e7fbffbc6f73d1`
- Rama: `feat/campaign-v2-persistence-base`
- Head Alembic confirmado al partir: `c3a7e1f5b9d2`
- Nueva revisión: `a4d8c2e6f1b5`

### Decisiones de modelado

Se introducen dos entidades propias, sin reutilizar ni generalizar las tablas legacy:

- `MarketingCampaignV2ORM` → `marketing_campaign_v2_campaigns`
- `MarketingCampaignV2RecipientORM` → `marketing_campaign_v2_recipients`

Campaign V2 representa la campaña lógica ya congelada. No agrega estados de proveedor, delivery ni iVentas.

Campos de Campaign V2:

- `id`
- `name`
- `purpose`
- `source`
- `audience_definition_json`
- `created_by_user_id`
- `frozen_at`
- `created_at`
- `updated_at`

`purpose` acepta exclusivamente `NEW_SALE`, `REACTIVATION`, `ACTIVE_MEMBERS` y `UNCLASSIFIED`, con default seguro `UNCLASSIFIED`.

`source` queda como columna estructurada, pero sin CHECK cerrado para no bloquear nuevas fuentes futuras. La definición heterogénea de filtros se conserva en `audience_definition_json`; no sustituye las columnas estructuradas de identidad, purpose o source.

### Recipient V2 y política phone-only

La identidad operativa es `phone_mx10`. La normalización seguirá usando exclusivamente `backend/app/services/marketing_phone.py::normalize_phone()`.

Campos obligatorios del recipient:

- `campaign_id`
- `phone_mx10`
- `source`

Campos snapshot opcionales:

- `member_id`
- `member_pin`
- `member_name`
- `sucursal`
- `tarifa_raw`
- `categoria_tarifa`
- `audience_family`
- `fecha_vencimiento_date`
- `inclusion_reason`

Todos pueden ser NULL cuando la fuente no los garantice. Esto permite recipients de tipo phone-only, incluyendo la futura fuente `FUNNEL_PORTFOLIO`, sin implementar todavía Funnel.

No se crea `source_record_id` genérico.

### Referencias canónicas

Recipient V2 puede conservar opcionalmente:

- `socios_vencidos_cartera_id` → FK a `socios_vencidos_cartera.id`, `ON DELETE RESTRICT`
- `socios_activos_snapshot_row_id` → FK a `socios_activos_snapshot_rows.id`, `ON DELETE RESTRICT`

Estas referencias son evidencia de procedencia, no sustituyen el snapshot mínimo del recipient.

`campaign_id` usa `ON DELETE CASCADE`: al borrar una campaña V2 se elimina únicamente su cohorte persistida.

### Freeze e inmutabilidad

La campaña persistida incluye `frozen_at`. Los campos snapshot del recipient permanecen físicamente almacenados y no se reconstruyen por joins a la fuente viva.

Por tanto, cambios posteriores en Socios Vencidos, Socios Activos o catálogo no reescriben los valores congelados del recipient. Las FKs sirven para trazabilidad cuando el registro canónico existe; los datos esenciales para explicar la cohorte quedan en la propia fila.

La evidencia multi-segmento/multi-tag no se modela todavía: pertenece al Audience Builder. `inclusion_reason` conserva una razón primaria opcional sin cerrar la puerta a una tabla de composición posterior.

### Constraints e índices

Campaign V2:

- CHECK de `purpose`
- índices por `created_at`, `purpose` y `source`

Recipient V2:

- UNIQUE `(campaign_id, phone_mx10)`
- CHECK `length(phone_mx10) = 10`
- CHECK nullable de los siete valores aprobados de `audience_family`
- índices por `campaign_id`, `phone_mx10`, `socios_vencidos_cartera_id` y `socios_activos_snapshot_row_id`

### Migración

`a4d8c2e6f1b5_add_marketing_campaign_v2_persistence.py`

La migración crea únicamente las dos tablas V2 y sus constraints/índices. No modifica tablas ni datos legacy. El downgrade elimina primero Recipient V2 y luego Campaign V2.

### Pruebas específicas

Archivo:

`backend/tests/marketing/test_marketing_campaign_v2_persistence.py`

Cobertura:

- contrato ORM Campaign V2;
- propósito válido y default `UNCLASSIFIED`;
- rechazo de propósito inválido;
- contrato ORM Recipient V2;
- phone-only con campos de socio/sucursal/tarifa NULL;
- uso de `normalize_phone()`;
- UNIQUE por campaña/teléfono;
- mismo teléfono permitido en otra campaña;
- longitud de `phone_mx10`;
- `audience_family` válida/nullable;
- referencia opcional a Socios Vencidos;
- referencia opcional a Socios Activos;
- RESTRICT de referencias canónicas;
- CASCADE de campaña a recipients;
- snapshot persistido independiente de cambios en fuente viva;
- upgrade/downgrade;
- legacy intacto.

En el entorno de esta conversación no se pudo clonar el repositorio ni instalar dependencias faltantes por ausencia de red. Sí se ejecutó un harness aislado de persistencia con SQLAlchemy/Alembic/SQLite que cubrió defaults, phone-only, constraints, referencias canónicas, freeze, RESTRICT, CASCADE y round-trip de migración con legacy intacto. Resultado:

`5 passed`

También se validó con `py_compile` la migración exacta y un equivalente local del test específico. El archivo de prueba versionado no se ejecutó dentro del repo completo porque este entorno no dispone de sus dependencias Flask ni acceso de red.

### Fuera de alcance del Milestone 2

No se agregan:

- Audience Builder;
- preview/drill-down;
- endpoints;
- Angular;
- permisos nuevos;
- Funnel operacional;
- supresiones;
- CampaignProvider;
- delivery/WhatsApp;
- estados o sync iVentas;
- templates;
- scheduling;
- cambios al flujo de Reactivaciones legacy.

## Milestone 3 — Audience Builder backend + Preview V2

Estado: **completado en rama, pendiente de merge**.

### Base y rama

- Base SHA: `b949817eff87d3d82a0c2ff0f540576c028ded4c`
- Rama: `feat/campaign-v2-audience-preview`
- Milestone 2 ya estaba mergeado vía PR #752.
- No se agregó migración: este milestone es exclusivamente read-only/in-memory.

### Arquitectura

Nuevo servicio:

`backend/app/services/marketing_campaign_v2_audience_service.py`

El motor mantiene una sola tubería V2:

`fuente canónica → scope → estado actual cuando aplica → clasificación V2 → familias seleccionadas → teléfono → deduplicación → Preview/Detail`

Dos dataclasses internas representan el flujo sin persistirlo:

- `MarketingCampaignV2AudienceCandidate`: candidato previo a freeze, con source ref, teléfono, identidad opcional, sucursal, tarifa, clasificación, fecha y evidencia.
- `MarketingCampaignV2RecipientCandidate`: teléfono final deduplicado con metadata de consenso, `conflict_fields` y todas las filas de evidencia.

El Preview no crea `MarketingCampaignV2ORM` ni `MarketingCampaignV2RecipientORM`.

### EXPIRED_MEMBERS

Fuente canónica: `SociosVencidosCarteraORM`.

El rango `expiration_date_from..expiration_date_to` es inclusivo.

El scope se aplica con `normalize_socios_vencidos_branch_key()`.

Para determinar si el episodio sigue siendo realmente vencido se reutilizan exclusivamente:

- `prepare_socios_vencidos_current_status_context()`
- `resolve_socios_vencidos_rows_with_context()`

Esto reutiliza el matcher vigente vencido↔activo y el snapshot activo canónico, pero corta antes del resolver específico de Reactivaciones.

Política fail-closed de estado actual:

- `NOT_FOUND` continúa como candidato vencido.
- cualquier evidencia `ACTIVE_CONFIRMED`, `ACTIVE_REVIEW`, `AMBIGUOUS` o `IDENTIFIER_CONFLICT` queda fuera del recipient final y se conserva en `current_status_counts` / `CURRENT_STATUS_BLOCKED`.

No se importa ni invoca el resolver de candidatos de Reactivaciones y no hay dependencia iVentas.

### ACTIVE_MEMBERS

El servicio llama obligatoriamente:

`resolve_latest_canonical_socios_activos_snapshot()`

y lee filas individuales `SociosActivosSnapshotRowORM` sólo del snapshot resuelto.

El Preview conserva:

- `activos_snapshot_id`
- `activos_cutoff_date`
- `activos_captured_at`
- `snapshot_kind`

Cada candidato conserva `SOCIOS_ACTIVOS_SNAPSHOT_ROW`, row id y snapshot id como referencia canónica.

### Scope y filtros

`allowed_sucursal_keys=None` significa scope global.

Una colección explícita —incluida una colección vacía— se normaliza con el matcher vigente y limita el universo backend.

Para `EXPIRED_MEMBERS` son obligatorios los dos extremos del rango.

Para `ACTIVE_MEMBERS` no se aceptan filtros de vencimiento.

`audience_families` exige al menos una de las cinco familias comerciales seleccionables:

- `DOMICILIADO`
- `TRIMESTRAL`
- `CONVENIO`
- `SEMESTRE`
- `ESTUDIANTE`

La selección es OR dentro de familias y AND respecto a source/scope/rango.

`MES`, `OUT_OF_SEGMENT` y tarifa sin match permanecen visibles en composición pero no son valores seleccionables del filtro comercial.

### Teléfono

La única identidad general es `phone_mx10`.

Se reutiliza exclusivamente `marketing_phone.normalize_phone()`.

Para Socios Activos se intenta primero el teléfono disponible y, si no normaliza, se vuelve a llamar el mismo `normalize_phone()` con `lada + teléfono`; no existe un normalizador V2 adicional.

Los inválidos permanecen en `INVALID_PHONE`.

### Clasificación de tarifa

Se consulta exclusivamente `MarketingCampaignV2TariffORM`.

La llave se obtiene con el helper puro vigente `normalize_reactivation_tariff_key()`, cuya semántica es exactamente la normalización aprobada en Milestone 1.

No se consulta `MarketingReactivationTariffORM`, no se lee `reactivation_group` y no se hereda ninguna exclusión legacy.

Una tarifa sin match conserva `tarifa_key` normalizada pero queda con `audience_family=None` y bucket `UNCLASSIFIED`.

### Deduplicación y conflictos

La deduplicación final es por `phone_mx10`.

El orden es estable por teléfono y referencia canónica.

Para un teléfono con varias filas:

- todas las filas quedan en `evidence_rows`;
- `duplicate_count = filas válidas absorbidas después de la primera referencia estable`;
- cada campo de metadata se conserva sólo cuando todos sus valores no nulos coinciden;
- si hay dos valores no nulos distintos, el valor consolidado queda `None` y el campo se agrega a `conflict_fields`.

Por tanto el orden de query nunca elige silenciosamente nombre, sucursal, tarifa o family como “verdad”.

### Contrato del Preview

`build_campaign_v2_audience_preview()` devuelve:

- `source`
- `source_metadata`
- `filters` normalizados
- `universe_count`
- `scoped_count`
- `current_status_counts`
- `current_status_blocked_count`
- `filtered_count`
- `family_counts`
- `unclassified_family_count`
- `out_of_segment_count`
- `invalid_phone_count`
- `duplicate_count`
- `unique_recipient_count`

`family_counts` describe filas clasificadas después de scope/estado actual y antes de selección/deduplicación. `filtered_count` son filas pertenecientes a las familias seleccionadas antes de bloqueo por teléfono.

### Drill-down

`build_campaign_v2_audience_preview_detail()` reconstruye el plan desde las mismas fuentes/filtros y permite buckets:

- `RECIPIENTS`
- `INVALID_PHONE`
- `DUPLICATES`
- `OUT_OF_SEGMENT`
- `UNCLASSIFIED`
- `FAMILY` + `audience_family`
- `CURRENT_STATUS_BLOCKED`

La paginación es estable.

Antes de paginar se compara el total reconstruido del bucket contra el contador del Preview. Si diverge, lanza `RuntimeError` y falla cerrado.

### Helpers reutilizados

Se reutilizan:

- `marketing_phone.normalize_phone()`
- `marketing_tariff_normalization.normalize_marketing_tariff_key()` como helper puro compartido de tarifa
- `marketing_reactivation_service.normalize_reactivation_tariff_key()` se conserva como API legacy compatible y delega al helper puro
- `socios_vencidos_current_status_resolver.normalize_socios_vencidos_branch_key()`
- `prepare_socios_vencidos_current_status_context()`
- `resolve_socios_vencidos_rows_with_context()`
- `resolve_latest_canonical_socios_activos_snapshot()`

Hardening previo a PR: la normalización de tarifa se extrajo de `marketing_reactivation_service.py` para eliminar la dependencia transitiva V2 → Reactivaciones/iVentas. La API legacy conserva nombre y resultados mediante delegación; no se refactorizó ninguna otra regla legacy.

### Pruebas específicas

Nuevo archivo:

`backend/tests/marketing/test_marketing_campaign_v2_audience_service.py`

Cobertura escrita:

- OR de familias y AND con source/scope/rango;
- MES separado;
- OUT_OF_SEGMENT separado;
- UNCLASSIFIED separado;
- familias comerciales válidas;
- `normalize_phone()` y fallback lada+teléfono con el mismo normalizador;
- inválidos;
- deduplicación por `phone_mx10`;
- determinismo ante orden invertido;
- conflictos de metadata explícitos;
- rango vencidos inclusivo;
- scope vencidos;
- current-status canónico;
- ausencia de iVentas/reactivation_group en el builder;
- snapshot canónico de activos;
- referencia snapshot/row activo;
- catálogo V2 exclusivo;
- paginación estable;
- preview count == detail count;
- mismatch fail-closed;
- bucket de estado actual bloqueado.

Resultado realmente ejecutado en harness aislado con stubs mínimos de las dependencias del repo antes del hardening:

`9 passed in 0.07s`

Hardening de frontera previo a PR:

- se agregó `backend/app/services/marketing_tariff_normalization.py`;
- V2 ya no importa `marketing_reactivation_service`;
- la API legacy delega al helper compartido;
- `backend/tests/marketing/test_marketing_tariff_normalization.py` demuestra equivalencia exacta para caso normal, whitespace, Unicode NFKC, `None` y vacío;
- la suite M3 incluye una comprobación AST de que el módulo V2 no importa `app.services.marketing_reactivation_service` y sí importa directamente el helper puro.

Resultados reales del hardening en harness aislado:

- suite M3 ejecutada con un stub de `marketing_reactivation_service.py` que falla inmediatamente si llega a importarse: `10 passed in 0.06s`;
- equivalencia helper compartido ↔ API legacy: `5 passed in 0.03s`;
- ejecución conjunta de ambas suites: `15 passed in 0.05s`;
- `py_compile` pasó para el servicio V2, helper compartido y ambos archivos de prueba.

La primera ejecución demuestra la frontera de imports de forma dinámica: importar y probar `marketing_campaign_v2_audience_service` no necesita cargar `marketing_reactivation_service`.

También pasaron `py_compile` del servicio y del test exactos.

Limitación del entorno: no hay acceso de red para clonar el repo y no están instalados Flask/Flask-SQLAlchemy. Por ello no se ejecutó el archivo de pytest dentro del árbol completo de Suite Ultra, PostgreSQL, toda la suite ni CI. Los tests de Milestone 1 y Milestone 2 no pudieron reejecutarse aquí; sus archivos/modelos/migraciones no fueron modificados por Milestone 3.

### Fuera de alcance

No se agregó:

- creación/freeze de Campaign V2 desde Preview;
- endpoints;
- Angular;
- permisos HTTP;
- Funnel;
- PREVIOUS_CAMPAIGN;
- supresión Funnel contra activos;
- iVentas;
- provider/broadcast;
- costos;
- templates;
- scheduling;
- migraciones;
- cambios de semántica legacy.

## Siguiente milestone propuesto

**Milestone 4 — Freeze/Create server-side desde Preview V2**

Objetivo recomendado: tomar una definición de Preview validada, reconstruir el universo server-side con el mismo builder, exigir consistencia/fail-closed y persistir `MarketingCampaignV2ORM` + `MarketingCampaignV2RecipientORM` usando la evidencia y snapshots del Milestone 3. Todavía sin endpoints/Angular si se mantiene la progresión backend-first.
