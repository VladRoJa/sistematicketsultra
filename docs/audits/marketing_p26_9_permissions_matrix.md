# Marketing P26.9 — Matriz integral de rutas y permisos (2026-10-26)

## Fuentes y estado
- Referencia: `main` luego de squash P26.8 `61b2213c2576aec81b542062d2fcf6205f7ccef7`.
- Fuentes: tres blueprints **registrados** en `backend/app/__init__.py::create_app()`: `marketing_bp`, `marketing_campaign_v2_bp`, `marketing_sales_funnel_bp`.
- Inventario en código: **82 operaciones por método** (GET 40, POST 36, PUT 5, PATCH 1), **42 métodos distintos de GET**; un POST puede ser solo vista previa, y un GET/export puede manejar datos sensibles. Confirmar registro vía `app.url_map` en el test de contrato P26.9.
- Otros cinco archivos `marketing_campaign_{delivery,export,preview_detail,source_status}_routes.py` y `marketing_reactivation_outcome_routes.py` contienen **11 decoradores de Reactivación V1 no registrados**. No son superficie HTTP activa en la aplicación actual. Está protegido por `test_campaign_v1_decommission_contract.py` y el nuevo inventario.
- El campo **Guard** resume el resolutor observado en el handler y NO certifica por sí solo la implementación de permisos en todos los servicios/filas. El rol regional legítimo puede gestionar campañas dentro de sus sucursales sin permiso de dispatch global.
- La columna **evidencia** separa tests HTTP específicos recientes de la mera comprobación estructural de JWT/resolutor: los tests históricos por módulo se deben consultar antes de declarar una ruta plenamente cubierta. **AST/JWT no es prueba de seguridad operacional**.

## Catálogo activo y clasificación

