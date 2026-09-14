import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { of } from 'rxjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MarketingReactivationOutcomesComponent } from './marketing-reactivation-outcomes.component';
import { MarketingReactivationService } from './marketing-reactivation.service';


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
        summary: {
          sent: 2,
          reactivated: 1,
          pending: 1,
          review: 0,
          window_closed: 0,
          in_tracking: 1,
          conversion_rate: 50,
        },
        rows: [
          {
            recipient_id: 1,
            member_name: 'Ana',
            campaign_branch: 'TEC MXL',
            fecha_vencimiento: '2026-09-01',
            status: 'REACTIVATED',
            review_reason: null,
            sent_at: '2026-09-10T17:00:00+00:00',
            sent_at_local: '2026-09-10T10:00:00',
            reactivated_at_local: '2026-09-12T09:30:00',
            days_to_reactivation: 2,
            active_id_socio: '1001',
            active_sucursal: 'SAN LUIS',
          },
          {
            recipient_id: 2,
            member_name: 'Luis',
            campaign_branch: 'TEC MXL',
            fecha_vencimiento: '2026-09-02',
            status: 'PENDING',
            review_reason: null,
            sent_at: '2026-09-10T17:00:00+00:00',
            sent_at_local: '2026-09-10T10:00:00',
            reactivated_at_local: null,
            days_to_reactivation: null,
            active_id_socio: null,
            active_sucursal: null,
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


test('loads sent/reactivated/conversion summary on init', () => {
  const {component, summaryRequests} = setup();

  assert.equal(summaryRequests.length, 1);
  assert.equal(component.result?.summary.sent, 100);
  assert.equal(component.result?.summary.reactivated, 12);
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


test('campaign drilldown exposes only attributed reactivations', () => {
  const {component, detailRequests} = setup();
  component.openCampaign(44);

  assert.deepEqual(detailRequests, [44]);
  assert.equal(component.detail?.campaign_id, 44);
  assert.equal(component.reactivatedRows.length, 1);
  assert.equal(component.reactivatedRows[0].member_name, 'Ana');
  assert.equal(component.reactivatedRows[0].days_to_reactivation, 2);
  assert.equal(component.reactivatedRows[0].active_sucursal, 'SAN LUIS');
});


test('inverted period is rejected before API call', () => {
  const {component, summaryRequests} = setup();
  component.filters.controls.dateFrom.setValue('2026-09-20');
  component.filters.controls.dateTo.setValue('2026-09-10');
  component.load();

  assert.equal(summaryRequests.length, 1);
  assert.equal(component.error, 'La fecha desde no puede ser posterior a la fecha hasta.');
});
