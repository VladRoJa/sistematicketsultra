import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ElementRef,
  OnInit,
  ViewChild,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
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
  MarketingSalesFunnelDetailResponse,
  MarketingSalesFunnelDetailRow,
  MarketingSalesFunnelMetrics,
  MarketingSalesFunnelResponse,
  MarketingSalesOriginBreakdown,
} from './marketing-sales-funnel.models';
import { MarketingSalesFunnelService } from './marketing-sales-funnel.service';


interface FunnelStage {
  step: string;
  label: string;
  value: string;
  explanation: string;
  share: string;
  width: number;
  metric: string;
  icon: string;
}

interface ContextMetric {
  label: string;
  value: string;
  supportingText: string;
  metric?: string;
  icon: string;
}

interface SalesFunnelBranchView extends MarketingSalesFunnelBranch {
  leads_meta_display: string;
  visits_total_display: string;
  visits_iventas_display: string;
  sales_total_display: string;
  sales_iventas_display: string;
  sales_iventas_meta_display: string;
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

interface DetailQuery {
  metric: string;
  branchId?: number;
  origin?: string;
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
    MatTooltipModule,
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
  private detailRequestId = 0;
  private detailQuery: DetailQuery | null = null;

  @ViewChild('detailSection')
  private detailSection?: ElementRef<HTMLElement>;

  readonly detailPageSize = 50;

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
    'leads_meta',
    'visits_total',
    'visits_iventas',
    'sales_total',
    'sales_iventas',
    'sales_iventas_meta',
    'sales_not_iventas',
    'revenue_total',
    'iventas_sale_share',
  ];

  readonly detailSalesColumns = [
    'branch',
    'date',
    'name',
    'pin',
    'phone',
    'tariff',
    'revenue',
    'origin',
    'survey',
    'transaction_branch',
  ];
  readonly detailVisitColumns = [
    'branch',
    'date',
    'phone',
    'origin',
    'source',
  ];
  readonly detailLeadColumns = [
    'branch',
    'date',
    'name',
    'phone',
    'channel',
    'contact_id',
  ];

  dashboard: MarketingSalesFunnelResponse | null = null;
  funnelStages: FunnelStage[] = [];
  contextMetrics: ContextMetric[] = [];
  traceMetrics: ContextMetric[] = [];
  branchRows: SalesFunnelBranchView[] = [];
  originRows: SalesFunnelOriginView[] = [];

  detail: MarketingSalesFunnelDetailResponse | null = null;
  detailRows: MarketingSalesFunnelDetailRow[] = [];
  detailColumns: string[] = [];
  detailLoading = false;
  detailError = '';

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

  get detailCanGoPrevious(): boolean {
    return Boolean(this.detail && this.detail.page > 1 && !this.detailLoading);
  }

  get detailCanGoNext(): boolean {
    return Boolean(
      this.detail
      && this.detail.total_pages > 0
      && this.detail.page < this.detail.total_pages
      && !this.detailLoading,
    );
  }

  get detailRangeLabel(): string {
    if (!this.detail || this.detail.count === 0) {
      return '0 registros';
    }

    const start = (this.detail.page - 1) * this.detail.page_size + 1;
    const end = Math.min(
      this.detail.page * this.detail.page_size,
      this.detail.count,
    );
    return `${this.formatInteger(start)}–${this.formatInteger(end)} de ${this.formatInteger(this.detail.count)}`;
  }

