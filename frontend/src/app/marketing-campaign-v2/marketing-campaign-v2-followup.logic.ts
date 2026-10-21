import type { CampaignV2FollowupStatus } from './marketing-campaign-v2.models';

export const CAMPAIGN_V2_FOLLOWUP_STATUS_OPTIONS: ReadonlyArray<{
  value: CampaignV2FollowupStatus;
  label: string;
}> = [
  { value: 'VIEWED', label: 'Leídos' },
  { value: 'DELIVERED', label: 'Entregados' },
  { value: 'SENT', label: 'Enviados' },
  { value: 'FAILED', label: 'Fallidos' },
  { value: 'SUCCESSFUL', label: 'Aceptados' },
  { value: 'NO_PROVIDER_STATUS', label: 'Sin estado' },
];

export function toggleCampaignV2FollowupStatus(
  selected: ReadonlyArray<CampaignV2FollowupStatus>,
  status: CampaignV2FollowupStatus,
): CampaignV2FollowupStatus[] {
  const next = new Set(selected);
  if (next.has(status)) {
    next.delete(status);
  } else {
    next.add(status);
  }
  // Keep visible option order stable regardless of the order of clicks.
  return CAMPAIGN_V2_FOLLOWUP_STATUS_OPTIONS
    .map(option => option.value)
    .filter(value => next.has(value));
}