| Método | Ruta HTTP | Handler | Guard observado | Riesgo | Evidencia |
|---|---|---|---|---|---|
| GET | `/api/marketing/dashboard` | `get_marketing_dashboard_endpoint` | Consulta de sucursales | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/attributions` | `get_marketing_attributions_endpoint` | Consulta de sucursales | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/investment-detail` | `get_marketing_investment_detail_endpoint` | Consulta de sucursales | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/leads-detail` | `get_marketing_leads_detail_endpoint` | Consulta de sucursales | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/visitors-detail` | `get_marketing_visitors_detail_endpoint` | Consulta de sucursales | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/inputs` | `get_marketing_inputs_endpoint` | Consulta de sucursales | Medio | AST/JWT + pruebas históricas por módulo |
| PUT | `/api/marketing/inputs/<int:sucursal_id>` | `put_marketing_input_endpoint` | Edición + sucursal | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/sales-funnel` | `get_marketing_sales_funnel_endpoint` | Consulta con filtro | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/sales-funnel/detail` | `get_marketing_sales_funnel_detail_endpoint` | Consulta con filtro | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/sales-funnel/detail/export` | `export_marketing_sales_funnel_detail_endpoint` | Consulta con filtro | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/options` | `campaign_v2_options_endpoint` | Gestión + alcance | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/blacklist` | `campaign_v2_blacklist_summary_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/blacklist/import` | `campaign_v2_blacklist_import_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/blacklist/export` | `campaign_v2_blacklist_export_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/excel/preview` | `campaign_v2_excel_preview_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/excel/freeze` | `campaign_v2_excel_freeze_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/preview` | `campaign_v2_preview_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/preview-detail` | `campaign_v2_preview_detail_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2` | `freeze_campaign_v2_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/tariffs/unclassified` | `list_campaign_v2_unclassified_tariffs_endpoint` | Gestión + alcance | Medio | AST/JWT + pruebas históricas por módulo |
| PUT | `/api/marketing/campaigns-v2/tariffs/<path:tarifa_key>/classification` | `classify_campaign_v2_tariff_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2` | `list_campaign_v2_endpoint` | Gestión + alcance | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/commercial-attribution/summary` | `campaign_v2_commercial_attribution_summary_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/provider-history/lookup` | `lookup_campaign_v2_provider_history_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>` | `get_campaign_v2_endpoint` | Gestión + alcance | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/commercial-attribution` | `get_campaign_v2_commercial_attribution_endpoint` | Gestión + alcance | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/reporting/export` | `export_campaign_v2_reporting_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/reporting` | `get_campaign_v2_reporting_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/report` | `get_campaign_v2_report_endpoint` | Gestión + alcance | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/provider-stats` | `get_campaign_v2_provider_stats_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/provider-stats/snapshots` | `capture_campaign_v2_provider_stats_snapshot_endpoint` | Gestión + alcance | Alto | P26.9 HTTP + AST |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/provider-stats/snapshots` | `list_campaign_v2_provider_stats_snapshots_endpoint` | Gestión + alcance | Alto | P26.9 HTTP + AST |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/provider-stats/snapshots/latest` | `latest_campaign_v2_provider_stats_snapshot_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/followup/preview` | `campaign_v2_followup_preview_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/followup/freeze` | `campaign_v2_followup_freeze_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/export-package` | `export_campaign_v2_delivery_package_endpoint` | Gestión + alcance | Alto | P26.9 HTTP + AST |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/sendable-export-package` | `export_campaign_v2_sendable_package_endpoint` | Gestión + alcance | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/recipients` | `list_campaign_v2_recipients_endpoint` | Gestión + alcance | Alto | P26.9 HTTP + AST |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/recipients/<int:recipient_id>` | `get_campaign_v2_recipient_endpoint` | Gestión + alcance | Alto | P26.9 HTTP + AST |
| PATCH | `/api/marketing/campaigns-v2/<int:campaign_id>/purpose` | `update_campaign_v2_purpose_endpoint` | Gestión + alcance | Alto | P26.8 HTTP + AST |
| PUT | `/api/marketing/campaigns-v2/<int:campaign_id>/provider-binding` | `bind_campaign_v2_provider_endpoint` | Gestión + alcance | Alto | P26.8 HTTP + AST |
| GET | `/api/marketing/campaigns-v2/dispatch/templates` | `list_campaign_v2_dispatch_templates_endpoint` | Preflight | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/templates/admin` | `list_campaign_v2_dispatch_templates_admin_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/catalog-branches` | `list_campaign_v2_dispatch_catalog_branches_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/templates` | `create_campaign_v2_dispatch_template_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| PUT | `/api/marketing/campaigns-v2/dispatch/templates/<int:template_id>` | `update_campaign_v2_dispatch_template_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/cost-rates` | `list_campaign_v2_cost_rate_revisions_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/cost-rates` | `create_campaign_v2_cost_rate_revision_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/approval` | `campaign_v2_dispatch_approval_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/approval` | `campaign_v2_dispatch_approval_state_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/reauthorize` | `campaign_v2_reauthorize_unattempted_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/materialize` | `campaign_v2_materialize_manifest_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/executions/<int:execution_id>/escalate` | `campaign_v2_governed_escalate_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/executions/<int:execution_id>/resolve` | `campaign_v2_governed_resolve_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/held/<int:child_id>/freeze-derived` | `campaign_v2_held_freeze_derived_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/held/<int:child_id>/release-preview` | `campaign_v2_held_release_preview_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/held/<int:child_id>/release-intent` | `campaign_v2_held_release_intent_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/monitor` | `campaign_v2_governed_monitor_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/execution` | `campaign_v2_execution_review_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/authorize` | `campaign_v2_governed_authorize_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/execute` | `campaign_v2_governed_execute_endpoint` | Global + configuración | Crítico | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/qa-manual/preview` | `preview_campaign_v2_qa_http_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/qa-manual/freeze` | `freeze_campaign_v2_qa_http_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/portfolio-review` | `campaign_v2_portfolio_review_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence` | `list_campaign_v2_channel_portfolio_evidence_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence` | `register_campaign_v2_channel_portfolio_evidence_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/portfolio-references` | `list_campaign_v2_portfolio_references_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/portfolio-references` | `register_campaign_v2_portfolio_reference_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/quota-evidence` | `list_campaign_v2_quota_evidence_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/quota-policies` | `register_campaign_v2_quota_policy_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/quota-attestations` | `register_campaign_v2_quota_attestation_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/dispatch/channel-bindings` | `list_campaign_v2_channel_bindings_endpoint` | Global + configuración | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/dispatch/channel-bindings` | `create_campaign_v2_channel_binding_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| PUT | `/api/marketing/campaigns-v2/dispatch/channel-bindings/<int:binding_id>` | `update_campaign_v2_channel_binding_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/provider-campaigns/<int:child_id>/reconcile` | `campaign_v2_provider_child_reconcile_endpoint` | Global + envío | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/provider-campaigns/<int:child_id>/retry` | `campaign_v2_provider_child_retry_endpoint` | Global + envío | Crítico | AST/JWT + pruebas históricas por módulo |
| GET | `/api/marketing/campaigns-v2/<int:campaign_id>/preparation/branches` | `campaign_v2_branch_diagnostics_endpoint` | Preflight | Medio | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/preparation/branches/exclude` | `campaign_v2_exclude_ambiguous_branches_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/preparation/previous/review` | `campaign_v2_previous_contacts_review_endpoint` | Preflight | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/preparation/previous/exclude` | `campaign_v2_previous_contacts_apply_endpoint` | Global + configuración | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/preflight` | `campaign_v2_preflight_endpoint` | Preflight | Alto | AST/JWT + pruebas históricas por módulo |
| POST | `/api/marketing/campaigns-v2/<int:campaign_id>/submit` | `campaign_v2_submit_endpoint` | Capacidad de envío | Crítico | AST/JWT + pruebas históricas por módulo |

