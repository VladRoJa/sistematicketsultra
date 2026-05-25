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

interface RegionalSummaryCard {
  label: string;
  value: string;
  helper: string;
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
        label: 'Mejor cumplimiento',
        value: complianceLeader
          ? `${complianceLeader.region_label} · ${this.formatPercent(complianceLeader.cumplimiento_ingreso_pct)}`
          : '-',
        helper: 'Eficiencia contra meta FAYCGO.',
      },
      {
        label: 'Mayor ingreso',
        value: incomeLeader
          ? `${incomeLeader.region_label} · ${this.formatMoney(incomeLeader.ingreso_real_total_mtd)}`
          : '-',
        helper: 'Volumen total acumulado.',
      },
      {
        label: 'Más clientes nuevos',
        value: newClientsLeader
          ? `${newClientsLeader.region_label} · ${this.formatInteger(newClientsLeader.clientes_nuevos_real_mtd)}`
          : '-',
        helper: 'Captación acumulada del mes.',
      },
      {
        label: 'Menor cumplimiento',
        value: complianceRisk
          ? `${complianceRisk.region_label} · ${this.formatPercent(complianceRisk.cumplimiento_ingreso_pct)}`
          : '-',
        helper: 'Región que requiere más atención.',
      },
    ];
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

    return `${position} de ${total}`;
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
}