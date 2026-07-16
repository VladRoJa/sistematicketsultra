import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges } from '@angular/core';

import { TrackForecastCenterResponse } from '../../services/track.service';

interface MethodologyItem { label: string; value: string; }

@Component({
  selector: 'app-track-forecast-center-methodology',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './track-forecast-center-methodology.component.html',
  styleUrls: ['./track-forecast-center-methodology.component.css'],
})
export class TrackForecastCenterMethodologyComponent implements OnChanges {
  @Input({ required: true }) response!: TrackForecastCenterResponse;

  universeItems: MethodologyItem[] = [];
  coverageItems: MethodologyItem[] = [];
  exclusionItems: string[] = [];
  fallbackItems: string[] = [];
  cutoffItems: MethodologyItem[] = [];
  methodologyItems: MethodologyItem[] = [];
  loaderItems: MethodologyItem[] = [];

  ngOnChanges(): void {
    if (!this.response) return;
    const quality = this.response.quality;
    this.universeItems = [
      { label: 'Sucursales seleccionadas', value: String(quality.branches.selected) },
      { label: 'Sucursales incluidas', value: String(quality.branches.included) },
      { label: 'Con meta', value: String(quality.branches.with_goal) },
      { label: 'Con proyección', value: String(quality.branches.with_projection) },
      { label: 'Sin región', value: String(quality.branches.without_region) },
    ];
    this.coverageItems = [
      { label: 'Meta conocida', value: this.currency(quality.monetary_coverage.known_goal_amount) },
      { label: 'Meta con proyección', value: this.currency(quality.monetary_coverage.goal_amount_with_projection) },
      { label: 'Real operativo total', value: this.currency(quality.monetary_coverage.real_amount_total) },
      { label: 'Real con proyección', value: this.currency(quality.monetary_coverage.real_amount_with_projection) },
      { label: 'Cobertura monetaria de proyección', value: this.percent(quality.monetary_coverage.projection_real_coverage_pct) },
    ];
    this.exclusionItems = quality.exclusions.map((item) => {
      const branch = item.sucursal_canon ?? 'Alcance';
      return `${branch}: ${item.reasons.map((reason) => this.translate(reason)).join(', ')}`;
    });
    this.fallbackItems = quality.fallbacks.map((item) => {
      const count = item.branch_count === undefined ? '' : ` · ${item.branch_count} sucursales`;
      return `${this.translate(item.type)}: ${this.translate(item.reason)}${count}`;
    });
    this.cutoffItems = [
      { label: 'Versión Track', value: String(quality.cutoff.track_daily_version_id) },
      { label: 'Tipo de versión', value: quality.cutoff.version_type },
      { label: 'Estado', value: quality.cutoff.status },
      { label: 'Fecha comercial canónica', value: quality.cutoff.canonical_business_date ?? 'No disponible' },
      { label: 'Snapshot canónico', value: quality.cutoff.canonical_snapshot_id === null ? 'No disponible' : String(quality.cutoff.canonical_snapshot_id) },
    ];
    this.methodologyItems = [
      { label: 'Agregación', value: this.translate(quality.methodology.aggregate_method) },
      { label: 'Alineación calendario', value: this.translate(quality.methodology.calendar_method) },
      { label: 'Base histórica', value: this.translate(quality.methodology.distribution_basis) },
      { label: 'Base de meta', value: this.translate(quality.methodology.goal_basis) },
      { label: 'Fórmula de proyección', value: quality.methodology.projection_formula },
      { label: 'Forma diaria de agregadoras', value: quality.methodology.aggregadoras_assumed_same_daily_shape ? 'Se asume la misma forma diaria.' : 'No se asume la misma forma diaria.' },
    ];
    this.loaderItems = Object.entries(quality.loader_invocations).map(([label, value]) => ({ label, value: String(value) }));
  }

  private translate(value: string | null): string {
    const translations: Record<string, string> = {
      sum_branch_forecasts: 'Suma de forecasts calculados por sucursal.',
      weekday_ordinal_aligned_historical_weights: 'Alineación por día de la semana y posición dentro del mes.',
      venta_total_base: 'Venta base histórica comparable.',
      total_mtd: 'Ingreso Track total acumulado.',
      calendar: 'Calendario',
      authorization: 'Autorización',
      last_weekday_occurrence_fallback: 'Se utilizó la última ocurrencia disponible del mismo día de la semana.',
      empty_assigned_branches_used_primary_branch: 'Se utilizó la sucursal primaria ante un pool vacío.',
      daily_gaps: 'faltan días en la serie diaria',
      missing_region_assignment: 'falta asignación regional',
      overlapping_region_assignments: 'hay asignaciones regionales traslapadas',
      missing_track_version_row: 'falta fila en la versión Track',
      unauthorized_branch: 'sucursal fuera del alcance autorizado',
    };
    return value === null ? 'Sin detalle' : translations[value] ?? value.replace(/_/g, ' ');
  }

  private currency(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(value);
  }

  private percent(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
  }
}
