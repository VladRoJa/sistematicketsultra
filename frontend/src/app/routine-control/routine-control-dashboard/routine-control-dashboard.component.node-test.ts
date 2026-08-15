import '@angular/compiler';
import { FormBuilder } from '@angular/forms';
import { HttpParams, HttpResponse } from '@angular/common/http';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { of } from 'rxjs';
import {
  RoutineControlCatalogs,
  RoutineControlFilters,
  RoutineControlMembersResponse,
  RoutineControlSummary,
} from '../models/routine-control.models';
import { RoutineControlService } from '../services/routine-control.service';
import {
  RoutineControlDashboardComponent,
} from './routine-control-dashboard.component';

const catalogs: RoutineControlCatalogs = {
  scope: {
    scope_type: 'GLOBAL',
    allowed_branch_ids: [],
    fixed_branch_id: null,
  },
  branches: [],
  regions: [],
  statuses: [],
  assignment_types: [],
  instructors: [],
};

const summary: RoutineControlSummary = {
  filters_applied: {},
  total_members: 0,
  classified_members: 0,
  incident_members: 0,
  status_counts: {
    SIN_RUTINA: 0,
    CON_RUTINA: 0,
    NO_DESEA_RUTINA: 0,
    INCIDENT: 0,
  },
  assignment_type_counts: {
    PREEXISTENTE: 0,
    MISMO_DIA: 0,
    POSTERIOR: 0,
    SIN_EVIDENCIA: 0,
  },
  branches: [],
  freshness: {
    last_successful_pipeline_at_utc: null,
    last_gasca_success_at_utc: null,
    last_trainingym_success_at_utc: null,
  },
};

const members: RoutineControlMembersResponse = {
  items: [],
  page: 1,
  page_size: 25,
  total: 0,
  total_pages: 0,
};

class RoutineControlServiceStub {
  readonly summaryFilters: RoutineControlFilters[] = [];
  readonly memberFilters: RoutineControlFilters[] = [];
  readonly exportFilters: RoutineControlFilters[] = [];

  getCatalogs() {
    return of(catalogs);
  }

  getSummary(filters: RoutineControlFilters) {
    this.summaryFilters.push({ ...filters });
    return of(summary);
  }

  getMembers(filters: RoutineControlFilters) {
    this.memberFilters.push({ ...filters });
    return of(members);
  }

  exportMembers(filters: RoutineControlFilters) {
    this.exportFilters.push({ ...filters });
    return of(new HttpResponse<Blob>());
  }

  downloadExport(): void {}
}

function createDashboard(service = new RoutineControlServiceStub()) {
  const component = new RoutineControlDashboardComponent(
    new FormBuilder(),
    service as unknown as RoutineControlService,
    { navigate: () => undefined } as never,
    { open: () => undefined } as never,
  );

  return { component, service };
}

test('formatPaymentTime convierte UTC a hora civil de America/Tijuana', () => {
  const { component } = createDashboard();

  assert.equal(
    component.formatPaymentTime(
      '2026-08-15T18:37:24+00:00',
    ),
    '11:37:24',
  );

  assert.equal(
    component.formatPaymentTime(null),
    '—',
  );
});

test('initializeCurrentMonthRange configura del primer día al día actual de Tijuana', () => {
  const { component } = createDashboard();

  component.initializeCurrentMonthRange(
    new Date('2026-07-28T19:00:00Z'),
  );

  assert.equal(
    component.form.controls.sale_date_from.value,
    '2026-07-01',
  );
  assert.equal(
    component.form.controls.sale_date_to.value,
    '2026-07-28',
  );
});

test('la primera carga usa el rango inicial y exportMembers reutiliza ese rango', () => {
  const RealDate = Date;
  const fixedNow = new RealDate('2026-07-28T19:00:00Z');

  globalThis.Date = class extends RealDate {
    constructor(value?: string | number | Date) {
      super(value === undefined ? fixedNow.getTime() : value);
    }

    static override now(): number {
      return fixedNow.getTime();
    }
  } as DateConstructor;

  try {
    const { component, service } = createDashboard();

    component.ngOnInit();
    component.exportMembers();

    assert.equal(service.summaryFilters.length, 1);
    assert.equal(service.memberFilters.length, 1);
    assert.deepEqual(
      {
        from: service.summaryFilters[0].sale_date_from,
        to: service.summaryFilters[0].sale_date_to,
      },
      { from: '2026-07-01', to: '2026-07-28' },
    );
    assert.deepEqual(
      {
        from: service.memberFilters[0].sale_date_from,
        to: service.memberFilters[0].sale_date_to,
      },
      { from: '2026-07-01', to: '2026-07-28' },
    );
    assert.deepEqual(
      {
        from: service.exportFilters[0].sale_date_from,
        to: service.exportFilters[0].sale_date_to,
      },
      { from: '2026-07-01', to: '2026-07-28' },
    );

    component.ngOnDestroy();
  } finally {
    globalThis.Date = RealDate;
  }
});

test('paginar conserva un rango elegido por el usuario', () => {
  const { component, service } = createDashboard();
  component.ngOnInit();
  component.form.patchValue({
    sale_date_from: '2026-01-15',
    sale_date_to: '2026-03-31',
  }, { emitEvent: false });

  component.pageChanged({
    pageIndex: 1,
    pageSize: 50,
    length: 0,
    previousPageIndex: 0,
  });

  const lastSummaryFilters =
    service.summaryFilters.at(-1);
  const lastMemberFilters =
    service.memberFilters.at(-1);
  assert.equal(
    lastSummaryFilters?.sale_date_from,
    '2026-01-15',
  );
  assert.equal(
    lastSummaryFilters?.sale_date_to,
    '2026-03-31',
  );
  assert.equal(
    lastMemberFilters?.sale_date_from,
    '2026-01-15',
  );
  assert.equal(
    lastMemberFilters?.sale_date_to,
    '2026-03-31',
  );

  component.ngOnDestroy();
});

test('el borde UTC usa la fecha civil de America/Tijuana sin desplazarla', () => {
  const { component } = createDashboard();

  component.initializeCurrentMonthRange(
    new Date('2026-08-01T06:30:00Z'),
  );

  assert.equal(
    component.form.controls.sale_date_from.value,
    '2026-07-01',
  );
  assert.equal(
    component.form.controls.sale_date_to.value,
    '2026-07-31',
  );
});

test('el servicio serializa las fechas sin transformarlas y exportación omite solo paginación', () => {
  let receivedParams = new HttpParams();
  const http = {
    get: (
      _url: string,
      options: { params: HttpParams },
    ) => {
      receivedParams = options.params;
      return of(new HttpResponse<Blob>());
    },
  };
  const service = new RoutineControlService(
    http as never,
  );

  service.exportMembers({
    sale_date_from: '2026-07-01',
    sale_date_to: '2026-07-28',
    page: 3,
    page_size: 50,
    search: 'socio',
  }).subscribe();

  assert.equal(
    receivedParams.get('sale_date_from'),
    '2026-07-01',
  );
  assert.equal(
    receivedParams.get('sale_date_to'),
    '2026-07-28',
  );
  assert.equal(receivedParams.get('search'), 'socio');
  assert.equal(receivedParams.has('page'), false);
  assert.equal(receivedParams.has('page_size'), false);
});
