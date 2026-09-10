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

function setup() {
  const requests: any[] = [];
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
      requests.push(request);
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
  };

  const injector = Injector.create({
    providers: [
      {provide: MarketingReactivationService, useValue: service},
      {provide: MAT_DIALOG_DATA, useValue: data},
      {provide: MatDialogRef, useValue: {close: () => undefined}},
      {provide: DestroyRef, useValue: {onDestroy: () => () => {}}},
    ],
  });

  const component = runInInjectionContext(
    injector,
    () => new MarketingAudienceExplorerDialogComponent(),
  );
  component.ngOnInit();
  return {component, requests};
}

test('initial explorer load keeps the original bucket unfiltered', () => {
  const {component, requests} = setup();

  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].explorer_filters, {});
  assert.equal(component.result?.total, 2258);
  assert.equal(component.result?.filtered_total, 2258);
  assert.equal(component.hasActiveFilters, false);
});

test('applying filters sends the exact explorer segment to backend', () => {
  const {component, requests} = setup();

  component.filterForm.controls.sucursal.setValue('MISION ENS');
  component.filterForm.controls.tariffCategory.setValue('Domiciliado');
  component.filterForm.controls.adeudoMin.setValue(500);
  component.filterForm.controls.operationalStatus.setValue('AVAILABLE');
  component.filterForm.controls.suiteHistory.setValue('NEVER');
  component.filterForm.controls.iventasStatus.setValue('DELIVERED');
  component.applyFilters();

  assert.equal(requests.length, 2);
  assert.deepEqual(requests[1].explorer_filters, {
    sucursal: 'MISION ENS',
    tariff_category: 'Domiciliado',
    adeudo_min: 500,
    operational_status: 'AVAILABLE',
    suite_history: 'NEVER',
    iventas_status: 'DELIVERED',
  });
  assert.equal(requests[1].page, 1);
  assert.equal(component.result?.total, 2258);
  assert.equal(component.result?.filtered_total, 327);
  assert.equal(component.hasActiveFilters, true);
});

test('pagination preserves the applied explorer filters', () => {
  const {component, requests} = setup();

  component.filterForm.controls.suiteHistory.setValue('TWO_PLUS');
  component.applyFilters();
  component.nextPage();

  assert.equal(requests.length, 3);
  assert.equal(requests[2].page, 2);
  assert.deepEqual(requests[2].explorer_filters, {
    suite_history: 'TWO_PLUS',
  });
});

test('clearing filters returns to the complete bucket', () => {
  const {component, requests} = setup();

  component.filterForm.controls.iventasStatus.setValue('FAILED');
  component.applyFilters();
  component.clearFilters();

  assert.equal(requests.length, 3);
  assert.deepEqual(requests[2].explorer_filters, {});
  assert.equal(component.filterForm.controls.iventasStatus.value, '');
  assert.equal(component.result?.filtered_total, 2258);
  assert.equal(component.hasActiveFilters, false);
});

test('invalid debt range is rejected before requesting backend', () => {
  const {component, requests} = setup();

  component.filterForm.controls.adeudoMin.setValue(1000);
  component.filterForm.controls.adeudoMax.setValue(500);
  component.applyFilters();

  assert.equal(requests.length, 1);
  assert.equal(
    component.error,
    'El adeudo mínimo no puede ser mayor que el adeudo máximo.',
  );
});
