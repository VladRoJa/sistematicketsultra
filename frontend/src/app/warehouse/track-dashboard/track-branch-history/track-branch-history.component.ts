//   frontend\src\app\warehouse\track-dashboard\track-branch-history\track-branch-history.component.ts


import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Router } from '@angular/router';
import { combineLatest } from 'rxjs';
import {
  TrackGenerationMode,
  TrackDailyMartRow,
  TrackService,
} from '../../../services/track.service'; 

interface LatestHistorySnapshot {
  trackDate: string;
  usuariosActivos: string;
  usuariosActivosDelta: string;
  usuariosActivosDeltaTone: 'success' | 'danger' | 'neutral';
  ingresoReal: string;
  ingresoDelta: string;
  ingresoDeltaTone: 'success' | 'danger' | 'neutral';
}

interface SparklinePoint {
  x: number;
  y: number;
}

interface SparklineData {
  path: string;
  points: SparklinePoint[];
}

interface BranchOption {
  value: string;
  label: string;
}

interface TargetMonthOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-track-branch-history',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './track-branch-history.component.html',
  styleUrls: ['./track-branch-history.component.css'],
})
export class TrackBranchHistoryComponent implements OnInit {
  readonly pageTitle = 'Detalle por sucursal';
  readonly defaultTargetMonth = this.buildCurrentTargetMonth();
  readonly branchOptions: BranchOption[] = [
  { value: 'VILLAS_DEL_REY', label: 'VILLAS_DEL_REY' },
  { value: 'VILLA_VERDE', label: 'VILLA_VERDE' },
  { value: 'INDEPENDENCIA', label: 'INDEPENDENCIA' },
  { value: 'TEC_MXL', label: 'TEC_MXL' },
  { value: 'SEND_MXL', label: 'SEND_MXL' },
  { value: 'SAN_LUIS', label: 'SAN_LUIS' },
  { value: 'PABELLON_RTO', label: 'PABELLON_RTO' },
  { value: 'MISION_ENS', label: 'MISION_ENS' },
  { value: 'PASEO_2000', label: 'PASEO_2000' },
  { value: 'LOMA_BONITA', label: 'LOMA_BONITA' },
  { value: 'SANTA_FE', label: 'SANTA_FE' },
  { value: 'CARROUSEL_TJ', label: 'CARROUSEL_TJ' },
  { value: 'PAPALOTE_TJ', label: 'PAPALOTE_TJ' },
  { value: 'SEND_CUL', label: 'SEND_CUL' },
  { value: 'SAN_ISIDRO_CUL', label: 'SAN_ISIDRO_CUL' },
  { value: 'AZAHARES_CUL', label: 'AZAHARES_CUL' },
  { value: 'STA_CATARINA', label: 'STA_CATARINA' },
  { value: 'SEND_SALTILLO', label: 'SEND_SALTILLO' },
  { value: 'SEND_CHIH', label: 'SEND_CHIH' },
  { value: 'PASEO_LA_PAZ', label: 'PASEO_LA_PAZ' },
  { value: 'IXTAPALUCA', label: 'IXTAPALUCA' },
  { value: 'INSURGENTES', label: 'INSURGENTES' },
  { value: 'TLALNEPANTLA', label: 'TLALNEPANTLA' },
  { value: 'METEPEC', label: 'METEPEC' },
  { value: 'SALTILLO_VILLALTA', label: 'SALTILLO_VILLALTA' },
  { value: 'LA_VIGA', label: 'LA_VIGA' },
];

  selectedSucursalCanon = '';
  targetMonthOptions: TargetMonthOption[] = [];

  sucursalCanon = '';
  generationMode: TrackGenerationMode = 'manual_preview';
  targetMonth = this.defaultTargetMonth;
  historyRows: TrackDailyMartRow[] = [];
  totalRows = 0;
  latestSnapshot: LatestHistorySnapshot | null = null;
  sociosActivosSparkline: SparklineData | null = null;
  ingresoRealSparkline: SparklineData | null = null;
  

