import { campaignV2BuildReadinessRows } from './marketing-campaign-v2-readiness.logic';
import { pendingGovernedBatchIds } from './marketing-campaign-v2-bulk-dispatch.logic';
import { parsePreviousCampaignIds } from './marketing-campaign-v2-preparation.logic';
import type { CampaignV2GovernedMonitor, CampaignV2GovernedExecutionReviewReady } from './marketing-campaign-v2.models';
import type { CampaignV2DispatchTemplate, CampaignV2ChannelBinding, CampaignV2QuotaPolicyRevision, CampaignV2BudgetRateRevision } from './marketing-campaign-v2.models';
import { campaignV2IndicativeBudget } from './marketing-campaign-v2-budget.logic';
import { isDispatchTemplateDraftValid, DispatchTemplateDraft } from './marketing-campaign-v2-dispatch-admin.logic';
import { isCampaignV2MxnUnitCostValid, isCampaignV2NominalLimitValid, isCampaignV2RemainingCountValid, isCampaignV2ZonedDateString } from './marketing-campaign-v2-admin-validation.logic';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import {
  buildCampaignV2AudienceRequest,
  buildCampaignV2FreezeRequest,
  buildCampaignV2HistoricalTargeting,
  buildCampaignV2ReportingQuery,
  campaignV2HistoryBreakdownRows,
  campaignV2HistoryDecisionLabel,
  campaignV2HistoryMatchedLabel,
  campaignV2HistoryReasonLabel,
  campaignV2HistoryReasonsLabel,
  isCampaignV2HistoryFilterValid,
  parseCampaignV2LookbackDays,
  campaignV2FieldInvalidatesPreview,
  campaignV2FreezeErrorInvalidatesPreview,
  campaignV2MetricBucket,
  campaignV2PurposePatch,
  campaignV2ReportingAudienceFamilyLabel,
  campaignV2ReportingBranchLabel,
  campaignV2ReportingCostLabel,
  campaignV2ReportingFilterValidation,
  campaignV2ReportingPercent,
  campaignV2ReportingSnapshotLabel,
  campaignV2ReportingValue,
  canFreezeCampaignV2,
  isCampaignV2AudienceValid,
  isCampaignV2AdeudoMinValid,
  selectAllCampaignV2Families,
  toggleCampaignV2Family,
} from './marketing-campaign-v2.logic';
import {
  CAMPAIGN_V2_MENU_ITEM,
  withCampaignV2MenuItem,
} from './marketing-campaign-v2-menu';
import {
  CampaignV2AudienceFamily,
  CampaignV2HistoryDeliveryBucket,
  CampaignV2HistoryOutcome,
  CampaignV2OptionsResponse,
  CampaignV2PreviewResponse,
} from './marketing-campaign-v2.models';

const allFamilies: CampaignV2AudienceFamily[] = [
  'DOMICILIADO',
  'TRIMESTRAL',
  'CONVENIO',
  'SEMESTRE',
  'ESTUDIANTE',
];

function preview(): CampaignV2PreviewResponse {
  return {
    source: 'EXPIRED_MEMBERS',
    source_metadata: {},
    filters: {
      source: 'EXPIRED_MEMBERS',
      audience_families: ['DOMICILIADO'],
      allowed_sucursal_keys: null,
      expiration_date_from: '2026-08-01',
      expiration_date_to: '2026-08-31',
    },
    universe_count: 10,
    scoped_count: 10,
    current_status_counts: {},
    current_status_blocked_count: 0,
    blacklist_excluded_count: 0,
    filtered_count: 8,
    family_counts: { DOMICILIADO: 8 },
    unclassified_family_count: 0,
    out_of_segment_count: 0,
    invalid_phone_count: 0,
    duplicate_count: 0,
    unique_recipient_count: 8,
    preview_fingerprint_version: 'campaign-v2-freeze-v1',
    preview_fingerprint: 'a'.repeat(64),
  };
}

test('EXPIRED incluye fechas y ACTIVE las elimina del request', () => {
  const expired = buildCampaignV2AudienceRequest({
    source: 'EXPIRED_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '2026-08-01',
    expirationDateTo: '2026-08-31',
  });
  assert.equal(expired.expiration_date_from, '2026-08-01');
  assert.equal(expired.expiration_date_to, '2026-08-31');

  const active = buildCampaignV2AudienceRequest({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '2026-08-01',
    expirationDateTo: '2026-08-31',
  });
  assert.deepEqual(active, {
    source: 'ACTIVE_MEMBERS',
    audience_families: ['DOMICILIADO'],
  });
});

test('estado actual iVentas viaja separado del historial de campañas', () => {
  const request = buildCampaignV2AudienceRequest({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '',
    expirationDateTo: '',
    iventasCurrentStatuses: ['VIEWED'],
    historyTargetingEnabled: false,
  });
  assert.deepEqual(request.iventas_current_statuses, ['VIEWED']);
  assert.equal('historical_targeting' in request, false);
  assert.equal(campaignV2FieldInvalidatesPreview('iventas_current_statuses'), true);
});

test('familias son lista OR, seleccionar todas usa Options y cero familias es inválido', () => {
  assert.deepEqual(selectAllCampaignV2Families(allFamilies), allFamilies);
  const selected = toggleCampaignV2Family([], 'DOMICILIADO', true, allFamilies);
  const second = toggleCampaignV2Family(selected, 'CONVENIO', true, allFamilies);
  assert.deepEqual(second, ['DOMICILIADO', 'CONVENIO']);
  assert.equal(isCampaignV2AudienceValid({
    source: 'ACTIVE_MEMBERS', audienceFamilies: [], expirationDateFrom: '', expirationDateTo: '',
  }), false);
});

test('validación EXPIRED exige fechas ordenadas', () => {
  assert.equal(isCampaignV2AudienceValid({
    source: 'EXPIRED_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '2026-08-31',
    expirationDateTo: '2026-08-01',
  }), false);
  assert.equal(isCampaignV2AudienceValid({
    source: 'EXPIRED_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '2026-08-01',
    expirationDateTo: '2026-08-31',
  }), true);
});

test('source/family/fechas invalidan Preview; name/purpose no', () => {
  for (const field of ['source', 'audience_families', 'expiration_date_from', 'expiration_date_to'] as const) {
    assert.equal(campaignV2FieldInvalidatesPreview(field), true);
  }
  assert.equal(campaignV2FieldInvalidatesPreview('name'), false);
  assert.equal(campaignV2FieldInvalidatesPreview('purpose'), false);
});

test('Freeze usa fingerprint vigente y payload no contiene scope/creator/cohorte', () => {
  const request = buildCampaignV2FreezeRequest(
    { source: 'ACTIVE_MEMBERS', audience_families: ['DOMICILIADO'] },
    ' Campaña ',
    'UNCLASSIFIED',
    'f'.repeat(64),
  );
  assert.deepEqual(Object.keys(request).sort(), [
    'audience_families',
    'expected_preview_fingerprint',
    'name',
    'purpose',
    'source',
  ]);
  assert.equal(request.name, 'Campaña');
  assert.equal(request.expected_preview_fingerprint, 'f'.repeat(64));
  for (const forbidden of ['allowed_sucursal_keys', 'created_by_user_id', 'phones', 'recipients', 'recipient_ids', 'source_record_ids', 'evidence_rows']) {
    assert.equal(forbidden in request, false);
  }
});

test('Freeze requiere Preview vigente con audiencia y 409 lo invalida', () => {
  assert.equal(canFreezeCampaignV2({ preview: preview(), name: 'X', purpose: 'UNCLASSIFIED', creating: false }), true);
  assert.equal(canFreezeCampaignV2({ preview: null, name: 'X', purpose: 'UNCLASSIFIED', creating: false }), false);
  assert.equal(campaignV2FreezeErrorInvalidatesPreview(409), true);
  assert.equal(campaignV2FreezeErrorInvalidatesPreview(400), false);
});

test('drill-down mapea buckets backend y purpose patch sólo manda purpose', () => {
  assert.equal(campaignV2MetricBucket('recipients'), 'RECIPIENTS');
  assert.equal(campaignV2MetricBucket('blacklist'), 'BLACKLIST');
  assert.equal(campaignV2MetricBucket('invalid_phone'), 'INVALID_PHONE');
  assert.equal(campaignV2MetricBucket('duplicates'), 'DUPLICATES');
  assert.equal(campaignV2MetricBucket('out_of_segment'), 'OUT_OF_SEGMENT');
  assert.equal(campaignV2MetricBucket('unclassified'), 'UNCLASSIFIED');
  assert.equal(campaignV2MetricBucket('current_status_blocked'), 'CURRENT_STATUS_BLOCKED');
  assert.equal(campaignV2MetricBucket('family'), 'FAMILY');
  assert.deepEqual(campaignV2PurposePatch('REACTIVATION'), { purpose: 'REACTIVATION' });
});

test('menu V2 reemplaza Campaign V1 y no duplica submenu', () => {
  const created = withCampaignV2MenuItem([{ label: 'Tickets', path: '/main/ver-tickets', submenu: [] }]);
  const marketing = created.find(item => item.label === 'Marketing y Conversión');
  assert.deepEqual(marketing?.submenu, [CAMPAIGN_V2_MENU_ITEM]);

  const withLegacy = withCampaignV2MenuItem([
    {
      label: 'Marketing y Conversión',
      path: '/marketing/reactivation',
      submenu: [{ label: 'Campañas', path: '/marketing/reactivation' }],
    },
  ]);
  assert.equal(withLegacy[0].path, '/marketing/campaigns-v2');
  assert.deepEqual(withLegacy[0].submenu, [CAMPAIGN_V2_MENU_ITEM]);
  assert.equal(
    withLegacy[0].submenu?.some(item => item.path === '/marketing/reactivation'),
    false,
  );

  const repeated = withCampaignV2MenuItem(withLegacy);
  assert.equal(repeated, withLegacy);
});

test('ruta legacy de campañas redirige a Campaign V2 sin cargar frontend V1', () => {
  const routes = fs.readFileSync(
    path.join(process.cwd(), 'src/app/app.routes.ts'),
    'utf8',
  );

  assert.equal(routes.includes("path: 'marketing/reactivation'"), true);
  assert.equal(routes.includes("redirectTo: 'marketing/campaigns-v2'"), true);
  assert.equal(
    routes.includes("import('./marketing-reactivation/marketing-reactivation-page.component')"),
    false,
  );
});

