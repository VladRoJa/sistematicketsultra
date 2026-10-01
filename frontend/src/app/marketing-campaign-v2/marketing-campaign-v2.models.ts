export type CampaignV2Source = 'EXPIRED_MEMBERS' | 'ACTIVE_MEMBERS';

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
  | 'CURRENT_STATUS_BLOCKED';

export interface CampaignV2Scope {
  is_global: boolean;
  allowed_sucursal_keys: string[] | null;
}

export interface CampaignV2OptionsResponse {
  sources: CampaignV2Source[];
  selectable_audience_families: CampaignV2AudienceFamily[];
  non_selectable_classifications: CampaignV2NonSelectableClassification[];
  purposes: CampaignV2Purpose[];
  scope: CampaignV2Scope;
}

export interface CampaignV2AudienceDefinitionRequest {
  source: CampaignV2Source;
  audience_families: CampaignV2AudienceFamily[];
  expiration_date_from?: string;
  expiration_date_to?: string;
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
  [key: string]: string | number | boolean | null | string[] | number[] | undefined;
}

export interface CampaignV2PreviewFilters {
  source: CampaignV2Source;
  audience_families: CampaignV2AudienceFamily[];
  allowed_sucursal_keys: string[] | null;
  expiration_date_from?: string;
  expiration_date_to?: string;
}

export interface CampaignV2PreviewSummary {
  universe_count: number;
  scoped_count: number;
  current_status_counts: Record<string, number>;
  current_status_blocked_count: number;
  filtered_count: number;
  family_counts: Partial<Record<CampaignV2ObservedFamily, number>>;
  unclassified_family_count: number;
  out_of_segment_count: number;
  invalid_phone_count: number;
  duplicate_count: number;
  unique_recipient_count: number;
}

export interface CampaignV2PreviewResponse extends CampaignV2PreviewSummary {
  source: CampaignV2Source;
  source_metadata: CampaignV2SourceMetadata;
  filters: CampaignV2PreviewFilters;
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
