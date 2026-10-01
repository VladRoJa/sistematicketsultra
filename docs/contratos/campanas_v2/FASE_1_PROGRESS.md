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

Estado: **completado y mergeado vía PR #753 a `main` en `be2fe1305c059382cf053ead2032af745ef74f3d`**.

### Base y rama

- Base SHA: `b949817eff87d3d82a0c2ff0f540576c028ded4c`
- Rama: `feat/campaign-v2-audience-preview`
- Milestone 2 ya estaba mergeado vía PR #752.
- Validación conjunta real previa al merge: `77 passed`.
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


### Hardening de parser Alembic previo a PR

La suite real conjunta detectó una regresión exclusivamente en test:

`python -m pytest tests/marketing/test_marketing_campaign_v2_tariff_catalog.py tests/marketing/test_marketing_campaign_v2_persistence.py tests/marketing/test_marketing_campaign_v2_audience_service.py tests/marketing/test_marketing_tariff_normalization.py tests/services/test_marketing_reactivation_campaign_service.py -q --basetemp .pytest_tmp`

Resultado previo reportado: `73 passed, 1 failed`, con fallo en `test_alembic_has_single_head_for_nullable_campaign_recipient_migration()`.

Alembic real no tenía bifurcación: `flask db heads` devolvió únicamente `a4d8c2e6f1b5 (head)`.

La causa era el parser del test, que sólo reconocía asignaciones sin anotación. Se corrigió exclusivamente `backend/tests/services/test_marketing_reactivation_campaign_service.py`:

- acepta `revision = "..."` y `revision: str = "..."`;
- acepta `down_revision` con o sin type annotation;
- conserva extracción de todos los parents citados, incluido un tuple tipado;
- agrega un caso explícito para `revision: str = ...`;
- la prueba de grafo ya no fija el head obsoleto `b9e2f7a4d3c5`, sino que exige exactamente un head.

No se creó merge migration y no se modificó ninguna migración, modelo, servicio productivo ni Audience Builder.

Validación ejecutada en este entorno para el parser: `4 cases passed`, incluyendo el caso real `c1d4e7f9a2b3 -> b9e2f7a4d3c5`.

Limitación: este entorno no dispone de Flask/Flask-SQLAlchemy y no puede instalar dependencias ni clonar el repo por falta de red. Por ello la suite real conjunta anterior no pudo reejecutarse aquí. Tampoco existe `.github/workflows` en la rama para delegar esa ejecución a GitHub Actions. El cambio queda preparado para repetir exactamente el comando anterior en un entorno completo.

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


## Milestone 4 — Freeze/Create server-side desde Preview V2

Estado: **completado en rama, pendiente de merge**.

### Base y rama

- Base obligatoria confirmada: `be2fe1305c059382cf053ead2032af745ef74f3d`.
- Esa base corresponde al merge del PR #753 de Milestone 3.
- Rama: `feat/campaign-v2-freeze-create`.
- Head Alembic confirmado antes de crear persistencia nueva: `a4d8c2e6f1b5`.
- No existía ninguna migración hija de `a4d8c2e6f1b5` en `main`.

### Decisión de persistencia de evidencia

El Recipient V2 de Milestone 2 no era suficiente para congelar completamente la semántica real de Milestone 3:

- un mismo `phone_mx10` puede absorber varias `evidence_rows`;
- cada evidencia puede apuntar a una fila canónica distinta;
- M3 conserva `conflict_fields` y deliberadamente deja metadata consolidada en NULL cuando hay conflicto;
- las dos FKs summary existentes no podían representar múltiples referencias sin elegir una arbitrariamente.

Por ello Milestone 4 agrega persistencia estructurada 1:N:

`MarketingCampaignV2RecipientORM -> MarketingCampaignV2RecipientEvidenceORM`

No se guarda la evidencia como mega-JSON ni se introduce `source_record_id` genérico.

Recipient summary agrega únicamente:

- `conflict_fields_json`: lista congelada de campos conflictivos detectados por M3.

Evidence V2 conserva por fila:

- `recipient_id`
- `evidence_order`
- `source`
- `phone_raw`
- `phone_mx10`
- `socios_vencidos_cartera_id`
- `socios_activos_snapshot_row_id`
- `socios_activos_snapshot_id`
- `member_id`
- `member_pin`
- `member_name`
- `sucursal`
- `sucursal_key`
- `tarifa_raw`
- `tarifa_key`
- `categoria_tarifa`
- `audience_family`
- `fecha_vencimiento_date`
- `current_status`
- `evidence_json`
- `created_at`

Las FKs canónicas son explícitas y nullable; por tanto el esquema sigue soportando una fuente futura phone-only.

### Política de referencias summary

La fila principal Recipient conserva una FK singular sólo si:

1. existe exactamente una `evidence_row`;
2. no existen `conflict_fields`;
3. la evidencia corresponde inequívocamente a una referencia canónica conocida.

Entonces:

- EXPIRED_MEMBERS → `socios_vencidos_cartera_id`;
- ACTIVE_MEMBERS → `socios_activos_snapshot_row_id`.