  isLoading = false;
  errorMessage = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly trackService: TrackService,
  ) {}

  ngOnInit(): void {
    this.targetMonthOptions = this.buildRecentTargetMonthOptions();

    combineLatest([this.route.paramMap, this.route.queryParamMap]).subscribe(
      ([paramMap, queryParamMap]) => {
        this.syncRouteStateFromMaps(paramMap, queryParamMap);
        this.ensureTargetMonthOption(this.targetMonth);
        this.loadBranchHistory();
      },
    );
  }

  goBackToTrack(): void {
    this.router.navigate(['/warehouse/track'], {
      queryParams: {
        generation_mode: this.generationMode,
      },
    });
  }

  onSucursalCanonChanged(sucursalCanon: string): void {
  const normalizedSucursalCanon = (sucursalCanon || '').trim().toUpperCase();

  if (!normalizedSucursalCanon || normalizedSucursalCanon === this.sucursalCanon) {
    return;
  }

  this.router.navigate(
    ['/warehouse/track/sucursal', normalizedSucursalCanon],
    {
      queryParams: {
        generation_mode: this.generationMode,
        target_month: this.targetMonth,
      },
    },
  );
}

onTargetMonthChanged(targetMonth: string): void {
  const normalizedTargetMonth = (targetMonth || '').trim();

  if (!normalizedTargetMonth || normalizedTargetMonth === this.targetMonth) {
    return;
  }

  this.router.navigate(
    ['/warehouse/track/sucursal', this.sucursalCanon],
    {
      queryParams: {
        generation_mode: this.generationMode,
        target_month: normalizedTargetMonth,
      },
    },
  );
}

private buildRecentTargetMonthOptions(monthCount = 12): TargetMonthOption[] {
  const options: TargetMonthOption[] = [];
  const today = new Date();

  for (let offset = 0; offset < monthCount; offset += 1) {
    const date = new Date(today.getFullYear(), today.getMonth() - offset, 1);
    const year = date.getFullYear();
    const month = `${date.getMonth() + 1}`.padStart(2, '0');
    const value = `${year}-${month}`;

    options.push({
      value,
      label: this.formatTargetMonthLabel(value),
    });
  }

  return options;
}

private ensureTargetMonthOption(targetMonth: string): void {
  const exists = this.targetMonthOptions.some(
    (option) => option.value === targetMonth,
  );

  if (exists || !targetMonth) {
    return;
  }

  this.targetMonthOptions = [
    {
      value: targetMonth,
      label: this.formatTargetMonthLabel(targetMonth),
    },
    ...this.targetMonthOptions,
  ];
}

  private loadBranchHistory(): void {
  if (!this.sucursalCanon || this.isLoading) {
    return;
  }

  this.isLoading = true;
  this.errorMessage = '';
  this.historyRows = [];
  this.totalRows = 0;
  this.latestSnapshot = null;
  this.sociosActivosSparkline = null;
  this.ingresoRealSparkline = null;

  this.trackService
    .getBranchHistory(
      this.sucursalCanon,
      this.targetMonth,
      this.generationMode,
    )
    .subscribe({
      next: (response) => {
        if (response.status !== 'ok') {
          this.errorMessage =
            response.message ||
            'No se pudo consultar el historial de la sucursal.';
          this.isLoading = false;
          return;
        }

      this.historyRows = this.sortHistoryRowsMostRecentFirst(response.rows || []);
      this.totalRows = this.historyRows.length;
      this.latestSnapshot = this.buildLatestSnapshot();

      const chronologicalRows = this.getHistoryRowsChronological();

      this.sociosActivosSparkline = this.buildSparklineData(
        chronologicalRows.map((row) => row.usuarios_activos_actual ?? 0),
      );

      this.ingresoRealSparkline = this.buildSparklineData(
        chronologicalRows.map((row) => row.ingreso_real_mtd ?? 0),
      );
        this.isLoading = false;
      },
      error: (error) => {
        this.errorMessage =
          error?.error?.message ||
          error?.error?.detail ||
          'Ocurrió un error al consultar el historial de la sucursal.';
        this.isLoading = false;
      },
    });
}

private sortHistoryRowsMostRecentFirst(
  rows: TrackDailyMartRow[],
): TrackDailyMartRow[] {
  return [...rows].sort((left, right) => {
    const leftDate = left.track_date || '';
    const rightDate = right.track_date || '';

    return rightDate.localeCompare(leftDate);
  });
}

private getHistoryRowsChronological(): TrackDailyMartRow[] {
  return [...this.historyRows].reverse();
}

formatInteger(value: number | null | undefined): string {
  return new Intl.NumberFormat('es-MX', {
    maximumFractionDigits: 0,
  }).format(value ?? 0);
}

formatCurrency(value: number | null | undefined): string {
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency: 'MXN',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value ?? 0);
}

