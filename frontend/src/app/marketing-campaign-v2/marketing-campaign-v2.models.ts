export type CampaignV2Source =
  | 'EXPIRED_MEMBERS'
  | 'ACTIVE_MEMBERS'
  | 'FUNNEL_PORTFOLIO';

export type CampaignV2IventasCurrentStatus =
  | 'SENT'
  | 'DELIVERED'
  | 'VIEWED'
  | 'FAILED'
  | 'NO_DATA';

export type CampaignV2HistoryDeliveryBucket =
  | 'SENT'
  | 'DELIVERED'
  | 'VIEWED';

export type CampaignV2HistoryOutcome =
  | 'SUCCESSFUL'
  | 'FAILED';

export type CampaignV2HistoryExclusionReason =
  | 'HISTORY_DELIVERY_SENT'
  | 'HISTORY_DELIVERY_DELIVERED'
  | 'HISTORY_DELIVERY_VIEWED'
  | 'HISTORY_OUTCOME_SUCCESSFUL'
  | 'HISTORY_OUTCOME_FAILED'
  | 'HISTORY_BUTTON_INTERACTION';

export type CampaignV2HistoricalTargetingMode = 'INCLUDE' | 'EXCLUDE';
export type CampaignV2HistoricalTargetingMatch = 'ALL' | 'ANY';
export type CampaignV2HistoricalTargetingWindowMode =
  | 'ALL_HISTORY'
  | 'LOOKBACK_DAYS';

export interface CampaignV2HistoricalTargeting {
  mode: CampaignV2HistoricalTargetingMode;
  match: CampaignV2HistoricalTargetingMatch;
  delivery_buckets: CampaignV2HistoryDeliveryBucket[];
  outcomes: CampaignV2HistoryOutcome[];
  button_interacted: boolean;
  lookback_days: number | null;
}

export interface CampaignV2HistoryExclusion {
  delivery_buckets: CampaignV2HistoryDeliveryBucket[];
  outcomes: CampaignV2HistoryOutcome[];
  button_interacted: boolean;
  lookback_days: number | null;
}

export interface CampaignV2HistoricalTargetingOptions {
  modes: CampaignV2HistoricalTargetingMode[];
  matches: CampaignV2HistoricalTargetingMatch[];
  delivery_buckets: CampaignV2HistoryDeliveryBucket[];
  outcomes: CampaignV2HistoryOutcome[];
  button_interaction: boolean;
  window_modes: CampaignV2HistoricalTargetingWindowMode[];
  legacy_history_exclusion_supported: boolean;
}

export interface CampaignV2HistoryDiagnostics {
  before_history_filter_count: number;
  history_excluded_count: number;
  after_history_filter_count: number;
  excluded_by_delivery_bucket: Partial<Record<CampaignV2HistoryDeliveryBucket, number>>;
  excluded_by_outcome: Partial<Record<CampaignV2HistoryOutcome, number>>;
  excluded_by_button_interaction: number;
}

export interface CampaignV2HistoryEvaluationMetadata {
  observed_before: string | null;
  observed_after: string | null;
}

export type CampaignV2AudienceFamily =
  | 'DOMICILIADO'
  | 'TRIMESTRAL'
  | 'CONVENIO'
  | 'SEMESTRE'
  | 'ESTUDIANTE';

export type CampaignV2ObservedFamily =
  | CampaignV2AudienceFamily
  | 'MES'
  | 'OUT_OF_SEGMENT';

export type CampaignV2NonSelectableClassification =
  | 'MES'
  | 'OUT_OF_SEGMENT'
  | 'UNCLASSIFIED';

export type CampaignV2Purpose =
  | 'NEW_SALE'
  | 'REACTIVATION'
  | 'ACTIVE_MEMBERS'
  | 'UNCLASSIFIED';

