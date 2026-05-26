// frontend\src\app\warehouse\track-intelligence-regional\track-intelligence-regional.component.ts


import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { Subject, takeUntil } from 'rxjs';

import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  TrackRegionalBranchDetailItem,
  TrackRegionalBusinessRule,
  TrackRegionalDetailRegion,
  TrackRegionalDetailResponse,
  TrackRegionalRankingItem,
  TrackService,

} from '../../services/track.service';

interface RegionalRankingSection {
  key: 'income_compliance' | 'income' | 'new_clients';
  title: string;
  subtitle: string;
  items: TrackRegionalRankingItem[];
  metricType: 'percent' | 'money' | 'integer';
}

type RegionalSummaryCardTone = 'success' | 'warning' | 'danger' | 'neutral';

interface RegionalSummaryCard {
  label: string;
  badge: string;
  regionLabel: string;
  metricValue: string;
  helper: string;
  tone: RegionalSummaryCardTone;
}

@Component({
  selector: 'app-track-intelligence-regional',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatButtonModule,
    MatCardModule,
    MatExpansionModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './track-intelligence-regional.component.html',
  styleUrls: ['./track-intelligence-regional.component.css'],
})
export class TrackIntelligenceRegionalComponent implements OnInit, OnDestroy {
  data: TrackRegionalDetailResponse | null = null;

  selectedTrackDate = '';
  generationMode = 'manual_preview';

  isLoading = false;
  errorMessage = '';

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly trackService: TrackService,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    const queryDate = this.route.snapshot.queryParamMap.get('track_date');
    const queryGenerationMode = this.route.snapshot.queryParamMap.get('generation_mode');

    this.selectedTrackDate = queryDate || this.getTodayIsoDate();
    this.generationMode = queryGenerationMode || 'manual_preview';

    this.loadRegionalDetail();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadRegionalDetail(): void {
    if (!this.selectedTrackDate) {
      this.errorMessage = 'Selecciona una fecha válida.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';

    this.trackService
      .getRegionalDetail(this.selectedTrackDate, this.generationMode as any)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.data = response;
          this.isLoading = false;
          this.updateUrlQueryParams();
        },
        error: (error) => {
          console.error('Error loading regional Track Intelligence detail', error);
          this.errorMessage = 'No se pudo cargar el detalle regional.';
          this.isLoading = false;
        },
      });
  }

    goToTrackDashboard(): void {
    this.router.navigate(['/warehouse/track'], {
        queryParams: {
        track_date: this.selectedTrackDate,
        },
    });
    }

getSummaryCards(): RegionalSummaryCard[] {
  const complianceLeader = this.data?.rankings.income_compliance?.[0] || null;
  const incomeLeader = this.data?.rankings.income?.[0] || null;
  const newClientsLeader = this.data?.rankings.new_clients?.[0] || null;
  const complianceRisk = this.getLastItem(this.data?.rankings.income_compliance || []);

  return [
    {
      label: 'Cumplimiento',
      badge: '1° lugar',
      regionLabel: complianceLeader?.region_label || '-',
      metricValue: this.formatPercent(complianceLeader?.cumplimiento_ingreso_pct),
      helper: 'Eficiencia contra meta FAYCGO.',
      tone: 'success',
    },
    {
      label: 'Ingreso real',
      badge: '1° lugar',
      regionLabel: incomeLeader?.region_label || '-',
      metricValue: this.formatMoney(incomeLeader?.ingreso_real_total_mtd),
      helper: 'Mayor volumen acumulado del mes.',
      tone: 'neutral',
    },
    {
      label: 'Clientes nuevos',
      badge: '1° lugar',
      regionLabel: newClientsLeader?.region_label || '-',
      metricValue: this.formatInteger(newClientsLeader?.clientes_nuevos_real_mtd),
      helper: 'Mayor captación acumulada del mes.',
      tone: 'neutral',
    },
    {
      label: 'Foco de atención',
      badge: 'Menor cumplimiento',
      regionLabel: complianceRisk?.region_label || '-',
      metricValue: this.formatPercent(complianceRisk?.cumplimiento_ingreso_pct),
      helper: 'Región con menor eficiencia relativa contra meta.',
      tone: 'danger',
    },
  ];
}

