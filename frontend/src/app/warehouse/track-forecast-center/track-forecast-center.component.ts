import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Router } from '@angular/router';
import { BarChart, LineChart } from 'echarts/charts';
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  LegendScrollComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { provideEchartsCore } from 'ngx-echarts';
import { Subscription } from 'rxjs';

import {
  TrackForecastCenterBreakdownDimension,
  TrackForecastCenterCatalogBranch,
  TrackForecastCenterCatalogRegion,
  TrackForecastCenterCatalogScope,
  TrackForecastCenterCatalogsResponse,
  TrackForecastCenterCohort,
  TrackForecastCenterParams,
  TrackForecastCenterResponse,
  TrackForecastCenterScope,
  TrackGenerationMode,
  TrackService,
} from '../../services/track.service';
import { TrackForecastCenterBreakdownComponent } from '../track-forecast-center-breakdown/track-forecast-center-breakdown.component';
import { TrackForecastCenterMethodologyComponent } from '../track-forecast-center-methodology/track-forecast-center-methodology.component';
import { TrackForecastCenterPaceComponent } from '../track-forecast-center-pace/track-forecast-center-pace.component';
import { TrackForecastCenterSummaryComponent } from '../track-forecast-center-summary/track-forecast-center-summary.component';
import {
  TrackForecastCenterFilterState,
  TrackForecastCenterNavigationEvent,
  TrackForecastCenterView,
} from './track-forecast-center.models';

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  LegendScrollComponent,
  MarkLineComponent,
  AriaComponent,
  CanvasRenderer,
]);

const VIEWS: TrackForecastCenterView[] = ['summary', 'pace', 'breakdown', 'methodology'];
const VIEW_LABELS: Record<TrackForecastCenterView, string> = {
  summary: 'Resumen',
  pace: 'Ritmo y forecast',
  breakdown: 'Desglose',
  methodology: 'Metodología',
};

@Component({
  selector: 'app-track-forecast-center',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    TrackForecastCenterSummaryComponent,
    TrackForecastCenterPaceComponent,
    TrackForecastCenterBreakdownComponent,
    TrackForecastCenterMethodologyComponent,
  ],
  templateUrl: './track-forecast-center.component.html',
  styleUrls: ['./track-forecast-center.component.css'],
  providers: [provideEchartsCore({ echarts })],
})
export class TrackForecastCenterComponent implements OnInit, OnDestroy {
  readonly views = VIEWS;
  readonly viewLabels = VIEW_LABELS;

  catalogs: TrackForecastCenterCatalogsResponse | null = null;
  response: TrackForecastCenterResponse | null = null;
  filters: TrackForecastCenterFilterState = {
    trackDate: this.getTodayIsoDate(),
    generationMode: 'manual_preview',
    scope: 'national',
    scopeId: '',
    cohort: 'all',
    view: 'summary',
    breakdown: 'cohort',
  };
  loadingCatalogs = true;
  loadingData = false;
  errorMessage = '';
  private routeSubscription?: Subscription;
  private requestSubscription?: Subscription;
  private lastCalculationKey = '';

  constructor(
    private readonly trackService: TrackService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loadCatalogs();
  }

  ngOnDestroy(): void {
    this.routeSubscription?.unsubscribe();
    this.requestSubscription?.unsubscribe();
  }

  get scopeOptions(): TrackForecastCenterCatalogScope[] {
    return this.catalogs?.scopes ?? [];
  }

  get regionOptions(): TrackForecastCenterCatalogRegion[] {
    return this.catalogs?.regions ?? [];
  }

  get branchOptions(): TrackForecastCenterCatalogBranch[] {
    return this.catalogs?.branches ?? [];
  }

  get showRegionSelector(): boolean {
    return this.filters.scope === 'region';
  }

  get showCohortSelector(): boolean {
    return this.filters.scope === 'national';
  }

  get showBranchSelector(): boolean {
    return this.filters.scope === 'branch';
  }

  get showBreakdownSelector(): boolean {
    return this.filters.scope === 'national';
  }

  get accessLabel(): string {
    const catalogs = this.catalogs;
    if (!catalogs) {
      return '';
    }
    if (catalogs.context.user_access_scope.is_global) {
      return `Acceso global · ${catalogs.branches.length} sucursales visibles`;
    }
    return `${catalogs.context.user_access_scope.authorized_branch_count} sucursales autorizadas`;
  }

