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
