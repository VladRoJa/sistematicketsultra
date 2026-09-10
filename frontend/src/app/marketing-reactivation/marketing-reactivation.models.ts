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

export interface ReactivationBranchOption {
  key: string;
  label: string;
}

export interface ReactivationSourcesResponse {
  vencidos_coverage: ReactivationVencidosCoverage;
  iventas_periods: ReactivationIventasPeriod[];
  branches: ReactivationBranchOption[];
  permissions: {
    can_manage_campaigns: boolean;
  };
}

export interface ReactivationCandidateSources {
  date_from: string;
  date_to: string;
  activos_snapshot_id: number;
  iventas_sync_run_id: number;
  iventas_period_key: string;
}

export interface ReactivationSummary {
  total_rows: number;
  status_counts: Record<ReactivationCandidateStatus, number>;
  reason_counts: Record<ReactivationCandidateReason, number>;
  operational_counts: Record<
    'ACTIVE' | 'REVIEW_IDENTITY' | 'CONTACTED_THIS_MONTH' | 'AVAILABLE',
    number
  >;
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
  operational_status: Exclude<
    ReactivationOperationalStatus,
    'WORK_PENDING' | 'ALL'
  >;
}

export interface ReactivationPagination {
  page: number;
  page_size: number;
  total: number | null;
  total_pages: number | null;
  has_next: boolean;
  has_prev: boolean;
  next_cursor: string | null;
}

export interface ReactivationCandidatesResponse {
  sources: ReactivationCandidateSources;
  pagination: ReactivationPagination;
  rows: ReactivationCandidateRow[];
}

export interface ReactivationCandidateSummaryResponse {
  sources: ReactivationCandidateSources;
  summary: ReactivationSummary;
}

export type ReactivationOperationalStatus =
  | 'WORK_PENDING'
  | 'AVAILABLE'
  | 'CONTACTED_THIS_MONTH'
  | 'REVIEW_IDENTITY'
  | 'ACTIVE'
  | 'ALL';

export interface ReactivationCampaignFilters {
  campaign_type?: CampaignType;
  iventas_period_key: string;
  sucursal: string | null;
  operational_status: ReactivationOperationalStatus;
  search: string | null;
  tarifa: string | null;
  tariff_category: string | null;
  tariff_group: ReactivationTariffGroup | null;
  campaign_cooldown_days?: number | null;
}

export type ReactivationCandidateSort =
  | 'nombre'
  | 'pin'
  | 'sucursal'
  | 'fecha_vencimiento'
  | 'fecha_ultimo_pago'
  | 'tarifa'
  | 'telefono';

export interface ReactivationCandidateQuery {
  dateFrom: string;
  dateTo: string;
  iventasPeriodKey: string;
  page: number;
  pageSize: number;
  sucursal: string | null;
  tarifa: string | null;
  tariffCategory: string | null;
  tariffGroup: ReactivationTariffGroup | null;
  operationalStatus: ReactivationOperationalStatus;
  search: string | null;
  sort: ReactivationCandidateSort;
  direction: 'asc' | 'desc';
  cursor: string | null;
}

export type ReactivationCandidateSummaryQuery = Omit<
  ReactivationCandidateQuery,
  'page' | 'pageSize' | 'sort' | 'direction' | 'cursor'
>;

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

export type WeeklyFrequencyAction = 'EXCLUDE' | 'KEEP';

export interface ReactivationCampaignSummary {
  excluded_weekly_limit?: number;
  weekly_limit_contacts?: number;
  weekly_frequency_decision_required?: boolean;
  total_candidates: number;
  eligible: number;
  excluded_active: number;
  excluded_invalid_phone: number;
  review_identity: number;
  duplicate_phone: number;
  excluded_tariff: number;
  excluded_tariff_general: number;
  domiciliated_flow: number;
  borron_cuenta_nueva: number;
  review_tariff: number;
  excluded_recent_campaign: number;
  review: number;
}

export interface ReactivationCampaignPreviewResponse {
  sources: ReactivationCandidateSources | {
    date_from: string;
    date_to: string;
    activos_snapshot_id?: number;
    nuevos_snapshot_ids?: number[];
  };
  filters: ReactivationCampaignFilters | CampaignV1Request['filters'];
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
  filters: ReactivationCampaignFilters | CampaignV1Request['filters'];
  recipient_count: number;
}

export interface ReactivationCampaignRecipient {
  id: number;
  socios_vencidos_cartera_id: number | null;
  phone_mx10: string;
  member_name: string | null;
  sucursal: string;
  fecha_vencimiento_date: string | null;
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

export type CampaignType = 'WINBACK' | 'PROXIMOS_VENCER' | 'VENCIDOS_RECIENTES'
  | 'BASCULA_RETENCION' | 'INVITA_GANA' | 'COBRANZA_LIGERA'
  | 'BORRON_CUENTA_NUEVA' | 'PERSONALIZADA';

export interface CampaignV1Request {
  name?: string;
  filters: {
    campaign_type: CampaignType;
    sucursal?: string;
    region_id?: number;
    segment?: string;
    universo?: 'ACTIVOS' | 'VENCIDOS';
    modo_vencidos?: 'DIAS' | 'FECHAS';
    dias_desde?: number;
    dias_hasta?: number;
    fecha_desde?: string;
    fecha_hasta?: string;
    weekly_frequency_action?: WeeklyFrequencyAction;
  };
}

export type CampaignAudienceBucket =
  | 'TOTAL_CANDIDATES'
  | 'EXCLUDED_ACTIVE'
  | 'REVIEW_IDENTITY'
  | 'EXCLUDED_TARIFF_GENERAL'
  | 'DOMICILIATED_FLOW'
  | 'BCN_CANDIDATES'
  | 'REVIEW_TARIFF'
  | 'INVALID_PHONE'
  | 'DUPLICATE_PHONE'
  | 'ELIGIBLE';

export interface CampaignAudienceCompositionRow {
  label: string;
  count: number;
  percentage: number;
}

export interface CampaignAudienceDetailRow {
  vencido_row_id: number | null;
  pin: string | null;
  nombre: string | null;
  phone_mx10: string | null;
  sucursal: string | null;
  fecha_vencimiento: string | null;
  tarifa: string | null;
  tarifa_categoria: string | null;
  tarifa_group: ReactivationTariffGroup | null;
  adeudo: string | null;
  operational_status: string | null;
  campaign_eligibility: string | null;
  eligibility_reason: string | null;
  suite_campaigns_total: number;
  suite_sent_total: number;
  last_suite_exported_at: string | null;
  last_suite_sent_at: string | null;
  iventas_contact_id: string | null;
  iventas_last_message_status: string | null;
  iventas_last_outbound_at_utc: string | null;
}

export interface CampaignAudiencePreviewDetailRequest extends CampaignV1Request {
  bucket: CampaignAudienceBucket;
  page: number;
  page_size: number;
}

export interface CampaignAudiencePreviewDetailResponse {
  bucket: CampaignAudienceBucket;
  label: string;
  sources: ReactivationCampaignPreviewResponse['sources'];
  total: number;
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
    has_prev: boolean;
    has_next: boolean;
  };
  composition: CampaignAudienceCompositionRow[];
  operational_counts: Record<string, number>;
  rows: CampaignAudienceDetailRow[];
}

export interface CampaignOptions {
  branches: Array<{ key: string; label: string }>;
  regions: Array<{ id: number; label: string; branch_keys: string[] }>;
}