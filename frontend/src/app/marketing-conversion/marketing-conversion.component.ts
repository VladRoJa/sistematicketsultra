import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  AbstractControl,
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  ValidatorFn,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  Subject,
  catchError,
  distinctUntilChanged,
  map,
  of,
  switchMap,
} from 'rxjs';

import {
  MarketingBranchMetrics,
  MarketingDashboardResponse,
  MarketingDataQuality,
  MarketingMetrics,
  MarketingMonthlyInput,
} from './marketing.models';
import { MarketingService } from './marketing.service';

interface MarketingMetricCard {
  label: string;
  value: string;
  supportingText: string;
}

interface MarketingBranchView extends MarketingBranchMetrics {
  investment_display: string;
  leads_display: string;
  visits_display: string;
  sales_display: string;
  sales_revenue_display: string;
  cost_per_lead_display: string;
  cost_per_visit_display: string;
  cost_per_sale_display: string;
  lead_to_visit_rate_display: string;
  visit_to_sale_rate_display: string;
  lead_to_sale_rate_display: string;
}

interface MarketingQualityItem {
  label: string;
  value: string;
}

type MarketingInputForm = FormGroup<{
  investment: FormControl<number>;
  leads: FormControl<number>;
  notes: FormControl<string>;
}>;

interface MarketingInputEditRow {
  branchId: number;
  branchName: string;
  input: MarketingMonthlyInput | null;
  form: MarketingInputForm;
  saving: boolean;
  errorMessage: string;
}

type DashboardRequestResult =
  | {
      requestId: number;
      status: 'success';
      data: MarketingDashboardResponse;
    }
  | {
      requestId: number;
      status: 'error';
      error: HttpErrorResponse;
    };

const integerValidator: ValidatorFn = (
  control: AbstractControl,
): ValidationErrors | null => {
  const value = Number(control.value);

  return Number.isInteger(value) ? null : { integer: true };
};

