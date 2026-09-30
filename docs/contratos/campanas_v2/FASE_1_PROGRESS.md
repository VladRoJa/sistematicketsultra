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

Estado: **completado en rama, pendiente de merge**.

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

## Siguiente milestone propuesto

**Milestone 3 — Audience Builder backend: fuentes canónicas + preview/composición V2**

Objetivo recomendado: construir los adapters de `EXPIRED_MEMBERS` y `ACTIVE_MEMBERS`, filtros y composición/deduplicación de preview sobre las fuentes canónicas, todavía sin envío y manteniendo la creación/freeze como paso server-side posterior.
