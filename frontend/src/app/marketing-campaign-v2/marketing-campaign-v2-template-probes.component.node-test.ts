import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { Subject } from 'rxjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MarketingCampaignV2TemplateProbesComponent } from './marketing-campaign-v2-template-probes.component';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

function harness() {
  const requests: Subject<any>[] = [];
  const calls: any[] = [];
  const api = {
    prepareTemplateProbes: (...args: any[]) => {
      calls.push(['prepare', ...args]);
      const subject = new Subject<any>(); requests.push(subject); return subject;
    },
    getTemplateProbes: (...args: any[]) => {
      calls.push(['read', ...args]);
      const subject = new Subject<any>(); requests.push(subject); return subject;
    },
    getCatalogTemplateCertifications: (...args: any[]) => {
      calls.push(['catalog-read', ...args]);
      const subject = new Subject<any>(); requests.push(subject); return subject;
    },
    prepareCatalogTemplateCertifications: (...args: any[]) => {
      calls.push(['catalog-prepare', ...args]);
      const subject = new Subject<any>(); requests.push(subject); return subject;
    },
  };
  const injector = Injector.create({providers: [
    { provide: MarketingCampaignV2Service, useValue: api },
    { provide: DestroyRef, useValue: { onDestroy: () => () => {} } },
  ]});
  const component = runInInjectionContext(injector, () => new MarketingCampaignV2TemplateProbesComponent());
  component.campaignId = 42; component.templateId = 7;
  component.name.setValue('QA autorizado'); component.phone.setValue('6861000001');
  component.reference.setValue('Autorización interna');
  return { component, requests, calls };
}

test('requires explicit authorization and never dispatches on prepare or refresh', () => {
  const { component, calls, requests } = harness();
  component.prepare(); assert.equal(calls.length, 0);
  component.matrix = { rows: [{ channel_id: 'villa-verde', result: 'RECHAZADA', qa_campaign_id: null }] } as any;
  component.toggleChannel(component.matrix.rows[0], true);
  component.authorized.setValue(true);
  component.prepare(); component.prepare(); // Double click cannot duplicate the HTTP request.
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'prepare');
  assert.equal(calls[0][2].confirmed_authorized, true);
  requests[0].next({ rows: [] });
  assert.equal(component.phone.value, '');
  assert.equal(component.authorized.value, false);
  component.refresh();
  assert.equal(calls[1][0], 'read');
});

test('phone edit revokes authorization and an HTTP error never triggers automatic retry', () => {
  const { component, requests, calls } = harness();
  component.authorized.setValue(true); component.phone.setValue('6861000002');
  assert.equal(component.canPrepare, false);
  component.matrix = { rows: [{ channel_id: 'send-cul', result: 'PENDIENTE', qa_campaign_id: null }] } as any;
  component.toggleChannel(component.matrix.rows[0], true);
  component.authorized.setValue(true); component.prepare();
  requests[0].error({ error: { message: 'Resultado de preparación desconocido' } });
  assert.equal(calls.length, 1);
  assert.equal(component.authorized.value, false);
  assert.match(component.error, /desconocido/);
});

test('changing template discards stale in-flight results', () => {
  const { component, requests } = harness();
  component.refresh(); component.templateId = 8; component.ngOnChanges();
  requests[0].next({ template_id: 7, rows: [] });
  assert.equal(component.matrix, null);
  assert.equal(component.authorized.value, false);
});


test('accepted certification from another campaign disables re-preparation', () => {
  const { component, calls } = harness();
  component.matrix = { rows: [{ result: 'VALIDADA' }] } as any;
  component.authorized.setValue(true);
  assert.equal(component.allCertified, true);
  assert.equal(component.canPrepare, false);
  component.prepare();
  assert.equal(calls.length, 0);
});


test('catalog preparation uses template scope rather than a commercial campaign', () => {
  const { component, calls, requests } = harness();
  component.catalogMode = true;
  component.campaignId = 0;
  component.refresh();
  assert.deepEqual(calls[0], ['catalog-read', 7]);
  requests[0].next({ rows: [{ channel_id: 'send-cul', result: 'PENDIENTE', qa_campaign_id: null }] });
  component.toggleChannel(component.matrix!.rows[0], true);
  component.authorized.setValue(true);
  component.prepare();
  assert.equal(calls[1][0], 'catalog-prepare');
  assert.equal(calls[1][1], 7);
  assert.equal(calls[1][2].confirmed_authorized, true);
  assert.deepEqual(calls[1][2].selected_channel_ids, ['send-cul']);
  assert.equal('campaign_id' in calls[1][2], false);
});

