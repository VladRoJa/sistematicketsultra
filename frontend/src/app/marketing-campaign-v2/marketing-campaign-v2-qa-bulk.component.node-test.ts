import '@angular/compiler';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Injector, runInInjectionContext } from '@angular/core';
import { of, throwError } from 'rxjs';
import { MarketingCampaignV2QaBulkComponent } from './marketing-campaign-v2-qa-bulk.component';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

function harness(opts: {blocked?: boolean; failOnExecute?: boolean; deterministicRejection?: boolean; closeOnExecute?: boolean} = {}) {
  let componentRef: MarketingCampaignV2QaBulkComponent | undefined;
  const calls: string[] = [];
  let submits = 0;
  const api = {
    preflightCampaign: (id: number) => {
      calls.push('preflight:' + id);
      const channel = id === 45 ? 'villa' : 'cul';
      return of({ campaign_id: id, mode: 'IMMEDIATE', ready: !opts.blocked,
        sendable_count: 1, frozen_count: 1, provider_campaign_count: 1,
        template: { id: 7 }, batches: [{
          ready: true, provider_channel_id: channel, recipient_count: 1,
        }],
        dispatch_fingerprint: String(id).padEnd(64, 'a'),
        budget_usd: { status: 'COMPLETE', currency: 'USD',
          quote_fingerprint: String(id).padEnd(64, 'b'), maximum_estimated_usd: '0.0542',
          sendable_recipients: 1 },
        quota: {status: 'REVIEWABLE'},
      });
    },
    getGovernedApproval: (id: number) => { calls.push('get-approval:' + id); return of({ approval: null }); },
    getGovernedMonitor: (id: number) => {
      calls.push('get-monitor:' + id);
      return of({children_count: submits > 0 || calls.some(x => x.startsWith('materialize:'))
          ? 1 : 0,
        children: calls.some(x => x.startsWith('materialize:')) ? [{
          child_id: id + 100, status: 'READY', provider_channel_id: id === 45 ? 'villa' : 'cul',
          needs_manual_review: false,
        }] : [],
        quota: {all_current: true},
        approval: { manifest_digest: 'c'.repeat(64) },
        execution: { status: 'AUTHORIZED' },
      });
    },
    approveGovernedCampaign: (id: number) => {
      calls.push('approve:' + id);
      return of({approval_id: id + 200});
    },
    materializeGovernedCampaign: (id: number) => {
      calls.push('materialize:' + id);
      return of({provider_children: 1});
    },
    getGovernedExecution: (id: number) => {
      calls.push('get-execution:' + id);
      const authorized = calls.includes('authorize:' + id);
      return of({approval_id: id + 200, manifest_digest: 'c'.repeat(64),
        manifest: { batches: [{planned_status: 'READY', recipients: 1}] },
        execution: authorized ? {execution_id: id + 300, status: 'AUTHORIZED'} : null,
      });
    },
    authorizeGovernedCampaign: (id: number) => {
      calls.push('authorize:' + id);
      return of({execution_id: id + 300});
    },
    executeGovernedChild: (id: number, payload: { operator_password: string }) => {
      calls.push('execute:' + id);
      assert.equal(payload.operator_password, 'password123');
      submits++;
      if (opts.closeOnExecute && id === 45) componentRef?.ngOnDestroy();
      if (opts.failOnExecute && id === 45) {
        return throwError(() => ({status: 502, error: {message: 'Resultado incierto'}}));
      }
      if (opts.deterministicRejection && id === 45) {
        return throwError(() => ({status: 502, error: {
          status: 'PROVIDER_ERROR', child_id: 145,
          error_code: 'TEMPLATE_NOT_FOUND', provider_campaign_id: null,
          definitively_not_accepted: true,
        }}));
      }
      return of({status: 'SUBMITTED', child_id: id + 100});
    },
  };
  const injector = Injector.create({providers: [
    {provide: MarketingCampaignV2Service, useValue: api},
  ]});
  const component = runInInjectionContext(injector, () => new MarketingCampaignV2QaBulkComponent());
  componentRef = component;
  component.templateId = 7;
  component.rows = [
    {channel_id: 'villa', sender: 'VILLA_VERDE', result: 'PENDIENTE',
      qa_campaign_id: 45, child_id: null, recipient_phone_masked: '******8369', stale: false},
    {channel_id: 'cul', sender: 'SEND_CUL', result: 'PENDIENTE',
      qa_campaign_id: 46, child_id: null, recipient_phone_masked: '******8369', stale: false},
    {channel_id: 'tec', sender: 'TEC_MXL', result: 'VALIDADA',
      qa_campaign_id: null, child_id: null, stale: false},
  ] as any;
  component.toggle(component.rows[0], true);
  component.toggle(component.rows[1], true);
  return {component, calls};
}

test('review of two existing QAs never calls write or provider', async () => {
  const {component, calls} = harness();
  await component.reviewAll();
  assert.equal(component.reviewed.length, 2);
  assert.equal(component.maximumUsd, '0.1084');
  assert.equal(component.reviewed[0].campaignId, 45);
  assert.equal(component.reviewed[1].campaignId, 46);
  assert.ok(calls.every(x => x.startsWith('preflight:') ||
    x.startsWith('get-approval:') || x.startsWith('get-monitor:')));
  assert.equal(component.canSend, false);
});

