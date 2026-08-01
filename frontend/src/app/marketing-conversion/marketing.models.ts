export interface MarketingScope {
  type: string;
  branch_ids: number[];
}

export interface MarketingPermissions {
  can_edit_inputs: boolean;
}

export interface MarketingMetrics {
  investment: number;
  leads: number;
  visits: number;
  sales: number;
  sales_revenue: number;
  cost_per_lead: number | null;
  cost_per_visit: number | null;
  cost_per_sale: number | null;
  lead_to_visit_rate: number | null;
  visit_to_sale_rate: number | null;
  lead_to_sale_rate: number | null;
}

export interface MarketingBranchMetrics extends MarketingMetrics {
  sucursal_id: number;
  sucursal: string;
}

export interface MarketingDataQuality {
  lead_mode: string;
  sales_attribution_mode: string;
  individual_lead_attribution: boolean;
  cohort_complete: boolean;
  eligible_visit_events: number;
  unique_visitors: number;
  visit_events_with_valid_phone: number;
  visit_events_without_valid_phone: number;
  visit_phone_coverage_rate: number | null;
  limitations: string[];
}

export interface MarketingDashboardResponse {
  month: string;
  cohort_mode: 'visit_month';
  scope: MarketingScope;
  permissions: MarketingPermissions;
  summary: MarketingMetrics;
  branches: MarketingBranchMetrics[];
  data_quality: MarketingDataQuality;
}

export interface MarketingMonthlyInput {
  id: number;
  month: string;
  sucursal_id: number;
  investment: number;
  leads: number;
  notes: string | null;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface MarketingInputsResponse {
  month: string;
  scope: MarketingScope;
  permissions: MarketingPermissions;
  inputs: MarketingMonthlyInput[];
}

export interface MarketingInputPayload {
  month: string;
  investment: number;
  leads: number;
  notes: string | null;
}

export interface MarketingInputSaveResponse {
  status: 'created' | 'updated';
  input: MarketingMonthlyInput;
}

export interface MarketingAttributionDetailSummary {
  sales: number;
  sales_revenue: number;
  review_sales: number;
  non_positive_sales: number;
  family_plan_additional_members: number;
}

export interface MarketingAttributionDetailSource {
  visit_snapshot_id: number | null;
  sales_snapshot_ids: number[];
}

export type MarketingAttributionClassification =
  | 'STANDARD_SALE'
  | 'FAMILY_PLAN_ADDITIONAL_MEMBER'
  | 'NON_POSITIVE_AMOUNT_REVIEW';

export interface MarketingAttributionDetailRow {
  sucursal_id: number;
  sucursal: string;
  sale_key: string;
  id_socio: string | null;
  id_folio: string | null;
  socio: string | null;
  telefono: string;
  fecha_visita: string;
  fecha_pago: string;
  dias_a_venta: number;
  tipo_visita: string;
  tipo_membresia: string | null;
  tarifa: string | null;
  inscripcion: string | null;
  pase: string | null;
  lugar_pago: string | null;
  total: number | null;
  total_pagado: number;
  attribution_classification:
    MarketingAttributionClassification;
  amount_assigned_to_primary_member: boolean;
  venta_sin_ingreso_positivo: boolean;
  snapshot_id: number | null;
  source_row_id: number | null;
}

export interface MarketingAttributionDetailResponse {
  month: string;
  cohort_mode: 'visit_month';
  scope: MarketingScope;
  filters: {
    sucursal_id: number | null;
  };
  summary: MarketingAttributionDetailSummary;
  source: MarketingAttributionDetailSource;
  rows: MarketingAttributionDetailRow[];
}