test('service y page conservan contrato M5 sin auth manual y builder intacto', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.service.ts'), 'utf8');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');

  for (const fragment of [
    '/options', '/preview', '/preview-detail', '/recipients', '/purpose',
  ]) {
    assert.equal(service.includes(fragment), true, fragment);
  }
  assert.equal(service.includes('Authorization'), false);
  assert.equal(service.includes('localStorage'), false);
  assert.equal(page.includes('showsExpirationRange'), true);
  assert.equal(page.includes('this.invalidatePreview();'), true);
  assert.equal(page.includes('this.loadCampaigns(1);'), true);
  assert.equal(html.includes('Nueva campaña'), true);
  assert.equal(service.includes('/v2/broadcast'), false);
  assert.equal(html.includes('DRAFT'), false);
  assert.equal(html.includes('SENT'), false);
});

test('catalogador trabaja por tarifa única, usa categorías backend e invalida Preview', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.service.ts'), 'utf8');
  const models = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.models.ts'), 'utf8');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const pageHtml = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const classifier = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-tariff-classifier-dialog.component.ts'),
    'utf8',
  );
  const classifierHtml = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-tariff-classifier-dialog.component.html'),
    'utf8',
  );
  const layout = fs.readFileSync(path.join(root, 'src/app/layout/layout.component.ts'), 'utf8');

  assert.equal(service.includes('/tariffs/unclassified'), true);
  assert.equal(service.includes('/classification'), true);
  assert.equal(models.includes('tariff_categories: string[];'), true);
  assert.equal(service.includes('Authorization'), false);
  assert.equal(service.includes('created_by_user_id'), false);
  assert.equal(pageHtml.includes('Catalogar tarifas'), true);
  assert.equal(classifierHtml.includes('row.row_count'), true);
  assert.equal(classifierHtml.includes('Categoría'), true);
  assert.equal(classifierHtml.includes('Familia'), true);
  assert.equal(classifierHtml.includes('<input'), false);
  assert.equal(classifierHtml.includes('<mat-select'), true);
  assert.equal(classifierHtml.includes('data.categories'), true);
  assert.equal(classifier.includes('categories: string[];'), true);
  assert.equal(classifier.includes('categoria_tarifa: row.categoriaTarifa.trim()'), true);
  assert.equal(classifier.includes('audience_family: row.audienceFamily'), true);
  assert.equal(classifier.includes('created_by_user_id'), false);
  assert.equal(page.includes('categories: this.options?.tariff_categories ?? []'), true);
  assert.equal(page.includes('ref.componentInstance.classificationSaved'), true);
  assert.equal(
    page.includes("this.success = 'Clasificación guardada. Revisa la audiencia nuevamente antes de congelar.'"),
    true,
  );
  assert.equal(layout.includes("'/marketing/campaigns-v2'"), true);
});



const historicalOptions = {
  modes: ['INCLUDE', 'EXCLUDE'] as const,
  matches: ['ALL', 'ANY'] as const,
  delivery_buckets: ['SENT', 'DELIVERED', 'VIEWED'] as const,
  outcomes: ['SUCCESSFUL', 'FAILED'] as const,
  button_interaction: true,
  window_modes: ['ALL_HISTORY', 'LOOKBACK_DAYS'] as const,
  legacy_history_exclusion_supported: true,
};

function historicalState(
  mode: 'INCLUDE' | 'EXCLUDE',
  match: 'ALL' | 'ANY',
) {
  return {
    source: 'ACTIVE_MEMBERS' as const,
    audienceFamilies: ['DOMICILIADO'] as CampaignV2AudienceFamily[],
    expirationDateFrom: '',
    expirationDateTo: '',
    historyTargetingEnabled: true,
    historyMode: mode,
    historyMatch: match,
    historyDeliveryBuckets: ['VIEWED'] as CampaignV2HistoryDeliveryBucket[],
    historyOutcomes: [] as CampaignV2HistoryOutcome[],
    historyButtonInteracted: true,
    historyWindowMode: 'ALL_HISTORY' as const,
    historyLookbackDays: '',
  };
}

for (const [mode, match] of [
  ['INCLUDE', 'ALL'],
  ['INCLUDE', 'ANY'],
  ['EXCLUDE', 'ALL'],
  ['EXCLUDE', 'ANY'],
] as const) {
  test('M24 payload ' + mode + ' + ' + match + ' usa historical_targeting', () => {
    const request = buildCampaignV2AudienceRequest(historicalState(mode, match));
    assert.deepEqual(request.historical_targeting, {
      mode,
      match,
      delivery_buckets: ['VIEWED'],
      outcomes: [],
      button_interacted: true,
      lookback_days: null,
    });
    assert.equal('history_exclusion' in request, false);
  });
}

test('M24 disabled omite historical_targeting aunque conserve state residual', () => {
  const request = buildCampaignV2AudienceRequest({
    ...historicalState('INCLUDE', 'ALL'),
    historyTargetingEnabled: false,
    historyWindowMode: 'LOOKBACK_DAYS',
    historyLookbackDays: '30',
  });
  assert.equal('historical_targeting' in request, false);
  assert.equal('history_exclusion' in request, false);
});

test('M24 enabled sin condiciones es inválido y builder omite regla', () => {
  const state = {
    ...historicalState('EXCLUDE', 'ANY'),
    historyDeliveryBuckets: [] as CampaignV2HistoryDeliveryBucket[],
    historyOutcomes: [] as CampaignV2HistoryOutcome[],
    historyButtonInteracted: false,
  };
  assert.equal(isCampaignV2HistoryFilterValid(state), false);
  assert.equal(buildCampaignV2HistoricalTargeting(state), undefined);
  assert.equal(isCampaignV2AudienceValid(state), false);
});

test('M24 LOOKBACK_DAYS exige entero positivo y ALL_HISTORY envía null', () => {
  const valid = {
    ...historicalState('INCLUDE', 'ALL'),
    historyWindowMode: 'LOOKBACK_DAYS' as const,
    historyLookbackDays: '90',
  };
  assert.equal(isCampaignV2HistoryFilterValid(valid), true);
  assert.equal(buildCampaignV2HistoricalTargeting(valid)?.lookback_days, 90);

  const invalid = { ...valid, historyLookbackDays: '0' };
  assert.equal(isCampaignV2HistoryFilterValid(invalid), false);

  const allHistory = {
    ...valid,
    historyWindowMode: 'ALL_HISTORY' as const,
    historyLookbackDays: '999',
  };
  assert.equal(buildCampaignV2HistoricalTargeting(allHistory)?.lookback_days, null);

  for (const value of ['', '0', '-1', '1.5', 'NaN', 'texto']) {
    assert.equal(parseCampaignV2LookbackDays(value), null, value);
  }
});

test('M24 cualquier cambio histórico invalida Preview; name/purpose no', () => {
  for (const field of [
    'history_targeting_enabled',
    'history_mode',
    'history_match',
    'history_delivery_buckets',
    'history_outcomes',
    'history_button_interacted',
    'history_window_mode',
    'history_lookback_days',
  ] as const) {
    assert.equal(campaignV2FieldInvalidatesPreview(field), true, field);
  }
  assert.equal(campaignV2FieldInvalidatesPreview('name'), false);
  assert.equal(campaignV2FieldInvalidatesPreview('purpose'), false);
});

test('reason mapper y breakdown neutral conservan múltiples señales', () => {
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_DELIVERY_VIEWED'), 'Visto anteriormente');
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_OUTCOME_FAILED'), 'Resultado fallido anteriormente');
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_BUTTON_INTERACTION'), 'Interactuó con un botón');

  const rows = campaignV2HistoryBreakdownRows({
    history_excluded_count: 1,
    matched_by_delivery_bucket: { VIEWED: 1 },
    matched_by_outcome: { FAILED: 1 },
    matched_by_button_interaction: 1,
  });
  assert.deepEqual(rows, [
    { label: 'Vistos', count: 1 },
    { label: 'Fallidos', count: 1 },
    { label: 'Interacción con botón', count: 1 },
  ]);
  assert.equal(rows.reduce((total, row) => total + row.count, 0), 3);
});

test('M24 Freeze conserva historical_targeting y no fabrica autoridad backend', () => {
  const audience = buildCampaignV2AudienceRequest({
    ...historicalState('INCLUDE', 'ALL'),
    historyOutcomes: ['FAILED'],
    historyWindowMode: 'LOOKBACK_DAYS',
    historyLookbackDays: '90',
  });
  const request = buildCampaignV2FreezeRequest(
    audience,
    ' Histórica ',
    'REACTIVATION',
    'f'.repeat(64),
  );
  assert.deepEqual(request.historical_targeting, {
    mode: 'INCLUDE',
    match: 'ALL',
    delivery_buckets: ['VIEWED'],
    outcomes: ['FAILED'],
    button_interacted: true,
    lookback_days: 90,
  });
  assert.equal('history_exclusion' in request, false);
  for (const forbidden of [
    'excluded_phones',
    'history_rows',
    'observed_before',
    'observed_after',
  ]) {
    assert.equal(forbidden in request, false, forbidden);
  }
});

test('M24 UI consume options y no evalúa historial en Angular', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.service.ts'), 'utf8');
  const models = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.models.ts'), 'utf8');
  const logic = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.logic.ts'), 'utf8');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');

  assert.equal(models.includes("CampaignV2HistoricalTargetingMode = 'INCLUDE' | 'EXCLUDE'"), true);
  assert.equal(models.includes("CampaignV2HistoricalTargetingMatch = 'ALL' | 'ANY'"), true);
  assert.equal(models.includes("| 'HISTORY_INCLUDED'"), true);
  assert.equal(page.includes('this.options?.historical_targeting?.modes'), true);
  assert.equal(page.includes('this.options?.historical_targeting?.matches'), true);
  assert.equal(page.includes('this.options?.historical_targeting?.delivery_buckets'), true);
  assert.equal(page.includes('this.options?.historical_targeting?.window_modes'), true);
  assert.equal(html.includes('Historial de campañas'), true);
  assert.equal(html.includes('Aplicar regla histórica'), true);
  assert.equal(html.includes('<mat-label>Modo</mat-label>'), true);
  assert.equal(html.includes('<mat-label>Cumplimiento</mat-label>'), true);
  assert.equal(html.includes('<mat-label>Ventana</mat-label>'), true);
  assert.equal(logic.includes('base.history_exclusion ='), false);
  assert.equal(logic.includes('base.historical_targeting = historicalTargeting'), true);

  for (const forbidden of [
    'provider-history/lookup',
    '/provider-history',
    'rest.iventas.mx',
    'IVENTAS_CAMPAIGNS_API_KEY',
    'Authorization',
    'localStorage',
  ]) {
    assert.equal(service.includes(forbidden), false, forbidden);
  }
});