test('only two explicitly selected rejected commercial channels enter QA request', () => {
  const { component, calls, requests } = harness();
  component.catalogMode = true;
  component.refresh();
  requests[0].next({ rows: [
    { channel_id: 'villa', result: 'RECHAZADA', qa_campaign_id: null },
    { channel_id: 'cul', result: 'RECHAZADA', qa_campaign_id: null },
    { channel_id: 'tec', result: 'PENDIENTE', qa_campaign_id: null },
    { channel_id: 'send', result: 'VALIDADA', qa_campaign_id: null },
    { channel_id: 'uncertain', result: 'INCIERTA', qa_campaign_id: null },
  ] });
  component.toggleChannel(component.matrix!.rows[0], true);
  component.toggleChannel(component.matrix!.rows[1], true);
  component.toggleChannel(component.matrix!.rows[3], true);
  component.toggleChannel(component.matrix!.rows[4], true);
  component.authorized.setValue(true);
  assert.deepEqual(component.selectedChannelIds, ['villa', 'cul']);
  component.prepare();
  assert.equal(calls[1][0], 'catalog-prepare');
  assert.deepEqual(calls[1][2].selected_channel_ids, ['villa', 'cul']);
  assert.equal(component.canPrepare, false); // in-flight request blocks duplicates
});

test('empty and changed selection never prepares; changing channels revokes consent', () => {
  const { component, calls } = harness();
  component.matrix = { rows: [
    { channel_id: 'villa', result: 'RECHAZADA', qa_campaign_id: null },
  ] } as any;
  component.authorized.setValue(true);
  component.prepare();
  assert.equal(calls.length, 0);
  component.toggleChannel(component.matrix.rows[0], true);
  assert.equal(component.authorized.value, false);
  component.authorized.setValue(true);
  component.ngOnChanges();
  assert.deepEqual(component.selectedChannelIds, []);
  assert.equal(component.canPrepare, false);
});

test('select all marks only eligible QA channels, supports mixed and unselect all', () => {
  const { component, calls } = harness();
  component.matrix = { rows: [
    { channel_id: 'pending', result: 'PENDIENTE', qa_campaign_id: null },
    { channel_id: 'rejected', result: 'RECHAZADA', qa_campaign_id: null },
    { channel_id: 'invalid', result: 'INVALIDADA', qa_campaign_id: null },
    { channel_id: 'stale-qa', result: 'RECHAZADA', qa_campaign_id: 5, stale: true },
    { channel_id: 'ongoing-qa', result: 'PENDIENTE', qa_campaign_id: 6, stale: false },
    { channel_id: 'certified', result: 'VALIDADA', qa_campaign_id: 7 },
    { channel_id: 'uncertain', result: 'INCIERTA', qa_campaign_id: 8 },
  ] } as any;

  assert.deepEqual(component.selectableChannelIds,
    ['pending', 'rejected', 'invalid', 'stale-qa']);
  assert.equal(component.allSelectableChannelsSelected, false);
  assert.equal(component.someSelectableChannelsSelected, false);
  component.toggleChannel(component.matrix.rows[0], true);
  assert.equal(component.someSelectableChannelsSelected, true);
  component.authorized.setValue(true);
  component.toggleAllChannels(true);
  assert.equal(component.allSelectableChannelsSelected, true);
  assert.equal(component.someSelectableChannelsSelected, false);
  assert.deepEqual(component.selectedChannelIds,
    ['pending', 'rejected', 'invalid', 'stale-qa']);
  assert.equal(component.authorized.value, false);
  assert.equal(calls.length, 0); // Bulk selection never certifies or sends.

  component.authorized.setValue(true);
  component.toggleAllChannels(false);
  assert.deepEqual(component.selectedChannelIds, []);
  assert.equal(component.allSelectableChannelsSelected, false);
  assert.equal(component.authorized.value, false);
  assert.equal(calls.length, 0);
});

test('select all is inert with no eligible channels or while blocked', () => {
  const { component, calls } = harness();
  component.matrix = { rows: [
    { channel_id: 'certified', result: 'VALIDADA', qa_campaign_id: 10 },
    { channel_id: 'inflight', result: 'PENDIENTE', qa_campaign_id: 11, stale: false },
  ] } as any;
  component.toggleAllChannels(true);
  assert.deepEqual(component.selectedChannelIds, []);
  assert.equal(component.selectableChannelIds.length, 0);

  component.matrix = { rows: [
    { channel_id: 'pending', result: 'PENDIENTE', qa_campaign_id: null },
  ] } as any;
  component.busy = true;
  component.toggleAllChannels(true);
  assert.deepEqual(component.selectedChannelIds, []);
  component.busy = false;
  component.disabled = true;
  component.toggleAllChannels(true);
  assert.deepEqual(component.selectedChannelIds, []);
  component.disabled = false;
  component.toggleAllChannels(true);
  assert.deepEqual(component.selectedChannelIds, ['pending']);
  component.ngOnChanges();
  assert.deepEqual(component.selectedChannelIds, []);
  assert.equal(calls.length, 0);
});
