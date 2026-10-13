# Google Ads → Funnel M5 — atribución diaria por sucursal (CONTRATO PROPUESTO)

**Estado:** DOCUMENTAL / PENDIENTE DE APROBACIÓN DE IDENTIDADES COMPUESTAS. No autoriza implementación, merge ni despliegue.
**Base inspeccionada:** `main` en `e91b69771cd77ec940e4d11e89a3dc5358f67119`.
**Período histórico auditado:** 2026-09-24 a 2026-10-08, zona operativa `America/Tijuana`.

## 1. Evidencia de producción, 12 de octubre de 2026

Auditoría de solo lectura reportada sobre PostgreSQL de producción:

| Evidencia | Resultado |
|---|---:|
| `google_ads_ad_group_daily_metrics` | 645 filas |
| Días / identidades cuenta-campaña-grupo | 15 / 43 |
| Cuentas | 1 |
| Inversión total (MXN) | 19,126.37 |
| Pases gratuitos Ads | 64.0000 |
| Compras web Ads | 16.0000 |
| Alias de M4 válidos, con 26 sucursales activas distintas | 26 |
| Grupos de campaña con nombre aprobado para sucursal | 26; 17,624.73 MXN |
| `Marca` nacional | 1; 1,375.60 MXN |
| `EGADE` preapertura | 1; 126.04 MXN |
| Otros grupos sin alias | 15 (seis nombres); 0.00 MXN, 0 clics, 0 impresiones, 0 pases, 0 compras |
| Identidades con ambos IDs oficiales presentes | 0 |

`17,624.73 + 1,375.60 + 126.04 + 0.00 = 19,126.37`.

**Interpretación:** M3 y M4 concilian para ese período; NO prueban identidad oficial ni autorizan atribución automatizada. La lista de 26 nombres aprobados no equivale a 26 asociaciones aprobadas de cuenta+campaña+grupo. Los grupos sin actividad histórica tampoco quedan autorizados para actividad futura.

## 2. Fuente de verdad, identidad y aprobación

1. `google_ads_daily_metrics` (campaña-día) sigue siendo la autoridad de inversión de cuenta. `google_ads_ad_group_daily_metrics` (grupo-día) es un desglose **no aditivo al ledger**; jamás sumar ambos conjuntos como si fueran gasto independiente.
2. Clave transitoria de M3: `(customer_id, campaign_key, ad_group_key, report_date)`. `campaign_key` proviene del texto de campaña; `ad_group_key` deriva de `campaign_key` y nombre normalizado del grupo. Ninguno es un ID de Google Ads API.
3. **Manifiesto explícito pendiente:** registrar/revisar 26 triples distintos `(customer_id, campaign_key, ad_group_key)`, cada uno asociado a un `sucursal_canon` aprobado en `google_ads_family` y a su `sucursal_id` activo. Requerir evidencia de nombre de campaña, nombre de grupo, fuente/upload y vigencia. No inventar valores ni construir asociaciones desde una coincidencia de nombre en tiempo de consulta.
4. Estado inequívoco de la aprobación: `APPROVED_PROVISIONAL_XLSX` para identidades históricas revisadas; `VERIFIED_OFFICIAL_IDS` solo tras conciliación independiente con `campaign_id` y `ad_group_id` oficiales. No presentar el primero como el segundo.
5. No puede haber dos sucursales activas para un mismo triple ni mapeo a sucursales inactivas/ajenas al catálogo. Cambios de cuenta, nombre/clave de campaña, grupo, sucursal, período o datos históricos requieren nueva revisión con trazabilidad; cualquier divergencia inesperada se bloquea, nunca se infiere silenciosamente.
6. `Marca` y `EGADE` están expresamente **sin asignación**. Los otros 15 grupos tampoco reciben asociación. Cualquier actividad posterior de grupos no aprobados permanece sin asignar y activa revisión, aunque el nombre coincida con el de un club.

### Gate previo a implementar: manifest auditable de 26 triples

Extraer en lectura de producción, sin escribir una sola fila, el triple exacto y su club candidato; comparar con alias M4 y obtener aprobación explícita antes de crear mappings. Los nombres se usan **solo en este reporte de auditoría**; no son el join operativo.