export type CampaignV2PreviewBucket =
  | 'RECIPIENTS'
  | 'INVALID_PHONE'
  | 'DUPLICATES'
  | 'OUT_OF_SEGMENT'
  | 'UNCLASSIFIED'
  | 'FAMILY'
  | 'CURRENT_STATUS_BLOCKED'
  | 'BLACKLIST'
  | 'HISTORY_EXCLUDED'
  | 'HISTORY_INCLUDED'
  | 'FUNNEL_CANDIDATES'
  | 'FUNNEL_BUYER_EXCLUDED'
  | 'ACTIVE_MEMBER_SUPPRESSION';

export interface CampaignV2Scope {
  is_global: boolean;
  can_manage_dispatch_config?: boolean;
  allowed_sucursal_keys: string[] | null;
}

export type CampaignV2AudienceFilterKey =
  | 'audience_families'
  | 'expiration_date_from'
  | 'expiration_date_to'
  | 'adeudo_min'
  | 'adeudo_max'
  | 'tarifa'
  | 'categoria_tarifa'
  | 'funnel_month'
  | 'funnel_cutoff_date';

export interface CampaignV2SourceFilterContract {
  required: CampaignV2AudienceFilterKey[];
  not_applicable: CampaignV2AudienceFilterKey[];
  cutoff_policy?: string;
}

export interface CampaignV2OptionsResponse {
  sources: CampaignV2Source[];
  source_filters?: Partial<Record<CampaignV2Source, CampaignV2SourceFilterContract>>;
  selectable_audience_families: CampaignV2AudienceFamily[];
  non_selectable_classifications: CampaignV2NonSelectableClassification[];
  purposes: CampaignV2Purpose[];
  historical_targeting?: CampaignV2HistoricalTargetingOptions;
  iventas_current_statuses?: CampaignV2IventasCurrentStatus[];
  tariff_categories: string[];
  scope: CampaignV2Scope;
  branch_options?: string[];
}

export interface CampaignV2AudienceDefinitionRequest {
  source: CampaignV2Source;
  audience_families?: CampaignV2AudienceFamily[];
  expiration_date_from?: string;
  expiration_date_to?: string;
  adeudo_min?: string;
  adeudo_max?: string;
  selected_sucursal_keys?: string[];
  excluded_sucursal_keys?: string[];
  funnel_month?: string;
  funnel_cutoff_date?: string;
  history_exclusion?: CampaignV2HistoryExclusion;
  historical_targeting?: CampaignV2HistoricalTargeting;
  iventas_current_statuses?: CampaignV2IventasCurrentStatus[];
}

export interface CampaignV2PreviewDetailRequest
  extends CampaignV2AudienceDefinitionRequest {
  bucket: CampaignV2PreviewBucket;
  audience_family?: CampaignV2ObservedFamily;
  page: number;
  page_size: number;
}

export interface CampaignV2FreezeRequest
  extends CampaignV2AudienceDefinitionRequest {
  name: string;
  purpose: CampaignV2Purpose;
  expected_preview_fingerprint: string;
}

export interface CampaignV2SourceMetadata {
  expired_storage?: string;
  expiration_date_from?: string;
  expiration_date_to?: string;
  current_status_activos_snapshot_id?: number | null;
  current_status_activos_cutoff_date?: string | null;
  activos_snapshot_id?: number | null;
  activos_cutoff_date?: string | null;
  activos_captured_at?: string | null;
  snapshot_kind?: string | null;
  funnel_month?: string | null;
  funnel_cutoff_date?: string | null;
  iventas_sync_run_id?: number | null;
  active_members_snapshot_id?: number | null;
  active_members_cutoff_date?: string | null;
  active_members_snapshot_kind?: string | null;
  active_members_captured_at?: string | null;
  funnel_scope?: Record<string, unknown> | null;
  history_evaluation?: CampaignV2HistoryEvaluationMetadata | null;
  [key: string]:
    | string
    | number
    | boolean
    | null
    | string[]
    | number[]
    | CampaignV2HistoryEvaluationMetadata
    | Record<string, unknown>
    | undefined;
}