test('M24 Preview Detail helpers cubren decisión/match/reasons y legacy fallback', () => {
  for (const [decision, matched, decisionLabel, matchedLabel] of [
    ['INCLUDED', true, 'Incluido', 'Sí'],
    ['INCLUDED', false, 'Incluido', 'No'],
    ['EXCLUDED', true, 'Excluido', 'Sí'],
    ['EXCLUDED', false, 'Excluido', 'No'],
  ] as const) {
    assert.equal(campaignV2HistoryDecisionLabel(decision), decisionLabel);
    assert.equal(campaignV2HistoryMatchedLabel(matched), matchedLabel);
  }

  assert.equal(
    campaignV2HistoryReasonsLabel(
      ['HISTORY_DELIVERY_VIEWED', 'HISTORY_BUTTON_INTERACTION'],
      undefined,
    ),
    'Visto anteriormente, Interactuó con un botón',
  );
  assert.equal(
    campaignV2HistoryReasonsLabel([], undefined),
    'Sin señales seleccionadas observadas',
  );
  assert.equal(
    campaignV2HistoryReasonsLabel(
      undefined,
      ['HISTORY_OUTCOME_FAILED'],
    ),
    'Resultado fallido anteriormente',
  );
});

test('M24 Preview Detail muestra buckets neutrales y fallback legacy', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const detail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.ts'),
    'utf8',
  );
  const detailHtml = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(detail.includes("HISTORY_INCLUDED: 'Incluidos por regla histórica'"), true);
  assert.equal(detail.includes("HISTORY_EXCLUDED: 'Excluidos por regla histórica'"), true);
  assert.equal(detail.includes('campaignV2HistoryReasonsLabel('), true);
  assert.equal(detailHtml.includes('historyDecisionLabel(row.history_decision)'), true);
  assert.equal(detailHtml.includes('historyMatchedLabel(row.history_matched)'), true);
  assert.equal(detailHtml.includes('historyReasonsLabel(row)'), true);
});

test('M24 frozen detail separa canónico y legacy sin reinterpretar', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const detail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );

  assert.equal(detail.includes('definition.filters.historical_targeting'), true);
  assert.equal(detail.includes("label: 'Historial de campañas · Modo'"), true);
  assert.equal(detail.includes("label: 'Historial de campañas · Cumplimiento'"), true);
  assert.equal(detail.includes("label: 'Historial de campañas · Condiciones'"), true);
  assert.equal(detail.includes("label: 'Historial de campañas · Ventana'"), true);
  assert.equal(detail.includes('else if (definition.filters.history_exclusion)'), true);
  assert.equal(detail.includes("label: 'Exclusión histórica'"), true);
  assert.equal(detail.includes("label: 'Ventana histórica legacy'"), true);
});

test('M24 Funnel usa contract options y envía sólo filtros aplicables + targeting', () => {
  const options: CampaignV2OptionsResponse = {
    sources: ['EXPIRED_MEMBERS', 'ACTIVE_MEMBERS', 'FUNNEL_PORTFOLIO'],
    source_filters: {
      FUNNEL_PORTFOLIO: {
        required: ['funnel_month', 'funnel_cutoff_date'],
        not_applicable: [
          'audience_families',
          'expiration_date_from',
          'expiration_date_to',
          'tarifa',
          'categoria_tarifa',
        ],
        cutoff_policy: 'EXACT_COMPLETE',
      },
    },
    selectable_audience_families: allFamilies,
    non_selectable_classifications: ['MES', 'OUT_OF_SEGMENT', 'UNCLASSIFIED'],
    purposes: ['NEW_SALE', 'REACTIVATION', 'ACTIVE_MEMBERS', 'UNCLASSIFIED'],
    historical_targeting: {
      modes: [...historicalOptions.modes],
      matches: [...historicalOptions.matches],
      delivery_buckets: [...historicalOptions.delivery_buckets],
      outcomes: [...historicalOptions.outcomes],
      button_interaction: true,
      window_modes: [...historicalOptions.window_modes],
      legacy_history_exclusion_supported: true,
    },
    tariff_categories: [],
    scope: { is_global: true, allowed_sucursal_keys: null },
  };

  const base = {
    ...historicalState('INCLUDE', 'ALL'),
    source: 'FUNNEL_PORTFOLIO' as const,
    funnelMonth: '2026-09',
    funnelCutoffDate: '2026-09-30',
  };

  assert.equal(isCampaignV2AudienceValid({ ...base, funnelMonth: '' }, options), false);
  assert.equal(isCampaignV2AudienceValid({ ...base, funnelCutoffDate: '' }, options), false);
  assert.equal(isCampaignV2AudienceValid(base, options), true);

  const request = buildCampaignV2AudienceRequest(base, options);
  assert.deepEqual(request, {
    source: 'FUNNEL_PORTFOLIO',
    funnel_month: '2026-09',
    funnel_cutoff_date: '2026-09-30',
    historical_targeting: {
      mode: 'INCLUDE',
      match: 'ALL',
      delivery_buckets: ['VIEWED'],
      outcomes: [],
      button_interacted: true,
      lookback_days: null,
    },
  });
  assert.equal('history_exclusion' in request, false);
  assert.equal('audience_families' in request, false);
  assert.equal('expiration_date_from' in request, false);
  assert.equal('expiration_date_to' in request, false);
});

test('M24 buckets e invalidación Funnel conservan M20', () => {
  for (const field of ['source', 'funnel_month', 'funnel_cutoff_date'] as const) {
    assert.equal(campaignV2FieldInvalidatesPreview(field), true, field);
  }
  assert.equal(campaignV2MetricBucket('history_included'), 'HISTORY_INCLUDED');
  assert.equal(campaignV2MetricBucket('history_excluded'), 'HISTORY_EXCLUDED');
  assert.equal(campaignV2MetricBucket('funnel_candidates'), 'FUNNEL_CANDIDATES');
  assert.equal(campaignV2MetricBucket('funnel_buyer_excluded'), 'FUNNEL_BUYER_EXCLUDED');
  assert.equal(campaignV2MetricBucket('active_member_suppression'), 'ACTIVE_MEMBER_SUPPRESSION');
});

test('M24 UI Funnel conserva source-specific + Historical Targeting común', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const campaignDetail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );
  const recipientHtml = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-recipient-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(page.includes("FUNNEL_PORTFOLIO: 'Cartera Funnel / Venta Nueva'"), true);
  assert.equal(html.includes('Mes Funnel'), true);
  assert.equal(html.includes('<mat-label>Corte Funnel</mat-label>'), false);
  assert.equal(page.includes('funnelService.getDashboard(month)'), true);
  assert.equal(page.includes('this.funnelCutoffDate.setValue(selected, { emitEvent: false });'), true);
  assert.equal(html.includes('Historial de campañas'), true);
  assert.equal(page.includes("label: 'Coincidieron con historial'"), true);
  assert.equal(page.includes("metric: 'history_included'"), true);
  assert.equal(page.includes("metric: 'history_excluded'"), true);
  assert.equal(campaignDetail.includes('definition.filters.audience_families?.length'), true);
  assert.equal(recipientHtml.includes("recipient.member_name || '—'"), true);
  assert.equal(recipientHtml.includes("recipient.tarifa_raw || '—'"), true);
});


test('M30 reporting query vacío omite params y fechas usan límites locales con offset', () => {
  const empty = buildCampaignV2ReportingQuery({
    observedFromDate: '',
    observedToDate: '',
    purpose: '',
    source: '',
    provider: '   ',
    snapshotStatus: '',
  });
  assert.deepEqual(empty, {});

  const fromOnly = buildCampaignV2ReportingQuery({
    observedFromDate: '2026-10-03',
    observedToDate: '',
    purpose: '',
    source: '',
    provider: '',
    snapshotStatus: '',
  });
  assert.match(
    fromOnly.observed_from ?? '',
    /^2026-10-03T00:00:00\.000[+-]\d{2}:\d{2}$/,
  );

  const toOnly = buildCampaignV2ReportingQuery({
    observedFromDate: '',
    observedToDate: '2026-10-03',
    purpose: '',
    source: '',
    provider: '',
    snapshotStatus: '',
  });
  assert.match(
    toOnly.observed_to ?? '',
    /^2026-10-03T23:59:59\.999[+-]\d{2}:\d{2}$/,
  );
});

test('M30 reporting query incluye filtros v1 y omite vacíos', () => {
  const query = buildCampaignV2ReportingQuery({
    observedFromDate: '2026-10-01',
    observedToDate: '2026-10-03',
    purpose: 'REACTIVATION',
    source: 'EXPIRED_MEMBERS',
    provider: ' IVENTAS ',
    snapshotStatus: 'WITH_SNAPSHOT',
  });
  assert.equal(query.purpose, 'REACTIVATION');
  assert.equal(query.source, 'EXPIRED_MEMBERS');
  assert.equal(query.provider, 'IVENTAS');
  assert.equal(query.snapshot_status, 'WITH_SNAPSHOT');
  assert.match(query.observed_from ?? '', /T00:00:00\.000[+-]\d{2}:\d{2}$/);
  assert.match(query.observed_to ?? '', /T23:59:59\.999[+-]\d{2}:\d{2}$/);
});

test('M30 reporting validation bloquea from posterior a to e inválidos', () => {
  const base = {
    purpose: '' as const,
    source: '' as const,
    provider: '',
    snapshotStatus: '' as const,
  };
  assert.equal(
    campaignV2ReportingFilterValidation({
      ...base,
      observedFromDate: '2026-10-04',
      observedToDate: '2026-10-03',
    }),
    '"Observado desde" no puede ser posterior a "Observado hasta".',
  );
  assert.equal(
    campaignV2ReportingFilterValidation({
      ...base,
      observedFromDate: '2026-02-30',
      observedToDate: '',
    }),
    'La fecha "Observado desde" no es válida.',
  );
  assert.equal(
    campaignV2ReportingFilterValidation({
      ...base,
      observedFromDate: '2026-10-01',
      observedToDate: '2026-10-03',
    }),
    null,
  );
});

