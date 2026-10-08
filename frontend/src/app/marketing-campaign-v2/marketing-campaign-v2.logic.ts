import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2AudienceFamily,
  CampaignV2FreezeRequest,
  CampaignV2HistoryDeliveryBucket,
  CampaignV2HistoryDiagnostics,
  CampaignV2HistoryExclusion,
  CampaignV2HistoricalTargeting,
  CampaignV2IventasCurrentStatus,
  CampaignV2HistoricalTargetingMatch,
  CampaignV2HistoricalTargetingMode,
  CampaignV2HistoricalTargetingWindowMode,
  CampaignV2HistoryOutcome,
  CampaignV2PreviewBucket,
  CampaignV2OptionsResponse,
  CampaignV2PreviewResponse,
  CampaignV2Purpose,
  CampaignV2ReportingFilters,
  CampaignV2ReportingObservation,
  CampaignV2ProviderChildReportingRow,
  CampaignV2ProviderStatsCompleteness,
  CampaignV2Source,
} from './marketing-campaign-v2.models';

export interface CampaignV2AudienceState {
  source: CampaignV2Source;
  audienceFamilies: CampaignV2AudienceFamily[];
  expirationDateFrom: string;
  expirationDateTo: string;
  adeudoMin?: string;
  funnelMonth?: string;
  funnelCutoffDate?: string;
  iventasCurrentStatuses?: CampaignV2IventasCurrentStatus[];
  historyTargetingEnabled?: boolean;
  historyMode?: CampaignV2HistoricalTargetingMode;
  historyMatch?: CampaignV2HistoricalTargetingMatch;
  historyDeliveryBuckets?: CampaignV2HistoryDeliveryBucket[];
  historyOutcomes?: CampaignV2HistoryOutcome[];
  historyButtonInteracted?: boolean;
  historyWindowMode?: CampaignV2HistoricalTargetingWindowMode;
  historyLookbackDays?: string;
}

export type CampaignV2AudienceField =
  | 'source'
  | 'audience_families'
  | 'expiration_date_from'
  | 'expiration_date_to'
  | 'adeudo_min'
  | 'funnel_month'
  | 'funnel_cutoff_date'
  | 'iventas_current_statuses'
  | 'history_targeting_enabled'
  | 'history_mode'
  | 'history_match'
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

export function campaignV2FilterApplies(
  options: CampaignV2OptionsResponse | null | undefined,
  source: CampaignV2Source,
  filter: 'audience_families' | 'expiration_date_from' | 'expiration_date_to' | 'adeudo_min' | 'funnel_month' | 'funnel_cutoff_date',
): boolean {
  const contract = options?.source_filters?.[source];
  if (contract) {
    return !contract.not_applicable.includes(filter);
  }
  if (source === 'FUNNEL_PORTFOLIO') {
    return filter === 'funnel_month' || filter === 'funnel_cutoff_date';
  }
  if (filter === 'audience_families') {
    return true;
  }
  if (
    filter === 'expiration_date_from'
    || filter === 'expiration_date_to'
    || filter === 'adeudo_min'
  ) {
    return source === 'EXPIRED_MEMBERS';
  }
  return false;
}

export function campaignV2FilterRequired(
  options: CampaignV2OptionsResponse | null | undefined,
  source: CampaignV2Source,
  filter: 'funnel_month' | 'funnel_cutoff_date',
): boolean {
  const contract = options?.source_filters?.[source];
  if (contract) {
    return contract.required.includes(filter);
  }
  return source === 'FUNNEL_PORTFOLIO';
}

export function buildCampaignV2AudienceRequest(
  state: CampaignV2AudienceState,
  options?: CampaignV2OptionsResponse | null,
): CampaignV2AudienceDefinitionRequest {
  const base: CampaignV2AudienceDefinitionRequest = {
    source: state.source,
  };

  if (campaignV2FilterApplies(options, state.source, 'audience_families')) {
    base.audience_families = [...state.audienceFamilies];
  }
  if (campaignV2FilterApplies(options, state.source, 'expiration_date_from')) {
    base.expiration_date_from = state.expirationDateFrom;
  }
  if (campaignV2FilterApplies(options, state.source, 'expiration_date_to')) {
    base.expiration_date_to = state.expirationDateTo;
  }
  if (
    campaignV2FilterApplies(options, state.source, 'adeudo_min')
    && state.adeudoMin?.trim()
  ) {
    base.adeudo_min = state.adeudoMin.trim();
  }
  if (campaignV2FilterApplies(options, state.source, 'funnel_month')) {
    base.funnel_month = state.funnelMonth?.trim();
  }
  if (campaignV2FilterApplies(options, state.source, 'funnel_cutoff_date')) {
    base.funnel_cutoff_date = state.funnelCutoffDate?.trim();
  }
  if ((state.iventasCurrentStatuses ?? []).length) {
    base.iventas_current_statuses = [...(state.iventasCurrentStatuses ?? [])];
  }

  const historicalTargeting = buildCampaignV2HistoricalTargeting(state);
  if (historicalTargeting) {
    base.historical_targeting = historicalTargeting;
  }

  return base;
}

