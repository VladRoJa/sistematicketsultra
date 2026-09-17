export type ReactivationOutcomeStatus =
  | 'PENDING'
  | 'REACTIVATED'
  | 'REVIEW'
  | 'WINDOW_CLOSED';

export type RecoveryBusinessResult = 'RENOVACION' | 'REACTIVACION';

export type IventasFollowupMatchStatus = 'NOT_FOUND' | 'MATCHED' | 'MULTIPLE';

export interface ReactivationOutcomeCounts {
  sent: number;
  reactivated: number;
  recovered: number;
  renewals: number;
  reactivations: number;
  unclassified_recovered: number;
  pending: number;
  review: number;
  window_closed: number;
  in_tracking: number;
  conversion_rate: number;
}

export interface ReactivationCampaignOutcomeSummary extends ReactivationOutcomeCounts {
  campaign_id: number;
  name: string;
  campaign_type: string | null;
  sent_at: string | null;
  sent_date_local: string | null;
  attribution_window_days: number;
}

export interface ReactivationOutcomeSummaryResponse {
  date_from: string | null;
  date_to: string | null;
  summary: ReactivationOutcomeCounts;
  campaigns: ReactivationCampaignOutcomeSummary[];
}

export interface IventasFollowupSource {
  available: boolean;
  sync_run_id: number | null;
  period_key: string | null;
  date_from: string | null;
  date_to: string | null;
  finished_at: string | null;
}

export interface ReactivationCampaignOutcomeRow {
  recipient_id: number;
  member_name: string | null;
  phone_mx10: string | null;
  campaign_branch: string;
  fecha_vencimiento: string | null;
  status: ReactivationOutcomeStatus;
  business_result: RecoveryBusinessResult | null;
  review_reason: string | null;
  sent_at: string;
  sent_at_local: string;
  reactivated_at_local: string | null;
  days_to_reactivation: number | null;
  active_id_socio: string | null;
  active_sucursal: string | null;
  iventas_contact_found: boolean;
  iventas_match_status: IventasFollowupMatchStatus;
  iventas_match_count: number;
  iventas_contact_id: string | null;
  iventas_name: string | null;
  iventas_branch_code: string | null;
  iventas_created_at_local: string | null;
  iventas_first_message_at_local: string | null;
  iventas_last_outbound_at_local: string | null;
  iventas_last_message_status: string | null;
  iventas_channel_name: string | null;
  iventas_channel_platform: string | null;
  iventas_agent_name: string | null;
  iventas_tags: string[];
  iventas_is_from_ads: boolean | null;
  iventas_ads_source_id: string | null;
  iventas_activity_after_send: boolean | null;
}

export interface ReactivationCampaignOutcomeDetailResponse {
  campaign_id: number;
  name: string;
  applicable: boolean;
  attribution_window_days?: number;
  summary: ReactivationOutcomeCounts;
  iventas_source?: IventasFollowupSource;
  rows: ReactivationCampaignOutcomeRow[];
}