test('single confirmation orchestrates distinct audited approvals then 2 guarded sends', async () => {
  const {component, calls} = harness();
  await component.reviewAll();
  component.confirmed.setValue(true);
  component.phrase.setValue('ENVIAR QA 2');
  component.password.setValue('password123');
  await component.sendAll();
  assert.deepEqual(calls.filter(x => x.startsWith('approve:')), ['approve:45', 'approve:46']);
  assert.deepEqual(calls.filter(x => x.startsWith('materialize:')),
    ['materialize:45', 'materialize:46']);
  assert.deepEqual(calls.filter(x => x.startsWith('authorize:')),
    ['authorize:45', 'authorize:46']);
  assert.deepEqual(calls.filter(x => x.startsWith('execute:')), ['execute:45', 'execute:46']);
  assert.equal(component.password.value, '');
  assert.equal(component.results[45], 'ACEPTADA POR IVENTAS');
  assert.equal(component.results[46], 'ACEPTADA POR IVENTAS');
});

test('blocked preflight never approves or sends', async () => {
  const {component, calls} = harness({blocked: true});
  await component.reviewAll();
  assert.equal(component.reviewed.length, 0);
  assert.equal(component.canSend, false);
  assert.equal(calls.some(x => x.startsWith('approve:') || x.startsWith('execute:')), false);
});

test('uncertain provider outcome stops and never sends second QA or retries', async () => {
  const {component, calls} = harness({failOnExecute: true});
  await component.reviewAll();
  component.confirmed.setValue(true);
  component.phrase.setValue(component.sendWord);
  component.password.setValue('password123');
  await component.sendAll();
  assert.deepEqual(calls.filter(x => x.startsWith('execute:')), ['execute:45']);
  assert.equal(component.results[45], 'REQUIERE REVISIÓN');
  assert.equal(component.results[46], 'SIN ENVÍO');
  assert.equal(component.canSend, false);
  assert.equal(component.password.value, '');
});

test('cannot send without explicit confirmation phrase and password', async () => {
  const {component, calls} = harness();
  await component.reviewAll();
  component.confirmed.setValue(true);
  component.password.setValue('password123');
  await component.sendAll();
  assert.equal(calls.some(x => x.startsWith('approve:') || x.startsWith('execute:')), false);
  assert.equal(component.canSend, false);
});


test('confirmed deterministic TEMPLATE_NOT_FOUND continues to other QA exactly once', async () => {
  const {component, calls} = harness({deterministicRejection: true});
  await component.reviewAll();
  component.confirmed.setValue(true);
  component.phrase.setValue(component.sendWord);
  component.password.setValue('password123');
  await component.sendAll();
  assert.deepEqual(calls.filter(x => x.startsWith('execute:')), ['execute:45', 'execute:46']);
  assert.equal(component.results[45], 'RECHAZADA POR IVENTAS');
  assert.equal(component.results[46], 'ACEPTADA POR IVENTAS');
  assert.match(component.notice, /1 aceptadas y 1 rechazadas/);
});


test('closing the modal during first provider POST blocks every subsequent POST', async () => {
  const {component, calls} = harness({closeOnExecute: true});
  await component.reviewAll();
  component.confirmed.setValue(true);
  component.phrase.setValue(component.sendWord);
  component.password.setValue('password123');
  await component.sendAll();
  assert.deepEqual(calls.filter(x => x.startsWith('execute:')), ['execute:45']);
  assert.equal(component.canSend, false);
});


test('single SEND_CHIH QA can be reviewed without starting any send', async () => {
  const {component, calls} = harness();
  component.rows[0] = {channel_id: 'cul', sender: 'SEND_CHIH', result: 'PENDIENTE',
    qa_campaign_id: 45, child_id: null, recipient_phone_masked: '******8369', stale: false} as any;
  component.rows[1] = {channel_id: 'tec', sender: 'TEC_MXL', result: 'VALIDADA',
    qa_campaign_id: null, child_id: null, stale: false} as any;
  component.selected.clear();
  component.toggle(component.rows[0], true);
  assert.equal(component.selected.size, 1);
  assert.equal(component.canReview, true);
  await component.reviewAll();
  assert.equal(component.reviewed.length, 1);
  assert.equal(component.reviewed[0].sender, 'SEND_CHIH');
  assert.equal(component.sendWord, 'ENVIAR QA 1');
  assert.equal(component.maximumUsd, '0.0542');
  assert.equal(component.canSend, false);
  assert.equal(calls.some(x => /^(approve|materialize|authorize|execute):/.test(x)), false);
});

test('single QA still requires explicit consent, phrase and password before provider send', async () => {
  const {component, calls} = harness();
  component.toggle(component.rows[1], false);
  await component.reviewAll();
  assert.equal(component.reviewed.length, 1);
  component.confirmed.setValue(true);
  component.phrase.setValue('ENVIAR QA 1');
  assert.equal(component.canSend, false);
  await component.sendAll();
  assert.equal(calls.some(x => x.startsWith('execute:')), false);
  component.password.setValue('password123');
  assert.equal(component.canSend, true);
  await component.sendAll();
  assert.deepEqual(calls.filter(x => x.startsWith('approve:')), ['approve:45']);
  assert.deepEqual(calls.filter(x => x.startsWith('materialize:')), ['materialize:45']);
  assert.deepEqual(calls.filter(x => x.startsWith('authorize:')), ['authorize:45']);
  assert.deepEqual(calls.filter(x => x.startsWith('execute:')), ['execute:45']);
  assert.equal(component.results[45], 'ACEPTADA POR IVENTAS');
  assert.equal(component.password.value, '');
  assert.equal(component.canSend, false);
});