Si hay varias evidencias o conflicto, ambas FKs summary quedan NULL. La procedencia completa permanece en Evidence V2.

Nunca se elige primera/última/menor ID como referencia principal.

### Migración

Nueva revisión:

`f6c1d8a3b2e4_add_campaign_v2_recipient_evidence.py`

Cadena:

`a4d8c2e6f1b5 -> f6c1d8a3b2e4`

Upgrade:

- agrega `conflict_fields_json JSON NOT NULL DEFAULT []` a Recipient V2;
- crea `marketing_campaign_v2_recipient_evidence`;
- FK Evidence → Recipient usa CASCADE;
- FKs hacia Socios Vencidos, Socios Activos row y Socios Activos snapshot usan RESTRICT;
- UNIQUE `(recipient_id, evidence_order)`;
- CHECK de teléfono de 10 dígitos;
- CHECK nullable de `audience_family`;
- índices por recipient y referencias canónicas.

Downgrade elimina Evidence V2 y luego `conflict_fields_json`.

No se modifica ni reescribe `a4d8c2e6f1b5`. Legacy queda intacto.

### Servicio Freeze/Create

Nuevo servicio:

`backend/app/services/marketing_campaign_v2_creation_service.py`

Interfaz principal:

- `build_campaign_v2_freeze_preview(...)`
- `freeze_campaign_v2(...)`

`freeze_campaign_v2()` recibe exclusivamente definición de negocio:

- `name`
- `purpose`
- `source`
- `audience_families`
- `allowed_sucursal_keys`
- rango de vencimiento cuando aplica
- `expected_preview_fingerprint`
- `created_by_user_id`

No acepta:

- recipients;
- recipient IDs;
- phones;
- filas Preview;
- source record IDs.

Create siempre vuelve a llamar al mismo `_build_campaign_v2_audience_plan()` de Milestone 3. El caller no es autoridad sobre las filas.

### Consistencia Preview → Create

Se introdujo un fingerprint determinista server-side:

`PREVIEW_FINGERPRINT_VERSION = "campaign-v2-freeze-v1"`

Algoritmo:

1. reconstruir el plan M3;
2. construir una representación canónica;
3. serializar JSON con `sort_keys=True` y separadores estables;
4. calcular SHA-256.

Incluye:

- versión;
- source;
- filtros normalizados;
- source metadata/snapshot;
- resumen completo del Preview;
- recipients finales deduplicados;
- `conflict_fields`;
- todas las `evidence_rows`;
- referencias canónicas;
- metadata congelada por evidencia;
- tags/evidence relevantes.

Recipients se ordenan por `phone_mx10` y evidencias por una llave canónica estable antes del hash.

Por ello:

- distinto orden de query → mismo fingerprint;
- cambio de filtro → fingerprint distinto;
- cambio de snapshot/source metadata → distinto;
- recipients distintos con mismo conteo → distinto;
- cambio de referencia/evidencia → distinto.

Create reconstruye nuevamente y compara contra `expected_preview_fingerprint`. Mismatch falla cerrado antes de persistir.

### Campaign V2 congelada

Se persiste:

- `name`
- `purpose`
- `source`
- `audience_definition_json`
- `created_by_user_id`
- `frozen_at`
- timestamps existentes.

`audience_definition_json` conserva únicamente:

- schema version;
- filtros normalizados;
- source metadata;
- fingerprint/version;
- resumen de composición.

No contiene la lista de recipients.

Una audiencia con `unique_recipient_count == 0` se rechaza antes de `session.add()`.

### Mapping RecipientCandidate → Recipient ORM

Se usa directamente el resultado deduplicado de M3, sin renormalizar ni rededuplicar:

- `phone_mx10`
- `source`
- `member_id`
- `member_pin`
- `member_name`
- `sucursal`
- `tarifa_raw`
- `categoria_tarifa`
- `audience_family`
- `fecha_vencimiento -> fecha_vencimiento_date`
- `inclusion_reason`
- `conflict_fields -> conflict_fields_json`
- FK summary sólo bajo la política inequívoca descrita arriba.

Los campos conflictivos permanecen NULL exactamente como los entrega M3.

### Mapping Evidence

Cada `recipient_candidate.evidence_rows` produce una Evidence ORM ordenada explícitamente con la misma llave canónica usada por el fingerprint; no se altera la deduplicación ni se introduce prioridad comercial.

EXPIRED_MEMBERS:

- `source_ref_type = SOCIOS_VENCIDOS_CARTERA`
- `source_ref_id -> socios_vencidos_cartera_id`

ACTIVE_MEMBERS:

- `source_ref_type = SOCIOS_ACTIVOS_SNAPSHOT_ROW`
- `source_ref_id -> socios_activos_snapshot_row_id`
- `source_snapshot_id -> socios_activos_snapshot_id`

Los demás valores se copian como snapshot, no se reconstruyen posteriormente mediante joins vivos.

### Atomicidad

El servicio construye el grafo:

`Campaign -> Recipients -> Evidence`

antes de persistir.

Boundary:

- un `session.add(campaign)`;
- un `session.flush()`;
- un `session.commit()`;
- cualquier `IntegrityError`/error SQLAlchemy → rollback completo y excepción V2 de persistencia;
- una excepción no SQLAlchemy también hace rollback y se propaga.

No hay commits por recipient/evidence.

### Excepciones V2

- `MarketingCampaignV2CreationValidationError`
- `MarketingCampaignV2PreviewMismatchError`
- `MarketingCampaignV2EmptyAudienceError`
- `MarketingCampaignV2PersistenceError`

No se devuelve `None` silenciosamente.

### Pruebas específicas

Nuevo archivo:

`backend/tests/marketing/test_marketing_campaign_v2_creation_service.py`

Cobertura:

- firma create no acepta recipients/phones/IDs arbitrarios;
- fingerprint determinista ante cambio de orden;
- cambio de filtros rechaza;
- cambio de source snapshot rechaza;
- recipients distintos con mismo conteo rechazan;
- cambio de evidencia rechaza;
- rebuild server-side;
- campaña y definición congeladas;
- campaña vacía falla antes de persistir;
- source/filter inválido falla antes de persistir;
- exactamente un Recipient por phone proveniente de M3;
- summary FK singular sólo cuando es inequívoca;
- conflicto conserva NULL + `conflict_fields_json`;
- múltiples evidencias por recipient;
- Active Member conserva snapshot + row explícitos;
- fallo de integridad hace rollback completo;
- upgrade/downgrade de migración;
- defaults/constraints de evidencia;
- snapshots permanecen inmutables ante cambios de fuente viva;
- CASCADE Campaign → Recipient → Evidence;
- RESTRICT hacia referencias canónicas de vencidos, active row y active snapshot;
- esquema Recipient sigue representando fuentes phone-only;
- reclasificar posteriormente category/family no modifica valores ya congelados;
- legacy intacto.

Resultado realmente ejecutado en harness aislado con SQLAlchemy/Alembic/SQLite y stubs mínimos de las dependencias de Suite, sobre los bytes finales del servicio/migración/test:

`15 passed in 0.34s`

También pasó `py_compile` para servicio, migración y test específicos.

### Regresiones y limitaciones

Baseline real antes de iniciar M4: la validación conjunta de M1 + M2 + M3 + normalización + legacy tocado terminó en `77 passed` antes del merge de PR #753.

En este entorno no hay checkout completo de Suite ni Flask/Flask-SQLAlchemy instalados y no hay red para clonar/instalar dependencias. Por ello no se ejecutó aquí PostgreSQL, `flask db upgrade`, la suite real de 77 tests, toda la suite ni CI.

La regresión específica de M4 sí se ejecutó en el harness indicado. Los archivos de M1/M2/M3 no son modificados por M4 salvo la ampliación compatible del modelo Recipient y el nuevo export de Evidence.

### Fuera de alcance

No se agregó:

- rutas Flask;
- JWT/request access;
- permisos HTTP;
- Angular;
- menú;
- UI Preview;
- iVentas delivery/stats;
- provider/broadcast;
- costos;
- Funnel operacional;
- ACTIVE_MEMBER_SUPPRESSION;
- PREVIOUS_CAMPAIGN operacional;
- scheduling;
- templates.

## Milestone 5 — API backend Campaign V2 + permisos y scope

Estado: **completado y mergeado vía PR #755 a `main` en `dd2e1d6ebbfe756d419d266fc833bb33046953a7`**.

### Base y rama

- Base obligatoria confirmada: `68d5e2b0988efa13d69c7e11697a1742c7a48c6d`.
- Esa base corresponde al merge del PR #754 de Milestone 4.
- Baseline real previo al milestone: `92 passed`.
- Rama: `feat/campaign-v2-api-permissions`.
- Validación real conjunta previa al merge: `132 passed`.
- No se agregó migración: M4 ya dejó el esquema suficiente para API/lectura.

### Permiso backend

Campaign V2 reutiliza la autoridad existente de Marketing:

`resolve_marketing_access(user)`

La gestión completa V2 exige explícitamente:

`access.can_edit_inputs == True`

No usa `can_view_reactivation` como permiso V2 y no agrega ifs por rol.

El blueprint V2 obtiene el usuario desde JWT, resuelve `UserORM.get_by_id()`, llama `resolve_marketing_access()` y después ejecuta `_require_campaign_v2_management(access)`.

El archivo V2 no importa `marketing_routes.py` ni depende de `_request_targets_reactivation()`; por tanto no hereda accidentalmente la heurística especial de paths `/reactivation`.

### Scope backend y mapper compartido

Se extrajo el mapper genérico sucursal Suite → Track branch key a:

`backend/app/services/marketing_branch_scope.py::marketing_branch_keys_by_sucursal_ids()`

Usa `TrackBranchCatalogORM` activo y `normalize_socios_vencidos_branch_key()`.

El wrapper legacy:

`reactivation_branch_keys_by_sucursal_ids()`

se conserva con el mismo nombre y ahora delega al helper compartido. No se cambió semántica del legacy.