  ngOnInit(): void {
    this.dashboardRequests
      .pipe(
        switchMap((month) => {
          const requestId = ++this.dashboardRequestId;
          this.loading = true;
          this.errorMessage = '';
          this.closeDetail();

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
    if (!metric || this.detailLoading) {
      return;
    }

    this.detailQuery = { metric, branchId, origin };
    this.detail = null;
    this.detailRows = [];
    this.detailColumns = [];
    this.loadDetailPage(1, true);
  }

  openOriginDetail(row: SalesFunnelOriginView): void {
    this.openDetail('origin', undefined, row.key);
  }

  openBranchDetail(metric: string, row: SalesFunnelBranchView): void {
    this.openDetail(metric, row.sucursal_id);
  }

  goToDetailPage(page: number): void {
    if (
      !this.detail
      || this.detailLoading
      || page < 1
      || page > this.detail.total_pages
      || page === this.detail.page
    ) {
      return;
    }

    this.loadDetailPage(page, true);
  }

  closeDetail(): void {
    this.detailRequestId += 1;
    this.detailQuery = null;
    this.detail = null;
    this.detailRows = [];
    this.detailColumns = [];
    this.detailLoading = false;
    this.detailError = '';
  }

  formatCurrency(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private loadDetailPage(page: number, scroll: boolean): void {
    if (!this.detailQuery) {
      return;
    }

    const requestId = ++this.detailRequestId;
    const query = this.detailQuery;
    this.detailLoading = true;
    this.detailError = '';

    this.salesFunnelService
      .getDetail(
        this.selectedMonth,
        query.metric,
        query.branchId,
        query.origin,
        page,
        this.detailPageSize,
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (detail) => {
          if (requestId !== this.detailRequestId) {
            return;
          }
          this.detailLoading = false;
          this.detail = detail;
          this.detailRows = detail.rows;
          this.detailColumns = this.resolveDetailColumns(detail.kind);
          if (scroll) {
            this.scrollToDetail();
          }
        },
        error: (error: HttpErrorResponse) => {
          if (requestId !== this.detailRequestId) {
            return;
          }
          this.detailLoading = false;
          this.detailError = this.resolveDetailError(error);
          if (scroll) {
            this.scrollToDetail();
          }
        },
      });
  }

  private applyDashboard(data: MarketingSalesFunnelResponse): void {
    this.dashboard = data;
    this.funnelStages = this.buildFunnelStages(data.summary);
    this.contextMetrics = this.buildContextMetrics(data.summary);
    this.traceMetrics = this.buildTraceMetrics(data.summary);
    this.branchRows = data.branches.map((branch) => this.buildBranchView(branch));
    this.originRows = data.summary.origin_breakdown.map((origin) =>
      this.buildOriginView(origin, data.summary.sales_total),
    );
  }

  private buildFunnelStages(summary: MarketingSalesFunnelMetrics): FunnelStage[] {
    const total = summary.sales_total;
    const withPhone = Math.max(0, total - summary.sales_without_valid_phone);

    return [
      this.createFunnelStage(
        '01',
        'Venta nueva oficial',
        total,
        total,
        'Filas de Ventas Nuevos Socios Detalle. KPI Desempeño funciona como control agregado.',
        'sales_total',
        'groups',
      ),
      this.createFunnelStage(
        '02',
        'Con teléfono utilizable',
        withPhone,
        total,
        'Socios cuya fila permite intentar un cruce técnico por teléfono.',
        'sales_with_phone',
        'phone_in_talk',
      ),
      this.createFunnelStage(
        '03',
        'Con match iVentas',
        summary.sales_iventas,
        total,
        'Teléfono exacto, misma sucursal KPI y evidencia iVentas previa dentro de la ventana.',
        'sales_iventas',
        'link',
      ),
      this.createFunnelStage(
        '04',
        'Meta Ads trazable',
        summary.sales_iventas_meta,
        total,
        'El match iVentas más reciente conserva evidencia META_AD.',
        'sales_iventas_meta',
        'campaign',
      ),
    ];
  }

  private createFunnelStage(
    step: string,
    label: string,
    value: number,
    total: number,
    explanation: string,
    metric: string,
    icon: string,
  ): FunnelStage {
    const ratio = total > 0 ? value / total : 0;
    return {
      step,
      label,
      value: this.formatInteger(value),
      explanation,
      share: this.formatPercent(total > 0 ? ratio : null),
      width: Math.max(38, Math.min(100, ratio * 100)),
      metric,
      icon,
    };
  }

  private buildContextMetrics(summary: MarketingSalesFunnelMetrics): ContextMetric[] {
    return [
      {
        label: 'Leads Meta',
        value: this.formatInteger(summary.leads_meta),
        supportingText: `${this.formatInteger(summary.iventas_contacts)} contactos iVentas con interacción`,
        metric: 'leads_meta',
        icon: 'ads_click',
      },
      {
        label: 'Visitas comerciales',
        value: this.formatInteger(summary.visits_total),
        supportingText: 'Pases de recorrido / 2 días detectados en Venta Total',
        metric: 'visits_total',
        icon: 'directions_walk',
      },
      {
        label: 'Visitas con iVentas',
        value: this.formatInteger(summary.visits_iventas),
        supportingText: `${this.formatInteger(summary.visits_iventas_meta)} con evidencia Meta`,
        metric: 'visits_iventas',
        icon: 'link',
      },
      {
        label: 'Sin match iVentas',
        value: this.formatInteger(summary.sales_not_iventas),
        supportingText: 'La clasificación de origen cae a Encuesta de Venta Total',
        metric: 'sales_not_iventas',
        icon: 'fact_check',
      },
    ];
  }

  private buildTraceMetrics(summary: MarketingSalesFunnelMetrics): ContextMetric[] {
    return [
      {
        label: 'Lead Meta con visita trazada',
        value: this.formatPercent(summary.meta_lead_to_visit_rate),
        supportingText: 'Visitas Meta trazables / leads Meta.',
        icon: 'route',
      },
      {
        label: 'Lead Meta con venta atribuida',
        value: this.formatPercent(summary.meta_lead_to_sale_rate),
        supportingText: 'Ventas Meta atribuidas / leads Meta. No exige pase previo.',
        icon: 'shopping_cart_checkout',
      },
      {
        label: 'Cobertura iVentas en visitas',
        value: this.formatPercent(summary.iventas_visit_share),
        supportingText: 'Visitas con match iVentas / visitas comerciales.',
        icon: 'visibility',
      },
      {
        label: 'Cobertura iVentas en venta nueva',
        value: this.formatPercent(summary.iventas_sale_share),
        supportingText: 'Ventas con match iVentas / venta nueva oficial.',
        icon: 'filter_alt',
      },
    ];
  }

  private buildBranchView(branch: MarketingSalesFunnelBranch): SalesFunnelBranchView {
    return {
      ...branch,
      leads_meta_display: this.formatInteger(branch.leads_meta),
      visits_total_display: this.formatInteger(branch.visits_total),
      visits_iventas_display: this.formatInteger(branch.visits_iventas),
      sales_total_display: this.formatInteger(branch.sales_total),
      sales_iventas_display: this.formatInteger(branch.sales_iventas),
      sales_iventas_meta_display: this.formatInteger(branch.sales_iventas_meta),
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

  private resolveDetailColumns(kind: string): string[] {
    if (kind === 'visits') {
      return this.detailVisitColumns;
    }
    if (kind === 'leads') {
      return this.detailLeadColumns;
    }
    return this.detailSalesColumns;
  }

  private scrollToDetail(): void {
    setTimeout(() => {
      this.detailSection?.nativeElement.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    });
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

  private resolveDetailError(error: HttpErrorResponse): string {
    const backendMessage = error.error?.message;
    if (typeof backendMessage === 'string' && backendMessage.trim()) {
      return backendMessage.trim();
    }
    return 'No fue posible cargar el detalle que compone este indicador.';
  }
}