formatTargetMonthLabel(value: string): string {
  const normalizedValue = (value || '').trim();

  if (!/^\d{4}-\d{2}$/.test(normalizedValue)) {
    return value;
  }

  const [year, month] = normalizedValue.split('-');
  const monthIndex = Number(month) - 1;

  const date = new Date(Number(year), monthIndex, 1);

  return new Intl.DateTimeFormat('es-MX', {
    month: 'long',
    year: 'numeric',
  }).format(date);
}

formatShortDate(value: string | null | undefined): string {
  const normalizedValue = (value || '').trim();

  if (!normalizedValue) {
    return '';
  }

  const date = new Date(`${normalizedValue}T00:00:00`);

  if (Number.isNaN(date.getTime())) {
    return normalizedValue;
  }

  return new Intl.DateTimeFormat('es-MX', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  }).format(date);
}
calculateProgressPercent(
  realValue: number | null | undefined,
  targetValue: number | null | undefined,
): number {
  const real = realValue ?? 0;
  const target = targetValue ?? 0;

  if (target <= 0) {
    return 0;
  }

  return (real / target) * 100;
}

formatPercent(value: number | null | undefined): string {
  return new Intl.NumberFormat('es-MX', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value ?? 0) + '%';
}

getPreviousHistoryRow(index: number): TrackDailyMartRow | null {
  const previousIndex = index + 1;

  if (index < 0 || previousIndex >= this.historyRows.length) {
    return null;
  }

  return this.historyRows[previousIndex] || null;
}

calculateDeltaFromPreviousDay(
  currentValue: number | null | undefined,
  previousValue: number | null | undefined,
): number {
  const current = currentValue ?? 0;
  const previous = previousValue ?? 0;

  return current - previous;
}

getDeltaTone(value: number): 'success' | 'danger' | 'neutral' {
  if (value > 0) {
    return 'success';
  }

  if (value < 0) {
    return 'danger';
  }

  return 'neutral';
}

formatSignedInteger(value: number | null | undefined): string {
  const normalizedValue = value ?? 0;
  const formatted = this.formatInteger(Math.abs(normalizedValue));

  if (normalizedValue > 0) {
    return `+${formatted}`;
  }

  if (normalizedValue < 0) {
    return `-${formatted}`;
  }

  return formatted;
}

formatSignedCurrency(value: number | null | undefined): string {
  const normalizedValue = value ?? 0;
  const formatted = this.formatCurrency(Math.abs(normalizedValue));

  if (normalizedValue > 0) {
    return `+${formatted}`;
  }

  if (normalizedValue < 0) {
    return `-${formatted}`;
  }

  return formatted;
}

getIngresoDeltaLabel(index: number): string {
  const currentRow = this.historyRows[index];
  const previousRow = this.getPreviousHistoryRow(index);

  if (!currentRow || !previousRow) {
    return '—';
  }

  const delta = this.calculateDeltaFromPreviousDay(
    currentRow.ingreso_real_mtd,
    previousRow.ingreso_real_mtd,
  );

  return this.formatSignedCurrency(delta);
}

getIngresoDeltaTone(index: number): 'success' | 'danger' | 'neutral' {
  const currentRow = this.historyRows[index];
  const previousRow = this.getPreviousHistoryRow(index);

  if (!currentRow || !previousRow) {
    return 'neutral';
  }

  const delta = this.calculateDeltaFromPreviousDay(
    currentRow.ingreso_real_mtd,
    previousRow.ingreso_real_mtd,
  );

  return this.getDeltaTone(delta);
}

getSociosActivosDeltaLabel(index: number): string {
  const currentRow = this.historyRows[index];
  const previousRow = this.getPreviousHistoryRow(index);

  if (!currentRow || !previousRow) {
    return '—';
  }

  const delta = this.calculateDeltaFromPreviousDay(
    currentRow.usuarios_activos_actual,
    previousRow.usuarios_activos_actual,
  );

  return this.formatSignedInteger(delta);
}

getSociosActivosDeltaTone(index: number): 'success' | 'danger' | 'neutral' {
  const currentRow = this.historyRows[index];
  const previousRow = this.getPreviousHistoryRow(index);

  if (!currentRow || !previousRow) {
    return 'neutral';
  }

  const delta = this.calculateDeltaFromPreviousDay(
    currentRow.usuarios_activos_actual,
    previousRow.usuarios_activos_actual,
  );

  return this.getDeltaTone(delta);
}

