import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HttpErrorResponse } from '@angular/common/http';
import { MarketingReactivationService } from './marketing-reactivation.service';
import { CampaignOptions, CampaignType, CampaignV1Request, ReactivationCampaign } from './marketing-reactivation.models';

@Component({
  selector: 'app-marketing-reactivation', standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatButtonModule, MatFormFieldModule,
    MatInputModule, MatSelectModule, MatProgressSpinnerModule],
  templateUrl: './marketing-reactivation.component.html',
  styleUrls: ['./marketing-reactivation.component.css'],
})
export class MarketingReactivationComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly service = inject(MarketingReactivationService);
  private revision = 0;
  readonly types: Array<{value: CampaignType; label: string}> = [
    {value: 'WINBACK', label: 'Winback'}, {value: 'PROXIMOS_VENCER', label: 'Próximos a vencer'},
    {value: 'VENCIDOS_RECIENTES', label: 'Vencidos recientes'}, {value: 'BASCULA_RETENCION', label: 'Báscula / Retención'},
    {value: 'INVITA_GANA', label: 'Invita y gana'}, {value: 'COBRANZA_LIGERA', label: 'Cobranza ligera'},
    {value: 'PERSONALIZADA', label: 'Personalizada'},
  ];
  readonly form = new FormGroup({
    type: new FormControl<CampaignType>('WINBACK', {nonNullable: true}),
    segment: new FormControl('WINBACK_30', {nonNullable: true}),
    universe: new FormControl<'ACTIVOS' | 'VENCIDOS'>('ACTIVOS', {nonNullable: true}),
    expiredMode: new FormControl<'DIAS' | 'FECHAS'>('DIAS', {nonNullable: true}),
    region: new FormControl<number | null>(null), branch: new FormControl('', {nonNullable: true}),
    from: new FormControl<number | null>(null), to: new FormControl<number | null>(null),
    dateFrom: new FormControl('', {nonNullable: true}), dateTo: new FormControl('', {nonNullable: true}),
  });
  readonly name = new FormControl('', {nonNullable: true});
  options: CampaignOptions = {branches: [], regions: []};
  campaigns: ReactivationCampaign[] = [];
  eligible: number | null = null;
  weeklyExcluded = 0;
  loading = true;
  reviewing = false;
  creating = false;
  exporting: number | null = null;
  error = '';
  success = '';
  get isWinback(): boolean { return this.form.controls.type.value === 'WINBACK'; }
  get isCollection(): boolean { return this.form.controls.type.value === 'COBRANZA_LIGERA'; }
  get isCustom(): boolean { return this.form.controls.type.value === 'PERSONALIZADA'; }
  get isCustomExpired(): boolean { return this.isCustom && this.form.controls.universe.value === 'VENCIDOS'; }
  get isCustomExpiredByDays(): boolean { return this.isCustomExpired && this.form.controls.expiredMode.value === 'DIAS'; }
  get isCustomExpiredByDates(): boolean { return this.isCustomExpired && this.form.controls.expiredMode.value === 'FECHAS'; }
  get showsDayRange(): boolean { return this.isCollection || this.isCustomExpiredByDays; }
  get branches(): CampaignOptions['branches'] {
    const region = this.options.regions.find(item => item.id === this.form.controls.region.value);
    return region ? this.options.branches.filter(item => region.branch_keys.includes(item.key)) : this.options.branches;
  }
  get canCreate(): boolean { return !this.creating && !this.reviewing && !!this.eligible && !!this.name.value.trim(); }
  get description(): string {
    if (this.isCustom) {
      if (!this.isCustomExpired) return 'Todos los socios actualmente activos con teléfono válido.';
      return this.isCustomExpiredByDates
        ? 'Selecciona una o ambas fechas de vencimiento. Puedes dejar un extremo vacío para usar un rango abierto.'
        : 'Define desde cuántos días vencidos quieres contactar. Deja “hasta” vacío para incluir todos los posteriores.';
    }
    const descriptions: Record<CampaignType, string> = {
      WINBACK: '8–30, 31–60 o 61–90 días vencidos, según el segmento.',
      PROXIMOS_VENCER: 'Membresías activas que vencen entre hoy y dentro de 5 días, inclusive.',
      VENCIDOS_RECIENTES: 'Socios con 1 a 7 días vencidos.',
      BASCULA_RETENCION: 'Socios actualmente activos.',
      INVITA_GANA: 'Socios nuevos con pago en la semana actual, de lunes a domingo.',
      COBRANZA_LIGERA: 'Selecciona el rango de días vencidos que necesitas contactar.',
      PERSONALIZADA: '',
    };
    return descriptions[this.form.controls.type.value];
  }
  ngOnInit(): void {
    this.form.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.revision++; this.eligible = null; this.reviewing = false; this.error = ''; this.success = '';
      if (!this.branches.some(item => item.key === this.form.controls.branch.value)) {
        this.form.controls.branch.setValue('', {emitEvent: false});
      }
    });
    this.loadOptions();
  }
  loadOptions(): void {
    this.loading = true; this.error = '';
    this.service.getCampaignOptions().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: options => { this.options = options; this.loading = false; this.loadCampaigns(); },
      error: error => { this.loading = false; void this.showError(error, 'No fue posible cargar las opciones.'); },
    });
  }
  private request(): CampaignV1Request | null {
    const values = this.form.getRawValue();
    const filters: CampaignV1Request['filters'] = {campaign_type: values.type};
    if (values.branch) filters.sucursal = values.branch;
    if (values.region !== null) filters.region_id = values.region;
    if (this.isWinback) filters.segment = values.segment;
    if (this.isCustom) {
      filters.universo = values.universe;
      if (this.isCustomExpired) {
        filters.modo_vencidos = values.expiredMode;
        if (this.isCustomExpiredByDays) {
          if (!Number.isInteger(values.from) || values.from! < 1) {
            this.error = 'Indica desde cuántos días vencidos quieres contactar.'; return null;
          }
          if (values.to !== null && (!Number.isInteger(values.to) || values.to! < values.from!)) {
            this.error = 'Días hasta debe quedar vacío o ser igual o mayor que días desde.'; return null;
          }
          filters.dias_desde = values.from!;
          if (values.to !== null) filters.dias_hasta = values.to!;
        } else {
          if (!values.dateFrom && !values.dateTo) {
            this.error = 'Indica al menos una fecha de vencimiento.'; return null;
          }
          if (values.dateFrom && values.dateTo && values.dateFrom > values.dateTo) {
            this.error = 'La fecha desde no puede ser posterior a la fecha hasta.'; return null;
          }
          if (values.dateFrom) filters.fecha_desde = values.dateFrom;
          if (values.dateTo) filters.fecha_hasta = values.dateTo;
        }
      }
    }
    if (this.isCollection) {
      if (!Number.isInteger(values.from) || !Number.isInteger(values.to) || values.from! < 1 || values.to! < values.from!) {
        this.error = 'Indica un rango de días válido: desde 1, hasta un valor igual o mayor.'; return null;
      }
      filters.dias_desde = values.from!; filters.dias_hasta = values.to!;
    }
    return {filters};
  }
  prepareCampaign(): void {
    const request = this.request(); if (!request || this.reviewing || this.creating) return;
    const revision = this.revision;
    this.reviewing = true; this.error = ''; this.eligible = null;
    this.service.previewCampaign(request).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (revision !== this.revision) return;
        this.reviewing = false; this.eligible = result.summary.eligible;
        this.weeklyExcluded = result.summary.excluded_weekly_limit ?? 0;
      },
      error: error => { if (revision === this.revision) { this.reviewing = false; void this.showError(error, 'No fue posible revisar la audiencia.'); } },
    });
  }
  confirmCampaign(): void {
    if (!this.canCreate) return;
    const request = this.request(); if (!request) return;
    this.creating = true; this.error = ''; this.form.disable({emitEvent: false});
    this.service.createCampaign({...request, name: this.name.value.trim()}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.creating = false; this.form.enable({emitEvent: false}); this.eligible = null; this.name.setValue('');
        this.success = `Campaña “${result.campaign.name}” creada con ${result.campaign.recipient_count} contactos. Puedes exportarla en el historial.`;
        this.loadCampaigns();
      },
      error: error => { this.creating = false; this.form.enable({emitEvent: false}); void this.showError(error, 'No fue posible crear la campaña.'); },
    });
  }
  loadCampaigns(): void {
    this.service.getCampaigns().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.campaigns = result.rows; },
      error: error => { void this.showError(error, 'No fue posible cargar el historial.'); },
    });
  }
  canExport(campaign: ReactivationCampaign): boolean { return this.exporting === null && ['DRAFT', 'EXPORTED'].includes(campaign.status); }
  exportCampaign(campaign: ReactivationCampaign): void {
    if (!this.canExport(campaign)) return;
    this.exporting = campaign.id; this.error = '';
    this.service.exportCampaign(campaign.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob); const link = document.createElement('a');
        link.href = url; link.download = `campana_${campaign.id}.xlsx`; link.click(); URL.revokeObjectURL(url);
        this.exporting = null; this.eligible = null; this.reviewing = false; this.revision++; this.loadCampaigns();
      },
      error: error => { this.exporting = null; void this.showError(error, 'No fue posible exportar la campaña.'); },
    });
  }
  typeLabel(campaign: ReactivationCampaign): string {
    return this.types.find(item => item.value === campaign.filters.campaign_type)?.label ?? 'Reactivación';
  }
  statusLabel(status: ReactivationCampaign['status']): string {
    return {DRAFT: 'Borrador', EXPORTED: 'Exportada', SENT: 'Enviada', CANCELLED: 'Cancelada'}[status];
  }
  formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-MX', {timeZone: 'America/Tijuana', dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value));
  }
  private friendlyCampaignError(message: unknown, fallback: string): string {
    if (typeof message !== 'string' || !message.trim()) {
      return fallback;
    }

    const normalized = message
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();

    const unavailableDataTerms = [
      'fuente canonica',
      'canonical',
      'snapshot',
      'fecha de corte',
      'corte disponible',
      'warehouse',
      'sin fuente',
      'fuente disponible',
      'datos actualizados',
      'informacion actualizada',
    ];

    if (unavailableDataTerms.some(term => normalized.includes(term))) {
      return 'No hay información actualizada disponible para esta campaña.';
    }

    return fallback;
  }

  private async showError(error: HttpErrorResponse, fallback: string): Promise<void> {
    let body = error.error;
    if (body instanceof Blob) {
      try {
        body = JSON.parse(await body.text());
      } catch {
        body = null;
      }
    }

    this.error = this.friendlyCampaignError(body?.message, fallback);
  }
}
