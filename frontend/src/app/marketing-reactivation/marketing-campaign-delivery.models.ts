import { ReactivationCampaign } from './marketing-reactivation.models';

export type CampaignDeliveryStatus =
  | 'DRAFT'
  | 'EXPORTED'
  | 'PARTIALLY_SENT'
  | 'SENT'
  | 'CANCELLED';

export interface CampaignDeliveryBranch {
  sucursal: string;
  recipient_count: number;
  sent: boolean;
  sent_at: string | null;
  sent_by_user_id: number | null;
}

export interface CampaignDeliverySummary {
  status: CampaignDeliveryStatus;
  total_branches: number;
  sent_branches: number;
  pending_branches: number;
  total_contacts: number;
  sent_contacts: number;
  pending_contacts: number;
}

export interface CampaignDeliveryDetailResponse {
  campaign_id: number;
  name: string;
  campaign_status: ReactivationCampaign['status'];
  delivery: CampaignDeliverySummary & {
    branches: CampaignDeliveryBranch[];
  };
}

export interface CampaignDeliverySaveRequest {
  sucursales: string[];
  sent_at_local: string;
}

export interface CampaignWithDelivery extends ReactivationCampaign {
  delivery?: CampaignDeliverySummary;
}

export interface CampaignDeliverySummaryListResponse {
  rows: Array<{
    id: number;
    delivery?: CampaignDeliverySummary;
  }>;
}
