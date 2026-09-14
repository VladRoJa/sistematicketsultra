import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import { MarketingReactivationService } from './marketing-reactivation.service';
import {
  ReactivationCampaignOutcomeDetailResponse,
  ReactivationCampaignOutcomeRow,
  ReactivationOutcomeSummaryResponse,
  ReactivationOutcomeStatus,
  RecoveryBusinessResult,
} from './marketing-reactivation-outcome.models';
import { CampaignOptions } from './marketing-reactivation.models';

@Component({
  selector: 'app-marketing-reactivation-outcomes',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './marketing-reactivation-outcomes.component.html',
  styleUrls: ['./marketing-reactivation-outcomes.component.css'],
})
export class MarketingReactivationOutcomesComponent implements OnInit {
  private readonly service = inject(MarketingReactivationService);
  private readonly destroyRef = inject(DestroyRef);

  readonly filters = new FormGroup({
    dateFrom: new FormControl(this.monthStart(), { nonNullable: true }),
    dateTo: new FormControl(this.today(), { nonNullable: true }),
    regionId: new FormControl<number | null>(null),
    sucursal: new FormControl('', { nonNullable: true }),
  });

  options: CampaignOptions = { branches: [], regions: [] };
  result: ReactivationOutcomeSummaryResponse | null = null;
  detail: ReactivationCampaignOutcomeDetailResponse | null = null;
  loading = false;
  loadingDetail = false;
  error = '';

  get branches(): CampaignOptions['branches'] {
    const regionId = this.filters.controls.regionId.value;
    const region = this.options.regions.find(item => item.id === regionId);
    return region
      ? this.options.branches.filter(item => region.branch_keys.includes(item.key))
      : this.options.branches;
  }

  get recoveredRows(): ReactivationCampaignOutcomeRow[] {
    return (this.detail?.rows ?? []).filter(row => row.status === 'REACTIVATED');
  }

  ngOnInit(): void {
    this.filters.controls.regionId.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        const selected = this.filters.controls.sucursal.value;
        if (selected && !this.branches.some(branch => branch.key === selected)) {
          this.filters.controls.sucursal.setValue('', { emitEvent: false });
        }
      });
    this.loadOptions();
    this.load();
  }

  load(): void {
    const values = this.filters.getRawValue();
    if (values.dateFrom && values.dateTo && values.dateFrom > values.dateTo) {
      this.error = 'La fecha desde no puede ser posterior a la fecha hasta.';
      return;
    }
    this.loading = true;
    this.error = '';
    this.detail = null;
    this.service.getOutcomeSummary({
      dateFrom: values.dateFrom || null,
      dateTo: values.dateTo || null,
      regionId: values.regionId,
      sucursal: values.sucursal || null,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.result = result;
        this.loading = false;
      },
      error: () => {
        this.result = null;
        this.loading = false;
        this.error = 'No fue posible cargar el seguimiento de recuperaciones.';
      },
    });
  }

  openCampaign(campaignId: number): void {
    this.loadingDetail = true;
    this.error = '';
    this.service.getCampaignOutcomes(campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: detail => {
          this.detail = detail;
          this.loadingDetail = false;
        },
        error: () => {
          this.detail = null;
          this.loadingDetail = false;
          this.error = 'No fue posible cargar el detalle de la campaña.';
        },
      });
  }

  closeDetail(): void {
    this.detail = null;
  }

  statusLabel(status: ReactivationOutcomeStatus): string {
    const labels: Record<ReactivationOutcomeStatus, string> = {
      PENDING: 'Pendiente',
      REACTIVATED: 'Recuperado',
      REVIEW: 'Revisar identidad',
      WINDOW_CLOSED: 'Ventana cerrada',
    };
    return labels[status];
  }

  businessResultLabel(result: RecoveryBusinessResult | null): string {
    if (result === 'RENOVACION') return 'Renovación';
    if (result === 'REACTIVACION') return 'Reactivación';
    return 'Sin clasificar';
  }

  formatDate(value: string | null): string {
    if (!value) return '—';
    const datePart = value.slice(0, 10);
    const [year, month, day] = datePart.split('-').map(Number);
    if (!year || !month || !day) return value;
    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(new Date(year, month - 1, day));
  }

  private loadOptions(): void {
    this.service.getCampaignOptions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: options => { this.options = options; },
        error: () => { this.options = { branches: [], regions: [] }; },
      });
  }

  private today(): string {
    return this.isoLocalDate(new Date());
  }

  private monthStart(): string {
    const now = new Date();
    return this.isoLocalDate(new Date(now.getFullYear(), now.getMonth(), 1));
  }

  private isoLocalDate(value: Date): string {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}
