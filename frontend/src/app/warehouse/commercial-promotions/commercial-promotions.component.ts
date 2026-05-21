// frontend\src\app\warehouse\commercial-promotions\commercial-promotions.component.ts


import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';

import {
  CommercialPromotionsByBranchItem,
  CommercialPromotionsByMonthItem,
  CommercialPromotionsRankingItem,
  CommercialPromotionsService,
  CommercialPromotionsSummary,
  CommercialPromotionsUnmappedItem,
} from '../services/commercial-promotions.service';

@Component({
  selector: 'app-commercial-promotions',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatTableModule,
    MatTabsModule,
  ],
  templateUrl: './commercial-promotions.component.html',
  styleUrls: ['./commercial-promotions.component.css'],
})
export class CommercialPromotionsComponent implements OnInit {
  loading = false;
  errorMessage = '';

  summary: CommercialPromotionsSummary | null = null;
  rankingItems: CommercialPromotionsRankingItem[] = [];
  byMonthItems: CommercialPromotionsByMonthItem[] = [];
  byBranchItems: CommercialPromotionsByBranchItem[] = [];
  unmappedItems: CommercialPromotionsUnmappedItem[] = [];

  rankingColumns = [
    'commercial_canon',
    'family',
    'meses_con_venta',
    'ingreso_promo',
    'ticket_promedio',
    'porcentaje_sobre_venta_total',
  ];

  byMonthColumns = [
    'mes',
    'ranking_mes',
    'commercial_canon',
    'ingreso_promo',
    'ticket_promedio',
    'porcentaje_sobre_venta_total_mes',
  ];

  byBranchColumns = [
    'sucursal_canon',
    'promo_ganadora',
    'ingreso_promo',
    'ticket_promedio',
    'porcentaje_sobre_venta_total_sucursal',
    'lectura_impacto',
  ];

  unmappedColumns = [
    'descripcion_raw',
    'operaciones',
    'ingreso_total',
    'ticket_promedio',
    'sucursales_detectadas',
    'ultimo_mes_detectado',
  ];

  constructor(
    private readonly commercialPromotionsService: CommercialPromotionsService,
  ) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.errorMessage = '';

    this.commercialPromotionsService.getSummary().subscribe({
      next: (response) => {
        this.summary = response.summary;
        this.loadRanking();
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudo cargar el resumen ejecutivo de promociones.';
      },
    });
  }

  private loadRanking(): void {
    this.commercialPromotionsService.getRanking().subscribe({
      next: (response) => {
        this.rankingItems = response.items;
        this.loadByMonth();
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudo cargar el ranking general de promociones.';
      },
    });
  }

  private loadByMonth(): void {
    this.commercialPromotionsService.getByMonth().subscribe({
      next: (response) => {
        this.byMonthItems = response.items;
        this.loadByBranch();
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudo cargar el top de promociones por mes.';
      },
    });
  }

  private loadByBranch(): void {
    this.commercialPromotionsService.getByBranch().subscribe({
      next: (response) => {
        this.byBranchItems = response.items;
        this.loadUnmapped();
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudo cargar el análisis por sucursal.';
      },
    });
  }

  private loadUnmapped(): void {
    this.commercialPromotionsService.getUnmapped().subscribe({
      next: (response) => {
        this.unmappedItems = response.items;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudieron cargar las descripciones sin clasificar.';
      },
    });
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '-';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatNumber(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '-';
    }

    return new Intl.NumberFormat('es-MX').format(value);
  }

  formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '-';
    }

    return `${value.toFixed(2)}%`;
  }

  formatMonth(value: string | null | undefined): string {
    if (!value) {
      return '-';
    }

    return value.slice(0, 7);
  }

  getWinnerName(): string {
    return this.summary?.winner?.commercial_canon || '-';
  }

  getWinnerIncome(): string {
    return this.formatCurrency(this.summary?.winner?.ingreso_promo);
  }

  getPromoTotalIncome(): string {
    return this.formatCurrency(this.summary?.totals.ingreso_promo_total);
  }

  getPromoTotalPercent(): string {
    return this.formatPercent(this.summary?.totals.porcentaje_promo_total);
  }

  getPeriodLabel(): string {
    if (!this.summary?.period) {
      return '-';
    }

    const firstMonth = this.formatMonth(this.summary.period.first_month);
    const lastMonth = this.formatMonth(this.summary.period.last_month);

    return `${firstMonth} a ${lastMonth}`;
  }

  getImpactLabel(value: string): string {
    if (value === 'impacto_fuerte') {
      return 'Impacto fuerte';
    }

    if (value === 'impacto_medio') {
      return 'Impacto medio';
    }

    return 'Bajo / no concluyente';
  }
}