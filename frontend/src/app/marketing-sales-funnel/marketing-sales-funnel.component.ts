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
  MarketingSalesOriginBreakdown,
} from './marketing-sales-funnel.models';
import {
  MarketingSalesFunnelDetailDialogComponent,
} from './marketing-sales-funnel-detail-dialog.component';
import { MarketingSalesFunnelService } from './marketing-sales-funnel.service';


interface SummaryCard {
  label: string;
  value: string;
  supportingText: string;
  metric: string;
  icon: string;
  tone: 'blue' | 'orange' | 'green' | 'purple';
}

interface StoryNode {
  step: string;
  label: string;
  value: string;
  share: string;
  metric: string;
  icon: string;
  tone: 'primary' | 'trace' | 'fallback' | 'meta' | 'other';
  origin?: string;
}

interface SalesFunnelBranchView extends MarketingSalesFunnelBranch {
  visits_total_display: string;
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
  icon: string;
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
  originRows: SalesFunnelOriginView[] = [];
  fallbackOrigins: SalesFunnelOriginView[] = [];

  officialNode: StoryNode | null = null;
  phoneNode: StoryNode | null = null;
  iventasNode: StoryNode | null = null;
  fallbackNode: StoryNode | null = null;
  metaNode: StoryNode | null = null;
  iventasOtherNode: StoryNode | null = null;

  loading = true;
  errorMessage = '';

  get selectedMonth(): string {
    return this.monthControl.value.trim();
  }

  get hasBranches(): boolean {
    return this.branchRows.length > 0;
  }

  get hasFallbackOrigins(): boolean {
    return this.fallbackOrigins.length > 0;
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

  get funnelNarrative(): string {
    const summary = this.dashboard?.summary;
    if (!summary) {
      return '';
    }

    return `${this.formatInteger(summary.sales_iventas)} pasaron por iVentas · ${this.formatInteger(summary.sales_not_iventas)} por fallback.`;
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

  openStoryNode(node: StoryNode | null): void {
    if (!node) {
      return;
    }
    this.openDetail(node.metric, undefined, node.origin);
  }

  openOriginDetail(row: SalesFunnelOriginView): void {
    this.openDetail('origin', undefined, row.key);
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
    this.buildStoryNodes(data.summary);
    this.branchRows = data.branches.map((branch) => this.buildBranchView(branch));

    const originRows = data.summary.origin_breakdown.map((origin) =>
      this.buildOriginView(origin, data.summary.sales_total),
    );
    this.originRows = originRows;
    this.fallbackOrigins = originRows
      .filter((row) => (
        !row.is_empty
        && row.key !== 'IVENTAS_META'
        && row.key !== 'IVENTAS_OTHER'
      ))
      .sort((left, right) => right.sales - left.sales);
  }

  private buildSummaryCards(summary: MarketingSalesFunnelMetrics): SummaryCard[] {
    return [
      {
        label: 'Visitas totales',
        value: this.formatInteger(summary.visits_total),
        supportingText: 'Pases comerciales detectados en Venta Total',
        metric: 'visits_total',
        icon: 'directions_walk',
        tone: 'blue',
      },
      {
        label: 'Ventas nuevas',
        value: this.formatInteger(summary.sales_total),
        supportingText: 'Universo oficial desde Nuevos Socios Detalle',
        metric: 'sales_total',
        icon: 'groups',
        tone: 'orange',
      },
      {
        label: 'Ingreso Venta Nueva',
        value: this.formatCurrency(summary.revenue_total),
        supportingText: 'Ingreso asociado al universo oficial',
        metric: 'revenue_total',
        icon: 'payments',
        tone: 'green',
      },
      {
        label: 'Ventas iVentas / Meta',
        value: this.formatInteger(summary.sales_iventas_meta),
        supportingText: 'Ventas con evidencia técnica META_AD',
        metric: 'sales_iventas_meta',
        icon: 'campaign',
        tone: 'orange',
      },
      {
        label: 'Ingreso iVentas / Meta',
        value: this.formatCurrency(summary.revenue_iventas_meta),
        supportingText: 'Ingreso atribuido técnicamente a Meta Ads',
        metric: 'revenue_iventas_meta',
        icon: 'paid',
        tone: 'purple',
      },
    ];
  }

  private buildStoryNodes(summary: MarketingSalesFunnelMetrics): void {
    const total = summary.sales_total;
    const withPhone = Math.max(0, total - summary.sales_without_valid_phone);

    this.officialNode = this.createStoryNode(
      '01',
      'Venta Nueva Oficial',
      total,
      total,
      'sales_total',
      'groups',
      'primary',
    );
    this.phoneNode = this.createStoryNode(
      '02',
      'Con teléfono utilizable',
      withPhone,
      total,
      'sales_with_phone',
      'phone_in_talk',
      'primary',
    );
    this.iventasNode = this.createStoryNode(
      '03',
      'Con Match iVentas',
      summary.sales_iventas,
      total,
      'sales_iventas',
      'link',
      'trace',
    );
    this.fallbackNode = this.createStoryNode(
      '04',
      'Sin Match iVentas',
      summary.sales_not_iventas,
      total,
      'sales_not_iventas',
      'person',
      'fallback',
    );
    this.metaNode = this.createStoryNode(
      '05',
      'Meta Ads trazable',
      summary.sales_iventas_meta,
      total,
      'sales_iventas_meta',
      'campaign',
      'meta',
    );
    this.iventasOtherNode = this.createStoryNode(
      '06',
      'iVentas / Otro',
      summary.sales_iventas_other,
      total,
      'origin',
      'account_tree',
      'other',
      'IVENTAS_OTHER',
    );
  }

  private createStoryNode(
    step: string,
    label: string,
    value: number,
    total: number,
    metric: string,
    icon: string,
    tone: StoryNode['tone'],
    origin?: string,
  ): StoryNode {
    return {
      step,
      label,
      value: this.formatInteger(value),
      share: this.formatPercent(total > 0 ? value / total : null),
      metric,
      icon,
      tone,
      origin,
    };
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
      icon: this.resolveOriginIcon(origin.key),
    };
  }

  private resolveOriginIcon(originKey: string): string {
    const icons: Record<string, string> = {
      IVENTAS_META: 'campaign',
      IVENTAS_OTHER: 'account_tree',
      SOCIAL_UNTRACED: 'alternate_email',
      REFERRAL: 'groups',
      PROXIMITY: 'location_on',
      PLAZA: 'storefront',
      OFFLINE: 'description',
      OTHER_SURVEY: 'more_horiz',
      UNKNOWN: 'help_outline',
    };
    return icons[originKey] || 'label';
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
