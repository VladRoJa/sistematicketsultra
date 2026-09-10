import {
  CampaignAudienceBucket,
  CampaignAudienceExplorerFilters,
  CampaignV1Request,
  ReactivationCampaign,
} from './marketing-reactivation.models';

export interface CampaignAudienceSelectionRequest extends CampaignV1Request {
  bucket: CampaignAudienceBucket;
  explorer_filters?: CampaignAudienceExplorerFilters;
}

export interface CampaignAudienceSelectionResponse {
  bucket: CampaignAudienceBucket;
  label: string;
  bucket_total: number;
  filtered_total: number;
  valid_phone_rows: number;
  unique_valid_contacts: number;
  duplicate_phone_rows: number;
  excluded_by_campaign_rules: number;
  weekly_limit_contacts: number;
  weekly_frequency_decision_required: boolean;
  recipient_count: number;
  can_create: boolean;
  explorer_filters: CampaignAudienceExplorerFilters;
}

export interface CampaignAudienceCreateRequest extends CampaignAudienceSelectionRequest {
  name: string;
  notes?: string | null;
}

export interface CampaignAudienceCreateResponse {
  campaign: ReactivationCampaign;
  selection: CampaignAudienceSelectionResponse;
}
