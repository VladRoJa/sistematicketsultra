import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import {
  MatDialog,
  MatDialogModule,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import {
  AttendanceAgeBucket,
  AttendanceBranch,
  AttendanceBranchRanking,
  AttendanceCatalogs,
  AttendanceDashboard,
  AttendanceHour,
  AttendanceInterval,
} from './attendance.models';
import { AttendanceDetailDialogComponent } from './attendance-detail-dialog.component';
import { AttendanceService } from './attendance.service';

interface OccupancyChartPoint {
  x: number;
  y: number;
  value: number;
  minute: number;
  label: string;
}

interface OccupancyChartTick {
  x: number;
  label: string;
}

interface OccupancyChartYTick {
  y: number;
  label: string;
}

interface OccupancyChartModel {
  width: number;
  height: number;
  plotX: number;
  plotY: number;
  plotWidth: number;
  plotHeight: number;
  points: string;
  pointItems: OccupancyChartPoint[];
  xTicks: OccupancyChartTick[];
  yTicks: OccupancyChartYTick[];
}

interface HourBarModel {
  hour: number;
  label: string;
  entries: number;
  heightPercent: number;
}

interface AgeBarModel {
  label: string;
  visits: number;
  widthPercent: number;
}

type RankingSortKey =
  | 'rank'
  | 'branch_name'
  | 'visits'
  | 'unique_members'
  | 'peak_occupancy';

type RankingSortDirection = 'asc' | 'desc';

@Component({
  selector: 'app-attendance-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './attendance-dashboard.component.html',
  styleUrls: ['./attendance-dashboard.component.css'],
})
export class AttendanceDashboardComponent implements OnInit {
  catalogs: AttendanceCatalogs | null = null;
  dashboard: AttendanceDashboard | null = null;

  dateFrom = '';
  dateTo = '';
  selectedRegionKey: string | null = null;
  selectedBranchId: number | null = null;
  selectedAttendanceType = 'SOCIO';

  loading = false;
  errorMessage = '';
  showFullRanking = false;
  rankingSortKey: RankingSortKey = 'visits';
  rankingSortDirection: RankingSortDirection = 'desc';

  occupancyChart: OccupancyChartModel | null = null;
  hourBars: HourBarModel[] = [];
  ageBars: AgeBarModel[] = [];

  private readonly numberFormatter = new Intl.NumberFormat('es-MX');

  constructor(
    private readonly attendanceService: AttendanceService,
    private readonly dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.loadCatalogs();
  }

  get availableBranches(): AttendanceBranch[] {
    const branches = this.catalogs?.branches ?? [];

    if (!this.selectedRegionKey) {
      return branches;
    }

    return branches.filter(
      (branch) =>
        branch.region_key === this.selectedRegionKey,
    );
  }

  get hasData(): boolean {
    return Boolean(
      this.dashboard
      && this.dashboard.summary.visits > 0,
    );
  }

  get periodLabel(): string {
    if (!this.dateFrom || !this.dateTo) {
      return 'Sin periodo';
    }
    if (this.dateFrom === this.dateTo) {
      return this.formatDate(this.dateFrom);
    }
    return `${this.formatDate(this.dateFrom)} – ${this.formatDate(this.dateTo)}`;
  }

  get visibleBranchRanking(): AttendanceBranchRanking[] {
    const ranking = this.sortedBranchRanking;
    return this.showFullRanking
      ? ranking
      : ranking.slice(0, 10);
  }

  get hasMoreRankingRows(): boolean {
    return (this.dashboard?.branch_ranking.length ?? 0) > 10;
  }

  get rankingSortSummary(): string {
    const labels: Record<RankingSortKey, string> = {
      rank: 'posición',
      branch_name: 'sucursal',
      visits: 'visitas',
      unique_members: 'únicos',
      peak_occupancy: 'aforo pico',
    };
    const direction = this.rankingSortDirection === 'asc'
      ? 'ascendente'
      : 'descendente';
    return `Ordenado por ${labels[this.rankingSortKey]} · ${direction}`;
  }

  toggleRanking(): void {
    this.showFullRanking = !this.showFullRanking;
  }

  setRankingSort(key: RankingSortKey): void {
    if (this.rankingSortKey === key) {
      this.rankingSortDirection =
        this.rankingSortDirection === 'asc'
          ? 'desc'
          : 'asc';
      return;
    }

    this.rankingSortKey = key;
    this.rankingSortDirection =
      key === 'branch_name' || key === 'rank'
        ? 'asc'
        : 'desc';
  }

  rankingSortIndicator(key: RankingSortKey): string {
    if (this.rankingSortKey !== key) {
      return '↕';
    }
    return this.rankingSortDirection === 'asc'
      ? '↑'
      : '↓';
  }

  rankingPosition(row: AttendanceBranchRanking): number {
    const ranking = this.dashboard?.branch_ranking ?? [];
    const index = ranking.findIndex(
      (item) => item.branch_id === row.branch_id,
    );
    return index >= 0 ? index + 1 : 0;
  }

  private get sortedBranchRanking(): AttendanceBranchRanking[] {
    const ranking = this.dashboard?.branch_ranking ?? [];
    const originalPosition = new Map(
      ranking.map((row, index) => [row.branch_id, index]),
    );
    const direction =
      this.rankingSortDirection === 'asc' ? 1 : -1;

    return [...ranking].sort((left, right) => {
      let comparison = 0;

      switch (this.rankingSortKey) {
        case 'rank':
          comparison =
            (originalPosition.get(left.branch_id) ?? 0)
            - (originalPosition.get(right.branch_id) ?? 0);
          break;
        case 'branch_name':
          comparison = left.branch_name.localeCompare(
            right.branch_name,
            'es',
            { sensitivity: 'base' },
          );
          break;
        case 'unique_members':
          comparison =
            left.unique_members - right.unique_members;
          break;
        case 'peak_occupancy':
          comparison =
            left.peak_occupancy - right.peak_occupancy;
          break;
        case 'visits':
        default:
          comparison = left.visits - right.visits;
          break;
      }

      if (comparison === 0) {
        comparison = left.branch_name.localeCompare(
          right.branch_name,
          'es',
          { sensitivity: 'base' },
        );
      }

      return comparison * direction;
    });
  }

  get occupancyChartTitle(): string {
    if (!this.dateFrom || this.dateFrom === this.dateTo) {
      return 'Aforo durante el día';
    }
    return 'Aforo promedio por hora del día';
  }

  loadCatalogs(): void {
    this.loading = true;
    this.errorMessage = '';

    this.attendanceService.getCatalogs().subscribe({
      next: (catalogs) => {
        this.catalogs = catalogs;
        this.selectedAttendanceType =
          catalogs.default_attendance_type || 'SOCIO';

        if (catalogs.scope.fixed_branch_id !== null) {
          this.selectedBranchId =
            catalogs.scope.fixed_branch_id;
        }

        if (catalogs.latest_business_date) {
          this.dateFrom = catalogs.latest_business_date;
          this.dateTo = catalogs.latest_business_date;
          this.loadDashboard();
          return;
        }

        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.errorMessage =
          'No fue posible cargar los catálogos de Análisis Deportivo.';
      },
    });
  }

  applyFilters(): void {
    if (!this.dateFrom || !this.dateTo) {
      this.errorMessage =
        'Selecciona una fecha inicial y una fecha final.';
      return;
    }

    if (this.dateFrom > this.dateTo) {
      this.errorMessage =
        'La fecha inicial no puede ser posterior a la fecha final.';
      return;
    }

    this.loadDashboard();
  }

  onRegionChange(regionKey: string | null): void {
    this.selectedRegionKey = regionKey || null;

    if (
      this.selectedBranchId !== null
      && !this.availableBranches.some(
        (branch) => branch.id === this.selectedBranchId,
      )
    ) {
      this.selectedBranchId = null;
    }
  }

  onBranchChange(branchId: number | null): void {
    this.selectedBranchId =
      branchId === null ? null : Number(branchId);
  }

  openVisitsDetail(): void {
    const filters = this.dashboard?.filters;
    if (
      !filters?.date_from
      || !filters.date_to
    ) {
      return;
    }

    this.dialog.open(
      AttendanceDetailDialogComponent,
      {
        width: '96vw',
        maxWidth: '1500px',
        height: '86vh',
        data: {
          metric: 'visits',
          dateFrom: filters.date_from,
          dateTo: filters.date_to,
          branchId: filters.branch_id,
          regionKey: filters.region_key,
          attendanceType: filters.attendance_type,
        },
      },
    );
  }

  formatNumber(value: number | null | undefined): string {
    return this.numberFormatter.format(
      Number(value ?? 0),
    );
  }

  formatDuration(
    seconds: number | null | undefined,
  ): string {
    if (seconds === null || seconds === undefined) {
      return '—';
    }

    const totalMinutes = Math.round(seconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;

    if (hours <= 0) {
      return `${minutes} min`;
    }

    return minutes
      ? `${hours} h ${minutes} min`
      : `${hours} h`;
  }

  formatMinute(
    minute: number | null | undefined,
  ): string {
    if (minute === null || minute === undefined) {
      return '—';
    }

    const hour = Math.floor(minute / 60);
    const minutes = minute % 60;
    return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  }

  formatDate(value: string | null): string {
    if (!value) {
      return '—';
    }

    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) {
      return value;
    }

    return `${match[3]}/${match[2]}/${match[1]}`;
  }

  attendanceTypeLabel(value: string): string {
    return value === '__ALL__'
      ? 'Todo el público'
      : value;
  }

  qualityTotal(): number {
    const quality = this.dashboard?.data_quality;
    if (!quality) {
      return 0;
    }

    return (
      quality.open
      + quality.cross_day
      + quality.invalid_time
      + quality.unresolved_branch
      + quality.non_operational_excluded
    );
  }

  private loadDashboard(): void {
    this.loading = true;
    this.errorMessage = '';

    this.attendanceService.getDashboard({
      dateFrom: this.dateFrom,
      dateTo: this.dateTo,
      branchId: this.selectedBranchId,
      regionKey: this.selectedRegionKey,
      attendanceType: this.selectedAttendanceType,
    }).subscribe({
      next: (dashboard) => {
        this.dashboard = dashboard;
        this.showFullRanking = false;
        this.rankingSortKey = 'visits';
        this.rankingSortDirection = 'desc';
        this.buildPresentationModels(dashboard);
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.errorMessage =
          error?.error?.detail
          || 'No fue posible consultar Aforo y Asistencia.';
      },
    });
  }

  private buildPresentationModels(
    dashboard: AttendanceDashboard,
  ): void {
    this.occupancyChart = this.buildOccupancyChart(
      dashboard.occupancy_profile,
    );
    this.hourBars = this.buildHourBars(
      dashboard.entries_by_hour,
    );
    this.ageBars = this.buildAgeBars(
      dashboard.age_distribution,
    );
  }

  private buildOccupancyChart(
    rows: AttendanceInterval[],
  ): OccupancyChartModel | null {
    if (!rows.length) {
      return null;
    }

    const width = 1040;
    const height = 310;
    const plotX = 58;
    const plotY = 20;
    const plotWidth = width - plotX - 24;
    const plotHeight = height - plotY - 44;
    const maxValue = Math.max(
      1,
      ...rows.map((row) => row.occupancy),
    );

    const pointItems = rows.map(
      (row, index): OccupancyChartPoint => {
        const ratio = rows.length <= 1
          ? 0
          : index / (rows.length - 1);
        const x = plotX + ratio * plotWidth;
        const y =
          plotY
          + plotHeight
          - (row.occupancy / maxValue) * plotHeight;

        return {
          x,
          y,
          value: row.occupancy,
          minute: row.minute,
          label: this.formatMinute(row.minute),
        };
      },
    );

    const points = pointItems
      .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
      .join(' ');

    const xTicks = rows
      .filter((_, index) => index % 8 === 0)
      .map((row, tickIndex, filteredRows) => {
        const originalIndex = rows.findIndex(
          (candidate) => candidate.minute === row.minute,
        );
        const ratio = rows.length <= 1
          ? 0
          : originalIndex / (rows.length - 1);

        return {
          x: plotX + ratio * plotWidth,
          label: this.formatMinute(row.minute),
        };
      });

    const yTicks = [0, 0.25, 0.5, 0.75, 1].map(
      (ratio) => ({
        y: plotY + plotHeight - ratio * plotHeight,
        label: this.formatNumber(
          Math.round(maxValue * ratio),
        ),
      }),
    );

    return {
      width,
      height,
      plotX,
      plotY,
      plotWidth,
      plotHeight,
      points,
      pointItems,
      xTicks,
      yTicks,
    };
  }

  private buildHourBars(
    rows: AttendanceHour[],
  ): HourBarModel[] {
    const maxValue = Math.max(
      1,
      ...rows.map((row) => row.entries),
    );

    return rows.map((row) => ({
      hour: row.hour,
      label: `${String(row.hour).padStart(2, '0')}:00`,
      entries: row.entries,
      heightPercent:
        (row.entries / maxValue) * 100,
    }));
  }

  private buildAgeBars(
    rows: AttendanceAgeBucket[],
  ): AgeBarModel[] {
    const maxValue = Math.max(
      1,
      ...rows.map((row) => row.visits),
    );

    return rows.map((row) => ({
      label: row.label,
      visits: row.visits,
      widthPercent:
        (row.visits / maxValue) * 100,
    }));
  }
}
