import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import {
  DataFreshnessService, DatasetFreshness, FreshnessDatasetKey, FreshnessStatus,
} from './data-freshness.service';

@Component({
  selector: 'app-data-freshness-indicator',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './data-freshness-indicator.component.html',
  styleUrls: ['./data-freshness-indicator.component.css'],
})
export class DataFreshnessIndicatorComponent implements OnChanges, OnDestroy {
  @Input({required:true}) moduleKey: FreshnessDatasetKey = 'marketing.sales_funnel';
  @Input() scopeMode: 'GLOBAL'|'FILTERED' = 'GLOBAL';
  @Input() month: string|null = null;
  @Input() cutoffDate: string|null = null;
  @Input() trackDate: string|null = null;

  state: DatasetFreshness|null = null;
  loading = false;
  private pending: Subscription|null = null;

  constructor(private readonly service: DataFreshnessService) {}

  ngOnChanges(): void {
    this.pending?.unsubscribe();
    this.state = null;
    this.loading = true;
    this.pending = this.service.get(
      this.moduleKey, this.scopeMode, this.month, this.cutoffDate, this.trackDate,
    ).subscribe({
      next: (value) => { this.state = value; this.loading = false; },
      error: () => { this.state = null; this.loading = false; },
    });
  }

  ngOnDestroy(): void {
    this.pending?.unsubscribe();
  }

  get status(): FreshnessStatus {
    return this.state?.status ?? 'UNKNOWN';
  }

  get compactLabel(): string {
    if (this.loading) return 'Verificando corte';
    if (this.status === 'UNKNOWN') {
      if (this.state?.latest_complete_business_date) {
        return 'Corte conjunto: ' + this.formatDate(this.state.latest_complete_business_date);
      }
      if (this.state?.latest_catalog_matched_business_date) {
        return 'Cobertura catálogo actual: ' +
          this.formatDate(this.state.latest_catalog_matched_business_date);
      }
      if (this.state?.latest_observed_business_date) {
        return 'Evidencia: ' + this.formatDate(this.state.latest_observed_business_date);
      }
      return 'Frescura sin verificar';
    }
    const labels: Record<FreshnessStatus,string> = {
      UP_TO_DATE:'Al día',LAGGING:'Pendiente',LATE:'Atrasado',
      NOT_DUE:'Aún no vence',DISABLED:'Deshabilitado',UNKNOWN:'Sin verificar',
    };
    return labels[this.status];
  }

  get detail(): string {
    if (this.loading) return 'Consultando frescura de datos.';
    if (!this.state) return 'No se pudo verificar el estado de los datos.';
    const sources = this.state.sources.map(source =>
      source.key + ': ' + (source.latest_complete_business_date || 'sin evidencia'),
    ).join('; ');
    const coverage=this.state.track_coverage?.coverage;
    const counts=coverage ?
      ' Cobertura catálogo actual: '+coverage.actual_branch_count+
      ' de '+coverage.expected_branch_count+
      ' sucursales. Faltantes: '+coverage.missing_branch_codes.length+
      '. Sobrantes: '+coverage.unexpected_branch_codes.length+
      '. Duplicadas: '+coverage.duplicate_branch_codes.length+
      '. Vigencia histórica del catálogo no certificada.' : '';
    return this.state.detail + counts + (
      this.state.latest_complete_business_date
        ? ' Último corte conjunto: ' + this.state.latest_complete_business_date + '.'
        : ''
    ) + (sources ? ' Fuentes: ' + sources + '.' : '');
  }

  get tone(): string {
    return this.loading ? 'unknown' : this.status.toLowerCase();
  }

  private formatDate(raw: string): string {
    const parts = raw.split('-');
    return parts.length === 3 ? parts[2] + '/' + parts[1] : raw;
  }
}