getSummaryCardClass(card: RegionalSummaryCard): string {
  return `summary-card summary-card--${card.tone}`;
}

  getRankingSections(): RegionalRankingSection[] {
    if (!this.data) {
      return [];
    }

    return [
      {
        key: 'income_compliance',
        title: 'Cumplimiento contra meta',
        subtitle: 'Ranking principal para comparar regiones de distinto tamaño.',
        items: this.data.rankings.income_compliance,
        metricType: 'percent',
      },
      {
        key: 'income',
        title: 'Ingreso real acumulado',
        subtitle: 'Ranking por volumen total acumulado del mes.',
        items: this.data.rankings.income,
        metricType: 'money',
      },
      {
        key: 'new_clients',
        title: 'Clientes nuevos acumulados',
        subtitle: 'Ranking por captación total acumulada.',
        items: this.data.rankings.new_clients,
        metricType: 'integer',
      },
    ];
  }

  getRegions(): TrackRegionalDetailRegion[] {
    return this.data?.regions || [];
  }

  getBusinessRules(): TrackRegionalBusinessRule[] {
    return this.data?.business_rules || [];
  }

  getRankingMetricValue(
    item: TrackRegionalRankingItem,
    metricType: 'percent' | 'money' | 'integer',
  ): string {
    if (metricType === 'percent') {
      return this.formatPercent(item.cumplimiento_ingreso_pct);
    }

    if (metricType === 'money') {
      return this.formatMoney(item.ingreso_real_total_mtd);
    }

    return this.formatInteger(item.clientes_nuevos_real_mtd);
  }

  getRegionCompliancePosition(region: TrackRegionalDetailRegion): string {
    return this.formatPosition(
      region.rankings.income_compliance_position,
      region.rankings.total_regions,
    );
  }

  getRegionIncomePosition(region: TrackRegionalDetailRegion): string {
    return this.formatPosition(
      region.rankings.income_position,
      region.rankings.total_regions,
    );
  }

  getRegionNewClientsPosition(region: TrackRegionalDetailRegion): string {
    return this.formatPosition(
      region.rankings.new_clients_position,
      region.rankings.total_regions,
    );
  }

  formatMoney(value: string | number | null | undefined): string {
    const numericValue = Number(value || 0);

    return numericValue.toLocaleString('es-MX', {
      style: 'currency',
      currency: 'MXN',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  formatPercent(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '-';
    }

    const numericValue = Number(value);

    return `${numericValue.toFixed(2)}%`;
  }

  formatInteger(value: string | number | null | undefined): string {
    const numericValue = Number(value || 0);

    return numericValue.toLocaleString('es-MX', {
      maximumFractionDigits: 0,
    });
  }

  private formatPosition(position: number | null | undefined, total: number): string {
    if (!position) {
      return '-';
    }

    return `${position}° lugar`;
  }

  private getTodayIsoDate(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
  }

  private getLastItem<T>(items: T[]): T | null {
    if (!items.length) {
      return null;
    }

    return items[items.length - 1];
  }

  private updateUrlQueryParams(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        track_date: this.selectedTrackDate,
        generation_mode: this.generationMode,
      },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  getRegionExecutiveReading(region: TrackRegionalDetailRegion): string {
    const total = region.rankings.total_regions;
    const compliancePosition = region.rankings.income_compliance_position;
    const incomePosition = region.rankings.income_position;
    const clientsPosition = region.rankings.new_clients_position;

    return (
      `Esta región va en ${compliancePosition}° lugar de ${total} en cumplimiento, ` +
      `${incomePosition}° lugar en ingreso y ` +
      `${clientsPosition}° lugar en clientes nuevos.`
    );
  }

getRegionInterpretation(region: TrackRegionalDetailRegion): string {
  const total = region.rankings.total_regions;
  const compliancePosition = region.rankings.income_compliance_position || 0;
  const incomePosition = region.rankings.income_position || 0;
  const clientsPosition = region.rankings.new_clients_position || 0;
  const regionalGap = this.getRegionIncomeGap(region);

  const worstGapBranch = this.getWorstIncomeGapBranch(region);
  const bestComplianceBranch = this.getBestComplianceBranch(region);

  if (compliancePosition === 1) {
    return (
      `La región lidera en cumplimiento contra meta. ` +
      `Su mejor referencia interna es ${bestComplianceBranch?.sucursal_name || 'un club destacado'}; ` +
      `conviene identificar qué práctica está empujando ese avance.`
    );
  }

  if (incomePosition === 1 && clientsPosition === 1 && compliancePosition > 1) {
    return (
      `La región lidera en ingreso y clientes nuevos, pero va ${compliancePosition}° de ${total} en cumplimiento contra meta. ` +
      `La brecha regional es ${this.formatSignedMoney(regionalGap)}; el foco debe estar en cerrar diferencia contra meta, ` +
      `especialmente en ${worstGapBranch?.sucursal_name || 'los clubes con mayor brecha'}.`
    );
  }

  if (incomePosition <= 2 && compliancePosition >= 4) {
    return (
      `La región tiene alto volumen de ingreso, pero su cumplimiento contra meta está rezagado. ` +
      `La brecha regional es ${this.formatSignedMoney(regionalGap)}; revisar clubes con meta alta y avance relativo bajo.`
    );
  }

  if (clientsPosition < compliancePosition) {
    return (
      `La captación está mejor posicionada que el cumplimiento de ingreso. ` +
      `Esto puede indicar oportunidad en conversión, ticket promedio, mix de ventas o velocidad de monetización de nuevos clientes.`
    );
  }

  if (compliancePosition >= total) {
    return (
      `Es la región con menor cumplimiento relativo. ` +
      `La prioridad es revisar la brecha contra meta por club; el mayor foco aparece en ` +
      `${worstGapBranch?.sucursal_name || 'el club con mayor diferencia negativa'}.`
    );
  }

  return (
    `La región se mantiene en una posición intermedia. ` +
    `El detalle por club ayuda a separar qué unidades empujan el resultado y cuáles explican la brecha contra meta.`
  );
}

getRegionIncomeGap(region: TrackRegionalDetailRegion): number {
  const ingreso = Number(region.summary.ingreso_real_total_mtd || 0);
  const meta = Number(region.summary.meta_faycgo_mes || 0);

  return ingreso - meta;
}

formatSignedMoney(value: number | null | undefined): string {
  const numericValue = Number(value || 0);
  const formatted = Math.abs(numericValue).toLocaleString('es-MX', {
    style: 'currency',
    currency: 'MXN',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  if (numericValue > 0) {
    return `+${formatted}`;
  }

  if (numericValue < 0) {
    return `-${formatted}`;
  }

  return formatted;
}

getBranchIncomeGap(branch: TrackRegionalBranchDetailItem): number {
  const ingreso = Number(branch.ingreso_real_total_mtd || 0);
  const meta = Number(branch.meta_faycgo_mes || 0);

  return ingreso - meta;
}

getWorstIncomeGapBranch(
  region: TrackRegionalDetailRegion,
): TrackRegionalBranchDetailItem | null {
  if (!region.branches.length) {
    return null;
  }

  return [...region.branches].sort(
    (left, right) => this.getBranchIncomeGap(left) - this.getBranchIncomeGap(right),
  )[0];
}

getBestComplianceBranch(
  region: TrackRegionalDetailRegion,
): TrackRegionalBranchDetailItem | null {
  if (!region.branches.length) {
    return null;
  }

  return [...region.branches].sort(
    (left, right) =>
      Number(right.cumplimiento_ingreso_pct || 0) -
      Number(left.cumplimiento_ingreso_pct || 0),
  )[0];
}

getRegionBranchesForDisplay(
  region: TrackRegionalDetailRegion,
): TrackRegionalBranchDetailItem[] {
  return [...region.branches].sort((left, right) => {
    const rightCompliance = Number(right.cumplimiento_ingreso_pct || 0);
    const leftCompliance = Number(left.cumplimiento_ingreso_pct || 0);

    if (rightCompliance !== leftCompliance) {
      return rightCompliance - leftCompliance;
    }

    const rightIncome = Number(right.ingreso_real_total_mtd || 0);
    const leftIncome = Number(left.ingreso_real_total_mtd || 0);

    return rightIncome - leftIncome;
  });
}

getBranchRegionalRank(
  region: TrackRegionalDetailRegion,
  branch: TrackRegionalBranchDetailItem,
): number {
  const branches = this.getRegionBranchesForDisplay(region);

  const index = branches.findIndex(
    (item) => item.sucursal_canon === branch.sucursal_canon,
  );

  return index >= 0 ? index + 1 : 0;
}

getIncomeGapClass(value: number | null | undefined): string {
  const numericValue = Number(value || 0);

  if (numericValue > 0) {
    return 'income-gap income-gap--positive';
  }

  if (numericValue < 0) {
    return 'income-gap income-gap--negative';
  }

  return 'income-gap income-gap--neutral';
}

getRegionIncomeGapClass(region: TrackRegionalDetailRegion): string {
  return this.getIncomeGapClass(this.getRegionIncomeGap(region));
}

getBranchIncomeGapClass(branch: TrackRegionalBranchDetailItem): string {
  return this.getIncomeGapClass(this.getBranchIncomeGap(branch));
}

getBestComplianceBranchLabel(region: TrackRegionalDetailRegion): string {
  const branch = this.getBestComplianceBranch(region);

  if (!branch) {
    return '-';
  }

  return `${branch.sucursal_name} · ${this.formatPercent(branch.cumplimiento_ingreso_pct)}`;
}

getWorstIncomeGapBranchLabel(region: TrackRegionalDetailRegion): string {
  const branch = this.getWorstIncomeGapBranch(region);

  if (!branch) {
    return '-';
  }

  return `${branch.sucursal_name} · ${this.formatSignedMoney(this.getBranchIncomeGap(branch))}`;
}



}