  get qualityNotice(): string {
    if (!this.response) {
      return '';
    }
    const branches = this.response.quality.branches;
    const unavailable = this.response.quality.projection_methods.unavailable.branch_count;
    if (branches.included === branches.selected && unavailable === 0) {
      return '';
    }
    if (unavailable > 0) {
      return `Cobertura de proyección: ${branches.with_projection} de ${branches.selected} sucursales; ${unavailable} sin proyección disponible.`;
    }
    return `Cobertura parcial: ${branches.included} de ${branches.selected} sucursales incluidas.`;
  }

  onCalculationFilterChange(): void {
    this.normalizeDependentFilters();
    this.navigateToFilters();
  }

  selectView(view: TrackForecastCenterView): void {
    if (this.filters.view === view) {
      return;
    }
    this.filters.view = view;
    this.navigateToFilters();
  }

  getGenerationModeLabel(mode: TrackGenerationMode): string {
    return mode === 'manual_preview' ? 'Preview operativo' : 'Cierre oficial';
  }

  getScopeLabel(scope: TrackForecastCenterScope): string {
    const labels: Record<TrackForecastCenterScope, string> = {
      national: 'Nacional',
      region: 'Región',
      authorized_pool: 'Mi pool',
      branch: 'Sucursal',
    };
    return labels[scope];
  }

  handleNavigation(event: TrackForecastCenterNavigationEvent): void {
    const drilldown = event.drilldown;
    if (drilldown.analytic_route) {
      void this.router.navigate([drilldown.analytic_route], {
        queryParams: {
          track_date: this.filters.trackDate,
          generation_mode: this.filters.generationMode,
          return_to: 'forecast-center',
          origin_scope: this.filters.scope,
          origin_scope_id: this.filters.scopeId || null,
          origin_cohort: this.filters.cohort,
          origin_view: event.sourceView,
        },
      });
      return;
    }

    this.filters.scope = drilldown.scope;
    this.filters.scopeId = drilldown.scope_id ?? '';
    this.filters.cohort = drilldown.cohort ?? this.filters.cohort;
    this.filters.breakdown = this.defaultBreakdown(this.filters.scope);
    this.normalizeDependentFilters();
    this.navigateToFilters();
  }

  private loadCatalogs(): void {
    this.loadingCatalogs = true;
    this.errorMessage = '';
    this.trackService.getForecastCenterCatalogs().subscribe({
      next: (catalogs) => {
        this.catalogs = catalogs;
        this.loadingCatalogs = false;
        this.routeSubscription = this.route.queryParamMap.subscribe((params) => {
          const normalized = this.normalizeQueryParams(params, catalogs);
          this.filters = normalized;
          if (!this.queryMatchesState(params, normalized)) {
            this.navigateToFilters(true);
            return;
          }
          this.loadDataIfChanged();
        });
      },
      error: (error: HttpErrorResponse) => {
        this.loadingCatalogs = false;
        this.errorMessage = this.resolveError(error, true);
      },
    });
  }

  private loadDataIfChanged(): void {
    const request = this.buildRequest();
    const calculationKey = JSON.stringify(request);
    if (calculationKey === this.lastCalculationKey) {
      return;
    }

    this.lastCalculationKey = calculationKey;
    this.loadingData = true;
    this.errorMessage = '';
    this.requestSubscription?.unsubscribe();
    this.requestSubscription = this.trackService.getForecastCenter(request).subscribe({
      next: (response) => {
        this.response = response;
        this.loadingData = false;
      },
      error: (error: HttpErrorResponse) => {
        this.loadingData = false;
        this.response = null;
        this.lastCalculationKey = '';
        this.errorMessage = this.resolveError(error, false);
      },
    });
  }

  private buildRequest(): TrackForecastCenterParams {
    return {
      track_date: this.filters.trackDate,
      generation_mode: this.filters.generationMode,
      scope: this.filters.scope,
      scope_id: this.filters.scopeId || null,
      cohort: this.filters.cohort,
      breakdown: this.filters.breakdown,
    };
  }