@Component({
  selector: 'app-marketing-conversion',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTableModule,
    ReactiveFormsModule,
  ],
  templateUrl: './marketing-conversion.component.html',
  styleUrls: ['./marketing-conversion.component.css'],
})
export class MarketingConversionComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly marketingService = inject(MarketingService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dashboardRequests = new Subject<string>();
  private dashboardRequestId = 0;
  private inputsRequestId = 0;

  readonly monthControl = new FormControl(this.resolveCurrentMonth(), {
    nonNullable: true,
    validators: [
      Validators.required,
      Validators.pattern(/^\d{4}-\d{2}$/),
    ],
  });

  readonly branchColumns = [
    'sucursal',
    'investment',
    'leads',
    'visits',
    'sales',
    'sales_revenue',
    'cost_per_lead',
    'cost_per_visit',
    'cost_per_sale',
    'lead_to_visit_rate',
    'visit_to_sale_rate',
    'lead_to_sale_rate',
  ];

  dashboard: MarketingDashboardResponse | null = null;
  primaryCards: MarketingMetricCard[] = [];
  costCards: MarketingMetricCard[] = [];
  conversionCards: MarketingMetricCard[] = [];
  branchRows: MarketingBranchView[] = [];
  qualityItems: MarketingQualityItem[] = [];
  qualityLimitations: string[] = [];
  leadModeLabel = '';
  salesAttributionModeLabel = '';

  loading = true;
  errorMessage = '';
  editingInputs = false;
  inputsLoading = false;
  inputsErrorMessage = '';
  inputRows: MarketingInputEditRow[] = [];

  get canEditInputs(): boolean {
    return Boolean(this.dashboard?.permissions.can_edit_inputs);
  }

  get hasBranches(): boolean {
    return this.branchRows.length > 0;
  }

  get cohortIsIncomplete(): boolean {
    return this.dashboard?.data_quality.cohort_complete === false;
  }

  get cohortStatusLabel(): string {
    return this.cohortIsIncomplete ? 'En curso' : 'Completa';
  }

  get selectedMonth(): string {
    return this.monthControl.value.trim();
  }

  ngOnInit(): void {
    this.dashboardRequests
      .pipe(
        switchMap((month) => {
          const requestId = ++this.dashboardRequestId;
          this.loading = true;
          this.errorMessage = '';

          return this.marketingService.getDashboard(month).pipe(
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
          this.errorMessage = this.resolveErrorMessage(
            result.error,
            'No fue posible cargar Marketing y Conversión.',
          );
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
        this.closeInputEditor();

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

  openInputEditor(): void {
    if (!this.canEditInputs || this.inputsLoading) {
      return;
    }

    this.editingInputs = true;
    this.loadInputs();
  }

  closeInputEditor(): void {
    this.editingInputs = false;
    this.inputsLoading = false;
    this.inputsErrorMessage = '';
    this.inputRows = [];
    this.inputsRequestId += 1;
  }

  retryInputs(): void {
    if (!this.editingInputs || this.inputsLoading) {
      return;
    }

    this.loadInputs();
  }

  saveInput(row: MarketingInputEditRow): void {
    if (row.saving) {
      return;
    }

    row.form.markAllAsTouched();
    if (row.form.invalid) {
      row.errorMessage = 'Revisa los campos marcados antes de guardar.';
      return;
    }

    const month = this.selectedMonth;
    const formValue = row.form.getRawValue();
    row.saving = true;
    row.errorMessage = '';

    this.marketingService
      .saveInput(row.branchId, {
        month,
        investment: formValue.investment,
        leads: formValue.leads,
        notes: formValue.notes.trim() || null,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          row.saving = false;
          if (this.selectedMonth === month && this.editingInputs) {
            row.input = response.input;
            row.form.patchValue({
              investment: response.input.investment,
              leads: response.input.leads,
              notes: response.input.notes || '',
            });
            row.form.markAsPristine();
            this.dashboardRequests.next(month);
          }

          this.snackBar.open(
            `Inputs de ${row.branchName} guardados.`,
            'Cerrar',
            { duration: 3500 },
          );
        },
        error: (error: HttpErrorResponse) => {
          row.saving = false;
          row.errorMessage = this.resolveInputSaveError(error);
        },
      });
  }

  getInvestmentError(row: MarketingInputEditRow): string {
    const control = row.form.controls.investment;
    if (!control.touched || !control.errors) {
      return '';
    }
    if (control.hasError('required')) {
      return 'La inversión es obligatoria.';
    }
    return 'Captura una inversión igual o mayor a cero.';
  }

  getLeadsError(row: MarketingInputEditRow): string {
    const control = row.form.controls.leads;
    if (!control.touched || !control.errors) {
      return '';
    }
    if (control.hasError('required')) {
      return 'Los leads son obligatorios.';
    }
    if (control.hasError('integer')) {
      return 'Los leads deben ser un número entero.';
    }
    return 'Captura una cantidad igual o mayor a cero.';
  }

  getInputStatusLabel(row: MarketingInputEditRow): string {
    return row.input ? 'Captura existente' : 'Sin captura previa';
  }

  getSaveButtonLabel(row: MarketingInputEditRow): string {
    return row.saving ? 'Guardando…' : 'Guardar';
  }

  trackInputRow(
    _index: number,
    row: MarketingInputEditRow,
  ): number {
    return row.branchId;
  }

  private loadInputs(): void {
    const month = this.selectedMonth;
    const requestId = ++this.inputsRequestId;
    this.inputsLoading = true;
    this.inputsErrorMessage = '';

    this.marketingService
      .getInputs(month)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          if (
            requestId !== this.inputsRequestId ||
            !this.editingInputs ||
            this.selectedMonth !== month
          ) {
            return;
          }

          const inputsByBranch = new Map(
            response.inputs.map((input) => [
              input.sucursal_id,
              input,
            ]),
          );
          this.inputRows = (this.dashboard?.branches || []).map(
            (branch) =>
              this.buildInputRow(
                branch,
                inputsByBranch.get(branch.sucursal_id) || null,
              ),
          );
          this.inputsLoading = false;
        },
        error: (error: HttpErrorResponse) => {
          if (
            requestId !== this.inputsRequestId ||
            !this.editingInputs ||
            this.selectedMonth !== month
          ) {
            return;
          }

          this.inputsLoading = false;
          this.inputsErrorMessage = this.resolveErrorMessage(
            error,
            'No fue posible cargar los inputs del mes.',
          );
        },
      });
  }

  private buildInputRow(
    branch: MarketingBranchMetrics,
    input: MarketingMonthlyInput | null,
  ): MarketingInputEditRow {
    return {
      branchId: branch.sucursal_id,
      branchName: branch.sucursal,
      input,
      saving: false,
      errorMessage: '',
      form: new FormGroup({
        investment: new FormControl(input?.investment || 0, {
          nonNullable: true,
          validators: [
            Validators.required,
            Validators.min(0),
          ],
        }),
        leads: new FormControl(input?.leads || 0, {
          nonNullable: true,
          validators: [
            Validators.required,
            Validators.min(0),
            integerValidator,
          ],
        }),
        notes: new FormControl(input?.notes || '', {
          nonNullable: true,
        }),
      }),
    };
  }

  private applyDashboard(data: MarketingDashboardResponse): void {
    this.dashboard = data;
    this.primaryCards = this.buildPrimaryCards(data.summary);
    this.costCards = this.buildCostCards(data.summary);
    this.conversionCards =
      this.buildConversionCards(data.summary);
    this.branchRows = data.branches.map((branch) =>
      this.buildBranchView(branch),
    );
    this.applyDataQuality(data.data_quality);
  }

  private buildPrimaryCards(
    metrics: MarketingMetrics,
  ): MarketingMetricCard[] {
    return [
      {
        label: 'Inversión',
        value: this.formatCurrency(metrics.investment),
        supportingText: 'Captura manual del mes',
      },
      {
        label: 'Leads',
        value: this.formatInteger(metrics.leads),
        supportingText: 'Captura manual agregada',
      },
      {
        label: 'Visitantes',
        value: this.formatInteger(metrics.visits),
        supportingText: 'Teléfonos únicos elegibles',
      },
      {
        label: 'Ventas atribuidas',
        value: this.formatInteger(metrics.sales),
        supportingText: 'Misma sucursal, hasta 30 días',
      },
      {
        label: 'Ingreso atribuido',
        value: this.formatCurrency(metrics.sales_revenue),
        supportingText: 'Ventas conciliadas por teléfono',
      },
    ];
  }

  private buildCostCards(
    metrics: MarketingMetrics,
  ): MarketingMetricCard[] {
    return [
      {
        label: 'Costo por lead',
        value: this.formatCurrency(metrics.cost_per_lead),
        supportingText: 'Inversión / leads',
      },
      {
        label: 'Costo por visita',
        value: this.formatCurrency(metrics.cost_per_visit),
        supportingText: 'Inversión / visitantes',
      },
      {
        label: 'Costo por venta',
        value: this.formatCurrency(metrics.cost_per_sale),
        supportingText: 'Inversión / ventas atribuidas',
      },
    ];
  }

  private buildConversionCards(
    metrics: MarketingMetrics,
  ): MarketingMetricCard[] {
    return [
      {
        label: 'Lead → visita',
        value: this.formatPercent(metrics.lead_to_visit_rate),
        supportingText: 'Visitantes / leads',
      },
      {
        label: 'Visita → venta',
        value: this.formatPercent(metrics.visit_to_sale_rate),
        supportingText: 'Ventas / visitantes',
      },
      {
        label: 'Lead → venta',
        value: this.formatPercent(metrics.lead_to_sale_rate),
        supportingText: 'Ventas / leads',
      },
    ];
  }

  private buildBranchView(
    branch: MarketingBranchMetrics,
  ): MarketingBranchView {
    return {
      ...branch,
      investment_display: this.formatCurrency(branch.investment),
      leads_display: this.formatInteger(branch.leads),
      visits_display: this.formatInteger(branch.visits),
      sales_display: this.formatInteger(branch.sales),
      sales_revenue_display: this.formatCurrency(branch.sales_revenue),
      cost_per_lead_display: this.formatCurrency(branch.cost_per_lead),
      cost_per_visit_display: this.formatCurrency(branch.cost_per_visit),
      cost_per_sale_display: this.formatCurrency(branch.cost_per_sale),
      lead_to_visit_rate_display: this.formatPercent(
        branch.lead_to_visit_rate,
      ),
      visit_to_sale_rate_display: this.formatPercent(
        branch.visit_to_sale_rate,
      ),
      lead_to_sale_rate_display: this.formatPercent(
        branch.lead_to_sale_rate,
      ),
    };
  }

  private applyDataQuality(dataQuality: MarketingDataQuality): void {
    this.leadModeLabel = this.resolveLeadMode(
      dataQuality.lead_mode,
    );
    this.salesAttributionModeLabel =
      this.resolveSalesAttributionMode(
        dataQuality.sales_attribution_mode,
      );
    this.qualityItems = [
      {
        label: 'Eventos de visita elegibles',
        value: this.formatInteger(
          dataQuality.eligible_visit_events,
        ),
      },
      {
        label: 'Visitantes únicos',
        value: this.formatInteger(dataQuality.unique_visitors),
      },
      {
        label: 'Eventos con teléfono válido',
        value: this.formatInteger(
          dataQuality.visit_events_with_valid_phone,
        ),
      },
      {
        label: 'Eventos sin teléfono válido',
        value: this.formatInteger(
          dataQuality.visit_events_without_valid_phone,
        ),
      },
      {
        label: 'Cobertura de teléfono',
        value: this.formatPercent(
          dataQuality.visit_phone_coverage_rate,
        ),
      },
    ];
    this.qualityLimitations = dataQuality.limitations;
  }

  private resolveLeadMode(mode: string): string {
    if (mode === 'monthly_aggregate_manual') {
      return 'Captura manual agregada por mes y sucursal';
    }
    return mode;
  }

  private resolveSalesAttributionMode(mode: string): string {
    if (mode === 'exact_phone_same_branch_30d') {
      return 'Teléfono exacto, misma sucursal y ventana de 30 días';
    }
    return mode;
  }

  private resolveInputSaveError(error: HttpErrorResponse): string {
    if (error.status === 403) {
      return this.resolveErrorMessage(
        error,
        'No tienes autorización para editar estos inputs.',
      );
    }

    return this.resolveErrorMessage(
      error,
      'No fue posible guardar los inputs de la sucursal.',
    );
  }

  private resolveErrorMessage(
    error: HttpErrorResponse,
    fallback: string,
  ): string {
    const backendMessage = error.error?.message;

    return typeof backendMessage === 'string' &&
      backendMessage.trim()
      ? backendMessage.trim()
      : fallback;
  }

  private formatCurrency(value: number | null): string {
    if (value === null) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 2,
    }).format(value);
  }

  private formatInteger(value: number | null): string {
    if (value === null) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value);
  }

  private formatPercent(value: number | null): string {
    if (value === null) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      maximumFractionDigits: 1,
    }).format(value);
  }

  private isValidMonth(value: string): boolean {
    return /^\d{4}-\d{2}$/.test(value.trim());
  }

  private resolveCurrentMonth(): string {
    const dateParts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Tijuana',
      year: 'numeric',
      month: '2-digit',
    }).formatToParts(new Date());
    const year = dateParts.find(
      (part) => part.type === 'year',
    )?.value;
    const month = dateParts.find(
      (part) => part.type === 'month',
    )?.value;

    return `${year}-${month}`;
  }
}
