import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  Subject,
  catchError,
  distinctUntilChanged,
  map,
  of,
  switchMap,
} from 'rxjs';

import {
  MarketingSalesFunnelBranch,
  MarketingSalesFunnelMetrics,
  MarketingSalesFunnelResponse,
} from './marketing-sales-funnel.models';
import {
  MarketingSalesFunnelDetailDialogComponent,
} from './marketing-sales-funnel-detail-dialog.component';
import {
  MarketingSalesFunnelStoryComponent,
} from './marketing-sales-funnel-story.component';
import { MarketingSalesFunnelService } from './marketing-sales-funnel.service';


interface SummaryCard {
  label: string;
  value: string;
  supportingText: string;
  metric: string;
  icon: string;
  cssClass: string;
}

interface SalesFunnelBranchView extends MarketingSalesFunnelBranch {
  visits_total_display: string;
  sales_total_display: string;
  sales_iventas_display: string;
  sales_not_iventas_display: string;
  revenue_total_display: string;
  iventas_sale_share_display: string;
}

type DashboardRequestResult =
  | {
      requestId: number;
      status: 'success';
      data: MarketingSalesFunnelResponse;
    }
  | {
      requestId: number;
      status: 'error';
      error: HttpErrorResponse;
    };


@Component({
  selector: 'app-marketing-sales-funnel',
  standalone: true,
  imports: [
    CommonModule,
    MarketingSalesFunnelStoryComponent,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTableModule,
    MatTooltipModule,
    ReactiveFormsModule,
  ],
  templateUrl: './marketing-sales-funnel.component.html',
  styleUrls: ['./marketing-sales-funnel.component.css'],
})
export class MarketingSalesFunnelComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly salesFunnelService = inject(MarketingSalesFunnelService);
  private readonly dialog = inject(MatDialog);
  private readonly dashboardRequests = new Subject<string>();
  private dashboardRequestId = 0;

  readonly monthControl = new FormControl(this.resolveCurrentMonth(), {
    nonNullable: true,
    validators: [
      Validators.required,
      Validators.pattern(/^\d{4}-\d{2}$/),
    ],
  });

  readonly monthOptions = this.buildMonthOptions();
  readonly branchColumns = [
    'sucursal',
    'visits_total',
    'sales_total',
    'sales_iventas',
    'sales_not_iventas',
    'revenue_total',
    'iventas_sale_share',
    'actions',
  ];

  dashboard: MarketingSalesFunnelResponse | null = null;
  summaryCards: SummaryCard[] = [];
  branchRows: SalesFunnelBranchView[] = [];

  loading = true;
  errorMessage = '';

  get selectedMonth(): string {
    return this.monthControl.value.trim();
  }

  get hasBranches(): boolean {
    return this.branchRows.length > 0;
  }

  get showDashboard(): boolean {
    return !this.loading && !this.errorMessage && this.dashboard !== null;
  }

  get refreshDisabled(): boolean {
    return this.loading || this.monthControl.invalid;
  }

  get hasLimitations(): boolean {
    return Boolean(this.dashboard?.data_quality.limitations.length);
  }

  get ventaTotalCutoffLabel(): string {
    const value = this.dashboard?.source.venta_total_business_date;
    return value ? this.formatDate(value) : 'Sin snapshot';
  }

  get newSalesCutoffLabel(): string {
    const value = this.dashboard?.source.ventas_nuevos_socios_detalle_business_date;
    return value ? this.formatDate(value) : 'Sin snapshot';
  }

  get kpiCutoffLabel(): string {
    const value = this.dashboard?.source.kpi_desempeno_business_date;
    return value ? this.formatDate(value) : 'Sin snapshot';
  }

  get matchWindowLabel(): string {
    const days = this.dashboard?.source.match_window_days;
    return days !== undefined ? `${days} días` : '—';
  }

  get reconciliationLabel(): string {
    const detail = this.dashboard?.data_quality.new_sales_detail_count;
    const kpi = this.dashboard?.data_quality.kpi_new_sales_control;
    const difference = this.dashboard?.data_quality.new_sales_vs_kpi_difference;

    if (detail === undefined || kpi === undefined || kpi === null) {
      return 'Sin control disponible';
    }

    const sign = (difference || 0) > 0 ? '+' : '';
    return `Detalle ${this.formatInteger(detail)} · KPI ${this.formatInteger(kpi)} · ${sign}${difference || 0}`;
  }

  ngOnInit(): void {
    this.dashboardRequests
      .pipe(
        switchMap((month) => {
          const requestId = ++this.dashboardRequestId;
          this.loading = true;
          this.errorMessage = '';

          return this.salesFunnelService.getDashboard(month).pipe(
            map(
              (data): DashboardRequestResult => ({
                requestId,
                status: 'success',
                data,
              }),
            ),
            catchError((error: HttpErrorResponse) =>
              of<DashboardRequestResult>({
                requestId,
                status: 'error',
                error,
              }),
            ),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if (result.requestId !== this.dashboardRequestId) {
          return;
        }

        this.loading = false;

        if (result.status === 'error') {
          this.errorMessage = this.resolveErrorMessage(result.error);
          return;
        }

        this.applyDashboard(result.data);
      });

    this.monthControl.valueChanges
      .pipe(
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((month) => {
        if (this.isValidMonth(month)) {
          this.dashboardRequests.next(month.trim());
        }
      });

    this.dashboardRequests.next(this.selectedMonth);
  }

  refreshDashboard(): void {
    this.monthControl.markAsTouched();
    if (!this.monthControl.invalid) {
      this.dashboardRequests.next(this.selectedMonth);
    }
  }

  openDetail(
    metric: string,
    branchId?: number,
    origin?: string,
  ): void {
    if (!metric) {
      return;
    }

    this.dialog.open(MarketingSalesFunnelDetailDialogComponent, {
      data: {
        month: this.selectedMonth,
        metric,
        branchId,
        origin,
      },
      width: '96vw',
      maxWidth: '1600px',
      height: '88vh',
      maxHeight: '920px',
      autoFocus: false,
      restoreFocus: true,
    });
  }

  openBranchDetail(metric: string, row: SalesFunnelBranchView): void {
    this.openDetail(metric, row.sucursal_id);
  }

  formatCurrency(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private applyDashboard(data: MarketingSalesFunnelResponse): void {
    this.dashboard = data;
    this.summaryCards = this.buildSummaryCards(data.summary);
    this.branchRows = data.branches.map((branch) => this.buildBranchView(branch));
  }

  private buildSummaryCards(summary: MarketingSalesFunnelMetrics): SummaryCard[] {
    return [
      {
        label: 'Visitas totales',
        value: this.formatInteger(summary.visits_total),
        supportingText: 'Pases comerciales detectados en Venta Total',
        metric: 'visits_total',
        icon: 'directions_walk',
        cssClass: 'summary-kpi--blue',
      },
      {
        label: 'Ventas nuevas',
        value: this.formatInteger(summary.sales_total),
        supportingText: 'Universo desde Nuevos Socios Detalle',
        metric: 'sales_total',
        icon: 'groups',
        cssClass: 'summary-kpi--orange',
      },
      {
        label: 'Ingreso Venta Nueva',
        value: this.formatCurrency(summary.revenue_total),
        supportingText: 'Ingreso asociado al universo de Venta Nueva',
        metric: 'revenue_total',
        icon: 'payments',
        cssClass: 'summary-kpi--green',
      },
      {
        label: 'Ventas por publicaciones',
        value: this.formatInteger(summary.sales_iventas_meta),
        supportingText: 'Ventas iVentas con evidencia de publicidad',
        metric: 'sales_iventas_meta',
        icon: 'campaign',
        cssClass: 'summary-kpi--orange',
      },
      {
        label: 'Ingreso por publicaciones',
        value: this.formatCurrency(summary.revenue_iventas_meta),
        supportingText: 'Ingreso atribuido a publicidad en iVentas',
        metric: 'revenue_iventas_meta',
        icon: 'paid',
        cssClass: 'summary-kpi--purple',
      },
    ];
  }

  private buildBranchView(branch: MarketingSalesFunnelBranch): SalesFunnelBranchView {
    return {
      ...branch,
      visits_total_display: this.formatInteger(branch.visits_total),
      sales_total_display: this.formatInteger(branch.sales_total),
      sales_iventas_display: this.formatInteger(branch.sales_iventas),
      sales_not_iventas_display: this.formatInteger(branch.sales_not_iventas),
      revenue_total_display: this.formatCurrency(branch.revenue_total),
      iventas_sale_share_display: this.formatPercent(branch.iventas_sale_share),
    };
  }

  private formatInteger(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private formatPercent(value: number | null): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

  private formatDate(value: string): string {
    const [year, month, day] = value.split('-').map(Number);
    const parsed = new Date(year, month - 1, day);

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(parsed);
  }

  private resolveCurrentMonth(): string {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }

  private buildMonthOptions(): Array<{ value: string; label: string }> {
    const firstMonth = new Date(2026, 6, 1);
    const currentMonth = new Date();
    const formatter = new Intl.DateTimeFormat('es-MX', {
      month: 'long',
      year: 'numeric',
    });
    const options: Array<{ value: string; label: string }> = [];
    const cursor = new Date(
      currentMonth.getFullYear(),
      currentMonth.getMonth(),
      1,
    );

    while (cursor >= firstMonth) {
      const year = cursor.getFullYear();
      const month = String(cursor.getMonth() + 1).padStart(2, '0');
      const formatted = formatter.format(cursor);
      options.push({
        value: `${year}-${month}`,
        label: formatted.charAt(0).toUpperCase() + formatted.slice(1),
      });
      cursor.setMonth(cursor.getMonth() - 1);
    }

    return options;
  }

  private isValidMonth(value: string): boolean {
    return /^\d{4}-\d{2}$/.test(value.trim());
  }

  private resolveErrorMessage(error: HttpErrorResponse): string {
    const backendMessage = error.error?.message;
    if (typeof backendMessage === 'string' && backendMessage.trim()) {
      return backendMessage.trim();
    }
    if (error.status === 0) {
      return 'No fue posible conectar con el backend.';
    }
    return 'No fue posible cargar el Funnel de Venta Total.';
  }
}