  private navigateToFilters(replaceUrl = false): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      replaceUrl,
      queryParams: {
        track_date: this.filters.trackDate,
        generation_mode: this.filters.generationMode,
        scope: this.filters.scope,
        scope_id: this.filters.scopeId || null,
        cohort: this.filters.cohort,
        view: this.filters.view,
        breakdown: this.filters.breakdown,
      },
    });
  }

  private normalizeQueryParams(
    params: ParamMap,
    catalogs: TrackForecastCenterCatalogsResponse,
  ): TrackForecastCenterFilterState {
    const defaultScope = catalogs.context.default_scope;
    const requestedScope = params.get('scope') as TrackForecastCenterScope | null;
    const scope = catalogs.scopes.some((item) => item.key === requestedScope)
      ? requestedScope as TrackForecastCenterScope
      : defaultScope;
    const cohort = this.normalizeCohort(scope, params.get('cohort'), catalogs);
    const requestedMode = params.get('generation_mode') as TrackGenerationMode | null;
    const generationMode = catalogs.generation_modes.includes(requestedMode as TrackGenerationMode)
      ? requestedMode as TrackGenerationMode
      : catalogs.context.default_generation_mode;
    const requestedView = params.get('view') as TrackForecastCenterView | null;
    const view = VIEWS.includes(requestedView as TrackForecastCenterView)
      ? requestedView as TrackForecastCenterView
      : 'summary';
    const scopeId = this.normalizeScopeId(scope, params.get('scope_id'), catalogs);
    const breakdown = this.normalizeBreakdown(scope, params.get('breakdown'));
    const trackDate = this.isIsoDate(params.get('track_date'))
      ? params.get('track_date') as string
      : this.getTodayIsoDate();

    return { trackDate, generationMode, scope, scopeId, cohort, view, breakdown };
  }

  private normalizeScopeId(
    scope: TrackForecastCenterScope,
    requestedScopeId: string | null,
    catalogs: TrackForecastCenterCatalogsResponse,
  ): string {
    if (scope === 'region') {
      const region = catalogs.regions.find((item) => item.region_key === requestedScopeId);
      return region?.region_key ?? catalogs.regions[0]?.region_key ?? '';
    }
    if (scope === 'branch') {
      const branch = catalogs.branches.find((item) => item.sucursal_canon === requestedScopeId);
      return branch?.sucursal_canon
        ?? catalogs.context.default_scope_id
        ?? catalogs.branches[0]?.sucursal_canon
        ?? '';
    }
    return '';
  }

  private normalizeBreakdown(
    scope: TrackForecastCenterScope,
    requested: string | null,
  ): TrackForecastCenterBreakdownDimension {
    if (scope === 'national' && (requested === 'cohort' || requested === 'region')) {
      return requested;
    }
    return this.defaultBreakdown(scope);
  }

  private normalizeDependentFilters(): void {
    const catalogs = this.catalogs;
    if (!catalogs) {
      return;
    }
    this.filters.scopeId = this.normalizeScopeId(this.filters.scope, this.filters.scopeId, catalogs);
    this.filters.cohort = this.normalizeCohort(this.filters.scope, this.filters.cohort, catalogs);
    this.filters.breakdown = this.normalizeBreakdown(this.filters.scope, this.filters.breakdown);
  }

  private normalizeCohort(
    scope: TrackForecastCenterScope,
    requested: string | null,
    catalogs: TrackForecastCenterCatalogsResponse,
  ): TrackForecastCenterCohort {
    if (scope !== 'national') {
      return 'all';
    }
    return catalogs.cohorts.some((item) => item.key === requested)
      ? requested as TrackForecastCenterCohort
      : 'all';
  }

  private defaultBreakdown(scope: TrackForecastCenterScope): TrackForecastCenterBreakdownDimension {
    if (scope === 'national') {
      return 'cohort';
    }
    if (scope === 'branch') {
      return 'none';
    }
    return 'branch';
  }

  private queryMatchesState(params: ParamMap, state: TrackForecastCenterFilterState): boolean {
    return params.get('track_date') === state.trackDate
      && params.get('generation_mode') === state.generationMode
      && params.get('scope') === state.scope
      && (params.get('scope_id') ?? '') === state.scopeId
      && params.get('cohort') === state.cohort
      && params.get('view') === state.view
      && params.get('breakdown') === state.breakdown;
  }

  private resolveError(error: HttpErrorResponse, catalogs: boolean): string {
    if (error.status === 403) {
      return 'No tienes acceso a este alcance del Centro de Forecast.';
    }
    if (error.status === 404) {
      return 'No existe una versión Track para la fecha y modo seleccionados.';
    }
    if (error.status === 400) {
      return error.error?.message || 'Los filtros seleccionados no son válidos.';
    }
    return catalogs
      ? 'No fue posible cargar los catálogos del Centro de Forecast.'
      : 'No fue posible cargar el Centro de Forecast.';
  }

  private isIsoDate(value: string | null): boolean {
    return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
  }

  private getTodayIsoDate(): string {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 10);
  }
}
