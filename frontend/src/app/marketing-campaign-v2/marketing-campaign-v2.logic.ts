import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2AudienceFamily,
  CampaignV2FreezeRequest,
  CampaignV2HistoryDeliveryBucket,
  CampaignV2HistoryDiagnostics,
  CampaignV2HistoryExclusion,
  CampaignV2HistoryOutcome,
  CampaignV2PreviewBucket,
  CampaignV2PreviewResponse,
  CampaignV2Purpose,
  CampaignV2Source,
} from './marketing-campaign-v2.models';

export type CampaignV2HistoryWindowMode = 'ALL' | 'DAYS';

export interface CampaignV2AudienceState {
  source: CampaignV2Source;
  audienceFamilies: CampaignV2AudienceFamily[];
  expirationDateFrom: string;
  expirationDateTo: string;
  historyEnabled?: boolean;
  historyDeliveryBuckets?: CampaignV2HistoryDeliveryBucket[];
  historyOutcomes?: CampaignV2HistoryOutcome[];
  historyButtonInteracted?: boolean;
  historyWindowMode?: CampaignV2HistoryWindowMode;
  historyLookbackDays?: string;
}

export type CampaignV2AudienceField =
  | 'source'
  | 'audience_families'
  | 'expiration_date_from'
  | 'expiration_date_to'
  | 'history_enabled'
  | 'history_delivery_buckets'
  | 'history_outcomes'
  | 'history_button_interacted'
  | 'history_window_mode'
  | 'history_lookback_days'
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

  const historyExclusion = buildCampaignV2HistoryExclusion(state);
  if (historyExclusion) {
    base.history_exclusion = historyExclusion;
  }

  return base;
}

export function buildCampaignV2HistoryExclusion(
  state: CampaignV2AudienceState,
): CampaignV2HistoryExclusion | undefined {
  if (!state.historyEnabled) {
    return undefined;
  }

  const deliveryBuckets = state.historyDeliveryBuckets ?? [];
  const outcomes = state.historyOutcomes ?? [];
  const buttonInteracted = Boolean(state.historyButtonInteracted);
  const hasCondition = Boolean(
    deliveryBuckets.length
    || outcomes.length
    || buttonInteracted,
  );

  if (!hasCondition) {
    return undefined;
  }

  return {
    delivery_buckets: [...deliveryBuckets],
    outcomes: [...outcomes],
    button_interacted: buttonInteracted,
    lookback_days: state.historyWindowMode === 'DAYS'
      ? parseCampaignV2LookbackDays(state.historyLookbackDays ?? '')
      : null,
  };
}

