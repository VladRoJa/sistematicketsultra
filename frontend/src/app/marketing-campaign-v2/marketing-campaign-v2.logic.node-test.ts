import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import {
  buildCampaignV2AudienceRequest,
  buildCampaignV2FreezeRequest,
  buildCampaignV2HistoryExclusion,
  campaignV2HistoryBreakdownRows,
  campaignV2HistoryReasonLabel,
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



test('history_exclusion se omite sin condiciones efectivas', () => {
  const request = buildCampaignV2AudienceRequest({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '',
    expirationDateTo: '',
    historyEnabled: true,
    historyDeliveryBuckets: [],
    historyOutcomes: [],
    historyButtonInteracted: false,
    historyWindowMode: 'ALL',
    historyLookbackDays: '',
  });
  assert.equal('history_exclusion' in request, false);
});

test('VIEWED genera payload exacto sin inferir SENT ni DELIVERED', () => {
  const request = buildCampaignV2AudienceRequest({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '',
    expirationDateTo: '',
    historyEnabled: true,
    historyDeliveryBuckets: ['VIEWED'],
    historyOutcomes: [],
    historyButtonInteracted: false,
    historyWindowMode: 'ALL',
    historyLookbackDays: '',
  });
  assert.deepEqual(request.history_exclusion, {
    delivery_buckets: ['VIEWED'],
    outcomes: [],
    button_interacted: false,
    lookback_days: null,
  });
});

test('FAILED + VIEWED + button conserva OR como criterios independientes', () => {
  const exclusion = buildCampaignV2HistoryExclusion({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '',
    expirationDateTo: '',
    historyEnabled: true,
    historyDeliveryBuckets: ['VIEWED'],
    historyOutcomes: ['FAILED'],
    historyButtonInteracted: true,
    historyWindowMode: 'DAYS',
    historyLookbackDays: '90',
  });
  assert.deepEqual(exclusion, {
    delivery_buckets: ['VIEWED'],
    outcomes: ['FAILED'],
    button_interacted: true,
    lookback_days: 90,
  });
});

test('lookback acepta null conceptual o entero positivo y rechaza inválidos', () => {
  assert.equal(parseCampaignV2LookbackDays('1'), 1);
  assert.equal(parseCampaignV2LookbackDays('90'), 90);
  for (const value of ['', '0', '-1', '1.5', 'NaN', 'texto']) {
    assert.equal(parseCampaignV2LookbackDays(value), null, value);
  }

  const base = {
    source: 'ACTIVE_MEMBERS' as const,
    audienceFamilies: ['DOMICILIADO'] as CampaignV2AudienceFamily[],
    expirationDateFrom: '',
    expirationDateTo: '',
    historyEnabled: true,
    historyDeliveryBuckets: ['VIEWED'] as Array<'SENT' | 'DELIVERED' | 'VIEWED'>,
    historyOutcomes: [] as Array<'SUCCESSFUL' | 'FAILED'>,
    historyButtonInteracted: false,
    historyWindowMode: 'DAYS' as const,
  };
  assert.equal(isCampaignV2HistoryFilterValid({ ...base, historyLookbackDays: '30' }), true);
  assert.equal(isCampaignV2HistoryFilterValid({ ...base, historyLookbackDays: '0' }), false);
});

test('cualquier criterio histórico invalida Preview; name/purpose no', () => {
  for (const field of [
    'history_enabled',
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

test('reason mapper traduce razones conocidas y tiene fallback seguro', () => {
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_DELIVERY_VIEWED'), 'Visto anteriormente');
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_OUTCOME_FAILED'), 'Resultado fallido anteriormente');
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_BUTTON_INTERACTION'), 'Interactuó con un botón');
  assert.equal(campaignV2HistoryReasonLabel('HISTORY_FUTURE_REASON'), 'Razón histórica: HISTORY_FUTURE_REASON');
});

test('Freeze conserva history_exclusion y nunca agrega teléfonos/cutoff efectivo', () => {
  const audience = buildCampaignV2AudienceRequest({
    source: 'ACTIVE_MEMBERS',
    audienceFamilies: ['DOMICILIADO'],
    expirationDateFrom: '',
    expirationDateTo: '',
    historyEnabled: true,
    historyDeliveryBuckets: ['VIEWED'],
    historyOutcomes: ['FAILED'],
    historyButtonInteracted: true,
    historyWindowMode: 'DAYS',
    historyLookbackDays: '90',
  });
  const request = buildCampaignV2FreezeRequest(
    audience,
    ' Histórica ',
    'REACTIVATION',
    'f'.repeat(64),
  );
  assert.deepEqual(request.history_exclusion, {
    delivery_buckets: ['VIEWED'],
    outcomes: ['FAILED'],
    button_interacted: true,
    lookback_days: 90,
  });
  for (const forbidden of [
    'excluded_phones',
    'history_rows',
    'observed_before',
    'observed_after',
  ]) {
    assert.equal(forbidden in request, false, forbidden);
  }
});


test('M15 renderiza diagnostics/history detail sin M13 ni auth manual', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.service.ts'), 'utf8');
  const pageTs = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const pageHtml = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const detailTs = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.ts'),
    'utf8',
  );
  const detailHtml = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(pageHtml.includes('Antes del filtro histórico'), true);
  assert.equal(pageHtml.includes('Excluidos por historial'), true);
  assert.equal(pageHtml.includes('Después del filtro histórico'), true);
  assert.equal(
    pageHtml.includes('Un contacto puede aparecer en más de una razón de exclusión.'),
    true,
  );
  assert.equal(pageTs.includes("openMetric('history_excluded'"), false);
  assert.equal(pageHtml.includes("openMetric('history_excluded'"), true);
  assert.equal(detailTs.includes("HISTORY_EXCLUDED: 'Excluidos por historial'"), true);
  assert.equal(detailTs.includes('campaignV2HistoryReasonLabel'), true);
  assert.equal(detailHtml.includes("data.bucket === 'HISTORY_EXCLUDED'"), true);

  assert.equal(service.includes('provider-history/lookup'), false);
  assert.equal(service.includes('Authorization'), false);
  assert.equal(service.includes('localStorage'), false);
  assert.equal(pageTs.includes('provider-history/lookup'), false);
});


test('UI M15 expone filtros/diagnostics/detail sin consultar M13 ni auth manual', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.service.ts'), 'utf8');
  const models = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.models.ts'), 'utf8');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const detail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.ts'),
    'utf8',
  );
  const detailHtml = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(models.includes("history_exclusion?: CampaignV2HistoryExclusion"), true);
  assert.equal(models.includes("| 'HISTORY_EXCLUDED'"), true);
  assert.equal(html.includes('Historial de campañas'), true);
  assert.equal(html.includes('Excluir contactos según historial'), true);
  assert.equal(html.includes('Antes del filtro histórico'), true);
  assert.equal(html.includes('Excluidos por historial'), true);
  assert.equal(html.includes('Después del filtro histórico'), true);
  assert.equal(html.includes('Un contacto puede aparecer en más de una razón de exclusión.'), true);
  assert.equal(page.includes('historyBreakdownRows()'), true);
  assert.equal(page.includes('this.invalidatePreview();'), true);
  assert.equal(detail.includes("HISTORY_EXCLUDED: 'Excluidos por historial'"), true);
  assert.equal(detail.includes('campaignV2HistoryReasonLabel'), true);
  assert.equal(detailHtml.includes('historyReasonsLabel(row.history_exclusion_reasons)'), true);

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

test('UI no expone cutoff editable ni copy de respondió/no contestó', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');

  assert.equal(html.includes('observed_before'), false);
  assert.equal(html.includes('observed_after'), false);
  assert.equal(html.toLowerCase().includes('no contestó'), false);
  assert.equal(html.toLowerCase().includes('respondió'), false);
  assert.equal(page.includes("label: 'Historial observado desde'"), true);
  assert.equal(page.includes("label: 'Historial evaluado hasta'"), true);
});


test('diagnostics solapados conservan total backend y razones no exclusivas', () => {
  const backendHistoryExcludedCount = 2;
  const rows = campaignV2HistoryBreakdownRows({
    history_excluded_count: backendHistoryExcludedCount,
    excluded_by_delivery_bucket: { VIEWED: 1 },
    excluded_by_outcome: { FAILED: 1 },
    excluded_by_button_interaction: 1,
  });
  assert.deepEqual(rows, [
    { label: 'Vistos', count: 1 },
    { label: 'Fallidos', count: 1 },
    { label: 'Interacción con botón', count: 1 },
  ]);
  assert.equal(rows.reduce((total, row) => total + row.count, 0), 3);
  assert.equal(backendHistoryExcludedCount, 2);
});


test('detalle congelado muestra criterios históricos persistidos sin backend nuevo', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const service = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.service.ts'), 'utf8');
  const detail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );

  assert.equal(detail.includes("label: 'Exclusiones históricas'"), true);
  assert.equal(detail.includes("label: 'Ventana histórica'"), true);
  assert.equal(detail.includes('definition.filters.history_exclusion'), true);
  assert.equal(detail.includes('campaignV2HistoryExclusionSummary'), true);
  assert.equal(detail.includes('campaignV2HistoryWindowLabel'), true);
  assert.equal(detail.includes("timeZone: 'America/Tijuana'"), true);
  assert.equal(service.includes('/provider-history'), false);
});