```sql
WITH identities AS (
  SELECT customer_id, campaign_key, ad_group_key,
         MIN(campaign_name) AS campaign_name,
         MIN(ad_group_name) AS ad_group_name,
         COUNT(DISTINCT campaign_name) AS campaign_names,
         COUNT(DISTINCT ad_group_name) AS group_names,
         MIN(report_date) AS first_day, MAX(report_date) AS last_day,
         SUM(cost) AS cost
  FROM google_ads_ad_group_daily_metrics
  WHERE report_date BETWEEN DATE '2026-09-24' AND DATE '2026-10-08'
  GROUP BY customer_id, campaign_key, ad_group_key
)
SELECT i.customer_id, i.campaign_name, i.campaign_key,
       i.ad_group_name, i.ad_group_key,
       a.sucursal_canon, t.sucursal_id,
       i.first_day, i.last_day, i.cost,
       i.campaign_names, i.group_names
FROM identities i
JOIN track_branch_aliases a
  ON a.source_family = 'google_ads_family'
 AND a.is_active = true
 AND LOWER(BTRIM(a.raw_branch_name)) = LOWER(BTRIM(i.ad_group_name))
JOIN track_branch_catalog t
  ON t.sucursal_canon = a.sucursal_canon
 AND t.is_track_active = true
ORDER BY t.sucursal_id, i.campaign_name, i.ad_group_name;
```

**Condición de autorización:** 26 triples únicos, 26 clubes distintos y `campaign_names = group_names = 1` en cada fila; revisión humana de todos los pares campaña+grupo+club. Si no concilia, detener; no completar mappings por nombre automáticamente.

## 3. Contrato de atribución y conciliación

- Asociar cada hecho grupo-día únicamente mediante el **triple aprobado**, vigente para su fecha, y al club verificado; cero mapeos por nombre de grupo aislado.
- Conciliar previamente cada `(customer_id, campaign_key, report_date)`: suma de grupos = campaña-día para coste, clics e impresiones. Reutilizar/fortalecer las garantías de ingesta M3; la atribución no debe aprobar datos que carecen de conciliación del período.
- Para el total global y el mismo corte: `gasto_cuenta = gasto_grupos_locales_aprobados + gasto_no_asignado`. Se desglosa el no asignado en `Marca`, `EGADE`, grupos sin mapa y excepciones; no se suma esta partición de nuevo al ledger de cuenta.
- Si faltan días, fuentes, identidades, conciliación o mapping vigente: devolver `partial` / `requires_review` o `unavailable` con importes incompletos rotulados o `null`. **Nunca interpretar ausencia como 0** ni presentar un subtotal parcial como total mensual.
- Inversión monetaria con `Decimal` (MXN, dos decimales). Conversiones con cuatro decimales. `free_pass_conversions` y `web_purchase_conversions` son métricas atribuidas de Ads, **no** pases emitidos ni ventas pagadas, y no se cruzan como compradores CRM/GASCA.
- Una corrección tardía de Excel, un cambio de campaña/grupo o una nueva identidad con gasto requiere proceso de revisión. No sobrescribir hechos raw/estructurados o mappings históricos.
- Períodos septiembre y octubre: septiembre 1–23 no tiene cobertura Google en este histórico; octubre 9+ tampoco queda cubierto por la importación del 8. La vista mensual debe distinguir `observed`, `complete_to_cutoff` y `missing_days`; Google no influye en `_cutoff_source_dates` del Funnel.

## 4. API y visibilidad por rol

Mantener **sin cambios** `investment_sources.google_ads` como lectura del **ledger de cuenta solo en alcance GLOBAL**, y `investment_sources.combined` con su regla de cobertura vigente. Mantener `summary.investment`, `branches[].investment` y CPL/CPT/CAC en base **META_ASSIGNED_ONLY**.

Agregar **un bloque separado** `google_ads_branch_attribution` de lectura, inicialmente apagado/pendiente de manifiesto, por ejemplo:

```json
{
  "status": "pending_mapping | complete | partial | requires_review | unavailable",
  "currency": "MXN",
  "allocation_basis": "APPROVED_PROVISIONAL_XLSX",
  "requested_from": "YYYY-MM-DD",
  "requested_to": "YYYY-MM-DD",
  "complete_to_cutoff": false,
  "covered_days": 0,
  "expected_days": 0,
  "rows": [
    {
      "sucursal_id": 1,
      "cost": 0.00,
      "clicks": 0,
      "impressions": 0,
      "free_pass_ads": 0.0000,
      "web_purchase_ads": 0.0000
    }
  ],
  "scope_attributed_cost": null
}
```