test('M30 helpers visuales no recalculan KPIs ni convierten null en cero', () => {
  assert.equal(campaignV2ReportingPercent(null), '—');
  assert.equal(campaignV2ReportingPercent(0), '0.00%');
  assert.equal(campaignV2ReportingPercent(0.753), '75.30%');
  assert.equal(campaignV2ReportingValue(null), '—');
  assert.equal(campaignV2ReportingValue(0), '0');
  assert.equal(campaignV2ReportingBranchLabel('UNKNOWN'), 'Sin atribución');
  assert.equal(campaignV2ReportingBranchLabel('MEXICALI'), 'MEXICALI');
  assert.equal(campaignV2ReportingAudienceFamilyLabel('UNKNOWN'), 'Sin clasificación');
  assert.equal(campaignV2ReportingAudienceFamilyLabel('DOMICILIADO'), 'DOMICILIADO');
  assert.equal(campaignV2ReportingCostLabel('unavailable'), 'Costos no disponibles');
  assert.equal(
    campaignV2ReportingSnapshotLabel({
      snapshot_id: null,
      latest_observed_at: null,
      analytics_status: null,
    }),
    'Sin observación',
  );
  assert.equal(
    campaignV2ReportingSnapshotLabel({
      snapshot_id: 9,
      latest_observed_at: '2026-10-03T20:00:00+00:00',
      analytics_status: 'ok',
    }),
    'ok',
  );
});

test('M30 service consume individual, consolidado y export con builder compartido', () => {
  const root = process.cwd();
  const service = fs.readFileSync(
    path.join(root, 'src/app/marketing-campaign-v2/marketing-campaign-v2.service.ts'),
    'utf8',
  );

  assert.equal(service.includes('getCampaignReport(campaignId: number)'), true);
  assert.equal(service.includes('${this.apiUrl}/${campaignId}/report'), true);
  assert.equal(service.includes('getReporting('), true);
  assert.equal(service.includes('${this.apiUrl}/reporting'), true);
  assert.equal(service.includes('exportReporting(filters:'), true);
  assert.equal(service.includes('exportCampaignReport(campaignId: number)'), true);
  assert.equal(service.includes("responseType: 'blob'"), true);
  assert.equal(service.includes("new HttpParams().set('campaign_id', String(campaignId))"), true);
  assert.equal(
    (service.match(/this\.buildReportingParams\(filters\)/g) ?? []).length >= 2,
    true,
  );
  assert.equal(service.includes('Authorization'), false);
  assert.equal(service.includes('localStorage'), false);
  assert.equal(service.includes('rest.iventas.mx'), false);
});

test('lista negra V2 tiene administración global, import incremental y métrica auditable', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2.service.ts'),
    'utf8',
  );
  const component = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.ts'),
    'utf8',
  );
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.html'),
    'utf8',
  );

  assert.equal(service.includes('getBlacklistSummary()'), true);
  assert.equal(service.includes('importBlacklist(file: File)'), true);
  assert.equal(service.includes("formData.append('file', file, file.name)"), true);
  assert.equal(service.includes('exportBlacklist()'), true);
  assert.equal(service.includes('${this.apiUrl}/blacklist/import'), true);
  assert.equal(service.includes('${this.apiUrl}/blacklist/export'), true);

  assert.equal(component.includes('get canManageBlacklist(): boolean'), true);
  assert.equal(component.includes('this.options?.scope.is_global'), true);
  assert.equal(component.includes('this.invalidatePreview();'), true);
  assert.equal(component.includes("campaignV2DownloadBlob(blob, 'campaign_v2_lista_negra.xlsx')"), true);

  assert.equal(html.includes('Lista negra global'), true);
  assert.equal(html.includes('Importar Excel'), true);
  assert.equal(html.includes('Descargar lista negra'), true);
  assert.equal(html.includes("openMetric('blacklist', preview.blacklist_excluded_count || 0)"), true);
  assert.equal(html.includes('Bloqueados globalmente'), true);
});

test('Campaign V2 separa cohorte congelada de lista para envío', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2.service.ts'),
    'utf8',
  );
  const detail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(service.includes('exportCampaignDeliveryPackage(campaignId: number)'), true);
  assert.equal(service.includes('${this.apiUrl}/${campaignId}/export-package'), true);
  assert.equal(service.includes('exportCampaignSendablePackage(campaignId: number)'), true);
  assert.equal(service.includes('${this.apiUrl}/${campaignId}/sendable-export-package'), true);

  assert.equal(detail.includes('this.service.exportCampaignDeliveryPackage(this.data.campaignId)'), true);
  assert.equal(detail.includes('this.service.exportCampaignSendablePackage(this.data.campaignId)'), true);
  assert.equal(detail.includes("'COHORTE_CONGELADA'"), true);
  assert.equal(detail.includes("'LISTA_ENVIO'"), true);
  assert.equal(detail.includes("blob.type === 'application/zip' ? 'zip' : 'xlsx'"), true);

  assert.equal(html.includes('Descargar lista original'), true);
  assert.equal(html.includes('Descargar lista para envío'), true);
  assert.equal(html.includes('Lista original: contactos guardados al crear la campaña.'), true);
  assert.equal(html.includes('Lista para envío: la misma lista menos los contactos excluidos actualmente'), true);
});

test('M33 UI polish da jerarquía al constructor sin cambiar su contrato', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const page = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.html'),
    'utf8',
  );
  const css = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.css'),
    'utf8',
  );
  const component = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.ts'),
    'utf8',
  );

  for (const label of [
    'Audiencia',
    'Preview',
    'Congelar',
    'Descargar',
    'Revisar audiencia',
    'Listo para congelar',
  ]) {
    assert.equal(page.includes(label), true, label);
  }
  assert.equal(page.includes('class="workflow-strip"'), true);
  assert.equal(page.includes('class="family-choice"'), true);
  assert.equal(page.includes('<span class="scope-inline">{{ scopeLabel }}</span>'), false);
  assert.equal(css.includes('grid-template-columns:minmax(0,1fr) 360px'), true);
  assert.equal(css.includes('.family-choice.selected'), true);
  assert.equal(component.includes('lastFreezeCompleted = false'), true);
});

test('Adeudo mínimo conserva string en el FormControl y evita NumberValueAccessor', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.html'),
    'utf8',
  );

  assert.equal(html.includes('<mat-label>Adeudo mínimo</mat-label>'), true);
  assert.equal(html.includes('type="number"'), false);
  assert.equal(html.includes('type="text"'), true);
  assert.equal(html.includes('inputmode="decimal"'), true);
  assert.equal(html.includes('[formControl]="adeudoMin"'), true);
});

test('Socios vencidos usa el selector compartido de rango de fechas', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.html'),
    'utf8',
  );
  const component = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-page.component.ts'),
    'utf8',
  );

  assert.equal(html.includes('<app-suite-date-range-selector'), true);
  assert.equal(html.includes('label="Periodo de vencimiento"'), true);
  assert.equal(html.includes('type="date" [formControl]="expirationDateFrom"'), false);
  assert.equal(html.includes('type="date" [formControl]="expirationDateTo"'), false);
  assert.equal(component.includes('DateRangeSelectorComponent'), true);
  assert.equal(component.includes('onExpirationDateFromChange(value: string)'), true);
  assert.equal(component.includes('onExpirationDateToChange(value: string)'), true);
});

test('M30 UI consolidado pinta backend summary y separa raw provider', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');

  for (const label of [
    'Resultados de todas las campañas',
    'Actualizado desde',
    'Actualizado hasta',
    'Objetivo de campaña',
    'Servicio de envío',
    'Disponibilidad de resultados',
    'Exposiciones de destinatarios',
    'Última observación de Suite',
    'Datos originales de iVentas (detalle técnico)',
    'Por sucursal',
    'Por familia de audiencia',
    'Contactos que respondieron según iVentas',
    'Respuestas de texto agregadas',
    'Exposiciones con interacción de botón',
  ]) {
    assert.equal(html.includes(label), true, label);
  }
  assert.equal(page.includes('this.service.getReporting(filters)'), true);
  assert.equal(page.includes('this.service.exportReporting(filters)'), true);
  assert.equal(page.includes('const filters = this.reportingQuery();'), true);
  assert.equal(html.includes('report.summary.rates.successful_rate'), true);
  assert.equal(html.includes('report.summary.rates.reach_rate'), true);
  assert.equal(html.includes('report.summary.rates.read_rate'), true);
  assert.equal(html.includes('report.summary.rates.failure_rate'), true);
  assert.equal(html.includes('report.summary.coverage.status_coverage_rate'), true);
  assert.equal(html.includes('report.summary.total_recipients'), true);
  assert.equal(html.includes('reportingCostLabel(report.summary.cost.status)'), true);
  assert.equal(html.includes('Personas únicas'), false);
});

test('M30 Campaign Detail carga reporting lazy, evolution y export individual', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const detail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(detail.includes('this.service.getCampaignReport(this.data.campaignId)'), true);
  assert.equal(detail.includes('this.service.exportCampaignReport(this.data.campaignId)'), true);
  assert.equal(html.includes('Resultados de la campaña'), true);
  assert.equal(html.includes('Cargar resultados'), true);
  assert.equal(html.includes('Exportar reporte'), true);
  assert.equal(
    html.includes('Aún no hay observaciones persistidas para esta campaña.'),
    true,
  );
  assert.equal(html.includes('Datos originales de iVentas (detalle técnico)'), true);
  assert.equal(html.includes('Evolución observada por Suite'), true);
  assert.equal(html.includes('report.evolution'), true);
  assert.equal(html.includes('report.provider_raw'), true);
  assert.equal(html.includes('reportingPercent(report.rates.read_rate)'), true);
});

test('M30 modelos Reporting están tipados explícitamente', () => {
  const root = process.cwd();
  const models = fs.readFileSync(
    path.join(root, 'src/app/marketing-campaign-v2/marketing-campaign-v2.models.ts'),
    'utf8',
  );
  for (const name of [
    'CampaignV2ReportingNormalized',
    'CampaignV2ReportingRates',
    'CampaignV2ReportingCoverage',
    'CampaignV2ReportingProviderRaw',
    'CampaignV2ReportingInteractions',
    'CampaignV2ReportingCost',
    'CampaignV2ReportingObservation',
    'CampaignV2ReportingCampaignIdentity',
    'CampaignV2IndividualReport',
    'CampaignV2ConsolidatedCampaignRow',
    'CampaignV2ConsolidatedSummary',
    'CampaignV2ReportingBreakdownRow',
    'CampaignV2ConsolidatedReport',
    'CampaignV2ReportingFilters',
    'CampaignV2ReportingSnapshotStatus',
  ]) {
    assert.equal(models.includes(`interface ${name}`) || models.includes(`type ${name}`), true, name);
  }
  assert.equal(
    models.includes('provider_raw: CampaignV2ReportingProviderRaw | null;'),
    true,
  );
});