Campaign V2 deriva scope exclusivamente del `MarketingAccess` autenticado:

- `access.is_global=True` → `allowed_sucursal_keys=None`;
- scope parcial → sólo keys provenientes de `access.branch_ids`;
- mapper sin keys válidas → 403 fail-closed;
- el payload nunca puede enviar `allowed_sucursal_keys`.

### Blueprint y rutas

Nuevo blueprint:

`backend/app/routes/marketing_campaign_v2_routes.py`

Registrado en app factory bajo:

`url_prefix="/api/marketing"`

Rutas:

- `GET /api/marketing/campaigns-v2/options`
- `POST /api/marketing/campaigns-v2/preview`
- `POST /api/marketing/campaigns-v2/preview-detail`
- `POST /api/marketing/campaigns-v2`
- `GET /api/marketing/campaigns-v2`
- `GET /api/marketing/campaigns-v2/<campaign_id>`
- `GET /api/marketing/campaigns-v2/<campaign_id>/recipients`
- `GET /api/marketing/campaigns-v2/<campaign_id>/recipients/<recipient_id>`
- `PATCH /api/marketing/campaigns-v2/<campaign_id>/purpose`

Todas requieren JWT y el permiso de gestión V2.

### Options

Devuelve dominios estables para la futura UI:

- sources: `EXPIRED_MEMBERS`, `ACTIVE_MEMBERS`;
- selectable families: `DOMICILIADO`, `TRIMESTRAL`, `CONVENIO`, `SEMESTRE`, `ESTUDIANTE`;
- non-selectable: `MES`, `OUT_OF_SEGMENT`, `UNCLASSIFIED`;
- purposes: `NEW_SALE`, `REACTIVATION`, `ACTIVE_MEMBERS`, `UNCLASSIFIED`;
- scope backend resuelto.

No consulta ni devuelve iVentas.

### Preview

`POST /campaigns-v2/preview` llama exclusivamente:

`build_campaign_v2_freeze_preview()`

Payload permitido:

- `source`
- `audience_families`
- `expiration_date_from`
- `expiration_date_to`

El route inyecta `allowed_sucursal_keys` desde backend.

Devuelve el Preview M3 completo más:

- `preview_fingerprint_version`
- `preview_fingerprint`

No persiste.

### Preview Detail

`POST /campaigns-v2/preview-detail` usa:

`build_campaign_v2_audience_preview_detail()`

Payload permitido:

- definición de audiencia;
- `bucket`;
- `audience_family`;
- `page`;
- `page_size`.

Scope siempre backend. Conserva el rebuild y fail-closed contador Preview == Detail de M3.

### Freeze/Create

`POST /campaigns-v2` permite sólo:

- `name`
- `purpose`
- `source`
- `audience_families`
- rango de vencimiento cuando aplica
- `expected_preview_fingerprint`

No acepta:

- `allowed_sucursal_keys`
- `created_by_user_id`
- `recipients`
- `recipient_ids`
- `phones`
- `source_record_ids`
- `evidence_rows`.

El route pasa internamente:

- `created_by_user_id=user.id`;
- `allowed_sucursal_keys=scope backend`.

M4 sigue siendo la autoridad para rebuild, fingerprint, atomicidad y persistencia.

### Read/query service

Nuevo servicio:

`backend/app/services/marketing_campaign_v2_query_service.py`

Trabaja exclusivamente con:

- `MarketingCampaignV2ORM`
- `MarketingCampaignV2RecipientORM`
- `MarketingCampaignV2RecipientEvidenceORM`

No consulta Socios Activos/Vencidos para reconstruir valores históricos.

Operaciones:

- `list_campaign_v2()`
- `get_campaign_v2()`
- `list_campaign_v2_recipients()`
- `get_campaign_v2_recipient()`
- `update_campaign_v2_purpose()`.

### Visibilidad de campañas congeladas

La campaña es una cohorte atómica.

El query service lee `audience_definition_json.filters.allowed_sucursal_keys` congelado y aplica política fail-closed:

- definición ausente/malformada → no visible, incluso para un scope que no necesita inferencia;
- usuario global → puede ver campañas con definición de scope válida, tanto globales como locales;
- usuario parcial → una campaña global (`allowed_sucursal_keys=None`) no es visible;
- usuario parcial → campaña local sólo es visible si todo su scope congelado está contenido en el scope actual;
- no se devuelve una vista parcial.

Campaign inexistente y Campaign existente fuera de scope se presentan como el mismo 404.

### List y Campaign Detail

List:

- paginación estable;
- orden `frozen_at DESC, id DESC`;
- filtros opcionales únicamente `purpose` y `source`;
- recipient count agregado;
- fingerprint/version cuando existe.

Campaign Detail devuelve datos congelados:

- identidad/purpose/source/timestamps;
- creator;
- recipient_count;
- fingerprint;
- `audience_definition`.

No hay joins a fuentes vivas.

### Recipients y Evidence

Listado:

`GET /campaigns-v2/<campaign_id>/recipients`

- paginación estable;
- orden `recipient.id ASC`;
- summary congelado;
- `conflict_fields`;
- `evidence_count` agregado sin cargar Evidence completa por cada row.

