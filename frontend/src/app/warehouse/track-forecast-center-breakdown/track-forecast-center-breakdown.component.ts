import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';

import { TrackForecastCenterBreakdownItem, TrackForecastCenterResponse } from '../../services/track.service';
import { TrackForecastCenterNavigationEvent } from '../track-forecast-center/track-forecast-center.models';

interface BreakdownRow {
  source: TrackForecastCenterBreakdownItem;
  label: string;
  branches: number;
  goal: string;
  real: string;
  expected: string;
  gap: string;
  projection: string;
  attainment: string;
  coverage: string;
  status: string;
  action: string;
}

@Component({
  selector: 'app-track-forecast-center-breakdown',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './track-forecast-center-breakdown.component.html',
  styleUrls: ['./track-forecast-center-breakdown.component.css'],
})
export class TrackForecastCenterBreakdownComponent implements OnChanges {
  @Input({ required: true }) response!: TrackForecastCenterResponse;
  @Output() navigate = new EventEmitter<TrackForecastCenterNavigationEvent>();

  rows: BreakdownRow[] = [];
  isBranchScope = false;
  branchLabel = '';

  ngOnChanges(): void {
    if (!this.response) return;
    this.isBranchScope = this.response.context.scope === 'branch';
    this.branchLabel = this.response.context.scope_id ?? 'Sucursal';
    this.rows = [...this.response.breakdown.items]
      .sort((left, right) => this.compareGap(left, right))
      .map((item) => this.toRow(item));
  }

  open(row: BreakdownRow): void {
    this.navigate.emit({ drilldown: row.source.drilldown, sourceView: 'breakdown' });
  }

  openBranchAnalysis(): void {
    const branch = this.response.context.scope_id;
    if (!branch) return;
    this.navigate.emit({
      drilldown: {
        scope: 'branch',
        scope_id: branch,
        analytic_route: `/warehouse/track/forecast/branches/${encodeURIComponent(branch)}`,
      },
      sourceView: 'breakdown',
    });
  }

  private compareGap(left: TrackForecastCenterBreakdownItem, right: TrackForecastCenterBreakdownItem): number {
    const a = left.summary.gap_vs_goal_pace;
    const b = right.summary.gap_vs_goal_pace;
    if (a === null && b === null) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    return a - b;
  }

  private toRow(item: TrackForecastCenterBreakdownItem): BreakdownRow {
    const summary = item.summary;
    const coverage = item.metric_coverage.gap_vs_goal_pace;
    return {
      source: item,
      label: item.label,
      branches: item.branch_count,
      goal: this.currency(summary.goal_month),
      real: this.currency(summary.real_mtd),
      expected: this.currency(summary.goal_expected_mtd_at_cutoff),
      gap: this.currency(summary.gap_vs_goal_pace),
      projection: this.currency(summary.projected_close_comparable_to_goal),
      attainment: this.percent(summary.projected_goal_attainment_pct),
      coverage: `${coverage.included_branch_count} de ${coverage.eligible_branch_count}`,
      status: this.status(item.quality_status),
      action: item.dimension === 'cohort' ? 'Ver cohorte' : item.dimension === 'region' ? 'Ver región' : 'Ver análisis completo',
    };
  }

  private currency(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 }).format(value);
  }

  private percent(value: number | null): string {
    if (value === null) return '—';
    return new Intl.NumberFormat('es-MX', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
  }

  private status(value: string): string {
    if (value === 'available') return 'Disponible';
    if (value === 'partial') return 'Cobertura parcial';
    return 'No disponible';
  }
}

