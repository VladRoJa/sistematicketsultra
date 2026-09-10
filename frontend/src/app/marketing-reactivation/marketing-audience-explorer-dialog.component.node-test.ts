import '@angular/compiler';
import { DestroyRef, Injector, runInInjectionContext } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { of } from 'rxjs';

import {
  MarketingAudienceExplorerDialogComponent,
  MarketingAudienceExplorerDialogData,
} from './marketing-audience-explorer-dialog.component';
import { MarketingReactivationService } from './marketing-reactivation.service';

function setup(options: {weeklyBlocked?: boolean} = {}) {
  const detailRequests: any[] = [];
  const selectionRequests: any[] = [];
  const createRequests: any[] = [];
  const dialogCloses: any[] = [];
  const data: MarketingAudienceExplorerDialogData = {
    request: {
      filters: {
        campaign_type: 'WINBACK',
        segment: 'WINBACK_30',
      },
    },
    bucket: 'DOMICILIATED_FLOW',
    label: 'Flujo domiciliados',
  };

  const service = {
    previewCampaignDetail: (request: any) => {
      detailRequests.push(request);
      const explorerFilters = request.explorer_filters ?? {};
      const filtered = Object.keys(explorerFilters).length > 0;
      return of({
        bucket: 'DOMICILIATED_FLOW',
        label: 'Flujo domiciliados',
        sources: {},
        total: 2258,
        filtered_total: filtered ? 327 : 2258,
        explorer_filters: explorerFilters,
        filter_options: {
          branches: ['MISION ENS', 'SEND MXL'],
          tariff_categories: ['Domiciliado', 'Recurrente'],
          tariffs: ['DOMICILIADO ANUAL', 'RECURRENTE 799'],
          operational_statuses: ['AVAILABLE', 'CONTACTED_THIS_MONTH'],
        },
        pagination: {
          page: request.page,
          page_size: request.page_size,
          total: filtered ? 327 : 2258,
          total_pages: filtered ? 7 : 46,
          has_prev: request.page > 1,
          has_next: true,
        },
        composition: [],
        operational_counts: {},
        rows: [],
      });
    },
    previewExplorerCampaignSelection: (request: any) => {
      selectionRequests.push(request);
      return of({
        bucket: 'DOMICILIATED_FLOW',
        label: 'Flujo domiciliados',
        bucket_total: 2258,
        filtered_total: 327,
        valid_phone_rows: 325,
        unique_valid_contacts: 324,
        duplicate_phone_rows: 1,
        excluded_by_campaign_rules: 4,
        weekly_limit_contacts: options.weeklyBlocked ? 5 : 0,
        weekly_frequency_decision_required: Boolean(options.weeklyBlocked),
        recipient_count: 320,
        can_create: !options.weeklyBlocked,
        explorer_filters: request.explorer_filters ?? {},
      });
    },
    createCampaignFromExplorer: (request: any) => {
      createRequests.push(request);
      return of({
        campaign: {
          id: 77,
          name: request.name,
          status: 'DRAFT',
          date_from: '2026-08-01',
          date_to: '2026-08-31',
          created_by_user_id: 7,
          created_by_username: 'vlad',
          created_at: '2026-09-10T18:00:00Z',
          updated_at: '2026-09-10T18:00:00Z',
          exported_at: null,
          sent_at: null,
          notes: null,
          filters: data.request.filters,
          recipient_count: 320,
        },
        selection: {
          recipient_count: 320,
        },
      });
    },
  };

  const injector = Injector.create({
    providers: [
      {provide: MarketingReactivationService, useValue: service},
      {provide: MAT_DIALOG_DATA, useValue: data},
      {provide: MatDialogRef, useValue: {close: (value?: any) => dialogCloses.push(value)}},
      {provide: DestroyRef, useValue: {onDestroy: () => () => {}}},
    ],
  });

  const component = runInInjectionContext(
    injector,
    () => new MarketingAudienceExplorerDialogComponent(),
  );
  component.ngOnInit();
  return {
    component,
    detailRequests,
    selectionRequests,
    createRequests,
    dialogCloses,
  };
}

test('initial explorer load keeps the original bucket unfiltered', () => {
  const {component, detailRequests} = setup();

  assert.equal(detailRequests.length, 1);
  assert.deepEqual(detailRequests[0].explorer_filters, {});
  assert.equal(component.result?.total, 2258);
  assert.equal(component.result?.filtered_total, 2258);
  assert.equal(component.hasActiveFilters, false);
  assert.equal(component.filtersDirty, false);
});

