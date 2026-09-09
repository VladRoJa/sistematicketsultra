import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { of, Subject } from 'rxjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MarketingReactivationComponent } from './marketing-reactivation.component';
import { MarketingReactivationService } from './marketing-reactivation.service';

function setup() {
  const preview = new Subject<any>();
  const creation = new Subject<any>();
  const requests: any[] = [];
  const creates: any[] = [];
  const sourceStatus = {
    business_date:'2026-09-08',
    sources:{
      activos:{cutoff_date:'2026-09-08',age_days:0,status:'CURRENT'},
      vencidos:{cutoff_date:'2026-09-07',age_days:1,status:'RECENT'},
      iventas:{cutoff_date:'2026-09-05',age_days:3,status:'STALE'},
    },
  };
  const service = {
    getCampaignOptions: () => of({branches: [{key:'CENTRO', label:'Centro'}, {key:'NORTE', label:'Norte'}],
      regions:[{id:1,label:'Región 1',branch_keys:['CENTRO']}]}),
    getCampaignSourceStatus: () => of(sourceStatus),
    getCampaigns: () => of({rows:[]}),
    previewCampaign: (request: any) => {requests.push(request); return preview;},
    createCampaign: (request: any) => {creates.push(request); return creation;},
  };
  const injector = Injector.create({providers:[
    {provide: MarketingReactivationService, useValue:service},
    {provide: DestroyRef, useValue:{onDestroy: () => () => {}}},
  ]});
  const component = runInInjectionContext(injector, () => new MarketingReactivationComponent());
  component.ngOnInit();
  return {component, preview, creation, requests, creates};
}

test('source strip exposes compact freshness labels', () => {
  const {component} = setup();
  assert.equal(component.sourceTiles.length, 3);
  assert.equal(component.sourceTiles[0].label, 'Socios activos');
  assert.equal(component.sourceStatusLabel(component.sourceTiles[0].source), 'Al día');
  assert.equal(component.sourceStatusLabel(component.sourceTiles[1].source), '1 día de atraso');
  assert.equal(component.sourceStatusLabel(component.sourceTiles[2].source), '3 días de atraso');
  assert.match(component.formatSourceDate('2026-09-08'), /2026/);
});

test('Winback sends only the commercial segment, without dates or iVentas', () => {
  const {component, requests} = setup();
  component.form.controls.segment.setValue('WINBACK_60');
  component.prepareCampaign();
  assert.deepEqual(requests, [{filters:{campaign_type:'WINBACK',segment:'WINBACK_60'}}]);
});

test('collection requires an explicit range and sends it', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('COBRANZA_LIGERA');
  component.prepareCampaign();
  assert.equal(requests.length, 0);
  component.form.controls.from.setValue(12); component.form.controls.to.setValue(28);
  component.prepareCampaign();
  assert.deepEqual(requests[0].filters, {campaign_type:'COBRANZA_LIGERA',dias_desde:12,dias_hasta:28});
});

test('BCN requires an explicit expired-day range and sends the dedicated type', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('BORRON_CUENTA_NUEVA');
  component.prepareCampaign();
  assert.equal(requests.length, 0);
  component.form.controls.from.setValue(91); component.form.controls.to.setValue(365);
  component.prepareCampaign();
  assert.deepEqual(requests[0].filters, {
    campaign_type:'BORRON_CUENTA_NUEVA', dias_desde:91, dias_hasta:365,
  });
});

test('changing region clears a branch outside the selected region and invalidates preview', () => {
  const {component} = setup();
  component.form.controls.branch.setValue('NORTE'); component.eligible = 20;
  component.form.controls.region.setValue(1);
  assert.equal(component.form.controls.branch.value, '');
  assert.equal(component.eligible, null);
  assert.equal(component.branches.length, 1);
});

test('late preview cannot recreate eligibility after changing the audience', () => {
  const {component, preview} = setup();
  component.prepareCampaign();
  component.form.controls.type.setValue('INVITA_GANA');
  preview.next({summary:{eligible:20}});
  assert.equal(component.eligible, null);
  assert.equal(component.canCreate, false);
});

