export type CampaignSourceStatus = 'CURRENT' | 'RECENT' | 'STALE' | 'UNAVAILABLE';

export interface CampaignSourceFreshness {
  cutoff_date: string | null;
  age_days: number | null;
  status: CampaignSourceStatus;
}

export interface CampaignSourceStatusResponse {
  business_date: string;
  sources: {
    activos: CampaignSourceFreshness;
    vencidos: CampaignSourceFreshness;
    iventas: CampaignSourceFreshness;
  };
}