test('Adeudo mínimo sólo aplica a vencidos, es inclusivo en contrato y vacío se omite', () => {
  const base = {
    source: 'EXPIRED_MEMBERS' as const,
    audienceFamilies: ['DOMICILIADO'] as CampaignV2AudienceFamily[],
    expirationDateFrom: '2020-12-01',
    expirationDateTo: '2026-09-30',
    adeudoMin: '3000',
  };
  const request = buildCampaignV2AudienceRequest(base);
  assert.equal(request.adeudo_min, '3000');
  assert.equal(campaignV2FieldInvalidatesPreview('adeudo_min'), true);
  assert.equal(isCampaignV2AdeudoMinValid('3000'), true);
  assert.equal(isCampaignV2AdeudoMinValid('0'), true);
  assert.equal(isCampaignV2AdeudoMinValid('-1'), false);
  assert.equal(isCampaignV2AudienceValid(base), true);
  assert.equal(isCampaignV2AudienceValid({ ...base, adeudoMin: '-1' }), false);

  const empty = buildCampaignV2AudienceRequest({ ...base, adeudoMin: '' });
  assert.equal('adeudo_min' in empty, false);

  const active = buildCampaignV2AudienceRequest({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '',
    expirationDateTo: '',
    adeudoMin: '3000',
  });
  assert.equal('adeudo_min' in active, false);

  const funnel = buildCampaignV2AudienceRequest({
    source: 'FUNNEL_PORTFOLIO',
    audienceFamilies: [],
    expirationDateFrom: '',
    expirationDateTo: '',
    adeudoMin: '3000',
    funnelMonth: '2026-07',
    funnelCutoffDate: '2026-07-31',
  });
  assert.equal('adeudo_min' in funnel, false);
});

test('F3-M2 submit service sólo envía template_id y fingerprint esperado', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2.service.ts'),
    'utf8',
  );
  const start = service.indexOf('submitCampaign(');
  const end = service.indexOf('exportCampaignDeliveryPackage(', start);
  const source = service.slice(start, end);

  assert.equal(start >= 0, true);
  assert.equal(source.includes('template_id: templateId'), true);
  assert.equal(
    source.includes('expected_dispatch_fingerprint: expectedDispatchFingerprint'),
    true,
  );
  for (const forbidden of [
    'phone_mx10',
    'phones',
    'provider_channel_id',
    'channelId',
    'vars',
    'urlVars',
    'sendAt',
    'provider_campaign_id',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test('F3-M2 detalle exige preflight ready, gate backend y confirmación explícita', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const component = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(component.includes('state.enabled'), true);
  assert.equal(component.includes('state.can_send'), true);
  assert.equal(component.includes("state.status === 'NOT_STARTED'"), true);
  assert.equal(component.includes('MarketingCampaignV2SubmitConfirmDialogComponent'), true);
  assert.equal(component.includes('plan.dispatch_fingerprint'), true);
  assert.equal(component.includes('this.service.submitCampaign('), true);
  assert.equal(html.includes('Envío directo (método anterior)'), true);
  assert.equal(html.includes('Enviar mensajes ahora'), true);
  assert.equal(html.includes('*ngIf="plan.submission.can_send"'), true);
  assert.equal(html.includes('[disabled]="!canSubmitDispatch"'), true);
});

test('F3-M2 confirmación muestra impacto real y no ofrece scheduling', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-submit-confirm-dialog.component.html'),
    'utf8',
  );

  for (const label of [
    'Esta acción enviará mensajes reales de WhatsApp a los destinatarios indicados.',
    'Contactos guardados',
    'Excluidos por lista negra',
    'Destinatarios de este envío',
    'Lotes de envío',
    'Modo',
    'Inmediato',
    'Referencia de seguridad aprobada',
    'Sí, enviar mensajes ahora',
  ]) {
    assert.equal(html.includes(label), true, label);
  }
  assert.equal(html.includes('sendAt'), false);
  assert.equal(html.includes('Programar'), false);
});

test('F3-M2 conserva ambas descargas manuales después de agregar submit', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const html = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.html'),
    'utf8',
  );
  const component = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );

  assert.equal(html.includes('Descargar lista original'), true);
  assert.equal(html.includes('Descargar lista para envío'), true);
  assert.equal(component.includes('exportDeliveryPackage()'), true);
  assert.equal(component.includes('exportSendablePackage()'), true);
});


test('Winback deuda en intervalos cero, bajo y alto y control de rango inverso', () => {
  const base = {
    source: 'EXPIRED_MEMBERS' as const,
    audienceFamilies: ['DOMICILIADO' as const],
    expirationDateFrom: '2020-01-01',
    expirationDateTo: '2026-09-30',
  };
  assert.equal(
    buildCampaignV2AudienceRequest({ ...base, adeudoMin: '0', adeudoMax: '0' }).adeudo_max,
    '0',
  );
  assert.equal(
    buildCampaignV2AudienceRequest({ ...base, adeudoMin: '0.01', adeudoMax: '2999.99' }).adeudo_max,
    '2999.99',
  );
  assert.equal(
    buildCampaignV2AudienceRequest({ ...base, adeudoMin: '3000' }).adeudo_max,
    undefined,
  );
  assert.equal(isCampaignV2AudienceValid({ ...base, adeudoMin: '3000', adeudoMax: '2999.99' }), false);
  assert.equal(isCampaignV2AudienceValid({ ...base, adeudoMin: '0', adeudoMax: '0' }), true);
  assert.equal(isCampaignV2AudienceValid({ ...base, adeudoMax: '-1' }), false);
});


test('Winback scope comercial viaja en preview/freeze y no amplía permisos de frontend', () => {
  const base = {
    source: 'EXPIRED_MEMBERS' as const,
    audienceFamilies: ['DOMICILIADO' as const],
    expirationDateFrom: '2020-01-01',
    expirationDateTo: '2026-09-30',
  };
  const opts = { branch_options: ['BRANCH A', 'BRANCH B'] } as CampaignV2OptionsResponse;
  assert.deepEqual(
    buildCampaignV2AudienceRequest({ ...base, branchFilterMode: 'INCLUDE', branchKeys: ['BRANCH A'] }).selected_sucursal_keys,
    ['BRANCH A'],
  );
  assert.deepEqual(
    buildCampaignV2AudienceRequest({ ...base, branchFilterMode: 'EXCLUDE', branchKeys: ['BRANCH B'] }).excluded_sucursal_keys,
    ['BRANCH B'],
  );
  assert.equal(
    isCampaignV2AudienceValid({ ...base, branchFilterMode: 'INCLUDE', branchKeys: [] }, opts),
    false,
  );
  assert.equal(
    isCampaignV2AudienceValid({ ...base, branchFilterMode: 'INCLUDE', branchKeys: ['FORGED'] }, opts),
    false,
  );
});

test('Issue #856 Phase A: template requires explicit compatible active channels', () => {
  const draft: DispatchTemplateDraft = {
    templateName: 'reactivacion_aprobada',
    label: 'Reactivación',
    purposes: ['REACTIVATION'],
    channelIds: ['channel-1'],
    activeChannelIds: ['channel-1', 'channel-2'],
    variables: ['branch'],
    fileUrl: '',
  };
  assert.equal(isDispatchTemplateDraftValid(draft), true);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, channelIds: [] }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, channelIds: ['inactive'] }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, channelIds: ['channel-1', 'channel-1'] }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, channelIds: ['channel-1', 'channel-2'] }), true);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, templateName: '   ' }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, purposes: [] }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, variables: ['arbitrary_browser_var'] }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, fileUrl: 'http://example.org/file.png' }), false);
  assert.equal(isDispatchTemplateDraftValid({ ...draft, fileUrl: 'https://media.example.org/file.png' }), true);
});

test('Issue #856/B preliminary MXN range uses versioned rates with full channel coverage', () => {
  const template = {
    id: 10, provider: 'IVENTAS', template_name: 'synthetic',
    label: 'Synthetic', is_active: true, purposes: ['REACTIVATION' as const],
    variables: {}, compatible_channel_ids: ['channel-1', 'channel-2'],
    metadata: {}, created_at: null, updated_at: null,
  };
  const rates = [
    { revision_id: 1, template_id: 10, provider_channel_id: 'channel-1',
      unit_cost_mxn: '0.750000', source_reference: 'QA-01',
      valid_from: '2026-10-12T08:00:00Z', created_at: '2026-10-12T08:00:00Z' },
    { revision_id: 2, template_id: 10, provider_channel_id: 'channel-2',
      unit_cost_mxn: '1.250000', source_reference: 'QA-02',
      valid_from: '2026-10-12T08:00:00Z', created_at: '2026-10-12T08:00:00Z' },
  ];
  const now = '2026-10-13T16:00:00Z';
  const quote = campaignV2IndicativeBudget(template, rates, 100, now);
  assert.equal(quote.status, 'RANGE');
  assert.equal(quote.min_mxn, '75.00');
  assert.equal(quote.max_mxn, '125.00');
  const missing = campaignV2IndicativeBudget(template, rates.slice(0,1), 100, now);
  assert.equal(missing.status, 'INCOMPLETE');
  assert.equal(missing.min_mxn, null);
  assert.equal(missing.max_mxn, null);
  assert.equal(missing.missing_channels, 1);
  const future = campaignV2IndicativeBudget(template,
    [{ ...rates[0], valid_from: '2026-11-01T00:00:00Z' }, rates[1]],
    100, now);
  assert.equal(future.status, 'INCOMPLETE');
  assert.equal(campaignV2IndicativeBudget(
    { ...template, compatible_channel_ids: [] }, rates, 100, now,
  ).status, 'UNPRICED');
});