export function buildCampaignV2HistoricalTargeting(
  state: CampaignV2AudienceState,
): CampaignV2HistoricalTargeting | undefined {
  if (!state.historyTargetingEnabled) {
    return undefined;
  }

  const deliveryBuckets = state.historyDeliveryBuckets ?? [];
  const outcomes = state.historyOutcomes ?? [];
  const buttonInteracted = Boolean(state.historyButtonInteracted);
  if (!historicalTargetingHasConditions(state)) {
    return undefined;
  }

  return {
    mode: state.historyMode ?? 'EXCLUDE',
    match: state.historyMatch ?? 'ANY',
    delivery_buckets: [...deliveryBuckets],
    outcomes: [...outcomes],
    button_interacted: buttonInteracted,
    lookback_days: state.historyWindowMode === 'LOOKBACK_DAYS'
      ? parseCampaignV2LookbackDays(state.historyLookbackDays ?? '')
      : null,
  };
}

export function historicalTargetingHasConditions(
  state: CampaignV2AudienceState,
): boolean {
  return Boolean(
    (state.historyDeliveryBuckets ?? []).length
    || (state.historyOutcomes ?? []).length
    || state.historyButtonInteracted,
  );
}


export function isCampaignV2AudienceValid(
  state: CampaignV2AudienceState,
  options?: CampaignV2OptionsResponse | null,
): boolean {
  if (!isCampaignV2HistoryFilterValid(state)) {
    return false;
  }

  if (
    campaignV2FilterApplies(options, state.source, 'audience_families')
    && !state.audienceFamilies.length
  ) {
    return false;
  }

  if (campaignV2FilterRequired(options, state.source, 'funnel_month') && !state.funnelMonth?.trim()) {
    return false;
  }
  if (
    campaignV2FilterRequired(options, state.source, 'funnel_cutoff_date')
    && !state.funnelCutoffDate?.trim()
  ) {
    return false;
  }

  if (
    campaignV2FilterApplies(options, state.source, 'adeudo_min')
    && !isCampaignV2AdeudoMinValid(state.adeudoMin ?? '')
  ) {
    return false;
  }

  if (!campaignV2FilterApplies(options, state.source, 'expiration_date_from')) {
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
  if (!state.historyTargetingEnabled) {
    return true;
  }
  if (!historicalTargetingHasConditions(state)) {
    return false;
  }
  if ((state.historyWindowMode ?? 'ALL_HISTORY') === 'ALL_HISTORY') {
    return true;
  }
  return parseCampaignV2LookbackDays(state.historyLookbackDays ?? '') !== null;
}


export function isCampaignV2AdeudoMinValid(value: string): boolean {
  const normalized = value.trim();
  if (!normalized) {
    return true;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed >= 0;
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

export function toggleCampaignV2IventasCurrentStatus(
  selected: CampaignV2IventasCurrentStatus[],
  status: CampaignV2IventasCurrentStatus,
  checked: boolean,
): CampaignV2IventasCurrentStatus[] {
  const order: CampaignV2IventasCurrentStatus[] = [
    'SENT',
    'DELIVERED',
    'VIEWED',
    'FAILED',
    'NO_DATA',
  ];
  const next = new Set(selected);
  checked ? next.add(status) : next.delete(status);
  return order.filter(value => next.has(value));
}

export function campaignV2IventasCurrentStatusLabel(
  status: CampaignV2IventasCurrentStatus,
): string {
  const labels: Record<CampaignV2IventasCurrentStatus, string> = {
    SENT: 'Enviado',
    DELIVERED: 'Entregado, no visto',
    VIEWED: 'Visto',
    FAILED: 'Fallido',
    NO_DATA: 'Sin dato',
  };
  return labels[status];
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
    'adeudo_min',
    'funnel_month',
    'funnel_cutoff_date',
    'iventas_current_statuses',
    'history_targeting_enabled',
    'history_mode',
    'history_match',
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
    | 'blacklist'
    | 'history_excluded'
    | 'history_included'
    | 'funnel_candidates'
    | 'funnel_buyer_excluded'
    | 'active_member_suppression'
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
    case 'blacklist':
      return 'BLACKLIST';
    case 'history_excluded':
      return 'HISTORY_EXCLUDED';
    case 'history_included':
      return 'HISTORY_INCLUDED';
    case 'funnel_candidates':
      return 'FUNNEL_CANDIDATES';
    case 'funnel_buyer_excluded':
      return 'FUNNEL_BUYER_EXCLUDED';
    case 'active_member_suppression':
      return 'ACTIVE_MEMBER_SUPPRESSION';
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
  diagnostics: Partial<CampaignV2HistoryDiagnostics> & {
    matched_by_delivery_bucket?: Partial<Record<CampaignV2HistoryDeliveryBucket, number>>;
    matched_by_outcome?: Partial<Record<CampaignV2HistoryOutcome, number>>;
    matched_by_button_interaction?: number;
  },
): Array<{ label: string; count: number }> {
  const rows: Array<{ label: string; count: number }> = [];
  const neutral = diagnostics.matched_by_delivery_bucket !== undefined
    || diagnostics.matched_by_outcome !== undefined
    || diagnostics.matched_by_button_interaction !== undefined;
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
    const count = neutral
      ? diagnostics.matched_by_delivery_bucket?.[bucket] ?? 0
      : diagnostics.excluded_by_delivery_bucket?.[bucket] ?? 0;
    if (count > 0) {
      rows.push({ label: deliveryLabels[bucket], count });
    }
  }
  for (const outcome of ['SUCCESSFUL', 'FAILED'] as const) {
    const count = neutral
      ? diagnostics.matched_by_outcome?.[outcome] ?? 0
      : diagnostics.excluded_by_outcome?.[outcome] ?? 0;
    if (count > 0) {
      rows.push({ label: outcomeLabels[outcome], count });
    }
  }
  const buttonCount = neutral
    ? diagnostics.matched_by_button_interaction ?? 0
    : diagnostics.excluded_by_button_interaction ?? 0;
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

export function campaignV2HistoricalTargetingModeLabel(
  value: CampaignV2HistoricalTargetingMode,
): string {
  return value === 'INCLUDE'
    ? 'Incluir sólo contactos que cumplan'
    : 'Excluir contactos que cumplan';
}

export function campaignV2HistoricalTargetingMatchLabel(
  value: CampaignV2HistoricalTargetingMatch,
): string {
  return value === 'ALL' ? 'Todas' : 'Cualquiera';
}

export function campaignV2HistoricalTargetingSummary(
  rule: CampaignV2HistoricalTargeting | undefined,
): string[] {
  if (!rule) {
    return [];
  }
  const rows = [
    ...rule.delivery_buckets.map(campaignV2HistoryDeliveryLabel),
    ...rule.outcomes.map(campaignV2HistoryOutcomeLabel),
  ];
  if (rule.button_interacted) {
    rows.push('Interacción con botón');
  }
  return rows;
}

export function campaignV2HistoricalTargetingWindowLabel(
  rule: CampaignV2HistoricalTargeting | undefined,
): string {
  if (!rule || rule.lookback_days === null) {
    return 'Todo el historial';
  }
  return 'Últimos ' + rule.lookback_days + ' días';
}

export function campaignV2HistoryMatchedLabel(
  matched: boolean | undefined,
): string {
  if (matched === true) {
    return 'Sí';
  }
  if (matched === false) {
    return 'No';
  }
  return '—';
}

export function campaignV2HistoryReasonsLabel(
  historyReasons: string[] | undefined,
  legacyReasons: string[] | undefined,
): string {
  const reasons = historyReasons ?? legacyReasons ?? [];
  if (!reasons.length) {
    return 'Sin señales seleccionadas observadas';
  }
  return reasons.map(campaignV2HistoryReasonLabel).join(', ');
}

export function campaignV2HistoryDecisionLabel(
  decision: 'INCLUDED' | 'EXCLUDED' | undefined,
): string {
  if (decision === 'INCLUDED') {
    return 'Incluido';
  }
  if (decision === 'EXCLUDED') {
    return 'Excluido';
  }
  return '—';
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

export interface CampaignV2ReportingFilterState {
  observedFromDate: string;
  observedToDate: string;
  purpose: CampaignV2Purpose | '';
  source: CampaignV2Source | '';
  provider: string;
  snapshotStatus: '' | 'WITH_SNAPSHOT' | 'WITHOUT_SNAPSHOT';
}

export function campaignV2ReportingFilterValidation(
  state: CampaignV2ReportingFilterState,
): string | null {
  if (state.observedFromDate && !campaignV2IsIsoDate(state.observedFromDate)) {
    return 'La fecha "Observado desde" no es válida.';
  }
  if (state.observedToDate && !campaignV2IsIsoDate(state.observedToDate)) {
    return 'La fecha "Observado hasta" no es válida.';
  }
  if (
    state.observedFromDate
    && state.observedToDate
    && state.observedFromDate > state.observedToDate
  ) {
    return '"Observado desde" no puede ser posterior a "Observado hasta".';
  }
  return null;
}

export function buildCampaignV2ReportingQuery(
  state: CampaignV2ReportingFilterState,
): CampaignV2ReportingFilters {
  const query: CampaignV2ReportingFilters = {};
  if (state.observedFromDate) {
    query.observed_from = campaignV2LocalDayBoundaryIso(
      state.observedFromDate,
      'START',
    );
  }
  if (state.observedToDate) {
    query.observed_to = campaignV2LocalDayBoundaryIso(
      state.observedToDate,
      'END',
    );
  }
  if (state.purpose) {
    query.purpose = state.purpose;
  }
  if (state.source) {
    query.source = state.source;
  }
  const provider = state.provider.trim();
  if (provider) {
    query.provider = provider;
  }
  if (state.snapshotStatus) {
    query.snapshot_status = state.snapshotStatus;
  }
  return query;
}

export function campaignV2ReportingPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return `${(value * 100).toFixed(2)}%`;
}

export function campaignV2ReportingValue(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  return String(value);
}

export function campaignV2ReportingSnapshotLabel(
  observation: CampaignV2ReportingObservation,
): string {
  if (observation.source === 'PROVIDER_CHILDREN') {
    return campaignV2ProviderStatsLabel(
      (observation.analytics_status as CampaignV2ProviderStatsCompleteness) || 'unavailable',
    );
  }
  if (observation.snapshot_id === null) {
    return 'Sin observación';
  }
  return observation.analytics_status || 'Con observación';
}

export function campaignV2ReportingBranchLabel(value: string): string {
  return value === 'UNKNOWN' ? 'Sin atribución' : value;
}

export function campaignV2ReportingAudienceFamilyLabel(value: string): string {
  return value === 'UNKNOWN' ? 'Sin clasificación' : value;
}

export function campaignV2ProviderStatsLabel(status: CampaignV2ProviderStatsCompleteness): string {
  const labels: Record<CampaignV2ProviderStatsCompleteness, string> = {
    complete: 'Estadísticas completas',
    partial: 'Estadísticas parciales',
    unavailable: 'Sin estadísticas disponibles',
  };
  return labels[status] || 'Estado desconocido';
}

export function campaignV2ProviderBatchLabel(status: string): string {
  const labels: Record<string, string> = {
    SUBMITTED: 'Aceptado por iVentas',
    SCHEDULED: 'Programado (no enviado aún)',
    RECONCILIATION_REQUIRED: 'Requiere conciliación',
    RETRY_ELIGIBLE: 'Elegible para reintento seguro',
    PROVIDER_ERROR: 'Error del proveedor',
    SUBMITTING: 'En proceso',
    PREPARED: 'Preparado',
  };
  return labels[status] || status || 'Desconocido';
}

export function campaignV2ProviderBatchStatsLabel(row: CampaignV2ProviderChildReportingRow): string {
  if (row.analytics_status === 'ok' && row.snapshot_id !== null) {
    return 'Estadísticas disponibles';
  }
  if (row.analytics_status === 'not_synced') {
    return 'Pendiente de sincronizar';
  }
  return 'Sin estadísticas';
}

export function campaignV2ReportingCostLabel(status: string): string {
  const labels: Record<string, string> = {
    complete: 'Costo completo',
    available: 'Costo disponible',
    partial: 'Costo parcial, total no confirmado',
    unavailable: 'Costos no disponibles',
  };
  return labels[status] || 'Costo sin confirmar';
}

export function campaignV2DownloadBlob(
  blob: Blob,
  filename: string,
): void {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(objectUrl);
}

function campaignV2LocalDayBoundaryIso(
  value: string,
  boundary: 'START' | 'END',
): string {
  if (!campaignV2IsIsoDate(value)) {
    throw new Error('Fecha local inválida.');
  }
  const [year, month, day] = value.split('-').map(Number);
  const local = boundary === 'START'
    ? new Date(year, month - 1, day, 0, 0, 0, 0)
    : new Date(year, month - 1, day, 23, 59, 59, 999);
  return campaignV2IsoWithLocalOffset(local);
}

function campaignV2IsoWithLocalOffset(value: Date): string {
  const pad = (part: number, size = 2): string => String(part).padStart(size, '0');
  const offsetMinutes = -value.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const absoluteOffset = Math.abs(offsetMinutes);
  const offsetHours = Math.floor(absoluteOffset / 60);
  const offsetRemainder = absoluteOffset % 60;
  return [
    `${pad(value.getFullYear(), 4)}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`,
    `T${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}.${pad(value.getMilliseconds(), 3)}`,
    `${sign}${pad(offsetHours)}:${pad(offsetRemainder)}`,
  ].join('');
}

function campaignV2IsIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(year, month - 1, day);
  return (
    parsed.getFullYear() === year
    && parsed.getMonth() === month - 1
    && parsed.getDate() === day
  );
}
