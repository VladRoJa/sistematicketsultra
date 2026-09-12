export interface MarketingSalesOriginBreakdown {
  key: string;
  label: string;
  sales: number;
  revenue: number;
}

export interface MarketingSalesFunnelMetrics {
  iventas_contacts: number;
  leads_meta: number;

  visits_total: number;
  visits_iventas: number;
  visits_iventas_meta: number;
  visits_iventas_other: number;
  visits_not_iventas: number;
  visits_unmatchable: number;

  sales_total: number;
  sales_iventas: number;
  sales_iventas_meta: number;
  sales_iventas_other: number;
  sales_not_iventas: number;
  sales_without_valid_phone: number;

  revenue_total: number;
  revenue_iventas: number;
  revenue_iventas_meta: number;
  revenue_iventas_other: number;
  revenue_not_iventas: number;

  meta_lead_to_visit_rate: number | null;
  meta_visit_to_sale_rate: number | null;
  meta_lead_to_sale_rate: number | null;
  total_visit_to_sale_rate: number | null;
  iventas_visit_share: number | null;
  iventas_sale_share: number | null;

  origin_breakdown: MarketingSalesOriginBreakdown[];
}

export interface MarketingSalesFunnelBranch
  extends MarketingSalesFunnelMetrics {
  sucursal_id: number;
  sucursal: string;
}

export interface MarketingSalesFunnelSource {
  venta_total_snapshot_id: number | null;
  venta_total_business_date: string | null;
  iventas_sync_run_ids: number[];
  match_window_days: number;
}

export interface MarketingSalesFunnelQuality {
  venta_total_available: boolean;
  iventas_available: boolean;
  new_sale_rule: string;
  match_mode: string;
  survey_fallback_only_after_no_iventas_match: boolean;
  limitations: string[];
}

export interface MarketingSalesFunnelResponse {
  month: string;
  scope: Record<string, unknown>;
  summary: MarketingSalesFunnelMetrics;
  branches: MarketingSalesFunnelBranch[];
  source: MarketingSalesFunnelSource;
  data_quality: MarketingSalesFunnelQuality;
}
