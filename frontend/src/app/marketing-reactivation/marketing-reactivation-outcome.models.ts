export type ReactivationOutcomeStatus =
  | 'PENDING'
  | 'REACTIVATED'
  | 'REVIEW'
  | 'WINDOW_CLOSED';

export interface ReactivationOutcomeCounts {
  sent: number;
  reactivated: number;
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

export interface ReactivationCampaignOutcomeRow {
  recipient_id: number;
  member_name: string | null;
  campaign_branch: string;
  fecha_vencimiento: string | null;
  status: ReactivationOutcomeStatus;
  review_reason: string | null;
  sent_at: string;
  sent_at_local: string;
  reactivated_at_local: string | null;
  days_to_reactivation: number | null;
  active_id_socio: string | null;
  active_sucursal: string | null;
}

export interface ReactivationCampaignOutcomeDetailResponse {
  campaign_id: number;
  name: string;
  applicable: boolean;
  attribution_window_days?: number;
  summary: ReactivationOutcomeCounts;
  rows: ReactivationCampaignOutcomeRow[];
}
