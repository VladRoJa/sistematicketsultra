import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
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
  MarketingSalesOriginBreakdown,
} from './marketing-sales-funnel.models';
import { MarketingSalesFunnelService } from './marketing-sales-funnel.service';


interface SalesFunnelCard {
  label: string;
  value: string;
  supportingText: string;
  stepLabel?: string;
}

interface SalesFunnelBranchView extends MarketingSalesFunnelBranch {
  visits_total_display: string;
  visits_iventas_display: string;
  visits_not_iventas_display: string;
  sales_total_display: string;
  sales_iventas_display: string;
  sales_not_iventas_display: string;
  revenue_total_display: string;
  iventas_sale_share_display: string;
}

interface SalesFunnelOriginView extends MarketingSalesOriginBreakdown {
  sales_display: string;
  revenue_display: string;
  share_display: string;
  is_empty: boolean;
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
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTableModule,
    ReactiveFormsModule,
  ],
  templateUrl: './marketing-sales-funnel.component.html',
  styleUrls: ['./marketing-sales-funnel.component.css'],
})
export class MarketingSalesFunnelComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly salesFunnelService = inject(MarketingSalesFunnelService);
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
    'visits_iventas',
    'visits_not_iventas',
    'sales_total',
    'sales_iventas',
    'sales_not_iventas',
    'revenue_total',
    'iventas_sale_share',
  ];

  dashboard: MarketingSalesFunnelResponse | null = null;
  commercialCards: SalesFunnelCard[] = [];
  iventasCards: SalesFunnelCard[] = [];
  conversionCards: SalesFunnelCard[] = [];
  branchRows: SalesFunnelBranchView[] = [];
  originRows: SalesFunnelOriginView[] = [];

  loading = true;
  errorMessage = '';

  get selectedMonth(): string {
    return this.monthControl.value.trim();
  }

  get hasBranches(): boolean {
    return this.branchRows.length > 0;
  }

  get hasOrigins(): boolean {
    return this.originRows.some((row) => row.sales > 0);
  }

  get showOriginEmpty(): boolean {
    return !this.hasOrigins;
  }

  get showBranchEmpty(): boolean {
    return !this.hasBranches;
  }

  get showLoading(): boolean {
    return this.loading;
  }

  get showError(): boolean {
    return !this.loading && Boolean(this.errorMessage);
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

  get matchWindowLabel(): string {
    const days = this.dashboard?.source.match_window_days;
    return days !== undefined ? `${days} días` : '—';
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
        if (!this.isValidMonth(month)) {
          return;
        }
        this.dashboardRequests.next(month.trim());
      });

    this.dashboardRequests.next(this.selectedMonth);
  }

  refreshDashboard(): void {
    this.monthControl.markAsTouched();
    if (this.monthControl.invalid) {
      return;
    }
    this.dashboardRequests.next(this.selectedMonth);
  }

  private applyDashboard(data: MarketingSalesFunnelResponse): void {
    this.dashboard = data;
    this.commercialCards = this.buildCommercialCards(data.summary);
    this.iventasCards = this.buildIventasCards(data.summary);
    this.conversionCards = this.buildConversionCards(data.summary);
    this.branchRows = data.branches.map((branch) =>
      this.buildBranchView(branch),
    );
    this.originRows = data.summary.origin_breakdown.map((origin) =>
      this.buildOriginView(origin, data.summary.sales_total),
    );
  }

  private buildCommercialCards(
    summary: MarketingSalesFunnelMetrics,
  ): SalesFunnelCard[] {
    return [
      {
        stepLabel: '01',
        label: 'Visitas totales',
        value: this.formatInteger(summary.visits_total),
        supportingText: (
          `${this.formatInteger(summary.visits_iventas)} con match iVentas · `
          + `${this.formatInteger(summary.visits_not_iventas)} sin match`
        ),
      },
      {
        stepLabel: '02',
        label: 'Ventas nuevas',
        value: this.formatInteger(summary.sales_total),
        supportingText: (
          `${this.formatInteger(summary.sales_iventas)} pasaron por iVentas · `
          + `${this.formatInteger(summary.sales_not_iventas)} por fallback`
        ),
      },
      {
        stepLabel: '03',
        label: 'Ingreso venta nueva',
        value: this.formatCurrency(summary.revenue_total),
        supportingText: (
          `${this.formatCurrency(summary.revenue_iventas)} iVentas · `
          + `${this.formatCurrency(summary.revenue_not_iventas)} no iVentas`
        ),
      },
    ];
  }

  private buildIventasCards(
    summary: MarketingSalesFunnelMetrics,
  ): SalesFunnelCard[] {
    return [
      {
        stepLabel: '01',
        label: 'Leads Meta',
        value: this.formatInteger(summary.leads_meta),
        supportingText: (
          `${this.formatInteger(summary.iventas_contacts)} contactos iVentas con interacción`
        ),
      },
      {
        stepLabel: '02',
        label: 'Visitas iVentas / Meta',
        value: this.formatInteger(summary.visits_iventas_meta),
        supportingText: (
          `${this.formatInteger(summary.visits_iventas)} visitas iVentas totales`
        ),
      },
      {
        stepLabel: '03',
        label: 'Ventas iVentas / Meta',
        value: this.formatInteger(summary.sales_iventas_meta),
        supportingText: (
          `${this.formatInteger(summary.sales_iventas)} ventas iVentas totales`
        ),
      },
      {
        stepLabel: '04',
        label: 'Ingreso iVentas / Meta',
        value: this.formatCurrency(summary.revenue_iventas_meta),
        supportingText: (
          `${this.formatCurrency(summary.revenue_iventas)} ingreso iVentas total`
        ),
      },
    ];
  }

  private buildConversionCards(
    summary: MarketingSalesFunnelMetrics,
  ): SalesFunnelCard[] {
    return [
      {
        label: 'Lead Meta → visita',
        value: this.formatPercent(summary.meta_lead_to_visit_rate),
        supportingText: 'Lead Meta con visita trazada por teléfono.',
      },
      {
        label: 'Visita Meta → venta',
        value: this.formatPercent(summary.meta_visit_to_sale_rate),
        supportingText: 'Visita iVentas/Meta que termina en venta nueva.',
      },
      {
        label: 'Lead Meta → venta',
        value: this.formatPercent(summary.meta_lead_to_sale_rate),
        supportingText: 'Conversión completa del recorrido Meta trazable.',
      },
      {
        label: 'Visita total → venta',
        value: this.formatPercent(summary.total_visit_to_sale_rate),
        supportingText: 'Conversión comercial de todas las visitas.',
      },
      {
        label: 'Peso iVentas en visitas',
        value: this.formatPercent(summary.iventas_visit_share),
        supportingText: 'Participación de iVentas dentro de las visitas.',
      },
      {
        label: 'Peso iVentas en ventas',
        value: this.formatPercent(summary.iventas_sale_share),
        supportingText: 'Participación de iVentas dentro de la venta nueva.',
      },
    ];
  }

  private buildBranchView(
    branch: MarketingSalesFunnelBranch,
  ): SalesFunnelBranchView {
    return {
      ...branch,
      visits_total_display: this.formatInteger(branch.visits_total),
      visits_iventas_display: this.formatInteger(branch.visits_iventas),
      visits_not_iventas_display: this.formatInteger(branch.visits_not_iventas),
      sales_total_display: this.formatInteger(branch.sales_total),
      sales_iventas_display: this.formatInteger(branch.sales_iventas),
      sales_not_iventas_display: this.formatInteger(branch.sales_not_iventas),
      revenue_total_display: this.formatCurrency(branch.revenue_total),
      iventas_sale_share_display: this.formatPercent(branch.iventas_sale_share),
    };
  }

  private buildOriginView(
    origin: MarketingSalesOriginBreakdown,
    salesTotal: number,
  ): SalesFunnelOriginView {
    return {
      ...origin,
      sales_display: this.formatInteger(origin.sales),
      revenue_display: this.formatCurrency(origin.revenue),
      share_display: this.formatPercent(
        salesTotal > 0 ? origin.sales / salesTotal : null,
      ),
      is_empty: origin.sales === 0,
    };
  }

  private formatInteger(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private formatCurrency(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
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
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
  }

  private buildMonthOptions(): Array<{
    value: string;
    label: string;
  }> {
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