export interface CampaignV2PreviewFilters {
  source: CampaignV2Source;
  audience_families?: CampaignV2AudienceFamily[];
  allowed_sucursal_keys: string[] | null;
  expiration_date_from?: string;
  expiration_date_to?: string;
  adeudo_min?: string;
  adeudo_max?: string;
  selected_sucursal_keys?: string[];
  excluded_sucursal_keys?: string[];
  funnel_month?: string;
  funnel_cutoff_date?: string;
  history_exclusion?: CampaignV2HistoryExclusion;
  historical_targeting?: CampaignV2HistoricalTargeting;
  iventas_current_statuses?: CampaignV2IventasCurrentStatus[];
}

export interface CampaignV2PreviewSummary {
  universe_count: number;
  scoped_count: number;
  current_status_counts: Record<string, number>;
  current_status_blocked_count: number;
  blacklist_excluded_count?: number;
  filtered_count: number;
  family_counts: Partial<Record<CampaignV2ObservedFamily, number>>;
  unclassified_family_count: number;
  out_of_segment_count: number;
  invalid_phone_count: number;
  duplicate_count: number;
  unique_recipient_count: number;
  funnel_candidate_count?: number;
  funnel_buyer_excluded_count?: number;
  active_member_suppression_count?: number;
  before_history_filter_count?: number;
  history_matched_count?: number;
  history_not_matched_count?: number;
  history_included_count?: number;
  history_excluded_count?: number;
  after_history_filter_count?: number;
  matched_by_delivery_bucket?: Partial<Record<CampaignV2HistoryDeliveryBucket, number>>;
  matched_by_outcome?: Partial<Record<CampaignV2HistoryOutcome, number>>;
  matched_by_button_interaction?: number;
  excluded_by_delivery_bucket?: Partial<Record<CampaignV2HistoryDeliveryBucket, number>>;
  excluded_by_outcome?: Partial<Record<CampaignV2HistoryOutcome, number>>;
  excluded_by_button_interaction?: number;
}

export interface CampaignV2BlacklistSummary {
  total: number;
  latest_created_at: string | null;
}

export interface CampaignV2BlacklistImportResult {
  filename: string;
  rows_read: number;
  valid_unique: number;
  added: number;
  already_existing: number;
  duplicates_in_file: number;
  invalid: number;
  blacklist_total: number;
  latest_created_at: string | null;
}

export interface CampaignV2RecipientDimension {
  label: string;
  count: number;
}

export interface CampaignV2PreviewResponse extends CampaignV2PreviewSummary {
  source: CampaignV2Source;
  source_metadata: CampaignV2SourceMetadata;
  filters: CampaignV2PreviewFilters;
  recipient_dimensions?: {
    branches: CampaignV2RecipientDimension[];
    families: CampaignV2RecipientDimension[];
  };
  preview_fingerprint_version: string;
  preview_fingerprint: string;
}

export interface CampaignV2SourceReference {
  type: string;
  id: number | null;
  snapshot_id: number | null;
}

export interface CampaignV2PreviewDetailRow {
  source: CampaignV2Source;
  source_ref_type?: string;
  source_ref_id?: number | null;
  source_snapshot_id?: number | null;
  phone_raw?: string | null;
  phone_mx10?: string | null;
  member_id?: string | null;
  member_pin?: string | null;
  member_name?: string | null;
  sucursal?: string | null;
  sucursal_key?: string | null;
  tarifa_raw?: string | null;
  tarifa_key?: string | null;
  categoria_tarifa?: string | null;
  audience_family?: CampaignV2ObservedFamily | null;
  fecha_vencimiento?: string | null;
  current_status?: string | null;
  inclusion_reason?: string | null;
  conflict_fields?: string[];
  evidence_count?: number;
  evidence?: string[] | CampaignV2PreviewDetailRow[];
  source_references?: CampaignV2SourceReference[];
  history_exclusion_reasons?: string[];
  history_matched?: boolean;
  history_decision?: 'INCLUDED' | 'EXCLUDED';
  history_reasons?: string[];
}

export interface CampaignV2PreviewDetailResponse {
  source: CampaignV2Source;
  source_metadata: CampaignV2SourceMetadata;
  filters: CampaignV2PreviewFilters;
  bucket: CampaignV2PreviewBucket;
  audience_family: CampaignV2ObservedFamily | null;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  rows: CampaignV2PreviewDetailRow[];
}