export function isCampaignV2AudienceValid(state: CampaignV2AudienceState): boolean {
  if (!state.audienceFamilies.length) {
    return false;
  }

  if (!isCampaignV2HistoryFilterValid(state)) {
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

export function isCampaignV2HistoryFilterValid(
  state: CampaignV2AudienceState,
): boolean {
  if (!state.historyEnabled) {
    return true;
  }

  const hasCondition = Boolean(
    (state.historyDeliveryBuckets ?? []).length
    || (state.historyOutcomes ?? []).length
    || state.historyButtonInteracted,
  );
  if (!hasCondition || (state.historyWindowMode ?? 'ALL') === 'ALL') {
    return true;
  }

  return parseCampaignV2LookbackDays(state.historyLookbackDays ?? '') !== null;
}

export function parseCampaignV2LookbackDays(value: string): number | null {
  const normalized = value.trim();
  if (!/^[1-9]\d*$/.test(normalized)) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
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

export function toggleCampaignV2HistoryDeliveryBucket(
  selected: CampaignV2HistoryDeliveryBucket[],
  bucket: CampaignV2HistoryDeliveryBucket,
  checked: boolean,
): CampaignV2HistoryDeliveryBucket[] {
  const order: CampaignV2HistoryDeliveryBucket[] = ['SENT', 'DELIVERED', 'VIEWED'];
  const next = new Set(selected);
  checked ? next.add(bucket) : next.delete(bucket);
  return order.filter(value => next.has(value));
}

export function toggleCampaignV2HistoryOutcome(
  selected: CampaignV2HistoryOutcome[],
  outcome: CampaignV2HistoryOutcome,
  checked: boolean,
): CampaignV2HistoryOutcome[] {
  const order: CampaignV2HistoryOutcome[] = ['SUCCESSFUL', 'FAILED'];
  const next = new Set(selected);
  checked ? next.add(outcome) : next.delete(outcome);
  return order.filter(value => next.has(value));
}

export function campaignV2FieldInvalidatesPreview(field: CampaignV2AudienceField): boolean {
  return [
    'source',
    'audience_families',
    'expiration_date_from',
    'expiration_date_to',
    'history_enabled',
    'history_delivery_buckets',
    'history_outcomes',
    'history_button_interacted',
    'history_window_mode',
    'history_lookback_days',
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
    | 'history_excluded'
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
    case 'history_excluded':
      return 'HISTORY_EXCLUDED';
    case 'family':
      return 'FAMILY';
  }
}

export function campaignV2HistoryDeliveryLabel(
  value: CampaignV2HistoryDeliveryBucket,
): string {
  const labels: Record<CampaignV2HistoryDeliveryBucket, string> = {
    SENT: 'Enviado',
    DELIVERED: 'Entregado',
    VIEWED: 'Visto',
  };
  return labels[value];
}

export function campaignV2HistoryOutcomeLabel(
  value: CampaignV2HistoryOutcome,
): string {
  const labels: Record<CampaignV2HistoryOutcome, string> = {
    SUCCESSFUL: 'Exitoso',
    FAILED: 'Fallido',
  };
  return labels[value];
}

export function campaignV2HistoryBreakdownRows(
  diagnostics: Partial<CampaignV2HistoryDiagnostics>,
): Array<{ label: string; count: number }> {
  const rows: Array<{ label: string; count: number }> = [];
  const deliveryLabels: Record<CampaignV2HistoryDeliveryBucket, string> = {
    SENT: 'Enviados',
    DELIVERED: 'Entregados',
    VIEWED: 'Vistos',
  };
  const outcomeLabels: Record<CampaignV2HistoryOutcome, string> = {
    SUCCESSFUL: 'Exitosos',
    FAILED: 'Fallidos',
  };

  for (const bucket of ['SENT', 'DELIVERED', 'VIEWED'] as const) {
    const count = diagnostics.excluded_by_delivery_bucket?.[bucket] ?? 0;
    if (count > 0) {
      rows.push({ label: deliveryLabels[bucket], count });
    }
  }
  for (const outcome of ['SUCCESSFUL', 'FAILED'] as const) {
    const count = diagnostics.excluded_by_outcome?.[outcome] ?? 0;
    if (count > 0) {
      rows.push({ label: outcomeLabels[outcome], count });
    }
  }
  const buttonCount = diagnostics.excluded_by_button_interaction ?? 0;
  if (buttonCount > 0) {
    rows.push({ label: 'Interacción con botón', count: buttonCount });
  }
  return rows;
}

export function campaignV2HistoryReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    HISTORY_DELIVERY_SENT: 'Enviado anteriormente',
    HISTORY_DELIVERY_DELIVERED: 'Entregado anteriormente',
    HISTORY_DELIVERY_VIEWED: 'Visto anteriormente',
    HISTORY_OUTCOME_SUCCESSFUL: 'Resultado exitoso anteriormente',
    HISTORY_OUTCOME_FAILED: 'Resultado fallido anteriormente',
    HISTORY_BUTTON_INTERACTION: 'Interactuó con un botón',
  };
  return labels[reason] ?? `Razón histórica: ${reason}`;
}

export function campaignV2HistoryExclusionSummary(
  exclusion: CampaignV2HistoryExclusion | undefined,
): string[] {
  if (!exclusion) {
    return [];
  }

  const rows = [
    ...exclusion.delivery_buckets.map(campaignV2HistoryDeliveryLabel),
    ...exclusion.outcomes.map(campaignV2HistoryOutcomeLabel),
  ];
  if (exclusion.button_interacted) {
    rows.push('Interacción con botón');
  }
  return rows;
}

export function campaignV2HistoryWindowLabel(
  exclusion: CampaignV2HistoryExclusion | undefined,
): string {
  if (!exclusion || exclusion.lookback_days === null) {
    return 'Todo el historial observado';
  }
  return `${exclusion.lookback_days} días de historial observado`;
}

export function campaignV2PurposePatch(
  purpose: CampaignV2Purpose,
): { purpose: CampaignV2Purpose } {
  return { purpose };
}

export function campaignV2FreezeErrorInvalidatesPreview(status: number): boolean {
  return status === 409;
}
