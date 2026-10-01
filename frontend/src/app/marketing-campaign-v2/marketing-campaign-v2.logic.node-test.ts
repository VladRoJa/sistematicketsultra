import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import {
  buildCampaignV2AudienceRequest,
  buildCampaignV2FreezeRequest,
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
  assert.equal(page.includes("if (source === 'ACTIVE_MEMBERS')"), true);
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

