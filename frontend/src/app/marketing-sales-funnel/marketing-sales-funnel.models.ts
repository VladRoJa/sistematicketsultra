export interface MarketingSalesOriginBreakdown {
  key: string;
  label: string;
  sales: number;
  revenue: number;
}

export interface MarketingSalesFunnelScopeOption {
  sucursal_id: number;
  sucursal: string;
  region_id: number | null;
  region: string | null;
}

export interface MarketingSalesFunnelMetrics {
  investment?: number | null;

  iventas_contacts: number | null;
  leads_iventas: number | null;
  leads_meta: number | null;

  visits_total: number;
  visits_iventas: number | null;
  visits_iventas_meta: number | null;
  visits_iventas_other: number | null;
  visits_not_iventas: number | null;
  visits_unmatchable: number;
  visits_iventas_bought: number | null;
  visits_iventas_not_bought: number | null;
  visits_not_iventas_bought: number | null;
  visits_not_iventas_not_bought: number | null;
  iventas_visit_conversion_rate: number | null;
  not_iventas_visit_conversion_rate: number | null;

  sales_total: number;
  sales_iventas: number | null;
  sales_iventas_meta: number | null;
  sales_iventas_other: number | null;
  sales_not_iventas: number | null;
  sales_without_valid_phone: number;

  sales_digital: number | null;
  sales_digital_organic: number;
  sales_web: number;
  sales_btl: number;

  revenue_total: number;
  revenue_iventas: number | null;
  revenue_iventas_meta: number | null;
  revenue_iventas_other: number | null;
  revenue_not_iventas: number | null;

  revenue_digital: number;
  revenue_web: number;
  revenue_btl: number;

  lead_to_visit_rate: number | null;
  visit_to_digital_sale_rate: number | null;
  lead_to_sale_rate: number | null;
  meta_lead_to_visit_rate: number | null;
  meta_visit_to_sale_rate: number | null;
  meta_lead_to_sale_rate: number | null;
  total_visit_to_sale_rate: number | null;
  iventas_visit_share: number | null;
  iventas_sale_share: number | null;

  origin_breakdown: MarketingSalesOriginBreakdown[];
  btl_origin_breakdown: MarketingSalesOriginBreakdown[];
}

export interface MarketingSalesFunnelBranch
  extends MarketingSalesFunnelMetrics {
  sucursal_id: number;
  sucursal: string;
}

export interface MarketingSalesFunnelSource {
  venta_total_snapshot_id: number | null;
  venta_total_business_date: string | null;
  ventas_nuevos_socios_detalle_snapshot_id?: number | null;
  ventas_nuevos_socios_detalle_business_date?: string | null;
  kpi_desempeno_snapshot_id?: number | null;
  kpi_desempeno_business_date?: string | null;
  iventas_sync_run_ids: number[];
  iventas_sync_run_id?: number | null;
  meta_sync_run_id?: number | null;
  meta_date_from?: string | null;
  meta_date_to?: string | null;
  match_window_days: number;
}

export interface MarketingSalesFunnelQuality {
  venta_total_available: boolean;
  ventas_nuevos_socios_detalle_available?: boolean;
  kpi_desempeno_available?: boolean;
  iventas_available: boolean;
  new_sale_source?: string;
  new_sale_control?: string;
  new_sales_detail_count?: number;
  kpi_new_sales_control?: number | null;
  new_sales_vs_kpi_difference?: number | null;
  venta_total_enriched_sales?: number;
  new_sale_rule: string;
  venta_total_role?: string;
  crm_history_available?: boolean;
  crm_dependent_metrics_available?: boolean;
  meta_available?: boolean;
  crm_history_start_month?: string;
  match_mode: string | null;
  commercial_classification_rule?: string;
  survey_fallback_only_after_no_iventas_match: boolean | null;
  visit_conversion_mode?: string | null;
  visit_conversion_cohort_complete?: boolean | null;
  visit_conversion_sales_snapshot_ids?: number[];
  limitations: string[];
}

export interface MarketingSalesFunnelResponse {
  month: string;
  selected_cutoff_date: string;
  available_cutoff_dates: string[];
  scope: Record<string, unknown>;
  scope_options?: MarketingSalesFunnelScopeOption[];
  summary: MarketingSalesFunnelMetrics;
  branches: MarketingSalesFunnelBranch[];
  source: MarketingSalesFunnelSource;
  data_quality: MarketingSalesFunnelQuality;
}

export type MarketingSalesFunnelDetailKind = 'sales' | 'visits' | 'leads';
export type MarketingSalesFunnelSortDirection = 'asc' | 'desc';

export interface MarketingSalesFunnelDetailRow {
  branch_id: number;
  branch: string;
  date: string | null;
  name?: string | null;
  member_id?: string | null;
  pin?: string | null;
  phone?: string | null;
  folio?: string | null;
  membership_type?: string | null;
  tariff?: string | null;
  revenue?: number | null;
  survey?: string | null;
  origin_key?: string | null;
  origin?: string | null;
  transaction_branch?: string | null;
  payment_method?: string | null;
  id_order?: string | null;
  payment_place?: string | null;
  source?: string | null;
  visit_type?: string | null;
  contact_id?: string | null;
  channel?: string | null;
  followup_status?: string | null;
  visit_status?: string | null;
  visit_date?: string | null;
  purchase_status?: string | null;
  purchase_branch?: string | null;
  conversion_status?: string | null;
  sale_date?: string | null;
  sale_member_id?: string | null;
  sale_revenue?: number | null;
}

export interface MarketingSalesFunnelDetailResponse {
  month: string;
  scope: Record<string, unknown>;
  metric: string;
  origin: string | null;
  kind: MarketingSalesFunnelDetailKind;
  title: string;
  branch_id: number | null;
  count: number;
  revenue_total: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort_by: string | null;
  sort_dir: MarketingSalesFunnelSortDirection;
  rows: MarketingSalesFunnelDetailRow[];
}