export interface CampaignV2FreezeResponse {
  campaign_id: number;
  name: string;
  purpose: CampaignV2Purpose;
  source: CampaignV2Source;
  frozen_at: string;
  recipient_count: number;
  preview_fingerprint_version: string;
  preview_fingerprint: string;
  preview: CampaignV2PreviewSummary & {
    source: CampaignV2Source;
    source_metadata: CampaignV2SourceMetadata;
    filters: CampaignV2PreviewFilters;
  };
}

export interface CampaignV2Pagination<T> {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  rows: T[];
}

export interface CampaignV2CampaignSummary {
  id: number;
  name: string;
  purpose: CampaignV2Purpose;
  source: CampaignV2Source;
  frozen_at: string;
  created_at: string;
  created_by_user_id: number | null;
  recipient_count: number;
  preview_fingerprint: string | null;
  preview_fingerprint_version: string | null;
}

export interface CampaignV2FrozenPreviewIdentity {
  fingerprint?: string | null;
  fingerprint_version?: string | null;
  summary?: CampaignV2PreviewSummary;
}

export interface CampaignV2AudienceDefinition {
  schema_version?: number;
  filters: CampaignV2PreviewFilters;
  source_metadata: CampaignV2SourceMetadata;
  preview: CampaignV2FrozenPreviewIdentity;
}

export interface CampaignV2CampaignDetail extends CampaignV2CampaignSummary {
  updated_at: string;
  audience_definition: CampaignV2AudienceDefinition;
}