test('M20 Funnel usa options como contrato, exige mes/corte y omite filtros no aplicables', () => {
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
    tariff_categories: [],
    scope: { is_global: true, allowed_sucursal_keys: null },
  };

  const base = {
    source: 'FUNNEL_PORTFOLIO' as const,
    audienceFamilies: ['DOMICILIADO'] as CampaignV2AudienceFamily[],
    expirationDateFrom: '2026-09-01',
    expirationDateTo: '2026-09-30',
    funnelMonth: '2026-09',
    funnelCutoffDate: '2026-09-30',
    historyEnabled: true,
    historyDeliveryBuckets: ['VIEWED'] as CampaignV2HistoryDeliveryBucket[],
    historyOutcomes: [] as CampaignV2HistoryOutcome[],
    historyButtonInteracted: false,
    historyWindowMode: 'ALL' as const,
    historyLookbackDays: '',
  };

  assert.equal(isCampaignV2AudienceValid(
    { ...base, funnelMonth: '' },
    options,
  ), false);
  assert.equal(isCampaignV2AudienceValid(
    { ...base, funnelCutoffDate: '' },
    options,
  ), false);
  assert.equal(isCampaignV2AudienceValid(base, options), true);

  const request = buildCampaignV2AudienceRequest(base, options);
  assert.deepEqual(request, {
    source: 'FUNNEL_PORTFOLIO',
    funnel_month: '2026-09',
    funnel_cutoff_date: '2026-09-30',
    history_exclusion: {
      delivery_buckets: ['VIEWED'],
      outcomes: [],
      button_interacted: false,
      lookback_days: null,
    },
  });
  assert.equal('audience_families' in request, false);
  assert.equal('expiration_date_from' in request, false);
  assert.equal('expiration_date_to' in request, false);

  const freeze = buildCampaignV2FreezeRequest(
    request,
    'Funnel septiembre',
    'NEW_SALE',
    'f'.repeat(64),
  );
  assert.deepEqual(Object.keys(freeze).sort(), [
    'expected_preview_fingerprint',
    'funnel_cutoff_date',
    'funnel_month',
    'history_exclusion',
    'name',
    'purpose',
    'source',
  ]);
  for (const forbidden of [
    'iventas_sync_run_id',
    'active_members_snapshot_id',
    'active_phones',
    'buyer_exclusions',
    'recipients',
    'observed_before',
  ]) {
    assert.equal(forbidden in freeze, false, forbidden);
  }
});

