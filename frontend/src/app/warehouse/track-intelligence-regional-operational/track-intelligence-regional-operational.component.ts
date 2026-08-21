import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subject, takeUntil } from 'rxjs';

import {
  TrackGenerationMode,
  TrackRegionalBusinessRule,
  TrackRegionalOperationalBranch,
  TrackRegionalOperationalLimitMetric,
  TrackRegionalOperationalPaceMetric,
  TrackRegionalOperationalPriorityGroup,
  TrackRegionalOperationalPriorityItem,
  TrackRegionalOperationalRegion,
  TrackRegionalOperationalResponse,
  TrackRegionalOperationalTargetMetric,
  TrackRegionalOperationalUsersMetric,
  TrackService,
} from '../../services/track.service';


@Component({
  selector: 'app-track-intelligence-regional-operational',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatExpansionModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './track-intelligence-regional-operational.component.html',
  styleUrls: ['./track-intelligence-regional-operational.component.css'],
})
export class TrackIntelligenceRegionalOperationalComponent
  implements OnInit, OnDestroy {
  data: TrackRegionalOperationalResponse | null = null;
  selectedTrackDate = '';
  selectedRegionKey = '';
  generationMode: TrackGenerationMode = 'manual_preview';
  isLoading = false;
  errorMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly trackService: TrackService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.selectedTrackDate = (
      this.route.snapshot.queryParamMap.get('track_date') ||
      this.getTodayIsoDate()
    );
    this.generationMode = this.normalizeGenerationMode(
      this.route.snapshot.queryParamMap.get('generation_mode'),
    );
    this.selectedRegionKey = (
      this.route.snapshot.queryParamMap.get('region_key') || ''
    ).trim();
    this.loadOperationalDetail();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadOperationalDetail(): void {
    if (!this.selectedTrackDate) {
      this.errorMessage = 'Selecciona una fecha válida.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    this.trackService
      .getRegionalOperationalDetail(
        this.selectedTrackDate,
        this.generationMode,
      )
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.data = response;

          if (
            this.selectedRegionKey &&
            !response.regions.some(
              (region) => region.region_key === this.selectedRegionKey,
            )
          ) {
            this.selectedRegionKey = '';
          }

          this.isLoading = false;
          this.updateUrlQueryParams();
        },
        error: (error) => {
          console.error('Error loading operational regional detail', error);
          this.errorMessage = (
            error?.error?.error ||
            'No se pudo cargar el seguimiento regional.'
          );
          this.isLoading = false;
        },
      });
  }

  goToTrackDashboard(): void {
    this.router.navigate(['/warehouse/track'], {
      queryParams: {
        track_date: this.selectedTrackDate,
        generation_mode: this.generationMode,
      },
    });
  }

  goToBranchOperational(sucursalCanon: string): void {
    this.router.navigate(
      [
        '/warehouse/track-intelligence/branch',
        sucursalCanon,
      ],
      {
        queryParams: {
          track_date: this.selectedTrackDate,
          generation_mode: this.generationMode,
        },
      },
    );
  }

  getPriorityGroups(): TrackRegionalOperationalPriorityGroup[] {
    const groups = this.data?.priorities || [];

    if (!this.selectedRegionKey) {
      return groups;
    }

    return groups.map((group) => ({
      ...group,
      items: group.items.filter(
        (item) => item.region_key === this.selectedRegionKey,
      ),
    }));
  }

  getRegions(): TrackRegionalOperationalRegion[] {
    const regions = this.data?.regions || [];

    if (!this.selectedRegionKey) {
      return regions;
    }

    return regions.filter(
      (region) => region.region_key === this.selectedRegionKey,
    );
  }

  getRegionOptions(): TrackRegionalOperationalRegion[] {
    return this.data?.regions || [];
  }

  onRegionFilterChange(): void {
    this.updateUrlQueryParams();
  }

  getBusinessRules(): TrackRegionalBusinessRule[] {
    return this.data?.business_rules || [];
  }

  hasAnyPriorities(): boolean {
    return this.getPriorityGroups().some((group) => group.items.length > 0);
  }

  getStatusLabel(status: string | null | undefined): string {
    const labels: Record<string, string> = {
      ADELANTADO: 'Adelantado',
      EN_RITMO: 'En ritmo',
      DEBAJO_RITMO: 'Debajo del ritmo',
      META_SUPERADA: 'Meta superada',
      LIMITE_EXCEDIDO: 'Límite excedido',
      DENTRO_LIMITE: 'Dentro del límite',
      SIN_META: 'Sin meta',
      DATOS_INSUFICIENTES: 'Datos insuficientes',
      DEBAJO_META: 'Pendiente de meta',
      INFORMATIVO: 'Informativo',
    };

    return labels[status || ''] || status || '-';
  }

  getStatusClass(status: string | null | undefined): string {
    if (status === 'LIMITE_EXCEDIDO') {
      return 'status status--exceeded';
    }

    if (status === 'DEBAJO_RITMO') {
      return 'status status--lagging';
    }

    if (status === 'ADELANTADO' || status === 'META_SUPERADA') {
      return 'status status--ahead';
    }

    if (status === 'SIN_META' || status === 'DATOS_INSUFICIENTES') {
      return 'status status--muted';
    }

    return 'status status--neutral';
  }

  formatNumber(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '-';
    }

    return Number(value).toLocaleString('es-MX', {
      maximumFractionDigits: 2,
    });
  }

  formatMoney(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '-';
    }

    return Number(value).toLocaleString('es-MX', {
      style: 'currency',
      currency: 'MXN',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
  }

  formatPercent(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '-';
    }

    return `${Number(value).toFixed(1)}%`;
  }

  formatSignedNumber(
    value: string | number | null | undefined,
    suffix = '',
  ): string {
    if (value === null || value === undefined || value === '') {
      return '-';
    }

    const numericValue = Number(value);
    const sign = numericValue > 0 ? '+' : '';
    return `${sign}${numericValue.toFixed(1)}${suffix}`;
  }

  getPriorityMainValue(item: TrackRegionalOperationalPriorityItem): string {
    if (item.metric_key === 'bajas') {
      return (
        `${this.formatNumber(item.actual_mtd)} / límite ` +
        `${this.formatNumber(item.monthly_limit)}`
      );
    }

    return (
      `${this.formatNumber(item.actual_mtd)} / ` +
      `${this.formatNumber(item.expected_mtd)} esperado al corte`
    );
  }

  getPriorityPacePercent(
    item: TrackRegionalOperationalPriorityItem,
  ): number | null {
    if (item.metric_key === 'bajas') {
      return null;
    }

    const actual = this.toFiniteNumber(item.actual_mtd);
    const expected = this.toFiniteNumber(item.expected_mtd);

    if (actual === null || expected === null || expected <= 0) {
      return null;
    }

    return actual / expected * 100;
  }

  getPriorityProgressValue(
    item: TrackRegionalOperationalPriorityItem,
  ): number {
    const progressPercent = item.metric_key === 'bajas'
      ? this.toFiniteNumber(item.limit_usage_pct)
      : this.getPriorityPacePercent(item);

    if (progressPercent === null) {
      return 0;
    }

    return Math.min(Math.max(progressPercent, 0), 100);
  }

  getPriorityProgressLabel(
    item: TrackRegionalOperationalPriorityItem,
  ): string {
    if (item.metric_key === 'bajas') {
      return `${this.formatPercent(item.limit_usage_pct)} del límite consumido`;
    }

    return `${this.formatPercent(this.getPriorityPacePercent(item))} del ritmo esperado`;
  }

  getPriorityMonthlyProgressLabel(
    item: TrackRegionalOperationalPriorityItem,
  ): string | null {
    if (item.metric_key === 'bajas') {
      return null;
    }

    return `${this.formatPercent(item.actual_progress_pct)} de la meta mensual`;
  }

  getPriorityGap(item: TrackRegionalOperationalPriorityItem): string {
    if (item.metric_key === 'bajas') {
      const actual = this.toFiniteNumber(item.actual_mtd);
      const limit = this.toFiniteNumber(item.monthly_limit);

      if (actual === null || limit === null) {
        return '-';
      }

      if (actual > limit) {
        return `Exceso: ${this.formatNumber(actual - limit)}`;
      }

      return (
        `Restan: ${this.formatNumber(Math.max(limit - actual, 0))} ` +
        'antes del límite'
      );
    }

    return `${this.formatSignedNumber(item.gap_pct_points, ' pp')} vs ritmo esperado`;
  }

  private toFiniteNumber(
    value: string | number | null | undefined,
  ): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }

    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : null;
  }

  getPaceSummary(metric: TrackRegionalOperationalPaceMetric): string {
    return (
      `${this.formatPercent(metric.actual_progress_pct)} real / ` +
      `${this.formatPercent(metric.expected_progress_pct)} esperado`
    );
  }

  getPaceGap(metric: TrackRegionalOperationalPaceMetric): string {
    return this.formatSignedNumber(metric.gap_pct_points, ' pp');
  }

  getLimitSummary(metric: TrackRegionalOperationalLimitMetric): string {
    return (
      `${this.formatNumber(metric.actual_mtd)} / ` +
      `${this.formatNumber(metric.monthly_limit)}`
    );
  }

  getTargetSummary(
    metric: TrackRegionalOperationalTargetMetric,
    money = false,
  ): string {
    const formatter = money
      ? this.formatMoney.bind(this)
      : this.formatNumber.bind(this);

    return (
      `${formatter(metric.actual_mtd)} / ` +
      `${formatter(metric.monthly_target)}`
    );
  }

  getUsersSummary(metric: TrackRegionalOperationalUsersMetric): string {
    return (
      `${this.formatNumber(metric.current_users)} actual / ` +
      `${this.formatNumber(metric.projected_close_users)} proyección`
    );
  }

  getIncomeProjectionLabel(
    metric: TrackRegionalOperationalTargetMetric,
  ): string {
    const projection = metric.projection;

    if (!projection || projection.status !== 'available') {
      return 'Proyección: historia insuficiente';
    }

    return `Proyección de cierre: ${this.formatMoney(projection.projected_close)}`;
  }

  trackRegion(
    _index: number,
    region: TrackRegionalOperationalRegion,
  ): string {
    return region.region_key;
  }

  trackBranch(
    _index: number,
    branch: TrackRegionalOperationalBranch,
  ): string {
    return branch.sucursal_canon;
  }

  private normalizeGenerationMode(
    value: string | null,
  ): TrackGenerationMode {
    return value === 'official_closed_day'
      ? 'official_closed_day'
      : 'manual_preview';
  }

  private getTodayIsoDate(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private updateUrlQueryParams(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        track_date: this.selectedTrackDate,
        generation_mode: this.generationMode,
        region_key: this.selectedRegionKey || null,
      },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