test('Issue 856: costo MXN y evidencia Meta aceptan numeros validos sin escapes dobles', () => {
  for (const price of ['0.85', '0.850000', '1', '1000', ' 12.50 ']) {
    assert.equal(isCampaignV2MxnUnitCostValid(price), true, price);
  }
  for (const price of ['', '0', '-1', '1.1234567', '1e3', '1000.01', 'abc']) {
    assert.equal(isCampaignV2MxnUnitCostValid(price), false, price);
  }
  for (const nominal of ['', '250', '100000']) {
    assert.equal(isCampaignV2NominalLimitValid(nominal), true, nominal);
  }
  for (const nominal of ['0', '-1', '2.0', '9007199254740992']) {
    assert.equal(isCampaignV2NominalLimitValid(nominal), false, nominal);
  }
  for (const remaining of ['0', '250', '10000']) {
    assert.equal(isCampaignV2RemainingCountValid(remaining), true, remaining);
  }
  for (const remaining of ['', '-1', '2.5', '250x', '9007199254740992']) {
    assert.equal(isCampaignV2RemainingCountValid(remaining), false, remaining);
  }
  assert.equal(isCampaignV2ZonedDateString('2026-10-13T09:00:00-07:00'), true);
  assert.equal(isCampaignV2ZonedDateString('2026-10-13T16:00:00Z'), true);
  assert.equal(isCampaignV2ZonedDateString('2026-10-13T09:00:00'), false);
});

test('Issue 856: administracion usa campo MDC acotado y editores progresivos', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const page = fs.readFileSync(path.join(root, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const templates = fs.readFileSync(path.join(root, 'marketing-campaign-v2-dispatch-admin-dialog.component.html'), 'utf8');
  const quotas = fs.readFileSync(path.join(root, 'marketing-campaign-v2-quota-admin-dialog.component.html'), 'utf8');
  const styles = fs.readFileSync(path.join(process.cwd(), 'src/styles.scss'), 'utf8');
  assert.equal(page.split("panelClass: 'campaign-v2-admin-dialog'").length - 1, 5);
  assert.equal(page.includes('MarketingCampaignV2ExcelDialogComponent'), true);
  assert.equal(page.includes('openExcelImport(): void'), true);
  assert.equal(styles.includes('.cdk-overlay-container .campaign-v2-admin-dialog'), true);
  assert.equal(templates.includes('*ngIf="showTemplateEditor"'), true);
  assert.equal(templates.includes('*ngIf="showBudgetEditor"'), true);
  assert.equal(quotas.includes('*ngIf="showPolicyForm"'), true);
  assert.equal(quotas.includes('*ngIf="showCapacityForm"'), true);
});

test('readiness for 26 channels does not require manual cap/portfolio/price', () => {
  const template = { id: 1, is_active: true, compatible_channel_ids: ['ch-1', 'ch-2'] } as CampaignV2DispatchTemplate;
  const bindings = [
    { id: 1, provider_channel_id: 'ch-1', sucursal_canon: 'AZAHARES_CUL', is_active: true, is_default: true },
    { id: 2, provider_channel_id: 'ch-2', sucursal_canon: 'TEC_MXL', is_active: true, is_default: true },
  ] as CampaignV2ChannelBinding[];
  const policies = [
    { revision_id: 11, provider_channel_id: 'ch-1', portfolio_key: 'unverified-1',
      account_key: 'account', operational_channel_cap: 100,
      operational_portfolio_cap: 200, valid_from: '2026-10-14T01:00:00Z' },
    { revision_id: 12, provider_channel_id: 'ch-2', portfolio_key: 'unverified-1',
      account_key: 'account', operational_channel_cap: 100,
      operational_portfolio_cap: 200, valid_from: '2026-10-14T01:00:00Z' },
  ] as CampaignV2QuotaPolicyRevision[];
  const rates = [
    { revision_id: 21, template_id: 1, provider_channel_id: 'ch-1',
      unit_cost_mxn: '1.001854', source_reference: 'FX documentation',
      valid_from: '2026-10-14T01:00:00Z' },
  ] as CampaignV2BudgetRateRevision[];
  const rows = campaignV2BuildReadinessRows(template, bindings, policies, rates);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].configured, true);
  assert.equal(rows[0].portfolioVerified, false);
  assert.equal(rows[1].configured, true);
  assert.equal(rows[1].issues.includes('Tarifa MXN pendiente'), false);
  assert.equal(rows[1].unitCostMxn, null);
  assert.equal(campaignV2BuildReadinessRows(template, bindings, [], []).every(r => r.configured), true);
  policies[1].operational_portfolio_cap = 300;
  assert.equal(campaignV2BuildReadinessRows(template, bindings, policies, rates)[0].configured, true);
  assert.equal(campaignV2BuildReadinessRows(null, bindings, policies, rates)[0].templateCompatible, false);
});

test('operator readiness UI uses catalog reads and has no provider send action', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ui = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.html'), 'utf8');
  assert.ok(ui.includes('forkJoin('));
  assert.ok(ui.includes('listQuotaEvidence()'));
  assert.ok(html.includes('Consultar políticas históricas'));
  assert.equal(ui.includes('submitCampaign('), false);
  assert.equal(ui.includes('registerQuotaPolicy('), false);
});


test('B1 catálogo de Business IDs es independiente de políticas, WABA y envíos', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ui = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.html'), 'utf8');
  const service = fs.readFileSync(path.join(root, 'marketing-campaign-v2.service.ts'), 'utf8');
  assert.ok(service.includes('/dispatch/portfolio-references'));
  assert.ok(ui.includes('listPortfolioReferences()'));
  assert.ok(ui.includes('registerPortfolioReference('));
  assert.ok(html.includes('Registrar referencia sin verificar'));
  assert.ok(html.includes('NO VERIFICADO'));
  assert.ok(html.includes('Canales verificados: 0'));
  assert.equal(ui.includes('submitCampaign('), false);
  assert.equal(ui.includes('registerQuotaPolicy('), false);
  assert.equal(html.includes('(click)="submitCampaign()"'), false);
});


test('B2 evidence modal requires confirmation and never changes operational quota or sends', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ts = fs.readFileSync(path.join(root, 'marketing-campaign-v2-channel-portfolio-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-channel-portfolio-dialog.component.html'), 'utf8');
  const readiness = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.ts'), 'utf8');
  const template = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.html'), 'utf8');
  assert.ok(ts.includes('expected_revision_id: expectedRevision'));
  assert.ok(ts.includes('this.acknowledgment.value'));
  assert.ok(ts.includes('listChannelPortfolioEvidence()'));
  assert.ok(ts.includes("save(state: 'DECLARED' | 'WITHDRAWN')"));
  assert.ok(html.includes('Guardar información del canal'));
  assert.ok(html.includes('Quitar relación del canal'));
  assert.ok(ts.includes('DECLARADA · NO VERIFICADA'));
  assert.ok(template.includes('Empresa Meta registrada (sin verificar)'));
  assert.ok(template.includes('Control de envíos Suite'));
  assert.ok(readiness.includes('mappingBusinessId'));
  assert.equal(ts.includes('submitCampaign('), false);
  assert.equal(ts.includes('registerQuotaPolicy('), false);
  assert.equal(ts.includes('approveDispatch('), false);
});


test('B3 documentary triage uses a read-only API and never claims verified Meta membership', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ui = fs.readFileSync(path.join(root, 'marketing-campaign-v2-portfolio-review-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-portfolio-review-dialog.component.html'), 'utf8');
  const editor = fs.readFileSync(path.join(root, 'marketing-campaign-v2-channel-portfolio-dialog.component.ts'), 'utf8');
  const service = fs.readFileSync(path.join(root, 'marketing-campaign-v2.service.ts'), 'utf8');
  const entry = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.html'), 'utf8');
  assert.ok(service.includes('/dispatch/portfolio-review'));
  assert.ok(ui.includes('listPortfolioReview()'));
  assert.ok(ui.includes('DOCUMENTED_UNVERIFIED'));
  assert.ok(ui.includes('REVIEW_REQUIRED'));
  assert.ok(ui.includes('data: { channelId: row.provider_channel_id }'));
  assert.ok(editor.includes('MAT_DIALOG_DATA'));
  assert.ok(entry.includes('Ver canales pendientes de revisión'));
  assert.ok(html.includes('sin confirmación directa de Meta'));
  assert.ok(html.includes('Agregar o corregir datos'));
  assert.equal(ui.includes('registerQuotaPolicy('), false);
  assert.equal(ui.includes('submitCampaign('), false);
  assert.equal(ui.includes('registerChannelPortfolioEvidence('), false);
});