test('applying filters sends the exact explorer segment to backend', () => {
  const {component, detailRequests} = setup();

  component.filterForm.controls.sucursal.setValue('MISION ENS');
  component.filterForm.controls.tariffCategory.setValue('Domiciliado');
  component.filterForm.controls.adeudoMin.setValue(500);
  component.filterForm.controls.operationalStatus.setValue('AVAILABLE');
  component.filterForm.controls.suiteHistory.setValue('NEVER');
  component.filterForm.controls.iventasStatus.setValue('DELIVERED');
  assert.equal(component.filtersDirty, true);
  component.applyFilters();

  assert.equal(detailRequests.length, 2);
  assert.deepEqual(detailRequests[1].explorer_filters, {
    sucursal: 'MISION ENS',
    tariff_category: 'Domiciliado',
    adeudo_min: 500,
    operational_status: 'AVAILABLE',
    suite_history: 'NEVER',
    iventas_status: 'DELIVERED',
  });
  assert.equal(detailRequests[1].page, 1);
  assert.equal(component.result?.total, 2258);
  assert.equal(component.result?.filtered_total, 327);
  assert.equal(component.hasActiveFilters, true);
  assert.equal(component.filtersDirty, false);
});

test('pagination preserves the applied explorer filters', () => {
  const {component, detailRequests} = setup();

  component.filterForm.controls.suiteHistory.setValue('TWO_PLUS');
  component.applyFilters();
  component.nextPage();

  assert.equal(detailRequests.length, 3);
  assert.equal(detailRequests[2].page, 2);
  assert.deepEqual(detailRequests[2].explorer_filters, {
    suite_history: 'TWO_PLUS',
  });
});

test('clearing filters returns to the complete bucket', () => {
  const {component, detailRequests} = setup();

  component.filterForm.controls.iventasStatus.setValue('FAILED');
  component.applyFilters();
  component.clearFilters();

  assert.equal(detailRequests.length, 3);
  assert.deepEqual(detailRequests[2].explorer_filters, {});
  assert.equal(component.filterForm.controls.iventasStatus.value, '');
  assert.equal(component.result?.filtered_total, 2258);
  assert.equal(component.hasActiveFilters, false);
  assert.equal(component.filtersDirty, false);
});

test('invalid debt range is rejected before requesting backend', () => {
  const {component, detailRequests} = setup();

  component.filterForm.controls.adeudoMin.setValue(1000);
  component.filterForm.controls.adeudoMax.setValue(500);
  component.applyFilters();

  assert.equal(detailRequests.length, 1);
  assert.equal(
    component.error,
    'El adeudo mínimo no puede ser mayor que el adeudo máximo.',
  );
});

test('preflight uses the exact applied result, not only the visible page', () => {
  const {component, selectionRequests} = setup();

  component.filterForm.controls.adeudoMin.setValue(500);
  component.filterForm.controls.operationalStatus.setValue('AVAILABLE');
  component.applyFilters();
  component.prepareCampaignSelection();

  assert.equal(selectionRequests.length, 1);
  assert.deepEqual(selectionRequests[0], {
    filters: {campaign_type: 'WINBACK', segment: 'WINBACK_30'},
    bucket: 'DOMICILIATED_FLOW',
    explorer_filters: {
      adeudo_min: 500,
      operational_status: 'AVAILABLE',
    },
  });
  assert.equal(component.campaignSelection?.filtered_total, 327);
  assert.equal(component.campaignSelection?.recipient_count, 320);
  assert.equal(component.invalidPhoneRows, 2);
});

test('editing filters after preflight invalidates selection until filters are applied', () => {
  const {component, selectionRequests} = setup();

  component.prepareCampaignSelection();
  assert.ok(component.campaignSelection);
  assert.equal(selectionRequests.length, 1);

  component.filterForm.controls.sucursal.setValue('MISION ENS');

  assert.equal(component.campaignSelection, null);
  assert.equal(component.filtersDirty, true);
  assert.equal(component.canPrepareCampaign, false);
  component.prepareCampaignSelection();
  assert.equal(selectionRequests.length, 1);

  component.applyFilters();
  assert.equal(component.filtersDirty, false);
  assert.equal(component.canPrepareCampaign, true);
});

test('creation sends applied filters and closes with the frozen campaign', () => {
  const {component, createRequests, dialogCloses} = setup();

  component.filterForm.controls.sucursal.setValue('MISION ENS');
  component.applyFilters();
  component.prepareCampaignSelection();
  component.campaignForm.controls.name.setValue('Rescate Misión');
  component.createFilteredCampaign();

  assert.equal(createRequests.length, 1);
  assert.deepEqual(createRequests[0], {
    filters: {campaign_type: 'WINBACK', segment: 'WINBACK_30'},
    bucket: 'DOMICILIATED_FLOW',
    explorer_filters: {sucursal: 'MISION ENS'},
    name: 'Rescate Misión',
  });
  assert.equal(dialogCloses.length, 1);
  assert.equal(dialogCloses[0].campaignCreated.id, 77);
  assert.equal(dialogCloses[0].campaignCreated.recipient_count, 320);
});

test('weekly frequency preflight keeps campaign creation disabled', () => {
  const {component, createRequests} = setup({weeklyBlocked: true});

  component.prepareCampaignSelection();
  component.campaignForm.controls.name.setValue('Segunda pasada');

  assert.equal(component.campaignSelection?.weekly_frequency_decision_required, true);
  assert.equal(component.campaignSelection?.can_create, false);
  assert.equal(component.canCreateFilteredCampaign, false);
  component.createFilteredCampaign();
  assert.equal(createRequests.length, 0);
});