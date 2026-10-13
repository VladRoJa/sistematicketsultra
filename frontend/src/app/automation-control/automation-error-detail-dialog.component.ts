import { CommonModule } from '@angular/common';
import { Component, Inject, OnDestroy, OnInit } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { Subscription } from 'rxjs';
import { AutomationControlService } from './automation-control.service';
import { AutomationDiagnostic } from './automation-control.models';

export interface AutomationErrorDialogData {
  jobKey: string;
  jobLabel: string;
  runId?: number;
  businessDate?: string;
}

@Component({
  selector: 'app-automation-error-detail-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule],
  templateUrl: './automation-error-detail-dialog.component.html',
  styleUrls: ['./automation-error-detail-dialog.component.css'],
})
export class AutomationErrorDetailDialogComponent implements OnInit, OnDestroy {
  loading = true;
  loadError = '';
  copyStatus = '';
  diagnostic: AutomationDiagnostic | null = null;
  private subscription?: Subscription;

  constructor(
    @Inject(MAT_DIALOG_DATA) public readonly data: AutomationErrorDialogData,
    private readonly api: AutomationControlService,
    private readonly ref: MatDialogRef<AutomationErrorDetailDialogComponent>,
  ) {}

  ngOnInit(): void {
    const result$ = this.data.runId !== undefined
      ? this.api.diagnostic(this.data.jobKey, this.data.runId)
      : this.api.lastError(this.data.jobKey, this.data.businessDate);
    this.subscription = result$.subscribe({
      next: ({ diagnostic }) => { this.diagnostic = diagnostic; this.loading = false; },
      error: () => {
        this.loadError = 'No fue posible consultar este diagnóstico.';
        this.loading = false;
      },
    });
  }

  ngOnDestroy(): void { this.subscription?.unsubscribe(); }
  close(): void { this.ref.close(); }

  formatDate(value?: string | null): string {
    if (!value) { return 'Sin registro'; }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? 'Fecha no disponible'
      : parsed.toLocaleString('es-MX', { timeZone: 'America/Tijuana' });
  }

  diagnosticLabel(item: AutomationDiagnostic): string {
    switch (item.diagnostic_state) {
      case 'STRUCTURED_COUNTERS_ONLY': return 'Contadores persistidos de esta corrida';
      case 'LOG_NOT_AVAILABLE': return 'Sin evidencia técnica atribuible';
      case 'NOT_APPLICABLE': return 'Sin resultado fallido';
      default: return 'No verificado';
    }
  }

  logLabel(item: AutomationDiagnostic): string {
    return item.log_state === 'LOG_NOT_AVAILABLE'
      || item.diagnostic_state === 'LOG_NOT_AVAILABLE'
      ? 'No disponible' : 'No verificado';
  }

  failureLabel(errorType: string): string {
    const labels: Record<string, string> = {
      ALIAS_UNRESOLVED: 'Alias de sucursal no resuelto',
      ALIAS_AMBIGUOUS_DESTINATION: 'Alias vinculado a varias sucursales',
      MarketingIventasBranchResolutionError: 'Error de resolución de sucursal',
      MarketingIventasBranchSyncError: 'Error durante la sincronización de sucursal',
      IventasClientError: 'Error del cliente/API iVentas',
      UNEXPECTED_BRANCH_ABORT: 'Sincronización abortada inesperadamente',
    };
    return labels[errorType] || 'Tipo no reconocido';
  }
  async copyDiagnostic(): Promise<void> {
    if (!this.diagnostic) { return; }
    const item = this.diagnostic;
    const safeText = [
      'Diagnóstico de automatización',
      `Job: ${item.job_key}`,
      `Corrida: ${item.run_id ?? 'No disponible'}`,
      `Corte: ${item.business_date ?? 'No disponible'}`,
      `Estado: ${item.status ?? 'No verificado'}`,
      'Evidencia: ' + this.diagnosticLabel(item),
      'Log técnico: ' + this.logLabel(item),
      item.sanitized_message,
      ...(item.counts ? [
        'Sucursales solicitadas: ' + item.counts.branches_requested,
        'Sucursales completadas: ' + item.counts.branches_completed,
        'Sucursales no completadas: ' + item.counts.branches_failed,
        'Alias sin resolver: ' + item.counts.aliases_unresolved,
      ] : []),
      ...(item.branch_failures ?? []).map(failure => `${failure.branch_code}: ${this.failureLabel(failure.error_type)}`),
    ].join('\n');
    try {
      await navigator.clipboard.writeText(safeText);
      this.copyStatus = 'Diagnóstico seguro copiado.';
    } catch {
      this.copyStatus = 'No se pudo copiar el diagnóstico.';
    }
  }
}
