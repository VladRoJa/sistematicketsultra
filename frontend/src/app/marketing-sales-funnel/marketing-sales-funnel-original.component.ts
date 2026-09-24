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
import {
  MarketingSalesFunnelBranch,
  MarketingSalesFunnelMetrics,
  MarketingSalesFunnelResponse,
  MarketingSalesFunnelScopeOption,
} from './marketing-sales-funnel.models';
import {
  MarketingSalesFunnelOriginalDetailDialogComponent,
} from './marketing-sales-funnel-original-detail-dialog.component';
import {
  MarketingSalesFunnelOriginalStoryComponent,
} from './marketing-sales-funnel-original-story.component';
import { MarketingSalesFunnelOriginalService } from './marketing-sales-funnel-original.service';
import {
  exportMarketingSalesFunnelBranchTable,
} from './marketing-sales-funnel-table-export';


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
  sales_digital_display: string;
  sales_digital_organic_display: string;
  sales_web_display: string;
  sales_btl_display: string;
  sales_total_display: string;
  revenue_digital_display: string;
  revenue_web_display: string;
  revenue_btl_display: string;
  revenue_total_display: string;
  lead_to_visit_display: string;
  visit_to_digital_sale_display: string;
  lead_to_sale_display: string;
  cpl_display: string;
  cpt_display: string;
  cac_display: string;
}

interface SalesFunnelBranchTotalsView {
  investment_display: string;
  leads_display: string;
  visits_display: string;
  sales_digital_display: string;
  sales_digital_organic_display: string;
  sales_web_display: string;
  sales_btl_display: string;
  sales_total_display: string;
  revenue_digital_display: string;
  revenue_web_display: string;
  revenue_btl_display: string;
  revenue_total_display: string;
  lead_to_visit_display: string;
  visit_to_digital_sale_display: string;
  lead_to_sale_display: string;
  cpl_display: string;
  cpt_display: string;
  cac_display: string;
}

