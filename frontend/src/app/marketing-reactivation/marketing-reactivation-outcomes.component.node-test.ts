import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { of } from 'rxjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MarketingReactivationOutcomesComponent } from './marketing-reactivation-outcomes.component';
import { MarketingReactivationService } from './marketing-reactivation.service';


function iventasContext(overrides: Record<string, unknown> = {}) {
  return {
    phone_mx10: '6861000001',
    iventas_contact_found: true,
    iventas_match_status: 'MATCHED',
    iventas_match_count: 1,
    iventas_contact_id: 'contact-1',
    iventas_name: 'Ana CRM',
    iventas_branch_code: 'tecnologico',
    iventas_created_at_local: '2026-09-01T10:00:00',
    iventas_first_message_at_local: '2026-09-01T10:01:00',
    iventas_last_outbound_at_local: '2026-09-10T11:00:00',
    iventas_last_message_status: 'viewed',
    iventas_channel_name: 'Ultra Gym Tecnológico',
    iventas_channel_platform: 'WHATSAPP',
    iventas_agent_name: 'Gerencia TEC',
    iventas_tags: ['Reasignada'],
    iventas_is_from_ads: false,
    iventas_ads_source_id: null,
    iventas_activity_after_send: true,
    ...overrides,
  };
}

function setup() {
  const summaryRequests: any[] = [];
  const detailRequests: number[] = [];
  const service = {
    getCampaignOptions: () => of({
      branches: [
        {key: 'TEC MXL', label: 'TEC MXL'},
        {key: 'SAN LUIS', label: 'SAN LUIS'},
      ],
      regions: [
        {id: 1, label: 'Mexicali / San Luis', branch_keys: ['TEC MXL', 'SAN LUIS']},
      ],
    }),
    getOutcomeSummary: (filters: any) => {
      summaryRequests.push(filters);
      return of({
        date_from: filters.dateFrom ?? null,
        date_to: filters.dateTo ?? null,
        summary: {
          sent: 100,
          reactivated: 12,
          recovered: 12,
          renewals: 5,
          reactivations: 7,
          unclassified_recovered: 0,
          pending: 20,
          review: 3,
          window_closed: 65,
          in_tracking: 23,
          conversion_rate: 12,
        },
        campaigns: [{
          campaign_id: 44,
          name: 'Winback 30',
          campaign_type: 'WINBACK',
          sent_at: '2026-09-10T17:00:00+00:00',
          sent_date_local: '2026-09-10',
          attribution_window_days: 14,
          sent: 100,
          reactivated: 12,
          recovered: 12,
          renewals: 5,
          reactivations: 7,
          unclassified_recovered: 0,
          pending: 20,
          review: 3,
          window_closed: 65,
          in_tracking: 23,
          conversion_rate: 12,
        }],
      });
    },
    getCampaignOutcomes: (id: number) => {
      detailRequests.push(id);
      return of({
        campaign_id: id,
        name: 'Winback 30',
        applicable: true,
        attribution_window_days: 14,
        iventas_source: {
          available: true,
          sync_run_id: 126,
          period_key: 'IVENTAS-2026-09',
          date_from: '2026-09-01',
          date_to: '2026-09-16',
          finished_at: '2026-09-16T20:43:28-07:00',
        },
        summary: {
          sent: 3,
          reactivated: 2,
          recovered: 2,
          renewals: 1,
          reactivations: 1,
          unclassified_recovered: 0,
          pending: 1,
          review: 0,
          window_closed: 0,
          in_tracking: 1,
          conversion_rate: 66.67,
        },
        rows: [
          {
            recipient_id: 1,
            member_name: 'Ana',
            campaign_branch: 'TEC MXL',
            fecha_vencimiento: '2026-09-01',
            status: 'REACTIVATED',
            business_result: 'RENOVACION',
            review_reason: null,
            sent_at: '2026-09-10T17:00:00+00:00',
            sent_at_local: '2026-09-10T10:00:00',
            reactivated_at_local: '2026-09-12T09:30:00',
            days_to_reactivation: 2,
            active_id_socio: '1001',
            active_sucursal: 'SAN LUIS',
            ...iventasContext(),
          },
          {
            recipient_id: 2,
            member_name: 'Luis',
            campaign_branch: 'TEC MXL',
            fecha_vencimiento: '2026-08-31',
            status: 'REACTIVATED',
            business_result: 'REACTIVACION',
            review_reason: null,
            sent_at: '2026-09-10T17:00:00+00:00',
            sent_at_local: '2026-09-10T10:00:00',
            reactivated_at_local: '2026-09-13T09:30:00',
            days_to_reactivation: 3,
            active_id_socio: '1002',
            active_sucursal: 'TEC MXL',
            ...iventasContext({
              phone_mx10: '6861000002',
              iventas_match_status: 'MULTIPLE',
              iventas_match_count: 2,
              iventas_last_message_status: 'delivered',
            }),
          },
          {
            recipient_id: 3,
            member_name: 'Mario',
            campaign_branch: 'TEC MXL',
            fecha_vencimiento: '2026-09-02',
            status: 'PENDING',
            business_result: null,
            review_reason: null,
            sent_at: '2026-09-10T17:00:00+00:00',
            sent_at_local: '2026-09-10T10:00:00',
            reactivated_at_local: null,
            days_to_reactivation: null,
            active_id_socio: null,
            active_sucursal: null,
            ...iventasContext({
              phone_mx10: '6861000003',
              iventas_contact_found: false,
              iventas_match_status: 'NOT_FOUND',
              iventas_match_count: 0,
              iventas_contact_id: null,
              iventas_name: null,
              iventas_last_message_status: null,
              iventas_activity_after_send: null,
              iventas_tags: [],
            }),
          },
        ],
      });
    },
  };
  const injector = Injector.create({providers: [
    {provide: MarketingReactivationService, useValue: service},
    {provide: DestroyRef, useValue: {onDestroy: () => () => {}}},
  ]});
  const component = runInInjectionContext(
    injector,
    () => new MarketingReactivationOutcomesComponent(),
  );
  component.ngOnInit();
  return {component, summaryRequests, detailRequests};
}