- Para **GLOBAL**, incluir además desglose de no asignado y conciliación con cuenta, solo cuando todos los gates lo permitan. `scope_attributed_cost` es un desglose del ledger, no inversión adicional.
- Para **GERENTE/REGIONAL** o cualquier usuario con `MarketingAccess.is_global = false`, consultar y exponer **únicamente** `sucursal_id` autorizados por `load_visible_marketing_branches(access)`; no leer ni filtrar en Python el gasto global, ni exponer total de cuenta, `Marca`, `EGADE`, otros clubes ni diferencias globales.
- Backend conserva control de acceso real; Angular no sustituye ninguna restricción. No crear endpoint público nuevo sin contratos y revisión de permisos.
- Mostrar Google Ads atribuido por club en una sección diferenciada, sin sobrescribir inversión de Meta ni alterar exportaciones existentes sin contrato separado.

## 5. Archivos y puntos de intervención **futura** (ningún cambio funcional en este PR)

- Nueva migración Alembic + modelo ORM de mapping explícito, con llave única del triple, sucursal canónica, vigencia, estado de certificación y auditoría de aprobación. **No modificar la migración ya aplicada M4.**
- `backend/app/services/marketing_google_ads_funnel_service.py`: nueva lectura de detalle aprobada y acotada; conservar `read_google_ads_funnel_investment()` y `build_funnel_investment_sources()` sin cambios de significado.
- `backend/app/services/marketing_sales_funnel_cutoff_service.py::build_marketing_sales_funnel_at_cutoff()`: adjuntar bloque separado sin cambiar `summary`, `branches[].investment` ni selección de corte.
- `backend/app/services/marketing_access.py` y `marketing_dashboard_service.py::load_visible_marketing_branches()`: reutilizar el alcance actual, sin ampliar roles.
- `frontend/src/app/marketing-sales-funnel/marketing-sales-funnel.models.ts`: tipos de respuesta M5.
- `frontend/src/app/marketing-sales-funnel/marketing-sales-funnel.component.ts`: toda la transformación/formato/decisión de visibilidad; `.html` solo estructura y bindings simples, `.css` estilos separados.
- Pruebas backend en PostgreSQL 16 real, pruebas de alcance negativo, regresiones M2/M3/M4, TypeScript y build Angular.

## 6. Criterios de aceptación / casos negativos

1. Manifiesto aprobado de **26 triples**, sin duplicados ni clubes inactivos; `Marca` y `EGADE` sin mapping.
2. Historial del 24-sep al 8-oct: 645 grupo-día / 43 identidades / 15 días / 19,126.37 MXN; 26 locales 17,624.73; no asignado 1,501.64 (Marca 1,375.60 + EGADE 126.04); otros 15 sin actividad.
3. Reconciliación de campaña-día y cuenta-día para coste/clics/impresiones; ni una doble contabilización. Verificar también el comportamiento al faltar referencias de campaña o días.
4. Rechazar/no atribuir triple desconocido, duplicado, modificado, cuenta equivocada, campaña equivocada, grupo homónimo en otra campaña, sucursal inactiva, nuevos grupos con actividad y conflicto de períodos.
5. Identidad sin IDs oficiales siempre etiquetada provisional; nunca mostrar `VERIFIED_OFFICIAL_IDS` sin evidencia externa comprobable.
6. Usuarios no globales: pruebas negativas demuestran ausencia de query al ledger global, ausencia de filtraciones por JSON y ausencia de acceso fuera del scope.
7. Septiembre incompleto y octubre posterior al día 8 marcado parcial, sin inventar cero; Google nunca retrasa o redefine el corte del Funnel.
8. Meta, CPL/CPT/CAC, ventas reales, campañas Meta e iVentas, permisos y Warehouse permanecen sin regresiones.
9. Transacción Alembic segura, revisión de constraints/reversibilidad y CI PostgreSQL 16 + frontend verde antes de solicitar merge. Cualquier despliegue requiere autorización explícita.

## 7. Secuencia de ejecución

1. **M5-IDENTITY:** correr consulta de 26 triples, comprobar invariantes, obtener aprobación explícita del manifiesto.
2. **M5-CORE:** implementar tabla de asociaciones y servicio de atribución con validación negativa y conciliación.
3. **M5-FUNNEL:** integrar el bloque separado al API y Angular con permisos y cobertura.
4. **M5-QA:** pruebas aisladas, revisión independiente, aprobación de merge, despliegue controlado y validación posterior.

**Prohibido hasta el gate M5-IDENTITY:** activar atribución operativa por sucursal, inferir mappings por nombres o cambiar cifras del Funnel existente.
