import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2AudienceFamily,
  CampaignV2FreezeRequest,
  CampaignV2PreviewBucket,
  CampaignV2PreviewResponse,
  CampaignV2Purpose,
  CampaignV2Source,
} from './marketing-campaign-v2.models';

export interface CampaignV2AudienceState {
  source: CampaignV2Source;
  audienceFamilies: CampaignV2AudienceFamily[];
  expirationDateFrom: string;
  expirationDateTo: string;
}

export type CampaignV2AudienceField =
  | 'source'
  | 'audience_families'
  | 'expiration_date_from'
  | 'expiration_date_to'
  | 'name'
  | 'purpose';

export interface CampaignV2FreezeEligibility {
  preview: CampaignV2PreviewResponse | null;
  name: string;
  purpose: CampaignV2Purpose | null;
  creating: boolean;
}

export function buildCampaignV2AudienceRequest(
  state: CampaignV2AudienceState,
): CampaignV2AudienceDefinitionRequest {
  const base: CampaignV2AudienceDefinitionRequest = {
    source: state.source,
    audience_families: [...state.audienceFamilies],
  };

  if (state.source === 'EXPIRED_MEMBERS') {
    base.expiration_date_from = state.expirationDateFrom;
    base.expiration_date_to = state.expirationDateTo;
  }

  return base;
}

export function isCampaignV2AudienceValid(state: CampaignV2AudienceState): boolean {
  if (!state.audienceFamilies.length) {
    return false;
  }

  if (state.source === 'ACTIVE_MEMBERS') {
    return true;
  }

  if (!state.expirationDateFrom || !state.expirationDateTo) {
    return false;
  }

  return state.expirationDateFrom <= state.expirationDateTo;
}

export function toggleCampaignV2Family(
  selected: CampaignV2AudienceFamily[],
  family: CampaignV2AudienceFamily,
  checked: boolean,
  available: CampaignV2AudienceFamily[],
): CampaignV2AudienceFamily[] {
  const next = new Set(selected);
  if (checked) {
    next.add(family);
  } else {
    next.delete(family);
  }
  return available.filter(value => next.has(value));
}

export function selectAllCampaignV2Families(
  available: CampaignV2AudienceFamily[],
): CampaignV2AudienceFamily[] {
  return [...available];
}

export function campaignV2FieldInvalidatesPreview(field: CampaignV2AudienceField): boolean {
  return [
    'source',
    'audience_families',
    'expiration_date_from',
    'expiration_date_to',
  ].includes(field);
}

export function buildCampaignV2FreezeRequest(
  audience: CampaignV2AudienceDefinitionRequest,
  name: string,
  purpose: CampaignV2Purpose,
  previewFingerprint: string,
): CampaignV2FreezeRequest {
  return {
    ...audience,
    name: name.trim(),
    purpose,
    expected_preview_fingerprint: previewFingerprint,
  };
}

export function canFreezeCampaignV2(input: CampaignV2FreezeEligibility): boolean {
  return Boolean(
    input.preview
    && input.preview.preview_fingerprint
    && input.preview.unique_recipient_count > 0
    && input.name.trim().length > 0
    && input.name.trim().length <= 255
    && input.purpose
    && !input.creating
  );
}

export function campaignV2MetricBucket(
  metric:
    | 'recipients'
    | 'invalid_phone'
    | 'duplicates'
    | 'out_of_segment'
    | 'unclassified'
    | 'current_status_blocked'
    | 'family',
): CampaignV2PreviewBucket {
  switch (metric) {
    case 'recipients':
      return 'RECIPIENTS';
    case 'invalid_phone':
      return 'INVALID_PHONE';
    case 'duplicates':
      return 'DUPLICATES';
    case 'out_of_segment':
      return 'OUT_OF_SEGMENT';
    case 'unclassified':
      return 'UNCLASSIFIED';
    case 'current_status_blocked':
      return 'CURRENT_STATUS_BLOCKED';
    case 'family':
      return 'FAMILY';
  }
}

export function campaignV2PurposePatch(purpose: CampaignV2Purpose): { purpose: CampaignV2Purpose } {
  return { purpose };
}

export function campaignV2FreezeErrorInvalidatesPreview(status: number): boolean {
  return status === 409;
}
