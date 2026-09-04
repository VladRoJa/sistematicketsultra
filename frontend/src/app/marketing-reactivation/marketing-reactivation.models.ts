export type ReactivationCandidateStatus =
  | 'EXCLUDED_ACTIVE'
  | 'REVIEW_ACTIVE_MATCH'
  | 'EXCLUDED_POST_EXPIRATION_CONTACT'
  | 'CONTACT_HISTORY_UNKNOWN';

export type ReactivationCandidateReason =
  | 'ACTIVE_CONFIRMED'
  | 'ACTIVE_REVIEW'
  | 'AMBIGUOUS'
  | 'IDENTIFIER_CONFLICT'
  | 'POST_EXPIRATION_OUTBOUND'
  | 'NO_MX10'
  | 'DUPLICATE_VENCIDO_PHONE'
  | 'NO_MATCH_CURRENT_IVENTAS_RUN'
  | 'AMBIGUOUS_IVENTAS_IDENTITY'
  | 'NO_OUTBOUND_EVIDENCE'
  | 'ONLY_PRE_EXPIRATION_OUTBOUND';

export interface ReactivationVencidosCoverage {
  min_date: string | null;
  max_date: string | null;
  total_rows: number;
}

export interface ReactivationIventasPeriod {
  period_key: string;
  sync_run_id: number;
  date_from: string;
  date_to: string;
  contacts_unique: number;
}

export interface ReactivationSourcesResponse {
  vencidos_coverage: ReactivationVencidosCoverage;
  iventas_periods: ReactivationIventasPeriod[];
  permissions: {
    can_manage_campaigns: boolean;
  };
}

export interface ReactivationCandidateSources {
  date_from: string;
  date_to: string;
  iventas_sync_run_id: number;
  iventas_period_key: string;
}

export interface ReactivationSummary {
  total_rows: number;
  status_counts: Record<ReactivationCandidateStatus, number>;
  reason_counts: Record<ReactivationCandidateReason, number>;
}

export interface ReactivationCandidateRow {
  vencido_row_id: number;
  pin: string;
  nombre: string | null;
  sucursal: string;
  telefono: string | null;
  correo: string | null;
  fecha_vencimiento: string;
  fecha_ultimo_pago: string | null;
  tarifa: string | null;
  tarifa_categoria: string | null;
  tarifa_group: ReactivationTariffGroup | null;
  tarifa_classified: boolean;
  adeudo: string | null;
  status: ReactivationCandidateStatus;
  reason: ReactivationCandidateReason;
  active_status: string;
  active_id_socio: string | null;
  iventas_contact_id: string | null;
  latest_outbound_at_utc: string | null;
}

export interface ReactivationCandidatesResponse {
  sources: ReactivationCandidateSources;
  summary: ReactivationSummary;
  rows: ReactivationCandidateRow[];
}

export type ReactivationOperationalStatus =
  | 'WORK_PENDING'
  | 'NO_CONTACT_IN_PERIOD'
  | 'NO_OUTBOUND_MESSAGE'
  | 'CONTACTED_BEFORE_EXPIRATION'
  | 'CONTACTED_AFTER_EXPIRATION'
  | 'REVIEW_IDENTITY'
  | 'ACTIVE'
  | 'ALL';

export interface ReactivationCampaignFilters {
  iventas_period_key: string;
  sucursal: string | null;
  operational_status: ReactivationOperationalStatus;
  search: string | null;
  tarifa: string | null;
  campaign_cooldown_days?: number | null;
}

export interface ReactivationTariffCount {
  tarifa: string | null;
  count: number;
  classified: boolean;
  categoria_tarifa: string | null;
  reactivation_group: ReactivationTariffGroup | null;
}

export type ReactivationTariffGroup =
  | 'REACTIVATE'
  | 'DOMICILIATED_FLOW'
  | 'EXCLUDE'
  | 'REVIEW';

export interface ReactivationTariffsResponse {
  date_from: string;
  date_to: string;
  rows: ReactivationTariffCount[];
}

export interface ReactivationCampaignSummary {
  total_candidates: number;
  eligible: number;
  excluded_active: number;
  excluded_invalid_phone: number;
  review_identity: number;
  duplicate_phone: number;
  excluded_tariff: number;
  domiciliated_flow: number;
  review_tariff: number;
  excluded_recent_campaign: number;
  review: number;
}

export interface ReactivationCampaignPreviewResponse {
  sources: ReactivationCandidateSources;
  filters: ReactivationCampaignFilters;
  summary: ReactivationCampaignSummary;
}

export type ReactivationCampaignStatus =
  | 'DRAFT'
  | 'EXPORTED'
  | 'SENT'
  | 'CANCELLED';

export interface ReactivationCampaign {
  id: number;
  name: string;
  status: ReactivationCampaignStatus;
  date_from: string;
  date_to: string;
  created_by_user_id: number | null;
  created_by_username: string | null;
  created_at: string;
  updated_at: string;
  exported_at: string | null;
  sent_at: string | null;
  notes: string | null;
  filters: ReactivationCampaignFilters;
  recipient_count: number;
}

export interface ReactivationCampaignRecipient {
  id: number;
  socios_vencidos_cartera_id: number;
  phone_mx10: string;
  member_name: string | null;
  sucursal: string;
  fecha_vencimiento_date: string;
  tarifa: string | null;
  inclusion_status: string;
  exclusion_reason: string | null;
  operational_status: string;
  operational_reason: string;
  created_at: string;
}

export interface ReactivationCampaignDetail extends ReactivationCampaign {
  recipients: ReactivationCampaignRecipient[];
}

export interface ReactivationCampaignListResponse {
  rows: ReactivationCampaign[];
  limit: number;
}

export interface ReactivationCampaignResponse {
  campaign: ReactivationCampaign;
}

export interface ReactivationCampaignDetailResponse {
  campaign: ReactivationCampaignDetail;
}

export interface ReactivationCampaignRequest {
  name?: string;
  date_from: string;
  date_to: string;
  filters: ReactivationCampaignFilters;
  notes?: string | null;
}