test('Issue 856 C QA modal only previews and freezes one recipient; no send or local persistence', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const component = fs.readFileSync(path.join(root, 'marketing-campaign-v2-qa-manual-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-qa-manual-dialog.component.html'), 'utf8');
  const page = fs.readFileSync(path.join(root, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const pageHtml = fs.readFileSync(path.join(root, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const api = fs.readFileSync(path.join(root, 'marketing-campaign-v2.service.ts'), 'utf8');
  assert.ok(api.includes('/qa-manual/preview'));
  assert.ok(api.includes('/qa-manual/freeze'));
  assert.ok(component.includes('this.confirmFreeze.value'));
  assert.ok(component.includes('expected_preview_fingerprint: this.preview.preview_fingerprint'));
  assert.ok(component.includes('expected_channel_binding_id: this.preview.channel_binding_id'));
  assert.ok(component.includes('recipients: [{'));
  assert.ok(component.includes('this.invalidatePreview()'));
  assert.ok(html.includes('no se envían mensajes ni se autorizan envíos'));
  assert.ok(html.includes('Guardar prueba de 1 contacto · NO ENVÍA'));
  assert.ok(page.includes('if (!this.canManageDispatchConfig) { return; }'));
  assert.ok(pageHtml.includes('*ngIf="canManageDispatchConfig"'));
  assert.equal(component.includes('submitCampaign('), false);
  assert.equal(component.includes('executeGovernedChild('), false);
  assert.equal(component.includes('localStorage'), false);
  assert.equal(component.includes('sessionStorage'), false);
});


test('Issue 856 D: governed console uses exact approval, manifest and one-child APIs', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ts = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const service = fs.readFileSync(path.join(root, 'marketing-campaign-v2.service.ts'), 'utf8');
  const detail = fs.readFileSync(path.join(root, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'), 'utf8');
  const detailHtml = fs.readFileSync(path.join(root, 'marketing-campaign-v2-campaign-detail-dialog.component.html'), 'utf8');
  for (const suffix of [
    '/dispatch/approval', '/dispatch/materialize', '/dispatch/execution',
    '/dispatch/authorize', '/dispatch/execute', '/dispatch/monitor',
  ]) assert.ok(service.includes(suffix), suffix);
  assert.ok(ts.includes('expected_dispatch_fingerprint: plan.dispatch_fingerprint'));
  assert.ok(ts.includes('expected_quote_fingerprint: plan.budget_usd.quote_fingerprint'));
  assert.ok(ts.includes("pricing_currency: 'USD'"));
  assert.ok(ts.includes('expected_manifest_digest: review.manifest_digest'));
  assert.ok(ts.includes('expected_ready_recipients: this.approvedReadyCount'));
  assert.ok(ts.includes('child_id: child.child_id'));
  assert.ok(ts.includes('this.executionCheckbox.value === true'));
  assert.ok(ts.includes('this.executionPhrase.value === this.sendWord'));
  assert.ok(ts.includes('this.uncertainResult = true'));
  assert.ok(ts.includes("this.monitor?.execution?.status") || ts.includes("monitor?.execution?.status"));
  assert.ok(ts.includes("review.manifest.batches.filter(batch => batch.planned_status === 'READY')"));
  assert.ok(html.includes('UN SOLO LOTE'));
  assert.ok(html.includes('no envía'));
  assert.ok(html.includes('NO vuelvas a enviar'));
  assert.ok(detail.includes('if (!this.data.canManageDispatchConfig || !this.campaign) { return; }'));
  assert.ok(detailHtml.includes('data.canManageDispatchConfig'));
  assert.equal(ts.includes('submitCampaign('), false);
  assert.equal(ts.includes('localStorage'), false);
  assert.equal(ts.includes('setInterval'), false);
});


test('Issue 856 E: no automatic dispatch, silent retry, or unlocked ambiguity in governed UI', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ui = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const api = fs.readFileSync(path.join(root, 'marketing-campaign-v2.service.ts'), 'utf8');
  assert.ok(ui.includes("this.uncertainResult = true"));
  assert.ok(ui.includes("this.refresh(true)"));
  assert.ok(ui.includes("this.monitor?.quota.all_current === true"));
  assert.ok(ui.includes("this.executionCheckbox.value === true"));
  assert.ok(ui.includes("this.executionPhrase.value === this.sendWord"));
  assert.ok(ui.includes("review.manifest.batches.filter(batch => batch.planned_status === 'READY')"));
  assert.ok(ui.includes("child.needs_manual_review"));
  assert.ok(html.includes('Enviar únicamente lote'));
  assert.ok(html.includes('UN SOLO LOTE'));
  assert.ok(html.includes('NO vuelvas a enviar'));
  assert.ok(api.includes("/dispatch/monitor"));
  assert.equal(ui.includes('setInterval('), false);
  assert.equal(ui.includes('setTimeout('), false);
  assert.equal(ui.includes('retryWhen('), false);
  assert.equal(ui.includes('submitCampaign('), false);
  assert.equal(ui.includes('localStorage'), false);
});


test('Issue 856 UX: preparación explica bloqueos, simplifica lenguaje y conserva gates de envío', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ts = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const css = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.css'), 'utf8');
  const page = fs.readFileSync(path.join(root, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const readiness = fs.readFileSync(path.join(root, 'marketing-campaign-v2-readiness-dialog.component.html'), 'utf8');
  const pricing = fs.readFileSync(path.join(root, 'marketing-campaign-v2-dispatch-admin-dialog.component.html'), 'utf8');
  assert.ok(ts.includes("if (!plan.budget_usd)"));
  assert.ok(ts.includes("plan.quota?.status !== 'REVIEWABLE'"));
  assert.ok(ts.includes("this.monitor?.quota.all_current === true"));
  assert.ok(ts.includes("this.uncertainResult = true"));
  assert.ok(ts.includes("'ENVIAR LOTE ' + this.nextReadyChild.child_id"));
  assert.ok(html.includes('Tarifa automática:'));
  assert.ok(html.includes('{{ preparationIssue }}'));
  assert.ok(html.includes('{{ budgetStatusLabel }}'));
  assert.ok(html.includes('{{ quotaStatusLabel }}'));
  assert.ok(html.includes('<details class="technical">'));
  assert.ok(html.includes('NO vuelvas a enviar'));
  assert.ok(css.includes('.review-summary'));
  assert.ok(page.includes('Preparar prueba interna · 1 contacto'));
  assert.ok(page.includes('Plantillas, canales y tarifas'));
  assert.ok(readiness.includes('Estado de canales para campañas'));
  assert.ok(pricing.includes('Historial de tarifas MXN (método anterior)'));
  assert.equal(ts.includes('submitCampaign('), false);
  assert.equal(ts.includes('setInterval('), false);
  assert.equal(ts.includes('retryWhen('), false);
});


test('Issue 856 USD: estimate is automatic delivered-based; approval cannot require per-channel MXN', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ts = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const models = fs.readFileSync(path.join(root, 'marketing-campaign-v2.models.ts'), 'utf8');
  assert.ok(models.includes('interface CampaignV2AutomaticUsdBudget'));
  assert.ok(models.includes("billable_basis: 'PROVIDER_CONFIRMED_DELIVERED'"));
  assert.ok(ts.includes('plan.budget_usd.quote_fingerprint'));
  assert.ok(ts.includes("pricing_currency: 'USD'"));
  assert.ok(ts.includes('get isSelectionWithinCapacity(): boolean'));
  assert.ok(ts.includes("this.monitor?.quota.all_current === true"));
  assert.ok(html.includes('Máximo si todos reciben'));
  assert.ok(html.includes('iVentas confirma el cobro después de entregar'));
  assert.equal(ts.includes('expected_total_mxn:'), false);
  assert.equal(ts.includes('plan.budget?.status !=='), false);
  assert.equal(ts.includes('setInterval('), false);
  assert.equal(ts.includes('executeOne();'), false);
});


test('Issue 856 exception-only capacity: client preserves quota and explicit HELD gates', () => {
  const dir = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const component = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const template = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const readiness = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-readiness.logic.ts'), 'utf8');
  const model = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.models.ts'), 'utf8');
  assert.ok(component.includes('get isSelectionWithinCapacity(): boolean'));
  assert.ok(component.includes("'CHANNEL_EXCEPTION_250_EXCEEDED'"));
  assert.ok(component.includes("'UNRESOLVED_PROVIDER_ACTIVITY'"));
  assert.ok(component.includes("this.heldBranches.includes(row.sucursal_canon)"));
  assert.ok(component.includes("this.heldBranches.every(branch => !!this.heldSources[branch])"));
  assert.ok(component.includes("this.monitor?.quota.all_current === true"));
  assert.ok(component.includes("this.uncertainResult"));
  assert.ok(template.includes('*ngIf="isSelectionWithinCapacity'));
  assert.ok(readiness.includes("binding.sucursal_canon.trim().toUpperCase()"));
  assert.ok(model.includes("'SUITE_BRANCH_EXCEPTION_CAPS_V1'"));
  assert.ok(template.includes('(click)="approve()"'));
  assert.equal(component.includes('setInterval('), false);
});


test('Issue 856 password gate: execution needs ephemeral operator password with no unlocked session', () => {
  const dir = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const component = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const template = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const models = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.models.ts'), 'utf8');
  assert.ok(component.includes('readonly executionPassword = new FormControl'));
  assert.ok(component.includes('this.executionPassword.value.length > 0'));
  assert.ok(component.includes('this.executionPassword.setValue(\'\');'));
  assert.ok(component.includes('operator_password: operatorPassword'));
  assert.ok(component.includes('err.status === 403 || err.status === 423'));
  assert.ok(component.includes('this.uncertainResult = true'));
  assert.ok(template.includes('type="password"'));
  assert.ok(template.includes('[formControl]="executionPassword"'));
  assert.ok(models.includes('operator_password: string'));
  assert.equal(component.includes('localStorage.setItem'), false);
  assert.equal(component.includes('setInterval('), false);
});


test('Bulk send explicit: only authorized pending suffix, never previously accepted #79', () => {
  const review: CampaignV2GovernedExecutionReviewReady = {
    approval_id: 4, manifest_digest: 'd'.repeat(64),
    manifest: {
      version: 'v1', quote_fingerprint: 'q'.repeat(64), send_authorized: false,
      batches: [
        { sucursal_canon: 'AZAHARES_CUL', provider_channel_id: 'ch1', recipients: 29, planned_status: 'READY', hold_reason: null },
        { sucursal_canon: 'CARROUSEL_TJ', provider_channel_id: 'ch2', recipients: 60, planned_status: 'READY', hold_reason: null },
        { sucursal_canon: 'INDEPENDENCIA', provider_channel_id: 'ch3', recipients: 114, planned_status: 'READY', hold_reason: null },
      ],
    },
    execution: { execution_id: 2, status: 'AUTHORIZED', last_child_id: 79 },
    expires_at: '2099-01-01T00:00:00Z', send_authorized: false,
  };
  const monitor: CampaignV2GovernedMonitor = {
    campaign_id: 20, as_of: '2026-10-16T00:00:00Z', basis: 'TEST',
    status: 'AUTHORIZED', next_manual_action: 'MANUAL_NEXT_CHILD_ONLY',
    send_authorized: false, may_auto_retry: false, may_auto_release_held: false,
    approval: {
      id: 4, expires_at: '2099-01-01T00:00:00Z',
      expired: false, dispatch_fingerprint: 'f'.repeat(64),
      manifest_digest: 'd'.repeat(64),
    },
    execution: { id: 2, status: 'AUTHORIZED', last_child_id: 79, expires_at: '2099-01-01T00:00:00Z' },
    quota: { basis: 'TEST', all_current: true }, children_count: 3,
    children_by_status: { SUBMITTED: 1, READY: 2 },
    children: [
      { child_id: 79, sucursal_canon: 'AZAHARES_CUL', provider_channel_id: 'ch1',
        recipient_count: 29, status: 'SUBMITTED', provider_campaign_id: 'iventas-79',
        error_code: null, needs_manual_review: false, send_authorized: false },
      { child_id: 80, sucursal_canon: 'CARROUSEL_TJ', provider_channel_id: 'ch2',
        recipient_count: 60, status: 'READY', provider_campaign_id: null,
        error_code: null, needs_manual_review: false, send_authorized: false },
      { child_id: 81, sucursal_canon: 'INDEPENDENCIA', provider_channel_id: 'ch3',
        recipient_count: 114, status: 'READY', provider_campaign_id: null,
        error_code: null, needs_manual_review: false, send_authorized: false },
    ],
  };
  assert.deepEqual(pendingGovernedBatchIds(monitor, review), [80, 81]);
  const after80: CampaignV2GovernedMonitor = {
    ...monitor,
    execution: { ...monitor.execution!, last_child_id: 80 },
    children: monitor.children.map(c => c.child_id === 80 ? {
      ...c, status: 'SUBMITTED', provider_campaign_id: 'iventas-80',
    } : c),
  };
  const review80: CampaignV2GovernedExecutionReviewReady = {
    ...review, execution: { ...review.execution!, last_child_id: 80 },
  };
  assert.deepEqual(pendingGovernedBatchIds(after80, review80), [81]);

  assert.deepEqual(pendingGovernedBatchIds({...monitor, quota: {...monitor.quota, all_current: false}}, review), []);
  assert.deepEqual(pendingGovernedBatchIds({...monitor, children: monitor.children.map(c => c.child_id === 80 ? {...c, needs_manual_review: true} : c)}, review), []);
  assert.deepEqual(pendingGovernedBatchIds({...monitor, children: monitor.children.map(c => c.child_id === 80 ? {...c, status: 'RECONCILIATION_REQUIRED'} : c)}, review), []);
  assert.deepEqual(pendingGovernedBatchIds({...monitor, children: monitor.children.map(c => c.child_id === 79 ? {...c, provider_campaign_id: null} : c)}, review), []);
  assert.deepEqual(pendingGovernedBatchIds({...monitor, execution: {...monitor.execution!, last_child_id: null}}, review), []);
  assert.deepEqual(pendingGovernedBatchIds({...monitor, approval: {...monitor.approval!, expired: true}}, review), []);
  assert.deepEqual(pendingGovernedBatchIds({...monitor, approval: {...monitor.approval!, manifest_digest: 'x'.repeat(64)}}, review), []);

  // After a valid first provider claim, expiry is no longer a blanket timer:
  // backend will validate current quota before each pending child.
  const continued: CampaignV2GovernedMonitor = {
    ...monitor, status: 'CONTINUATION_REVIEW_REQUIRED',
    next_manual_action: 'MANUAL_NEXT_PENDING_WITH_FRESH_QUOTA',
    approval: {...monitor.approval!, expired: true},
    quota: {...monitor.quota, all_current: false},
  };
  assert.deepEqual(pendingGovernedBatchIds(continued, review), [80, 81]);
  assert.deepEqual(pendingGovernedBatchIds({
    ...continued, status: 'APPROVAL_EXPIRED',
  }, review), []);
  assert.deepEqual(pendingGovernedBatchIds({
    ...continued,
    execution: {...continued.execution!, last_child_id: null},
  }, review), []);
  assert.deepEqual(pendingGovernedBatchIds({
    ...continued, children: continued.children.map(child => child.child_id === 79
      ? {...child, provider_campaign_id: null} : child),
  }, review), []);
});

test('Bulk send explicit: one gesture, sequential per-child guarded requests, no replay or secrets persisted', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const ui = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  assert.ok(html.includes('(click)="executePendingSequentially()"'));
  assert.ok(html.includes("'Enviar ' + bulkPendingIds.length + ' lotes pendientes'"));
  assert.ok(html.includes("working === 'bulk' ? 'Enviando lotes… ' + bulkAccepted + '/' + bulkTotal"));
  assert.ok(html.includes('Detener después del lote actual'));
  assert.ok(ui.includes('this.reviewReady!.execution!.execution_id'));
  assert.ok(ui.includes('this.bulkPassword.setValue(\'\')'));
  assert.ok(ui.includes('await this.readFreshBulkState()'));
  assert.ok(ui.includes('pendingIds.slice(index)'));
  assert.ok(ui.includes("result.status !== 'SUBMITTED'"));
  assert.ok(ui.includes("persisted?.status !== 'SUBMITTED'"));
  assert.ok(ui.includes('operator_password: password'));
  assert.equal(ui.includes('retryWhen('), false);
  assert.equal(ui.includes('setInterval('), false);
  assert.equal(ui.includes('setTimeout('), false);
  assert.equal(ui.includes('localStorage'), false);
  assert.equal(ui.includes('sessionStorage'), false);
});


test('Campaign V2: BI purpose does not hide iVentas creatives or override dispatch safety', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const excel = fs.readFileSync(path.join(root, 'marketing-campaign-v2-excel-dialog.component.ts'), 'utf8');
  const ui = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  assert.ok(excel.includes('this.templates.filter(template => template.is_active)'));
  assert.ok(ui.includes('get creativePurposeNotice()'));
  assert.ok(ui.includes('this.preflight?.campaign_purpose'));
  assert.ok(html.includes('{{ creativePurposeNotice }}'));
  assert.ok(ui.includes('this.monitor?.quota.all_current === true'));
  assert.ok(ui.includes('this.executionPhrase.value === this.sendWord'));
});


test('Previous-contact preparation accepts actual numeric IDs and rejects invalid or self references', () => {
  assert.deepEqual(parsePreviousCampaignIds('20, 21', 22), { ids: [20, 21], error: '' });
  assert.deepEqual(parsePreviousCampaignIds(' 20 ,  21 ', 22), { ids: [20, 21], error: '' });
  assert.ok(parsePreviousCampaignIds('20, 20', 22).error);
  assert.ok(parsePreviousCampaignIds('20, 22', 22).error);
  assert.deepEqual(parsePreviousCampaignIds('21, 23', 22), { ids: [21, 23], error: '' });
  assert.ok(parsePreviousCampaignIds('', 22).error);
  assert.ok(parsePreviousCampaignIds('abc, 21', 22).error);
  assert.ok(parsePreviousCampaignIds('20;21', 22).error);
  assert.ok(parsePreviousCampaignIds('9007199254740993', 22).error);
});

test('Campaign V2 preparation and governed approval show contextual pending feedback', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const component = fs.readFileSync(path.join(root, 'marketing-campaign-v2-preparation-dialog.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-preparation-dialog.component.html'), 'utf8');
  const governedHtml = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  assert.ok(component.includes('parsePreviousCampaignIds(this.sourceIdsControl.value'));
  assert.ok(component.includes("this.workingAction = 'previous-review'"));
  assert.ok(html.includes('role="alert">{{ previousError }}'));
  for (const action of ['branches-review', 'branches-apply', 'previous-review', 'previous-apply']) {
    assert.ok(html.includes("workingAction === '" + action + "'"));
  }
  for (const action of ['read', 'preflight', 'approve', 'materialize', 'authorize', 'execute', 'bulk']) {
    assert.ok(governedHtml.includes("working === '" + action + "'"));
  }
  assert.equal((governedHtml.match(/mat-progress-spinner/g) || []).length >= 7, true);
});