test('M20 month/cutoff y source invalidan Preview y buckets Funnel mapean backend', () => {
  for (const field of ['source', 'funnel_month', 'funnel_cutoff_date'] as const) {
    assert.equal(campaignV2FieldInvalidatesPreview(field), true, field);
  }
  assert.equal(campaignV2MetricBucket('funnel_candidates'), 'FUNNEL_CANDIDATES');
  assert.equal(campaignV2MetricBucket('funnel_buyer_excluded'), 'FUNNEL_BUYER_EXCLUDED');
  assert.equal(campaignV2MetricBucket('active_member_suppression'), 'ACTIVE_MEMBER_SUPPRESSION');
});

test('M20 UI Funnel renderiza contrato/diagnostics, reutiliza cortes y tolera recipients phone-only', () => {
  const root = process.cwd();
  const dir = path.join(root, 'src/app/marketing-campaign-v2');
  const models = fs.readFileSync(path.join(dir, 'marketing-campaign-v2.models.ts'), 'utf8');
  const page = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.ts'), 'utf8');
  const html = fs.readFileSync(path.join(dir, 'marketing-campaign-v2-page.component.html'), 'utf8');
  const previewDetail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-preview-detail-dialog.component.ts'),
    'utf8',
  );
  const campaignDetail = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-campaign-detail-dialog.component.ts'),
    'utf8',
  );
  const recipientHtml = fs.readFileSync(
    path.join(dir, 'marketing-campaign-v2-recipient-detail-dialog.component.html'),
    'utf8',
  );

  assert.equal(models.includes("| 'FUNNEL_PORTFOLIO'"), true);
  assert.equal(models.includes("| 'FUNNEL_CANDIDATES'"), true);
  assert.equal(models.includes("| 'FUNNEL_BUYER_EXCLUDED'"), true);
  assert.equal(models.includes("| 'ACTIVE_MEMBER_SUPPRESSION'"), true);
  assert.equal(html.includes('Cartera Funnel / Venta Nueva'), false);
  assert.equal(page.includes("FUNNEL_PORTFOLIO: 'Cartera Funnel / Venta Nueva'"), true);
  assert.equal(html.includes('Mes Funnel'), true);
  assert.equal(html.includes('Corte Funnel'), true);
  assert.equal(page.includes('funnelService.getDashboard(month)'), true);
  assert.equal(page.includes("'audience_families'"), true);
  assert.equal(html.includes('Leads Funnel'), true);
  assert.equal(html.includes('Compradores excluidos'), true);
  assert.equal(html.includes('Socios activos excluidos'), true);
  assert.equal(html.includes('Teléfonos no utilizables'), true);
  assert.equal(html.includes('Audiencia final'), true);
  assert.equal(
    html.includes('Número asociado actualmente a Socios Activos'),
    true,
  );
  assert.equal(
    html.includes('Conversión detectada por lógica Funnel'),
    true,
  );
  assert.equal(previewDetail.includes("FUNNEL_CANDIDATES: 'Leads Funnel'"), true);
  assert.equal(
    previewDetail.includes("ACTIVE_MEMBER_SUPPRESSION: 'Socios activos excluidos'"),
    true,
  );
  assert.equal(campaignDetail.includes('definition.filters.audience_families?.length'), true);
  assert.equal(campaignDetail.includes("label: 'Mes Funnel'"), true);
  assert.equal(recipientHtml.includes("recipient.member_name || '—'"), true);
  assert.equal(recipientHtml.includes("recipient.tarifa_raw || '—'"), true);

  for (const forbidden of [
    'active_members_snapshot_id:',
    'iventas_sync_run_id:',
    'buyer_exclusions:',
    'recipients:',
  ]) {
    assert.equal(page.includes(forbidden), false, forbidden);
  }
});