Detalle:

`GET /campaigns-v2/<campaign_id>/recipients/<recipient_id>`

devuelve summary + todas las `MarketingCampaignV2RecipientEvidenceORM` congeladas ordenadas por:

`evidence_order ASC, id ASC`.

El recipient debe pertenecer a la Campaign indicada; un ID de otra Campaign responde como no encontrado.

### PATCH purpose

Única mutación posterior al freeze:

`PATCH /campaigns-v2/<campaign_id>/purpose`

Payload permitido únicamente:

`purpose`

Valores:

- `NEW_SALE`
- `REACTIVATION`
- `ACTIVE_MEMBERS`
- `UNCLASSIFIED`.

Modifica sólo:

- `purpose`;
- `updated_at`.

No modifica `frozen_at`, definición, fingerprint, recipients ni evidence.

### Errores HTTP

- JWT ausente/inválido → manejo estándar JWT, 401;
- sin permiso/scope backend resoluble → 403;
- payload/query/definición inválida → 400;
- Campaign/Recipient inexistente o fuera de scope → 404;
- Preview mismatch → 409;
- audiencia vacía al Freeze → 409;
- persistencia Freeze → 500 genérico;
- inesperado → 500 genérico.

No se filtran detalles SQL ni stack traces.

### Pruebas M5

Archivos agregados:

- `backend/tests/marketing/test_marketing_branch_scope.py`
- `backend/tests/marketing/test_marketing_campaign_v2_query_service.py`
- `backend/tests/marketing/test_marketing_campaign_v2_routes.py`

Cobertura versionada incluye:

- JWT obligatorio;
- usuario inválido;
- permiso `can_edit_inputs`;
- independencia de `can_view_reactivation` y heurística Reactivaciones;
- global/partial/empty scope;
- mapper sucursal → key y wrapper legacy;
- allowlists de payload;
- spoof de scope/creator/cohort rechazado;
- Preview + fingerprint;
- Detail M3;
- Freeze creator/fingerprint/scope;
- mapping 400/403/404/409/500 relevante;
- list/read scope fail-closed;
- campaña global oculta a usuario parcial;
- definición malformada oculta;
- recipient ajeno no revelado;
- paginación estable;
- counts de recipients/evidence;
- evidence congelada en orden;
- purpose como única mutación.

Validación realmente ejecutada en este runtime sobre el código M5:

- helper/branch scope harness: `2 passed`;
- query/read harness con SQLAlchemy/SQLite: `9 passed`;
- route/scope harness con Flask/JWT stubs mínimos: `8 passed`;
- combinado: `19 passed in 0.23s`;
- `py_compile` pasó para los tres archivos productivos nuevos y los tres tests versionados.

Limitación: este runtime no tiene Flask, Flask-JWT-Extended ni Flask-SQLAlchemy y no tiene acceso de red para instalar/clonar. Por ello los tests Flask versionados, el corredor real M1-M5, PostgreSQL, CI y full suite no se ejecutaron aquí.

Baseline real confirmado antes de M5: `92 passed`.

### Migraciones

No hay migración M5.

No se modificó la cadena Alembic de M4.

### Fuera de alcance

No se agregó:

- Angular;
- ruta/menu frontend;
- service Angular;
- iVentas provider/broadcast/stats;
- costos/templates;
- Funnel operacional;
- ACTIVE_MEMBER_SUPPRESSION;
- PREVIOUS_CAMPAIGN operacional;
- mutación de cohorte;
- nuevo sistema de permisos.

## Milestone 6 — Angular Campaign V2 + integración Fase 1

Estado: **completado y mergeado vía PR #756 a `main` en `aec0e78022d2acf03b3fe1b1887d4f7676e0c6d9`**.

### Base y rama

- Base obligatoria confirmada: `dd2e1d6ebbfe756d419d266fc833bb33046953a7`.
- Esa base corresponde al merge del PR #755 de Milestone 5.
- Baseline backend real antes de M6: `132 passed`.
- Rama: `feat/campaign-v2-angular-phase1`.
- No se modificó backend ni Alembic.

### Ruta Angular

Nueva ruta independiente:

`/marketing/campaigns-v2`

Con hash routing:

`/#/marketing/campaigns-v2`

La ruta legacy `/marketing/reactivation` permanece intacta.

### Archivos/componentes

Nuevo módulo bajo:

`frontend/src/app/marketing-campaign-v2/`

Archivos principales:

- `marketing-campaign-v2.models.ts`
- `marketing-campaign-v2.logic.ts`
- `marketing-campaign-v2-menu.ts`
- `marketing-campaign-v2.service.ts`
- `marketing-campaign-v2-page.component.ts/.html/.css`
- `marketing-campaign-v2-preview-detail-dialog.component.ts/.html/.css`
- `marketing-campaign-v2-campaign-detail-dialog.component.ts/.html/.css`
- `marketing-campaign-v2-recipient-detail-dialog.component.ts/.html/.css`
- `marketing-campaign-v2.logic.node-test.ts`