test('Campaign V2 saved campaigns display the stable internal ID for cross-campaign dedupe', () => {
  const html = fs.readFileSync(
    path.join(process.cwd(), 'src/app/marketing-campaign-v2/marketing-campaign-v2-page.component.html'),
    'utf8',
  );
  const savedCampaignsSection = html.split('id="campaign-v2-history"')[1] || '';
  assert.ok(savedCampaignsSection.includes('<th scope="col">ID</th>'));
  assert.ok(savedCampaignsSection.includes('<strong>#{{ campaign.id }}</strong>'));
  assert.ok(savedCampaignsSection.includes('(click)="openCampaign(campaign)"'));
});

test('Campaign V2 shows unresolved provider result without claiming an accepted send', () => {
  const html = fs.readFileSync(
    path.join(process.cwd(), 'src/app/marketing-campaign-v2/marketing-campaign-v2-preparation-dialog.component.html'),
    'utf8',
  );
  assert.ok(html.includes('review.unconfirmed_batches.length'));
  assert.ok(html.includes('item.source_campaign_id'));
  assert.ok(html.includes('item.child_id'));
  assert.ok(html.includes('No se cuentan'.toLowerCase()) || html.includes('NO se cuentan'));
  assert.ok(html.includes('resultados') || html.includes('rechazo'));
});


test('Campaign V2 UI: envio compacto, una zona vertical de scroll y seguridad visible', () => {
  const root = path.join(process.cwd(), 'src/app/marketing-campaign-v2');
  const html = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.html'), 'utf8');
  const css = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.css'), 'utf8');
  const ts = fs.readFileSync(path.join(root, 'marketing-campaign-v2-governed-console-dialog.component.ts'), 'utf8');
  assert.ok(html.includes('class="dispatch-overview"'));
  assert.ok(html.includes('class="setup-history"'));
  assert.ok(html.includes('[attr.open]="reviewReady ? null :'));
  assert.ok(html.includes('class="manifest-details"'));
  assert.ok(html.includes('class="batch-details"'));
  assert.ok(html.includes('class="send-panel bulk-execution"'));
  assert.ok(html.includes('class="single-send"'));
  assert.ok(html.indexOf('class="send-panel bulk-execution"') <
    html.indexOf('class="single-send"'));
  assert.ok(html.includes('(click)="executePendingSequentially()"'));
  assert.ok(html.includes('(click)="executeOne()"'));
  assert.ok(html.includes('El envío real siempre requiere confirmación'));
  assert.ok(html.includes('No hay reintentos automáticos'));
  assert.equal(html.includes('appearance="outline"'), false);
  assert.equal(html.includes('style="'), false);
  assert.ok(css.includes('.table-scroll { overflow-x: auto; overflow-y: visible; }'));
  assert.equal(css.includes('max-height:260px'), false);
  assert.ok(ts.includes('get sentLotCount(): number'));
  assert.ok(ts.includes('get acceptedContactCount(): number'));
  for (const name of [
    'governed-console-dialog', 'preparation-dialog', 'dispatch-admin-dialog',
    'quota-admin-dialog', 'readiness-dialog', 'channel-portfolio-dialog',
    'portfolio-review-dialog', 'qa-manual-dialog', 'excel-dialog',
    'tariff-classifier-dialog',
  ]) {
    const fields = fs.readFileSync(
      path.join(root, 'marketing-campaign-v2-' + name + '.component.html'), 'utf8',
    );
    assert.equal(fields.includes('appearance="outline"'), false, name);
  }
});