## Cobertura y fronteras verificadas
1. **P26.1–P26.8:** pruebas de denegaciones HTTP/JWT y casos regionales para dispatch, HELD, creación, Excel y actualización de metadatos. Fuente: `backend/tests/marketing/test_marketing_campaign_v2_quota_routes.py`. Pruebas negativas con servicios/proveedor/sesión DB simulados: no prueban ausencia de escritura real en PostgreSQL.
2. **P26.9 — inventario estructural:** `backend/tests/marketing/test_marketing_permissions_p26_9_integral_inventory.py` exige exactamente 82 rutas activas, 42 métodos no GET, JWT directo en todas y presencia de resolutor/gates en todas las rutas de métodos no GET. Si el catálogo cambia, exige revisión explícita y actualización de esta matriz.
3. **P26.9 — fronteras de datos sensibles:** HTTP 403 para scope regional vacío antes de servicios en export manual, export enviable, listado y detalle de destinatarios, y captura de provider stats. HTTP 200 para captura de stats regional autorizada, con forwarding exclusivo de sucursales autorizadas a servicio simulado.
4. **Pruebas existentes:** `test_marketing_campaign_v2_routes.py` (reporting, recipients, scope, preflight, submit, retry, reconciliación, admin), `test_marketing_campaign_v2_qa_http.py`, suites de servicio y pruebas PG específicas de dispatch. La presencia de una suite no equivale a certificar individualmente cada ruta; revisar aserciones y mocks según riesgo.
5. **Límites:** sin lectura de mapa de permisos de base de datos productiva, sin test end-to-end de iVentas, sin invocar envíos reales. No activar resolvedor global ni cambios de grants. Si se descubre desviación productiva, registrar como brecha independiente antes de corregir.

## Criterios para cerrar el bloque Marketing y continuar la Fase A global
- PR P26.9 con CI PostgreSQL sintético, backend complementario y Angular en verde; sin regresión.
- Inventario runtime sin rutas de V1; diferencias entre registro real, semillas históricas y catálogo DB actual **no deben confundirse con bypass**.
- Brechas verificadas de controles backend o de servicios se documentan con caso reproducible; pendientes de validación sobre PostgreSQL real quedan explícitos, no declarados PASS.
- La **Fase A global del issue #1053 permanece abierta** hasta completar los demás módulos y comparación de la tabla de permisos vigente (solo lectura) de cada entorno.