test('preview exposes the campaign construction breakdown', () => {
  const {component, preview} = setup();
  component.prepareCampaign();
  preview.next({summary:{
    total_candidates:9422, eligible:1010, excluded_active:45,
    excluded_invalid_phone:0, review_identity:28, duplicate_phone:15,
    excluded_tariff:8043, excluded_tariff_general:6057,
    domiciliated_flow:1986, borron_cuenta_nueva:624, review_tariff:281,
    excluded_recent_campaign:0, review:309, excluded_weekly_limit:0,
  }});
  assert.equal(component.eligible, 1010);
  assert.deepEqual(component.audienceBreakdown.map(row => [row.label, row.value]), [
    ['Candidatos encontrados', 9422],
    ['Actualmente activos', 45],
    ['Identidad por revisar', 28],
    ['Excluidos por tarifa', 6057],
    ['Flujo domiciliados', 1986],
    ['↳ Con adeudo / candidatos BCN', 624],
    ['Tarifa por revisar', 281],
    ['Teléfonos duplicados', 15],
  ]);
});

test('creation requires reviewed contacts and blocks double submission', () => {
  const {component, preview, creates} = setup();
  component.name.setValue('Septiembre');
  component.confirmCampaign(); assert.equal(creates.length, 0);
  component.prepareCampaign(); preview.next({summary:{eligible:5}});
  component.confirmCampaign(); component.confirmCampaign();
  assert.equal(creates.length, 1);
  assert.equal(creates[0].name, 'Septiembre');
  assert.equal(component.form.disabled, true);
});

test('custom active sends only the active universe', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('PERSONALIZADA');
  component.form.controls.universe.setValue('ACTIVOS');
  component.prepareCampaign();
  assert.deepEqual(requests[0].filters, {campaign_type:'PERSONALIZADA', universo:'ACTIVOS'});
});

test('custom expired supports an open-ended day range', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('PERSONALIZADA');
  component.form.controls.universe.setValue('VENCIDOS');
  component.form.controls.expiredMode.setValue('DIAS');
  component.form.controls.from.setValue(91);
  component.form.controls.to.setValue(null);
  component.prepareCampaign();
  assert.deepEqual(requests[0].filters, {
    campaign_type:'PERSONALIZADA',
    universo:'VENCIDOS',
    modo_vencidos:'DIAS',
    dias_desde:91,
  });
});

test('custom expired supports an open-ended expiration date range', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('PERSONALIZADA');
  component.form.controls.universe.setValue('VENCIDOS');
  component.form.controls.expiredMode.setValue('FECHAS');
  component.form.controls.dateFrom.setValue('2026-01-01');
  component.form.controls.dateTo.setValue('');
  component.prepareCampaign();
  assert.deepEqual(requests[0].filters, {
    campaign_type:'PERSONALIZADA',
    universo:'VENCIDOS',
    modo_vencidos:'FECHAS',
    fecha_desde:'2026-01-01',
  });
});

test('custom expiration dates reject an inverted range before calling API', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('PERSONALIZADA');
  component.form.controls.universe.setValue('VENCIDOS');
  component.form.controls.expiredMode.setValue('FECHAS');
  component.form.controls.dateFrom.setValue('2026-08-01');
  component.form.controls.dateTo.setValue('2026-07-01');
  component.prepareCampaign();
  assert.equal(requests.length, 0);
  assert.equal(component.error, 'La fecha desde no puede ser posterior a la fecha hasta.');
});

test('campaign package uses zip extension for multi-branch archive', () => {
  const {component} = setup();
  const campaign = {id: 9, name: 'Vencidos agosto 2026'} as any;
  const filename = (component as any).exportFilename(
    campaign,
    new Blob([], {type:'application/zip'}),
  );
  assert.equal(filename, 'VENCIDOS_AGOSTO_2026.zip');
});

test('campaign package keeps xlsx extension for a single branch', () => {
  const {component} = setup();
  const campaign = {id: 10, name: 'Villas del Rey'} as any;
  const filename = (component as any).exportFilename(
    campaign,
    new Blob([], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}),
  );
  assert.equal(filename, 'VILLAS_DEL_REY.xlsx');
});