test('loads sent/recovered/business breakdown/conversion summary on init', () => {
  const {component, summaryRequests} = setup();

  assert.equal(summaryRequests.length, 1);
  assert.equal(component.result?.summary.sent, 100);
  assert.equal(component.result?.summary.recovered, 12);
  assert.equal(component.result?.summary.renewals, 5);
  assert.equal(component.result?.summary.reactivations, 7);
  assert.equal(component.result?.summary.conversion_rate, 12);
  assert.equal(component.result?.summary.in_tracking, 23);
});


test('region keeps compatible branches and forwards branch scope to summary', () => {
  const {component, summaryRequests} = setup();
  component.filters.controls.regionId.setValue(1);
  component.filters.controls.sucursal.setValue('TEC MXL');
  component.load();

  assert.equal(component.branches.length, 2);
  assert.equal(summaryRequests.at(-1)?.regionId, 1);
  assert.equal(summaryRequests.at(-1)?.sucursal, 'TEC MXL');
});


test('campaign drilldown exposes all sent recipients and filters recovered', () => {
  const {component, detailRequests} = setup();
  component.openCampaign(44);

  assert.deepEqual(detailRequests, [44]);
  assert.equal(component.detail?.campaign_id, 44);
  assert.equal(component.detail?.iventas_source?.sync_run_id, 126);
  assert.equal(component.detailRows.length, 3);
  assert.equal(component.detailRows[0].member_name, 'Ana');
  assert.equal(component.detailRows[0].business_result, 'RENOVACION');

  component.detailStatus.setValue('REACTIVATED');
  assert.equal(component.detailRows.length, 2);
  assert.equal(component.detailRows[1].business_result, 'REACTIVACION');
  assert.equal(component.businessResultLabel(component.detailRows[0].business_result), 'Renovación');
  assert.equal(component.businessResultLabel(component.detailRows[1].business_result), 'Reactivación');

  component.detailStatus.setValue('PENDING');
  assert.equal(component.detailRows.length, 1);
  assert.equal(component.detailRows[0].member_name, 'Mario');
});


test('iVentas helpers keep observation wording separate from campaign delivery claims', () => {
  const {component} = setup();

  assert.equal(component.iventasMatchLabel('MATCHED'), 'Contacto localizado');
  assert.equal(component.iventasMatchLabel('MULTIPLE'), 'Múltiples contactos');
  assert.equal(component.iventasMessageStatusLabel('viewed'), 'Visto');
  assert.equal(component.iventasMessageStatusLabel('failed'), 'Falló');
  assert.equal(component.iventasActivityLabel(true), 'Sí, posterior al envío');
  assert.equal(component.iventasActivityLabel(null), 'Sin dato comparable');
});


test('inverted period is rejected before API call', () => {
  const {component, summaryRequests} = setup();
  component.filters.controls.dateFrom.setValue('2026-09-20');
  component.filters.controls.dateTo.setValue('2026-09-10');
  component.load();

  assert.equal(summaryRequests.length, 1);
  assert.equal(component.error, 'La fecha desde no puede ser posterior a la fecha hasta.');
});
