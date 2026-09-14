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

import { MarketingDashboardResponse } from '../marketing-conversion/marketing.models';
import { MarketingService } from '../marketing-conversion/marketing.service';
import {
  MarketingSalesFunnelBranch,
  MarketingSalesFunnelMetrics,
  MarketingSalesFunnelResponse,
  MarketingSalesFunnelScopeOption,
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
  metric: string | null;
  icon: string;
  cssClass: string;
  secondaryLabel?: string;
  secondaryValue?: string;
}

interface SalesFunnelBranchView extends MarketingSalesFunnelBranch {
  investment_display: string;
  leads_meta_display: string;
  visits_total_display: string;
  visits_iventas_display: string;
  visits_not_iventas_display: string;
  sales_total_display: string;
  sales_iventas_display: string;
  sales_iventas_meta_display: string;
  sales_iventas_other_display: string;
  sales_not_iventas_display: string;
  revenue_total_display: string;
  cost_per_lead_display: string;
  cost_per_visit_display: string;
  cost_per_sale_display: string;
  lead_to_visit_display: string;
  iventas_visit_conversion_rate_display: string;
  not_iventas_visit_conversion_rate_display: string;
  iventas_sale_share_display: string;
}

interface DashboardRequest {
  month: string;
  branchIds: number[];
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
  styleUrls: [
    './marketing-sales-funnel.component.css',
    './marketing-sales-funnel-branch-table.component.css',
  ],
})
export class MarketingSalesFunnelComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly salesFunnelService = inject(MarketingSalesFunnelService);
  private readonly marketingService = inject(MarketingService);
  private readonly dialog = inject(MatDialog);
  private readonly dashboardRequests = new Subject<DashboardRequest>();
  private dashboardRequestId = 0;

  readonly monthControl = new FormControl(this.resolveCurrentMonth(), {
    nonNullable: true,
    validators: [
      Validators.required,
      Validators.pattern(/^\d{4}-\d{2}$/),
    ],
  });
  readonly regionControl = new FormControl<number | null>(null);
  readonly branchControl = new FormControl<number | null>(null);

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
  scopeOptions: MarketingSalesFunnelScopeOption[] = [];
  regionOptions: Array<{ id: number; label: string }> = [];
  branchOptions: MarketingSalesFunnelScopeOption[] = [];
  activeScopeBranchIds: number[] = [];

  /* POLISH: investment dashboard */
  investmentDashboard: MarketingDashboardResponse | null = null;
  /* END POLISH: investment dashboard */

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
        switchMap((dashboardRequest) => {
          const requestId = ++this.dashboardRequestId;
          this.loading = true;
          this.errorMessage = '';

          return this.salesFunnelService
            .getDashboard(dashboardRequest.month, dashboardRequest.branchIds)
            .pipe(
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
          this.requestInvestmentDashboard();
          this.requestDashboard();
        }
      });

    this.regionControl.valueChanges
      .pipe(
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((regionId) => {
        this.branchControl.setValue(null, { emitEvent: false });
        this.refreshBranchOptions(regionId);
        this.refreshActiveScopeBranchIds();
        this.requestDashboard();
      });

    this.branchControl.valueChanges
      .pipe(
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((branchId) => {
        this.syncRegionToBranch(branchId);
        this.refreshActiveScopeBranchIds();
        this.requestDashboard();
      });
    this.requestInvestmentDashboard();
    this.requestDashboard();
  }

  refreshDashboard(): void {
    this.monthControl.markAsTouched();
    if (!this.monthControl.invalid) {
      this.requestInvestmentDashboard();
      this.requestDashboard();
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
        branchIds: this.activeScopeBranchIds,
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


  /* POLISH: investment scope methods */
  private requestInvestmentDashboard(): void {
    const month = this.selectedMonth;

    this.marketingService
      .getDashboard(month)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          if (month !== this.selectedMonth) {
            return;
          }

          this.investmentDashboard = data;

          if (this.dashboard) {
            this.summaryCards = this.buildSummaryCards(
              this.dashboard.summary,
            );
            this.refreshBranchRows();
          }
        },
        error: () => {
          if (month !== this.selectedMonth) {
            return;
          }

          this.investmentDashboard = null;

          if (this.dashboard) {
            this.summaryCards = this.buildSummaryCards(
              this.dashboard.summary,
            );
            this.refreshBranchRows();
          }
        },
      });
  }

  private resolveIventasCost(): number | null {
    const dashboard = this.investmentDashboard;

    if (!dashboard || dashboard.month !== this.selectedMonth) {
      return null;
    }

    if (this.activeScopeBranchIds.length === 0) {
      return dashboard.summary.investment;
    }

    const allowedIds = new Set(this.activeScopeBranchIds);

    const scopedBranches = dashboard.branches.filter(
      (branch) => allowedIds.has(branch.sucursal_id),
    );

    const availableInvestments = scopedBranches
      .map((branch) => branch.investment)
      .filter(
        (investment): investment is number =>
          investment !== null && investment !== undefined,
      );

    if (availableInvestments.length === 0) {
      return null;
    }

    return availableInvestments.reduce(
      (total, investment) => total + investment,
      0,
    );
  }
  /* END POLISH: investment scope methods */
  private requestDashboard(): void {
    if (this.monthControl.invalid) {
      return;
    }
    this.dashboardRequests.next({
      month: this.selectedMonth,
      branchIds: this.activeScopeBranchIds,
    });
  }

  private applyDashboard(data: MarketingSalesFunnelResponse): void {
    this.dashboard = data;
    this.scopeOptions = data.scope_options || [];
    this.refreshRegionOptions();
    this.refreshBranchOptions(this.regionControl.value);
    this.refreshActiveScopeBranchIds();
    this.summaryCards = this.buildSummaryCards(data.summary);
    this.refreshBranchRows();
  }

  private refreshRegionOptions(): void {
    const regions = new Map<number, string>();
    for (const option of this.scopeOptions) {
      if (option.region_id !== null && option.region) {
        regions.set(option.region_id, option.region);
      }
    }

    this.regionOptions = Array.from(regions.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((left, right) => left.label.localeCompare(right.label, 'es'));
  }

  private refreshBranchOptions(regionId: number | null): void {
    this.branchOptions = this.scopeOptions
      .filter((option) => regionId === null || option.region_id === regionId)
      .slice()
      .sort((left, right) => left.sucursal.localeCompare(right.sucursal, 'es'));
  }

  private syncRegionToBranch(branchId: number | null): void {
    if (branchId === null) {
      return;
    }

    const branch = this.scopeOptions.find(
      (option) => option.sucursal_id === branchId,
    );
    if (!branch) {
      return;
    }

    const regionId = branch.region_id;
    if (this.regionControl.value !== regionId) {
      this.regionControl.setValue(regionId, { emitEvent: false });
    }
    this.refreshBranchOptions(regionId);
  }

  private refreshActiveScopeBranchIds(): void {
    const branchId = this.branchControl.value;
    if (branchId !== null) {
      this.activeScopeBranchIds = [branchId];
      return;
    }

    const regionId = this.regionControl.value;
    if (regionId === null) {
      this.activeScopeBranchIds = [];
      return;
    }

    this.activeScopeBranchIds = this.branchOptions.map(
      (option) => option.sucursal_id,
    );
  }

  private buildSummaryCards(summary: MarketingSalesFunnelMetrics): SummaryCard[] {
    const investment = this.resolveIventasCost();

    const costPerLead = (
      investment !== null
      && summary.leads_meta > 0
    )
      ? investment / summary.leads_meta
      : null;

    const costPerSale = (
      investment !== null
      && summary.sales_iventas > 0
    )
      ? investment / summary.sales_iventas
      : null;

    return [
      {
        label: 'Inversión',
        value: investment !== null
          ? this.formatCurrency(investment)
          : 'Sin corte',
        supportingText: 'Inversión del alcance',
        metric: null,
        icon: 'account_balance_wallet',
        cssClass: 'summary-kpi--purple',
      },
      {
        label: 'Leads iVentas',
        value: this.formatInteger(summary.leads_meta),
        supportingText: 'Leads canónicos identificados por iVentas',
        metric: 'leads_meta',
        icon: 'phone_in_talk',
        cssClass: 'summary-kpi--blue',
        secondaryLabel: 'Costo por lead',
        secondaryValue: costPerLead !== null
          ? this.formatCurrency(costPerLead)
          : '—',
      },
      {
        label: 'Ventas iVentas',
        value: this.formatInteger(summary.sales_iventas),
        supportingText: `${this.formatPercent(summary.iventas_sale_share)} de Venta Nueva`,
        metric: 'sales_iventas',
        icon: 'point_of_sale',
        cssClass: 'summary-kpi--orange',
        secondaryLabel: 'Costo por venta',
        secondaryValue: costPerSale !== null
          ? this.formatCurrency(costPerSale)
          : '—',
      },
      {
        label: 'Venta por publicaciones',
        value: this.formatInteger(summary.sales_iventas_meta),
        supportingText: 'Ventas trazadas a publicidad',
        metric: 'sales_iventas_meta',
        icon: 'campaign',
        cssClass: 'summary-kpi--orange',
        secondaryLabel: 'Costo por venta',
        secondaryValue: (
          investment !== null
          && summary.sales_iventas_meta > 0
        )
          ? this.formatCurrency(
              investment / summary.sales_iventas_meta,
            )
          : '—',
      },
      {
        label: 'Orgánico',
        value: this.formatInteger(summary.sales_iventas_other),
        supportingText: 'Ventas iVentas sin evidencia Meta',
        metric: 'sales_iventas_other',
        icon: 'eco',
        cssClass: 'summary-kpi--green',
        secondaryLabel: 'Inversión plantillas',
        secondaryValue: '—',
      },
    ];
  }

  private refreshBranchRows(): void {
    if (!this.dashboard) {
      this.branchRows = [];
      return;
    }

    this.branchRows = this.dashboard.branches.map(
      (branch) => this.buildBranchView(branch),
    );
  }

  private resolveBranchInvestment(branchId: number): number | null {
    const dashboard = this.investmentDashboard;
    if (!dashboard || dashboard.month !== this.selectedMonth) {
      return null;
    }

    const branch = dashboard.branches.find(
      (item) => item.sucursal_id === branchId,
    );
    return branch?.investment ?? null;
  }

  private buildBranchView(branch: MarketingSalesFunnelBranch): SalesFunnelBranchView {
    const investment = this.resolveBranchInvestment(branch.sucursal_id);
    const costPerLead = (
      investment !== null && branch.leads_meta > 0
        ? investment / branch.leads_meta
        : null
    );
    const costPerVisit = (
      investment !== null && branch.visits_total > 0
        ? investment / branch.visits_total
        : null
    );
    const costPerSale = (
      investment !== null && branch.sales_iventas > 0
        ? investment / branch.sales_iventas
        : null
    );
    const leadToVisit = (
      branch.leads_meta > 0
        ? branch.visits_iventas / branch.leads_meta
        : null
    );

    return {
      ...branch,
      investment_display: this.formatOptionalCurrency(investment),
      leads_meta_display: this.formatInteger(branch.leads_meta),
      visits_total_display: this.formatInteger(branch.visits_total),
      visits_iventas_display: this.formatInteger(branch.visits_iventas),
      visits_not_iventas_display: this.formatInteger(branch.visits_not_iventas),
      sales_total_display: this.formatInteger(branch.sales_total),
      sales_iventas_display: this.formatInteger(branch.sales_iventas),
      sales_iventas_meta_display: this.formatInteger(branch.sales_iventas_meta),
      sales_iventas_other_display: this.formatInteger(branch.sales_iventas_other),
      sales_not_iventas_display: this.formatInteger(branch.sales_not_iventas),
      revenue_total_display: this.formatCurrency(branch.revenue_total),
      cost_per_lead_display: this.formatOptionalCurrency(costPerLead),
      cost_per_visit_display: this.formatOptionalCurrency(costPerVisit),
      cost_per_sale_display: this.formatOptionalCurrency(costPerSale),
      lead_to_visit_display: this.formatPercent(leadToVisit),
      iventas_visit_conversion_rate_display: this.formatPercent(
        branch.iventas_visit_conversion_rate,
      ),
      not_iventas_visit_conversion_rate_display: this.formatPercent(
        branch.not_iventas_visit_conversion_rate,
      ),
      iventas_sale_share_display: this.formatPercent(branch.iventas_sale_share),
    };
  }

  private formatOptionalCurrency(value: number | null): string {
    return value === null ? '—' : this.formatCurrency(value);
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