export interface CampaignV2DispatchTemplate {
  id: number;
  provider: string;
  template_name: string;
  label: string;
  is_active: boolean;
  purposes: CampaignV2Purpose[];
  variables: Record<string, string>;
  compatible_channel_ids: string[];
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface CampaignV2DispatchTemplatesResponse {
  rows: CampaignV2DispatchTemplate[];
}

export interface CampaignV2ChannelBinding {
  id: number;
  provider: string;
  sucursal_id: number;
  sucursal_canon: string;
  provider_channel_id: string;
  is_active: boolean;
  is_default: boolean;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface CampaignV2CatalogBranch {
  sucursal_id: number;
  sucursal_canon: string;
  track_label: string;
}

export interface CampaignV2ChannelBindingsResponse {
  rows: CampaignV2ChannelBinding[];
}

export interface CampaignV2CatalogBranchesResponse {
  rows: CampaignV2CatalogBranch[];
}

export interface CampaignV2TemplateConfigRequest {
  provider: 'IVENTAS';
  template_name: string;
  label: string;
  purposes: CampaignV2Purpose[];
  variables: Record<string, string>;
  compatible_channel_ids: string[];
  is_active: boolean;
  metadata: Record<string, unknown>;
}

export interface CampaignV2ChannelBindingRequest {
  provider: 'IVENTAS';
  sucursal_id: number;
  provider_channel_id: string;
  is_active: boolean;
  is_default: boolean;
  metadata: Record<string, unknown>;
}

export interface CampaignV2BudgetRateRevision {
  revision_id: number;
  template_id: number;
  provider_channel_id: string;
  unit_cost_mxn: string;
  valid_from: string;
  source_reference: string;
  created_at: string;
}

export interface CampaignV2BudgetRatesResponse {
  rows: CampaignV2BudgetRateRevision[];
}

export interface CampaignV2BudgetRateRequest {
  template_id: number;
  provider_channel_id: string;
  unit_cost_mxn: string;
  source_reference: string;
}

export interface CampaignV2BudgetBatch {
  sucursal_canon: string;
  channel_id: string | null;
  recipients: number;
  revision_id: number | null;
  unit_cost_mxn: string | null;
  source_reference: string | null;
  estimated_mxn: string | null;
}

export interface CampaignV2BranchDiagnosticRow {
  recipient_id: number;
  kind: 'AMBIGUOUS_EVIDENCE' | 'MISSING_EVIDENCE' | 'SINGLE_EVIDENCE_RESOLVABLE' | 'UNMAPPED_BRANCH_ALIAS';
  branch_keys: string[];
  existing_exclusion_reason: string | null;
}

export interface CampaignV2BranchReview {
  campaign_id: number;
  review_fingerprint: string;
  unresolved_count: number;
  counts: Record<string, number>;
  candidate_count: number;
  already_excluded_count: number;
  conflict_count: number;
  new_exclusions: number;
  requires_bulk_confirmation: boolean;
  can_apply: boolean;
  page: number;
  page_size: number;
  rows: CampaignV2BranchDiagnosticRow[];
}

export interface CampaignV2PreviousContactReview {
  campaign_id: number;
  source_campaign_ids: number[];
  matched: number;
  review_fingerprint: string;
  source_breakdown: Array<{
    source_campaign_id: number;
    submitted_contacts: number;
    overlap_contacts: number;
    unique_assigned: number;
  }>;
  new_exclusions: number;
  already_excluded_count: number;
  conflict_count: number;
  can_apply: boolean;
}

export interface CampaignV2PreparationApplyResponse {
  campaign_id: number;
  added: number;
  already_present: number;
}

export interface CampaignV2PreparationApplyRequest {
  expected_fingerprint: string;
  expected_count: number;
  allow_bulk: boolean;
}

export interface CampaignV2QuotaPolicyRevision {
  revision_id: number;
  provider_channel_id: string;
  portfolio_key: string;
  account_key: string;
  phone_alias: string;
  nominal_channel_limit: number | null;
  operational_channel_cap: number | null;
  operational_portfolio_cap: number | null;
  reset_timezone: string;
  valid_from: string;
  source_reference: string;
}

export interface CampaignV2QuotaAttestation {
  attestation_id: number;
  scope_kind: 'CHANNEL' | 'PORTFOLIO';
  scope_key: string;
  remaining_messages: number;
  observed_at: string;
  expires_at: string;
  window_ends_at: string;
  source_reference: string;
}

export interface CampaignV2PortfolioReference {
  revision_id: number;
  business_id: string;
  display_name: string | null;
  app_id: string | null;
  source_reference: string;
  created_by_user_id: number;
  created_at: string;
  verification_status: 'UNVERIFIED';
  verified_channel_count: 0;
}

export interface CampaignV2PortfolioReferenceRequest {
  business_id: string;
  display_name: string | null;
  app_id: string | null;
  source_reference: string;
}

export interface CampaignV2PortfolioReferencesResponse {
  rows: CampaignV2PortfolioReference[];
}

export interface CampaignV2QuotaEvidence {
  policies: CampaignV2QuotaPolicyRevision[];
  attestations: CampaignV2QuotaAttestation[];
}

export interface CampaignV2QuotaPolicyRequest {
  provider_channel_id: string;
  portfolio_key: string;
  account_key: string;
  phone_alias: string;
  nominal_channel_limit: number | null;
  operational_channel_cap: number;
  operational_portfolio_cap: number;
  reset_timezone: string;
  source_reference: string;
}

export interface CampaignV2QuotaAttestationRequest {
  scope_kind: 'CHANNEL' | 'PORTFOLIO';
  scope_key: string;
  observed_at: string;
  expires_at: string;
  window_ends_at: string;
  remaining_messages: number;
  source_reference: string;
}

export interface CampaignV2PreflightQuota {
  basis: 'OPERATOR_ATTESTED_NOT_META_VERIFIED' | 'SUITE_OPERATOR_ROLLING_24H_V1';
  status: 'REVIEWABLE' | 'INCOMPLETE';
  send_authorized: false;
  as_of: string;
  reviewed_recipients: number;
  hold_recommended_recipients: number;
  portfolio_demands: Array<{
    portfolio_key: string;
    recipients: number;
    attested_remaining: number | null;
    operational_cap?: number | null;
    suite_attempted?: number;
    suite_reserved?: number;
  }>;
  batches: Array<{
    sucursal_canon: string;
    provider_channel_id: string | null;
    portfolio_key: string | null;
    account_key: string | null;
    phone_alias: string | null;
    reset_timezone: string | null;
    reported_nominal_channel_limit: number | null;
    operator_channel_cap?: number | null;
    operator_portfolio_cap?: number | null;
    policy_revision_id?: number | null;
    suite_channel_attempted?: number;
    suite_portfolio_attempted?: number;
    suite_channel_reserved?: number;
    suite_portfolio_reserved?: number;
    channel_remaining: number | null;
    portfolio_remaining: number | null;
    channel_evidence_id: number | null;
    portfolio_evidence_id: number | null;
    recipients: number;
    recommendation: 'REVIEW_HOLD' | 'CAPACITY_REVIEWED';
    blocking_reason: string | null;
  }>;
}

export interface CampaignV2PreflightBudget {
  status: 'COMPLETE' | 'INCOMPLETE';
  currency: 'MXN';
  basis: 'MANUAL_OPERATOR_RATE_NOT_PROVIDER_QUOTE';
  as_of: string;
  sendable_recipients: number;
  priced_recipients: number;
  unassigned_recipients: number;
  missing_rate_channels: Array<{sucursal_canon: string; recipient_count: number}>;
  priced_subtotal_mxn: string;
  total_estimated_mxn: string | null;
  batches: CampaignV2BudgetBatch[];
}

export interface CampaignV2PreflightBatch {
  sucursal_id: number;
  sucursal_canon: string;
  track_label: string;
  channel_binding_id: number | null;
  provider_channel_id: string | null;
  template_id: number;
  template_name: string;
  recipient_count: number;
  blocked_reasons: string[];
  ready: boolean;
}

export type CampaignV2SubmitStatus =
  | 'NOT_STARTED'
  | 'READY'
  | 'SUBMITTING'
  | 'SUBMITTED'
  | 'PROVIDER_ERROR'
  | 'RECONCILIATION_REQUIRED'
  | 'HELD'
  | 'SCHEDULED'
  | 'RETRY_ELIGIBLE'
  | 'RETRY_EXHAUSTED'
  | 'PARTIAL';

export interface CampaignV2SubmitBatch {
  child_id: number;
  sucursal_id: number;
  sucursal_canon: string;
  provider_channel_id: string;
  template_name: string;
  recipient_count: number;
  status: string;
  provider_campaign_id: string | null;
  provider_deduplicated: boolean | null;
  error_code: string | null;
  support_ref: string | null;
}

export interface CampaignV2SubmitState {
  enabled: boolean;
  can_send: boolean;
  status: CampaignV2SubmitStatus;
  has_provider_campaigns: boolean;
  batches: CampaignV2SubmitBatch[];
}

export interface CampaignV2SubmitResponse {
  campaign_id: number;
  dispatch_fingerprint: string;
  status: CampaignV2SubmitStatus;
  all_submitted: boolean;
  stopped_after_child_id: number | null;
  batches: CampaignV2SubmitBatch[];
}

export interface CampaignV2PreflightResponse {
  campaign_id: number;
  campaign_name: string;
  campaign_purpose: CampaignV2Purpose;
  provider: string;
  mode: 'IMMEDIATE';
  frozen_count: number;
  suppressed: {
    blacklist: number;
    campaign_exclusions: number;
  };
  sendable_count: number;
  template: {
    id: number;
    template_name: string;
  } | null;
  batches: CampaignV2PreflightBatch[];
  blocked: {
    missing_branch: number;
    missing_channel: number;
    missing_required_variable: number;
    invalid_phone: number;
    template_channel_mismatch: number;
  };
  provider_campaign_count: number;
  dispatch_fingerprint_version: string;
  dispatch_fingerprint: string;
  ready: boolean;
  submission: CampaignV2SubmitState;
  budget?: CampaignV2PreflightBudget;
  quota?: CampaignV2PreflightQuota;
}

export interface CampaignV2RecipientSummary {
  id: number;
  phone_mx10: string;
  source: CampaignV2Source;
  member_id: string | null;
  member_pin: string | null;
  member_name: string | null;
  sucursal: string | null;
  tarifa_raw: string | null;
  categoria_tarifa: string | null;
  audience_family: CampaignV2ObservedFamily | null;
  fecha_vencimiento_date: string | null;
  inclusion_reason: string | null;
  conflict_fields: string[];
  evidence_count: number;
}

export interface CampaignV2RecipientEvidence {
  id: number;
  evidence_order: number;
  source: CampaignV2Source;
  phone_raw: string | null;
  phone_mx10: string;
  socios_vencidos_cartera_id: number | null;
  socios_activos_snapshot_row_id: number | null;
  socios_activos_snapshot_id: number | null;
  member_id: string | null;
  member_pin: string | null;
  member_name: string | null;
  sucursal: string | null;
  sucursal_key: string | null;
  tarifa_raw: string | null;
  tarifa_key: string | null;
  categoria_tarifa: string | null;
  audience_family: CampaignV2ObservedFamily | null;
  fecha_vencimiento_date: string | null;
  current_status: string | null;
  evidence: string[];
  created_at: string;
}

export interface CampaignV2RecipientDetail extends CampaignV2RecipientSummary {
  evidence: CampaignV2RecipientEvidence[];
}

export type CampaignV2CampaignPage = CampaignV2Pagination<CampaignV2CampaignSummary>;
export type CampaignV2RecipientPage = CampaignV2Pagination<CampaignV2RecipientSummary>;

export interface CampaignV2CampaignQuery {
  page: number;
  page_size: number;
  purpose?: CampaignV2Purpose;
  source?: CampaignV2Source;
}

export interface CampaignV2TariffClassificationRequest {
  categoria_tarifa: string;
  audience_family: CampaignV2ObservedFamily;
}

export interface CampaignV2UnclassifiedTariffRow {
  tarifa_raw: string;
  tarifa_key: string;
  source: CampaignV2Source;
  row_count: number;
}

export interface CampaignV2UnclassifiedTariffsResponse {
  source: CampaignV2Source;
  source_metadata: CampaignV2SourceMetadata;
  filters: {
    source: CampaignV2Source;
    expiration_date_from?: string;
    expiration_date_to?: string;
  };
  total_unique_tariffs: number;
  total_unclassified_rows: number;
  unkeyed_row_count: number;
  rows: CampaignV2UnclassifiedTariffRow[];
}

export interface CampaignV2TariffClassificationResult {
  id: number;
  tarifa_key: string;
  tarifa_raw: string;
  categoria_tarifa: string;
  audience_family: CampaignV2ObservedFamily;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  created: boolean;
}

export interface CampaignV2ErrorResponse {
  status?: string;
  message?: string;
}

export type CampaignV2ReportingSnapshotStatus =
  | 'WITH_SNAPSHOT'
  | 'WITHOUT_SNAPSHOT';

export interface CampaignV2ReportingNormalized {
  successful: number;
  failed: number;
  sent: number;
  delivered: number;
  viewed: number;
  reach_count: number;
}

export interface CampaignV2ReportingRates {
  successful_rate: number | null;
  reach_rate: number | null;
  read_rate: number | null;
  failure_rate: number | null;
}

export interface CampaignV2ReportingCoverage {
  matched_recipient_count: number;
  unmatched_provider_count?: number;
  frozen_recipient_without_provider_status_count: number;
  status_coverage_rate: number | null;
}

export interface CampaignV2ReportingProviderRaw {
  successful: number;
  failed: number;
  sent: number;
  delivered: number;
  viewed: number;
  answered?: number;
  interaction_groups?: number;
  interaction_items?: number;
}

export interface CampaignV2ReportingCost {
  status: string;
  currency: string | null;
  total: number | null;
}

export interface CampaignV2ReportingObservation {
  snapshot_id: number | null;
  latest_observed_at: string | null;
  analytics_status: string | null;
  fingerprint?: string | null;
}

export interface CampaignV2ReportingCampaignIdentity {
  id: number;
  name: string;
  purpose: CampaignV2Purpose;
  source: CampaignV2Source;
  provider: string;
  provider_campaign_id: string | null;
  frozen_at: string;
}

export interface CampaignV2ReportingButtonGroup {
  label: string;
  unique_recipient_count: number;
  raw_item_count: number | null;
}

export interface CampaignV2ReportingInteractions {
  unique_button_recipients?: number;
  button_interaction_recipient_exposures?: number;
  button_groups?: CampaignV2ReportingButtonGroup[];
  responders_aggregate: number | null;
  responders_campaigns_with_value?: number;
  free_text_aggregate: number | null;
  free_text_campaigns_with_value?: number;
}

export interface CampaignV2ReportingScope {
  is_global: boolean;
  allowed_sucursal_keys: string[] | null;
}

export interface CampaignV2ReportingDimensions {
  scope: CampaignV2ReportingScope;
  branches: Array<{ value: string; recipient_count: number }>;
  audience_families: Array<{ value: string; recipient_count: number }>;
}

export interface CampaignV2ReportingEvolutionPoint {
  snapshot_id: number;
  observed_at: string;
  normalized: CampaignV2ReportingNormalized;
  provider_raw: Pick<
    CampaignV2ReportingProviderRaw,
    'successful' | 'failed' | 'sent' | 'delivered' | 'viewed'
  >;
  coverage: Pick<
    CampaignV2ReportingCoverage,
    'matched_recipient_count' | 'unmatched_provider_count'
  >;
}

export interface CampaignV2IndividualReport {
  campaign: CampaignV2ReportingCampaignIdentity;
  observation: CampaignV2ReportingObservation;
  audience: {
    total_recipients: number;
  };
  normalized: CampaignV2ReportingNormalized;
  rates: CampaignV2ReportingRates;
  coverage: CampaignV2ReportingCoverage;
  provider_raw: CampaignV2ReportingProviderRaw | null;
  interactions: CampaignV2ReportingInteractions;
  cost: CampaignV2ReportingCost;
  dimensions: CampaignV2ReportingDimensions;
  evolution: CampaignV2ReportingEvolutionPoint[];
}

export interface CampaignV2ConsolidatedCampaignRow {
  campaign: CampaignV2ReportingCampaignIdentity;
  observation: CampaignV2ReportingObservation;
  audience: {
    total_recipients: number;
  };
  normalized: CampaignV2ReportingNormalized;
  rates: CampaignV2ReportingRates;
  coverage: CampaignV2ReportingCoverage;
  provider_raw: CampaignV2ReportingProviderRaw | null;
  interactions: CampaignV2ReportingInteractions;
  cost: CampaignV2ReportingCost;
}

export interface CampaignV2ConsolidatedSummary {
  campaign_count: number;
  campaigns_with_snapshot: number;
  campaigns_without_snapshot: number;
  total_recipients: number;
  normalized: CampaignV2ReportingNormalized;
  rates: CampaignV2ReportingRates;
  coverage: CampaignV2ReportingCoverage;
  provider_raw: CampaignV2ReportingProviderRaw;
  interactions: CampaignV2ReportingInteractions;
  cost: CampaignV2ReportingCost;
}

export interface CampaignV2ReportingBreakdownRow {
  value: string;
  recipient_exposures: number;
  successful: number;
  failed: number;
  sent: number;
  delivered: number;
  viewed: number;
  reach_count: number;
  button_interaction_recipient_exposures: number;
  rates: CampaignV2ReportingRates;
  coverage: Omit<CampaignV2ReportingCoverage, 'unmatched_provider_count'>;
}

export interface CampaignV2ReportingFilters {
  observed_from?: string | null;
  observed_to?: string | null;
  purpose?: CampaignV2Purpose | null;
  source?: CampaignV2Source | null;
  provider?: string | null;
  snapshot_status?: CampaignV2ReportingSnapshotStatus | null;
}

export interface CampaignV2ConsolidatedReport {
  filters: {
    observed_from: string | null;
    observed_to: string | null;
    purpose: CampaignV2Purpose | null;
    source: CampaignV2Source | null;
    provider: string | null;
    snapshot_status: CampaignV2ReportingSnapshotStatus | null;
  };
  summary: CampaignV2ConsolidatedSummary;
  campaigns: CampaignV2ConsolidatedCampaignRow[];
  breakdowns: {
    branches: CampaignV2ReportingBreakdownRow[];
    audience_families: CampaignV2ReportingBreakdownRow[];
  };
}