Runner nuevo:

`frontend/scripts/test-campaign-v2.cjs`

Todos los componentes conservan archivos TypeScript/HTML/CSS separados; no hay template/style inline.

### Menú y acceso backend-authoritative

`layout.component.ts` consulta:

`GET /api/marketing/campaigns-v2/options`

sin construir Authorization headers manualmente.

Política:

- 200 → publica `Campañas V2`;
- error/401/403 → no publica;
- si `Marketing y Conversión` ya existe, agrega el submenu;
- si no existe pero backend autoriza V2, crea el grupo;
- `withCampaignV2MenuItem()` hace la mutación idempotente y evita duplicados;
- la entrada legacy `Campañas → /marketing/reactivation` no se renombra ni elimina.

No se reutiliza `puedeVerMarketingReactivacionPorRol()` como autoridad V2.

### Service Angular

`MarketingCampaignV2Service` usa exclusivamente `environment.apiUrl` + `HttpClient`.

No lee token/localStorage ni construye Authorization.

Métodos:

- `getOptions()`
- `preview()`
- `previewDetail()`
- `freeze()`
- `listCampaigns()`
- `getCampaign()`
- `listRecipients()`
- `getRecipient()`
- `updatePurpose()`

Corresponden exactamente a las nueve operaciones M5.

### Modelos TypeScript

Se modelaron explícitamente:

- `CampaignV2Source`
- `CampaignV2AudienceFamily`
- `CampaignV2ObservedFamily`
- `CampaignV2Purpose`
- `CampaignV2PreviewBucket`
- Options/scope;
- Preview/filter/source metadata/family counts;
- Preview Detail;
- Freeze request/response;
- Campaign summary/detail;
- paginación;
- Recipient summary/detail;
- Evidence.

No se usa `any` como contrato principal.

### Builder UX

Pantalla operativa dividida conceptualmente en:

- Nueva campaña;
- Historial Campaign V2.

Builder:

- fuente desde Options;
- familias seleccionables desde Options;
- shortcut `Seleccionar todas`;
- mínimo una familia;
- EXPIRED muestra y exige ambas fechas;
- ACTIVE limpia fechas y nunca las envía;
- no existe selector de sucursal;
- scope backend se muestra sólo como información;
- nombre y purpose están visualmente separados de la definición de audiencia;
- purpose no se deriva automáticamente desde source.

### Invalidación Preview/fingerprint

Cambios en:

- source;
- audience_families;
- expiration_date_from;
- expiration_date_to

ejecutan `invalidatePreview()`.

Cambios de:

- name;
- purpose

no invalidan Preview.

El fingerprint sólo vive en memoria del componente.

Freeze queda deshabilitado si no existe Preview vigente, fingerprint, audiencia > 0, nombre/purpose válidos o existe request en curso.

### Preview visual

Se muestran:

- universe;
- scoped;
- filtered;
- unique recipients;
- invalid phones;
- duplicates;
- out-of-segment;
- tarifa sin clasificación;
- current-status blocked;
- composición por las cinco familias + MES + OUT_OF_SEGMENT;
- metadata importante de la fuente.

`UNCLASSIFIED` de tarifa se presenta como “Tarifa sin clasificación”, separado del purpose “Sin clasificar”.

### Preview Detail

Dialog dedicado:

`MarketingCampaignV2PreviewDetailDialogComponent`

Los contadores mapean a buckets backend:

- RECIPIENTS
- INVALID_PHONE
- DUPLICATES
- OUT_OF_SEGMENT
- UNCLASSIFIED
- FAMILY + audience_family
- CURRENT_STATUS_BLOCKED.

Paginación llama nuevamente al backend; no reconstruye detalle local.

### Freeze/Create

Payload se construye con `buildCampaignV2FreezeRequest()`.

Sólo envía:

- name;
- purpose;
- source;
- audience_families;
- fechas cuando source=EXPIRED_MEMBERS;
- expected_preview_fingerprint.

No puede enviar scope, creator, phones, recipients, recipient IDs, source IDs ni evidence.

Al 201:

- muestra confirmación;
- limpia audiencia/Preview para evitar doble freeze;
- conserva Options;
- refresca historial.

No existe Exportar ni estados DRAFT/EXPORTED/SENT.

### Manejo 409

Cualquier 409 de Freeze invalida inmediatamente Preview/fingerprint.

Para mismatch se muestra:

“La audiencia cambió desde la última revisión. Vuelve a revisar antes de crear la campaña.”

No existe retry ni Preview silencioso automático.

### Historial

Consume `GET /campaigns-v2`.

- tabla paginada;
- filtros backend sólo source/purpose;
- orden proviene del backend;
- columnas: nombre, frozen_at, source, purpose, recipient_count y acciones.

### Campaign Detail

Dialog dedicado que consume únicamente Campaign V2 congelada.

Muestra:

- name;
- source;
- purpose;
- frozen/created;
- recipient count;
- fingerprint;
- filters congelados;
- source metadata congelada.

No ejecuta Preview ni consulta fuentes vivas.

### Recipients