interface DashboardRequest {
  month: string;
  cutoffDate: string | null;
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
  selector: 'app-marketing-sales-funnel-original',
  standalone: true,
  imports: [
    CommonModule,
    MarketingSalesFunnelOriginalStoryComponent,
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
  templateUrl: './marketing-sales-funnel-original.component.html',
  styleUrls: [
    './marketing-sales-funnel.component.css',
    './marketing-sales-funnel-branch-table.component.css',
  ],
})
export class MarketingSalesFunnelOriginalComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly salesFunnelService = inject(MarketingSalesFunnelOriginalService);
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
  readonly cutoffControl = new FormControl<string | null>(null);
  readonly regionControl = new FormControl<number | null>(null);
  readonly branchControl = new FormControl<number | null>(null);

  readonly monthOptions = this.buildMonthOptions();
  cutoffOptions: Array<{ value: string; label: string }> = [];

  dashboard: MarketingSalesFunnelResponse | null = null;
  summaryCards: SummaryCard[] = [];
  branchRows: SalesFunnelBranchView[] = [];
  branchTotals: SalesFunnelBranchTotalsView | null = null;
  scopeOptions: MarketingSalesFunnelScopeOption[] = [];
  regionOptions: Array<{ id: number; label: string }> = [];
  branchOptions: MarketingSalesFunnelScopeOption[] = [];
  activeScopeBranchIds: number[] = [];

  loading = true;
  errorMessage = '';

  get selectedMonth(): string {
    return this.monthControl.value.trim();
  }

  get selectedCutoff(): string | null {
    return this.cutoffControl.value;
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
            .getDashboard(
              dashboardRequest.month,
              dashboardRequest.branchIds,
              dashboardRequest.cutoffDate,
            )
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
          this.cutoffControl.setValue(null, { emitEvent: false });
          this.cutoffOptions = [];
          this.requestDashboard();
        }
      });

    this.cutoffControl.valueChanges
      .pipe(
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.requestDashboard());

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

    this.requestDashboard();
  }

  refreshDashboard(): void {
    this.monthControl.markAsTouched();
    if (!this.monthControl.invalid) {
      this.requestDashboard();
    }
  }

  exportBranchTable(): void {
    if (!this.dashboard || !this.hasBranches) {
      return;
    }

    const investmentDashboard = {
      month: this.selectedMonth,
      summary: {
        investment: this.dashboard.summary.investment ?? null,
      },
      branches: this.dashboard.branches.map((branch) => ({
        sucursal_id: branch.sucursal_id,
        investment: branch.investment ?? null,
      })),
    } as unknown as MarketingDashboardResponse;

    exportMarketingSalesFunnelBranchTable({
      month: this.selectedMonth,
      branches: this.dashboard.branches,
      investmentDashboard,
      scopeOptions: this.scopeOptions,
      regionId: this.regionControl.value,
      branchId: this.branchControl.value,
    });
  }

  openDetail(
    metric: string,
    branchId?: number,
    origin?: string,
  ): void {
    if (!metric) {
      return;
    }

    this.dialog.open(MarketingSalesFunnelOriginalDetailDialogComponent, {
      data: {
        month: this.selectedMonth,
        cutoffDate: this.dashboard?.selected_cutoff_date || this.selectedCutoff,
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
    if (!this.isBranchMetricAvailable(metric, row)) {
      return;
    }
    this.openDetail(metric, row.sucursal_id);
  }

  private isBranchMetricAvailable(
    metric: string,
    row: SalesFunnelBranchView,
  ): boolean {
    if (metric === 'leads_meta') {
      return row.leads_meta !== null;
    }
    if (metric === 'visits_iventas_meta') {
      return row.visits_iventas_meta !== null;
    }
    if (metric === 'sales_iventas') {
      return row.sales_iventas !== null;
    }
    return true;
  }

  formatCurrency(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private resolveIventasCost(): number | null {
    return this.dashboard?.summary.investment ?? null;
  }

  private requestDashboard(): void {
    if (this.monthControl.invalid) {
      return;
    }
    this.dashboardRequests.next({
      month: this.selectedMonth,
      cutoffDate: this.selectedCutoff,
      branchIds: this.activeScopeBranchIds,
    });
  }

  private applyDashboard(data: MarketingSalesFunnelResponse): void {
    this.dashboard = data;
    this.cutoffOptions = (data.available_cutoff_dates || []).map((value) => ({
      value,
      label: this.formatDate(value),
    }));
    if (this.cutoffControl.value !== data.selected_cutoff_date) {
      this.cutoffControl.setValue(data.selected_cutoff_date, { emitEvent: false });
    }
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
    const costPerLead = this.safeRatio(investment, summary.leads_meta);
    const costPerSale = this.safeRatio(investment, summary.sales_iventas);
    const publicationCostPerSale = this.safeRatio(
      investment,
      summary.sales_iventas_meta,
    );

    return [
      {
        label: 'Inversión',
        value: investment !== null
          ? this.formatCurrency(investment)
          : (
              this.dashboard?.data_quality.crm_history_available === false
                ? '—'
                : 'Sin corte'
            ),
        supportingText: 'Inversión del alcance',
        metric: null,
        icon: 'account_balance_wallet',
        cssClass: 'summary-kpi--purple',
      },
      {
        label: 'Leads CRM',
        value: this.formatInteger(summary.leads_meta),
        supportingText: 'Leads canónicos identificados por iVentas',
        metric: summary.leads_meta === null ? null : 'leads_meta',
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
        metric: summary.sales_iventas === null ? null : 'sales_iventas',
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
        metric: summary.sales_iventas_meta === null
          ? null
          : 'sales_iventas_meta',
        icon: 'campaign',
        cssClass: 'summary-kpi--orange',
        secondaryLabel: 'Costo por venta',
        secondaryValue: publicationCostPerSale !== null
          ? this.formatCurrency(publicationCostPerSale)
          : '—',
      },
      {
        label: 'Orgánico',
        value: this.formatInteger(summary.sales_iventas_other),
        supportingText: 'Ventas iVentas sin evidencia Meta',
        metric: summary.sales_iventas_other === null
          ? null
          : 'sales_iventas_other',
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
      this.branchTotals = null;
      return;
    }

    this.branchRows = this.dashboard.branches.map(
      (branch) => this.buildBranchView(branch),
    );

    this.branchTotals = this.buildBranchTotals(this.dashboard.summary);
  }

  private buildBranchTotals(
    summary: MarketingSalesFunnelMetrics,
  ): SalesFunnelBranchTotalsView {
    const investment = this.resolveIventasCost();

    const digitalSalesForCac = this.sumAvailable(
      summary.sales_digital,
      summary.sales_digital_organic,
    );
    const leadToVisit = this.safeRatio(
      summary.visits_total,
      summary.leads_meta,
    );
    const visitToDigitalSale = this.safeRatio(
      summary.sales_digital,
      summary.visits_total,
    );
    const leadToSale = this.safeRatio(
      summary.sales_digital,
      summary.leads_meta,
    );
    const cpl = this.safeRatio(investment, summary.leads_meta);
    const cpt = this.safeRatio(investment, summary.visits_total);
    const cac = this.safeRatio(investment, digitalSalesForCac);

    return {
      investment_display: this.formatOptionalCurrency(investment),
      leads_display: this.formatInteger(summary.leads_meta),
      visits_display: this.formatInteger(summary.visits_total),
      sales_digital_display: this.formatInteger(summary.sales_digital),
      sales_digital_organic_display: this.formatInteger(
        summary.sales_digital_organic,
      ),
      sales_web_display: this.formatInteger(summary.sales_web),
      sales_btl_display: this.formatInteger(summary.sales_btl),
      sales_total_display: this.formatInteger(summary.sales_total),
      revenue_digital_display: this.formatCurrency(summary.revenue_digital),
      revenue_web_display: this.formatCurrency(summary.revenue_web),
      revenue_btl_display: this.formatCurrency(summary.revenue_btl),
      revenue_total_display: this.formatCurrency(summary.revenue_total),
      lead_to_visit_display: this.formatPercent(leadToVisit),
      visit_to_digital_sale_display: this.formatPercent(visitToDigitalSale),
      lead_to_sale_display: this.formatPercent(leadToSale),
      cpl_display: this.formatOptionalCurrency(cpl),
      cpt_display: this.formatOptionalCurrency(cpt),
      cac_display: this.formatOptionalCurrency(cac),
    };
  }

  private resolveBranchInvestment(branchId: number): number | null {
    const branch = this.dashboard?.branches.find(
      (item) => item.sucursal_id === branchId,
    );
    return branch?.investment ?? null;
  }

  private buildBranchView(branch: MarketingSalesFunnelBranch): SalesFunnelBranchView {
    const investment = this.resolveBranchInvestment(branch.sucursal_id);
    const cpl = this.safeRatio(investment, branch.leads_meta);
    const cpt = this.safeRatio(investment, branch.visits_total);
    const digitalSalesForCac = this.sumAvailable(
      branch.sales_digital,
      branch.sales_digital_organic,
    );
    const cac = this.safeRatio(investment, digitalSalesForCac);
    const leadToVisit = this.safeRatio(
      branch.visits_total,
      branch.leads_meta,
    );
    const leadToSale = this.safeRatio(
      branch.sales_digital,
      branch.leads_meta,
    );

    return {
      ...branch,
      investment_display: this.formatOptionalCurrency(investment),
      leads_meta_display: this.formatInteger(branch.leads_meta),
      visits_total_display: this.formatInteger(branch.visits_total),
      sales_digital_display: this.formatInteger(branch.sales_digital),
      sales_digital_organic_display: this.formatInteger(
        branch.sales_digital_organic,
      ),
      sales_web_display: this.formatInteger(branch.sales_web),
      sales_btl_display: this.formatInteger(branch.sales_btl),
      sales_total_display: this.formatInteger(branch.sales_total),
      revenue_digital_display: this.formatCurrency(branch.revenue_digital),
      revenue_web_display: this.formatCurrency(branch.revenue_web),
      revenue_btl_display: this.formatCurrency(branch.revenue_btl),
      revenue_total_display: this.formatCurrency(branch.revenue_total),
      lead_to_visit_display: this.formatPercent(leadToVisit),
      visit_to_digital_sale_display: this.formatPercent(
        branch.visit_to_digital_sale_rate,
      ),
      lead_to_sale_display: this.formatPercent(leadToSale),
      cpl_display: this.formatOptionalCurrency(cpl),
      cpt_display: this.formatOptionalCurrency(cpt),
      cac_display: this.formatOptionalCurrency(cac),
    };
  }

  private formatOptionalCurrency(value: number | null): string {
    return value === null ? '—' : this.formatCurrency(value);
  }

  private safeRatio(
    numerator: number | null | undefined,
    denominator: number | null | undefined,
  ): number | null {
    if (
      numerator === null
      || numerator === undefined
      || denominator === null
      || denominator === undefined
      || denominator <= 0
    ) {
      return null;
    }
    return numerator / denominator;
  }

  private sumAvailable(
    left: number | null | undefined,
    right: number | null | undefined,
  ): number | null {
    if (
      left === null
      || left === undefined
      || right === null
      || right === undefined
    ) {
      return null;
    }
    return left + right;
  }

  private formatInteger(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value);
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
    const firstMonth = new Date(2026, 0, 1);
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
