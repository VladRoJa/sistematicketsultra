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
  newBranchProjectionItems: MethodologyItem[] = [];
  newBranchProjectionDescription = '';
  newBranchProjectionNotes: string[] = [];
  showNewBranchProjection = false;

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
    const ageThreshold = quality.methodology.operational_age_threshold_months;

    this.methodologyItems = [
      { label: 'Agregación', value: this.translate(quality.methodology.aggregate_method) },
      {
        label: 'Selección de método',
        value: `Menos de ${ageThreshold} meses operando: Proyección lineal · ${ageThreshold} meses o más: Proyección histórica.`,
      },
      {
        label: 'Fórmula histórica',
        value: 'Ingreso real MTD ÷ avance histórico esperado al corte.',
      },
      {
        label: 'Fórmula lineal',
        value: 'Ingreso real MTD ÷ día de corte × días del mes.',
      },
      { label: 'Alineación calendario histórica', value: this.translate(quality.methodology.calendar_method) },
      { label: 'Base histórica', value: this.translate(quality.methodology.distribution_basis) },
      { label: 'Base de meta', value: this.translate(quality.methodology.goal_basis) },
      { label: 'Forma diaria de agregadoras', value: quality.methodology.aggregadoras_assumed_same_daily_shape ? 'Se asume la misma forma diaria.' : 'No se asume la misma forma diaria.' },
      { label: 'Ruta fallback', value: quality.methodology.projection_method_priority.map((method) => this.translate(method)).join(' → ') },
      { label: 'Fallback provisional', value: this.fallbackLinearityLabel(quality.methodology.fallback_is_linear) },
    ];

    const linearCount = quality.projection_methods.linear_mtd_pace.branch_count;
    const provisionalCount = quality.projection_methods.legacy_21_calendar_weights.branch_count;

    this.showNewBranchProjection = linearCount + provisionalCount > 0;
    this.newBranchProjectionItems = [];
    this.newBranchProjectionNotes = [];

    if (linearCount > 0) {
      this.newBranchProjectionItems.push({
        label: 'Sucursales con proyección lineal',
        value: String(linearCount),
      });
      this.newBranchProjectionDescription =
        `Las sucursales con menos de ${ageThreshold} meses de operación se proyectan con su ritmo real acumulado al corte.`;
      this.newBranchProjectionNotes.push(
        'La escala proviene únicamente del ingreso real MTD de cada sucursal.',
        'No utiliza el histórico de otras sucursales para calcular el cierre.',
        'La proyección lineal es un método principal por edad operativa; no es un fallback provisional.',
      );
    }

    if (provisionalCount > 0) {
      this.newBranchProjectionItems.push(
        { label: 'Sucursales con fallback provisional', value: String(provisionalCount) },
        { label: 'Muestras válidas', value: String(quality.legacy_21_curve.valid_branch_month_samples) },
        { label: 'Sucursales contribuyentes', value: String(quality.legacy_21_curve.contributing_branch_count) },
        { label: 'Pesos suman 1', value: quality.legacy_21_curve.weights_sum === 1 ? 'Sí' : 'No' },
        { label: 'Cutoff mínimo fallback', value: `Día ${quality.legacy_21_curve.cutoff_minimum_day}` },
        { label: 'Patrón calendario fallback', value: this.translate(quality.legacy_21_curve.calendar_method) },
      );

      if (linearCount === 0) {
        this.newBranchProjectionDescription =
          'El fallback provisional escala el patrón calendario histórico de las sucursales maduras con el real acumulado de la sucursal.';
      }

      this.newBranchProjectionNotes.push(
        'El fallback provisional utiliza distribución histórica; no utiliza un run rate lineal.',
      );
    }
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
      legacy_21_calendar_projection_fallback: 'Proyección provisional con patrón Ultra',
      branch_historical_calendar_weights: 'Proyección histórica',
      linear_mtd_pace: 'Proyección lineal',
      legacy_21_calendar_weights: 'Proyección provisional con patrón Ultra',
      unavailable: 'Proyección no disponible',
      insufficient_comparable_branch_history: 'Sin histórico propio comparable',
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

  private fallbackLinearityLabel(fallbackIsLinear: false): string {
    return fallbackIsLinear
      ? 'El fallback provisional utiliza un run rate lineal.'
      : 'El fallback provisional no utiliza un run rate lineal.';
  }

  private percent(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
  }
}
