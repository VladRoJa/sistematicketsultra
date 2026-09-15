import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { of } from 'rxjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MarketingCampaignDeliveryComponent } from './marketing-campaign-delivery.component';
import { MarketingCampaignDeliveryService } from './marketing-campaign-delivery.service';


function deliveryDetail() {
  return {
    campaign_id: 10,
    name: 'REACTIVACION_AGOSTO_SEP_2026_01',
    campaign_status: 'EXPORTED' as const,
    delivery: {
      status: 'PARTIALLY_SENT' as const,
      total_branches: 3,
      sent_branches: 1,
      pending_branches: 2,
      total_contacts: 146,
      sent_contacts: 55,
      pending_contacts: 91,
      branches: [
        {
          sucursal: 'INDEPENDENCIA',
          recipient_count: 11,
          sent: false,
          sent_at: null,
          sent_by_user_id: null,
        },
        {
          sucursal: 'TEC MXL',
          recipient_count: 80,
          sent: false,
          sent_at: null,
          sent_by_user_id: null,
        },
        {
          sucursal: 'VILLAS DEL REY',
          recipient_count: 55,
          sent: true,
          sent_at: '2026-09-14T17:15:00+00:00',
          sent_by_user_id: 7,
        },
      ],
    },
  };
}

function setup() {
  const saveRequests: any[] = [];
  const service = {
    getCampaigns: () => of({
      rows: [{
        id: 10,
        name: 'REACTIVACION_AGOSTO_SEP_2026_01',
        status: 'EXPORTED',
        date_from: '2026-08-01',
        date_to: '2026-08-31',
        created_at: '2026-09-14T14:23:00+00:00',
        updated_at: '2026-09-14T14:23:00+00:00',
        exported_at: '2026-09-14T14:30:00+00:00',
        sent_at: null,
        notes: null,
        filters: {},
        recipient_count: 146,
        created_by_user_id: 7,
        created_by_name: 'Vlad',
        recipients: [],
      }],
      limit: 50,
    }),
    getDeliverySummaries: () => of({
      rows: [{
        id: 10,
        delivery: {
          status: 'PARTIALLY_SENT',
          total_branches: 3,
          sent_branches: 1,
          pending_branches: 2,
          total_contacts: 146,
          sent_contacts: 55,
          pending_contacts: 91,
        },
      }],
    }),
    getDelivery: () => of(deliveryDetail()),
    saveDelivery: (_id: number, request: any) => {
      saveRequests.push(request);
      return of({
        ...deliveryDetail(),
        delivery: {
          ...deliveryDetail().delivery,
          sent_branches: 2,
          pending_branches: 1,
          sent_contacts: 66,
          pending_contacts: 80,
          branches: deliveryDetail().delivery.branches.map(branch =>
            branch.sucursal === 'INDEPENDENCIA'
              ? {
                  ...branch,
                  sent: true,
                  sent_at: '2026-09-14T17:15:00+00:00',
                  sent_by_user_id: 7,
                }
              : branch,
          ),
        },
      });
    },
  };
  const injector = Injector.create({providers: [
    {provide: MarketingCampaignDeliveryService, useValue: service},
    {provide: DestroyRef, useValue: {onDestroy: () => () => {}}},
  ]});
  const component = runInInjectionContext(
    injector,
    () => new MarketingCampaignDeliveryComponent(),
  );
  component.ngOnInit();
  component.campaignId.setValue(10);
  return {component, saveRequests};
}


test('pending branches start selected while already sent branches stay historical', () => {
  const {component} = setup();

  assert.equal(component.detail?.delivery.sent_branches, 1);
  assert.equal(component.selectedBranchCount, 2);
  assert.equal(component.selectedContactCount, 91);
  assert.equal(component.allPendingSelected, true);
  assert.equal(component.selectedPending.has('VILLAS DEL REY'), false);
});


test('user can remove exceptions before saving selected branches', () => {
  const {component, saveRequests} = setup();
  const tec = component.pendingBranches.find(branch => branch.sucursal === 'TEC MXL');
  assert.ok(tec);
  component.toggleBranch(tec, false);
  component.sentDate.setValue('2026-09-14');
  component.sentTime.setValue('10:15');

  assert.equal(component.selectedBranchCount, 1);
  assert.equal(component.selectedContactCount, 11);
  assert.equal(component.remainingBranchesAfterSave, 1);

  component.save();

  assert.deepEqual(saveRequests, [{
    sucursales: ['INDEPENDENCIA'],
    sent_at_local: '2026-09-14T10:15:00',
  }]);
  assert.equal(component.detail?.delivery.sent_branches, 2);
  assert.equal(component.detail?.delivery.pending_branches, 1);
  assert.equal(component.selectedPending.has('TEC MXL'), true);
});


test('select all pending can clear and restore the default selection', () => {
  const {component} = setup();

  component.toggleAllPending(false);
  assert.equal(component.selectedBranchCount, 0);
  assert.equal(component.canSave, false);

  component.toggleAllPending(true);
  assert.equal(component.selectedBranchCount, 2);
  assert.equal(component.selectedContactCount, 91);
});