Dentro de Campaign Detail:

- paginación backend;
- id/phone/name/member/pin/sucursal/tarifa/category/family/vencimiento;
- inclusion reason mediante modelo;
- conflict_fields;
- evidence_count.

Cuando hay conflictos se muestra “Datos con conflicto”.

### Evidence

Recipient dialog usa exclusivamente:

`GET /campaigns-v2/:campaignId/recipients/:recipientId`

Renderiza summary + Evidence ya ordenada por backend.

Los IDs técnicos de Vencidos/Active row/Active snapshot aparecen sólo en un bloque técnico secundario.

No consulta fuente viva.

### PATCH purpose

Se implementa en Campaign Detail.

Payload:

`{ purpose }`

Al éxito se sustituye únicamente la representación Campaign devuelta por backend; no se ejecuta Preview ni se modifica cohorte desde frontend.

### Errores/estados

Se manejan explícitamente:

- 401 sesión;
- 403 acceso;
- 404 “Campaña no encontrada o no disponible”;
- 409 Preview stale/audiencia no congelable;
- validación 400;
- fallback 500.

No se usa `alert()`.

Estados de carga separados para Options, Preview, Create, historial, Campaign Detail, Recipients, Preview Detail y Purpose.

Las subscriptions nuevas usan `takeUntilDestroyed()`.

### Tests frontend ejecutados

Runner nuevo ejecutado realmente:

`node scripts/test-campaign-v2.cjs`

Resultado:

`9 passed, 0 failed`

Cobertura del runner:

- EXPIRED incluye fechas;
- ACTIVE elimina fechas residuales;
- selección de familias y “seleccionar todas”;
- cero familias inválido;
- orden de fechas;
- invalidación por source/family/fechas y no por name/purpose;
- payload Freeze exacto sin scope/creator/cohorte;
- fingerprint requerido;
- 409 invalida;
- buckets Preview Detail;
- PATCH purpose sólo manda purpose;
- menú crea grupo/conserva legacy/no duplica;
- service no usa Authorization/localStorage;
- UI no contiene Exportar/DRAFT/SENT.

Validaciones adicionales ejecutadas:

- `tsc --noEmit` sobre models/logic/menu: OK;
- typecheck de todos los TS productivos M6 con declaraciones mínimas Angular/RxJS del harness: OK;
- `transpileModule` de los 9 TS locales M6: sin diagnósticos sintácticos.

### Validación final previa al merge M6

Antes del merge del PR #756 se validaron realmente en un checkout completo:

- Frontend Campaign V2: `9 passed`;
- Frontend legacy campañas: `38 passed`;
- Angular: `npm run build` OK.

Estos resultados pertenecen al estado mergeado de M6 y son el baseline de entrada de M7.

### Backend

Cero archivos backend modificados.

No se reejecutó backend M1–M5 porque M6 no toca backend.

### Fuera de alcance

No se agregó:

- WhatsApp;
- iVentas stats/provider/broadcast;
- templates/costos;
- delivery status;
- Funnel operacional;
- PREVIOUS_CAMPAIGN operacional;
- scheduler;
- Exportar;
- estados DRAFT/EXPORTED/SENT;
- producción/migraciones.

## Milestone 7 — Aceptación integrada + cierre de Fase 1

Estado: **iniciado en rama; aceptación integrada bloqueada por entorno, sin cambios productivos**.

### Base y rama

- Base obligatoria confirmada: `aec0e78022d2acf03b3fe1b1887d4f7676e0c6d9`.
- Esa base corresponde al merge del PR #756 de Milestone 6.
- Rama: `feat/campaign-v2-phase1-acceptance`.
- Baselines reales ya validados antes de M7:
  - backend M1–M5: `132 passed`;
  - frontend Campaign V2: `9 passed`;
  - frontend legacy campañas: `38 passed`;
  - Angular: `npm run build` OK.

### Entorno M7 realmente disponible

El runtime de esta conversación no contiene un checkout completo de Suite Ultra.

Disponible:

- Node `v22.16.0`;
- npm `10.9.2`;
- Python `3.13.5`;
- SQLAlchemy/Alembic/pytest;
- staging parcial de M6 suficiente para el runner V2.

No disponible:

- checkout completo backend/frontend;
- Flask;
- Flask-SQLAlchemy;
- Angular CLI / `node_modules`;
- PostgreSQL/`psql`;
- Docker;
- browser/computer conectado a un entorno local de Suite;
- red/DNS para instalar dependencias o clonar el repo.

Por contrato M7 exige checkout local completo, backend/frontend funcionando y PostgreSQL local. Por ello no se sustituyó el smoke con mocks ni se usó producción.

### DB head/current

No fue posible ejecutar:

- `flask db heads`;
- `flask db current`;
- `flask db upgrade`.

Motivo: Flask no está instalado y no existe PostgreSQL local disponible.

Validación estática del repo:

- existe la revisión `f6c1d8a3b2e4`;
- ningún archivo de migración declara `down_revision` hacia `f6c1d8a3b2e4`.

