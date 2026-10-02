import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import {
  buildCampaignV2AudienceRequest,
  buildCampaignV2FreezeRequest,
  buildCampaignV2HistoricalTargeting,
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
  canFreezeCampaignV2,
  isCampaignV2AudienceValid,
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
  assert.equal(campaignV2MetricBucket('invalid_phone'), 'INVALID_PHONE');
  assert.equal(campaignV2MetricBucket('duplicates'), 'DUPLICATES');
  assert.equal(campaignV2MetricBucket('out_of_segment'), 'OUT_OF_SEGMENT');
  assert.equal(campaignV2MetricBucket('unclassified'), 'UNCLASSIFIED');
  assert.equal(campaignV2MetricBucket('current_status_blocked'), 'CURRENT_STATUS_BLOCKED');
  assert.equal(campaignV2MetricBucket('family'), 'FAMILY');
  assert.deepEqual(campaignV2PurposePatch('REACTIVATION'), { purpose: 'REACTIVATION' });
});

test('menu V2 crea grupo cuando falta, conserva legacy y no duplica submenu', () => {
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
  assert.deepEqual(withLegacy[0].submenu?.map(item => item.path), [
    '/marketing/reactivation',
    '/marketing/campaigns-v2',
  ]);

  const repeated = withCampaignV2MenuItem(withLegacy);
  assert.equal(repeated[0].submenu?.filter(item => item.path === '/marketing/campaigns-v2').length, 1);
});

test('service y page conservan contrato M5 sin auth manual ni Exportar', () => {
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
  assert.equal(html.includes('Exportar'), false);
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
  assert.equal(layout.includes("path: '/marketing/reactivation'"), true);
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
  assert.equal(html.includes('Corte Funnel'), true);
  assert.equal(page.includes('funnelService.getDashboard(month)'), true);
  assert.equal(html.includes('Historial de campañas'), true);
  assert.equal(page.includes("label: 'Coincidieron con historial'"), true);
  assert.equal(page.includes("metric: 'history_included'"), true);
  assert.equal(page.includes("metric: 'history_excluded'"), true);
  assert.equal(campaignDetail.includes('definition.filters.audience_families?.length'), true);
  assert.equal(recipientHtml.includes("recipient.member_name || '—'"), true);
  assert.equal(recipientHtml.includes("recipient.tarifa_raw || '—'"), true);
});
