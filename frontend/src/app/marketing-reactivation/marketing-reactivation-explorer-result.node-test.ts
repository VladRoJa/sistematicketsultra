import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { of, Subject } from 'rxjs';

import { MarketingReactivationComponent } from './marketing-reactivation.component';
import { MarketingReactivationService } from './marketing-reactivation.service';


test('explorer campaign creation refreshes history and surfaces success', () => {
  const preview = new Subject<any>();
  const dialogClosed = new Subject<any>();
  let campaignLoads = 0;

  const service = {
    getCampaignOptions: () => of({branches: [], regions: []}),
    getCampaignSourceStatus: () => of({
      business_date: '2026-09-10',
      sources: {
        activos: {cutoff_date: '2026-09-10', age_days: 0, status: 'CURRENT'},
        vencidos: {cutoff_date: '2026-09-09', age_days: 1, status: 'RECENT'},
        iventas: {cutoff_date: '2026-09-10', age_days: 0, status: 'CURRENT'},
      },
    }),
    getCampaigns: () => {
      campaignLoads += 1;
      return of({rows: []});
    },
    previewCampaign: () => preview,
  };
  const dialog = {
    open: () => ({afterClosed: () => dialogClosed}),
  };
  const injector = Injector.create({providers: [
    {provide: MarketingReactivationService, useValue: service},
    {provide: MatDialog, useValue: dialog},
    {provide: DestroyRef, useValue: {onDestroy: () => () => {}}},
  ]});
  const component = runInInjectionContext(
    injector,
    () => new MarketingReactivationComponent(),
  );
  component.ngOnInit();
  assert.equal(campaignLoads, 1);

  component.prepareCampaign();
  preview.next({summary: {eligible: 5}});
  component.openEligibleExplorer();

  dialogClosed.next({
    campaignCreated: {
      id: 88,
      name: 'BCN disponible 500',
      status: 'DRAFT',
      recipient_count: 507,
    },
  });

  assert.equal(
    component.success,
    'Campaña “BCN disponible 500” creada con 507 contactos. Puedes exportarla en el historial.',
  );
  assert.equal(campaignLoads, 2);
});
