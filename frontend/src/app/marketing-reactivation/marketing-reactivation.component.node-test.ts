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
  const service = {
    getCampaignOptions: () => of({branches: [{key:'CENTRO', label:'Centro'}, {key:'NORTE', label:'Norte'}],
      regions:[{id:1,label:'Región 1',branch_keys:['CENTRO']}]}),
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

test('custom expired supports an open-ended range', () => {
  const {component, requests} = setup();
  component.form.controls.type.setValue('PERSONALIZADA');
  component.form.controls.universe.setValue('VENCIDOS');
  component.form.controls.from.setValue(91);
  component.form.controls.to.setValue(null);
  component.prepareCampaign();
  assert.deepEqual(requests[0].filters, {
    campaign_type:'PERSONALIZADA',
    universo:'VENCIDOS',
    dias_desde:91,
  });
});
