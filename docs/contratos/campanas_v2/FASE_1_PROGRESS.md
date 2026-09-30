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

Estado: **completado en rama, pendiente de merge**.

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

## Fuera de alcance del Milestone 1

No se agregaron:

- endpoints;
- Angular;
- Campaign V2;
- Recipient V2;
- integración iVentas;
- cambios a Reactivaciones legacy.

## Siguiente milestone propuesto

**Milestone 2 — Persistencia base Campaign V2 + Recipient V2**

Objetivo propuesto: definir y migrar únicamente las entidades genéricas de campaña y cohorte congelada, respetando fuentes canónicas y soporte de recipients phone-only, sin agregar todavía envío WhatsApp ni sincronización iVentas.

Antes de implementarlo se debe cerrar el diseño exacto de:

- identidad y estados de Campaign V2;
- propósito con default `UNCLASSIFIED`;
- referencias opcionales de fuente por tipo de audiencia;
- snapshot mínimo del recipient;
- constraints para teléfono normalizado y deduplicación por campaña;
- política de inmutabilidad de la cohorte congelada.