private buildLatestSnapshot(): LatestHistorySnapshot | null {
  if (this.historyRows.length === 0) {
    return null;
  }

  const latestRow = this.historyRows[0];

  return {
    trackDate: latestRow.track_date,
    usuariosActivos: this.formatInteger(latestRow.usuarios_activos_actual),
    usuariosActivosDelta: this.getSociosActivosWindowDeltaLabel(),
    usuariosActivosDeltaTone: this.getSociosActivosWindowDeltaTone(),
    ingresoReal: this.formatCurrency(latestRow.ingreso_real_mtd),
    ingresoDelta: this.getIngresoWindowDeltaLabel(),
    ingresoDeltaTone: this.getIngresoWindowDeltaTone(),
  };
}

private buildSparklineData(values: number[]): SparklineData | null {
  if (!values.length) {
    return null;
  }

  if (values.length === 1) {
    return {
      path: 'M 6 24 L 114 24',
      points: [
        {
          x: 60,
          y: 24,
        },
      ],
    };
  }

  const width = 120;
  const height = 48;
  const padding = 6;

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const valueRange = maxValue - minValue || 1;

  const points: SparklinePoint[] = values.map((value, index) => {
    const x =
      padding +
      (index * (width - padding * 2)) / (values.length - 1);

    const normalizedY = (value - minValue) / valueRange;
    const y = height - padding - normalizedY * (height - padding * 2);

    return {
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
    };
  });

  const path = points
    .map((point, index) =>
      `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`,
    )
    .join(' ');

  return {
    path,
    points,
  };
}

private getSociosActivosWindowDeltaLabel(): string {
  if (this.historyRows.length < 2) {
    return '—';
  }

  const latestRow = this.historyRows[0];
  const oldestRow = this.historyRows[this.historyRows.length - 1];

  const delta = this.calculateDeltaFromPreviousDay(
    latestRow.usuarios_activos_actual,
    oldestRow.usuarios_activos_actual,
  );

  return this.formatSignedInteger(delta);
}

private getSociosActivosWindowDeltaTone(): 'success' | 'danger' | 'neutral' {
  if (this.historyRows.length < 2) {
    return 'neutral';
  }

  const latestRow = this.historyRows[0];
  const oldestRow = this.historyRows[this.historyRows.length - 1];

  const delta = this.calculateDeltaFromPreviousDay(
    latestRow.usuarios_activos_actual,
    oldestRow.usuarios_activos_actual,
  );

  return this.getDeltaTone(delta);
}

private getIngresoWindowDeltaLabel(): string {
  if (this.historyRows.length < 2) {
    return '—';
  }

  const latestRow = this.historyRows[0];
  const oldestRow = this.historyRows[this.historyRows.length - 1];

  const delta = this.calculateDeltaFromPreviousDay(
    latestRow.ingreso_real_mtd,
    oldestRow.ingreso_real_mtd,
  );

  return this.formatSignedCurrency(delta);
}

private getIngresoWindowDeltaTone(): 'success' | 'danger' | 'neutral' {
  if (this.historyRows.length < 2) {
    return 'neutral';
  }

  const latestRow = this.historyRows[0];
  const oldestRow = this.historyRows[this.historyRows.length - 1];

  const delta = this.calculateDeltaFromPreviousDay(
    latestRow.ingreso_real_mtd,
    oldestRow.ingreso_real_mtd,
  );

  return this.getDeltaTone(delta);
}

  private syncRouteStateFromMaps(
    paramMap: ParamMap,
    queryParamMap: ParamMap,
  ): void {
    const rawSucursalCanon = paramMap.get('sucursalCanon') || '';
    const rawGenerationMode = queryParamMap.get('generation_mode') || '';
    const rawTargetMonth = queryParamMap.get('target_month') || '';

    this.sucursalCanon = rawSucursalCanon.trim().toUpperCase();
    this.generationMode = this.normalizeGenerationMode(rawGenerationMode);
    this.targetMonth = this.normalizeTargetMonth(rawTargetMonth);
    this.selectedSucursalCanon = this.sucursalCanon;
  }

  private normalizeGenerationMode(value: string): TrackGenerationMode {
    if (value === 'official_closed_day') {
      return 'official_closed_day';
    }

    return 'manual_preview';
  }

private normalizeTargetMonth(value: string): string {
  const normalizedValue = value.trim();

  if (/^\d{4}-\d{2}$/.test(normalizedValue)) {
    return normalizedValue;
  }

  return this.defaultTargetMonth;
}

private buildCurrentTargetMonth(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = `${today.getMonth() + 1}`.padStart(2, '0');

  return `${year}-${month}`;
}


}