Por tanto el head estático del código sigue siendo `f6c1d8a3b2e4`, pero el current de una DB local no pudo verificarse.

### Usuarios/roles de smoke

No se usaron usuarios reales de prueba porque no existe backend local ejecutable ni base local conectada.

En consecuencia no se validaron manualmente:

- usuario autorizado Campaign V2;
- usuario no autorizado;
- usuario parcial vs global.

Las reglas automatizadas ya validadas en M5/M6 siguen siendo baseline, pero no sustituyen el smoke de aceptación M7.

### Smoke ACTIVE_MEMBERS

No ejecutado.

Blocker:

- no existe backend local;
- no existe PostgreSQL local;
- no se puede consultar el canonical snapshot real.

No se fabricaron recipients ni metadata.

### Smoke EXPIRED_MEMBERS

No ejecutado.

Blocker:

- no existe backend local;
- no existe PostgreSQL local;
- no se puede seleccionar un rango real de Socios Vencidos ni observar current-status/drill-down contra datos locales.

No se insertaron filas manuales.

### Preview invalidation

No se ejecutó en browser real durante M7.

La prueba automatizada V2 se reejecutó y cubrió:

- source/family/fechas invalidan;
- name/purpose no invalidan.

Resultado fresco M7: `9 passed, 0 failed` para todo el runner V2.

### Freeze/Create

No ejecutado contra backend/DB reales.

No se creó Campaign local y no existen campaign IDs M7 que registrar.

### Stale Preview / 409

No se forzó manualmente porque no existe backend/DB local donde producir drift reversible.

La cobertura automatizada previa de backend/frontend permanece como baseline, pero no se presenta como smoke M7.

### History / Campaign Detail / Recipients / Evidence / PATCH purpose

No ejecutados manualmente por ausencia de Campaign local creada mediante el flujo real.

No se consultaron fuentes vivas ni se alteró historia congelada.

### Scope/auth

No validado manualmente en M7 por falta de usuarios/backend/DB locales.

No se intentó usar producción.

### Validación visual

No ejecutada en browser real a 1366px ni viewport angosto porque el frontend Angular no puede levantarse en este runtime.

No se afirma validación visual.

### Defects encontrados

No se encontró un defect funcional reproducible de Campaign V2.

El único hallazgo de M7 es un blocker de entorno de aceptación:

- el runtime no cumple los prerrequisitos explícitos del milestone.

Esto no se trató como bug de producto.

### Fixes realizados

Ninguno.

No se modificó backend, frontend, modelos, migraciones, rutas, servicios ni estilos.

M7 sólo actualiza este documento para dejar continuidad verificable.

### Pruebas finales M7

#### Backend M1–M5

No ejecutable aquí.

Motivo:

- no existe checkout backend completo;
- Flask y Flask-SQLAlchemy no están instalados;
- no existe PostgreSQL local.

Baseline previo válido: `132 passed`.

#### Frontend Campaign V2

Ejecutado realmente en M7:

`node scripts/test-campaign-v2.cjs`

Resultado:

`9 passed, 0 failed`.

#### Frontend legacy campañas

Se intentó ejecutar realmente:

`node scripts/test-campaigns.cjs`

Resultado: el runner no pudo iniciar porque el staging parcial no contiene:

`src/app/marketing-reactivation/marketing-reactivation.component.node-test.ts`

Error: `ENOENT`.

No se interpreta como regresión legacy.

Baseline previo válido: `38 passed`.

#### Angular build

Se intentó ejecutar realmente:

`npm run build`

Resultado:

`sh: 1: ng: not found`

El runtime no tiene Angular CLI ni `node_modules`.

No se interpreta como fallo de compilación del código M6.

Baseline previo válido antes de M7: `npm run build` OK.

### Producción

No se usó producción.

No hubo:

- deploy;
- Docker Compose en servidor;
- `flask db upgrade` en producción;
- `git pull` de servidor.

### Fase 2

No se inició Fase 2.

No se agregó iVentas, WhatsApp, broadcast, provider IDs, stats, costos, templates, Funnel operacional, exportación ni scheduler.

### Criterio de cierre Fase 1

**No cumplido dentro de este runtime.**

Para declarar Fase 1 cerrada aún falta ejecutar en un checkout local completo:

1. `flask db heads` → único head `f6c1d8a3b2e4`;
2. `flask db current` y upgrade local si aplica;
3. corredor backend M1–M5 → `132 passed`;
4. frontend V2 → `9 passed`;
5. frontend legacy → `38 passed`;
6. `npm run build` OK;
7. smoke real Options → Preview → Detail → Freeze → History → Recipients → Evidence → PATCH purpose;
8. acceso autorizado/no autorizado y scope global/parcial;
9. validación visual;
10. confirmar ausencia de defect crítico.

Hasta completar esos puntos la recomendación formal es:

**FASE 1 NO LISTA PARA MERGE DESDE M7 EN ESTE ENTORNO — blocker: falta entorno local integrado para la aceptación requerida.**

No existe blocker de diseño identificado ni cambio arquitectónico pendiente; el blocker es exclusivamente de capacidad de ejecución del smoke M7.
