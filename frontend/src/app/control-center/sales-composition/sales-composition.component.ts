import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  SalesCompositionBranch,
  SalesCompositionGroup,
  SalesCompositionResponse,
  SalesCompositionService,
  SalesCompositionSignal,
  SalesCompositionSnapshot,
  SalesCompositionTariff,
} from './sales-composition.service';

type ViewMode = 'general' | 'advanced';
type SalesModeFilter = 'ALL' | 'CONTRACT' | 'NO_CONTRACT';

@Component({
  selector: 'app-sales-composition',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sales-composition.component.html',
  styleUrls: ['./sales-composition.component.css'],
})
export class SalesCompositionComponent implements OnInit {
  analysis: SalesCompositionResponse | null = null;
  snapshots: SalesCompositionSnapshot[] = [];
  selectedSnapshotId: number | null = null;
  viewMode: ViewMode = 'general';

  isLoading = false;
  isUploading = false;
  errorMessage = '';
  successMessage = '';
  uploadVisible = false;
  selectedFile: File | null = null;
  uploadDateFrom = this.firstDayOfCurrentMonth();
  uploadDateTo = this.todayIso();

  tariffSearch = '';
  branchSearch = '';
  salesModeFilter: SalesModeFilter = 'ALL';

  constructor(
    private readonly salesCompositionService: SalesCompositionService,
  ) {}

  ngOnInit(): void {
    this.loadSnapshotsAndAnalysis();
  }

  get summary() {
    return this.analysis?.summary ?? null;
  }

  get dataQualityOk(): boolean {
    return String(
      this.analysis?.data_quality?.['reconciliation_status'] ?? '',
    ).toLowerCase() === 'ok';
  }

  get topGroups(): SalesCompositionGroup[] {
    return (this.analysis?.groups ?? []).slice(0, 6);
  }

  get positiveDrivers(): SalesCompositionGroup[] {
    return (this.analysis?.drivers.positive ?? []).slice(0, 4);
  }

  get negativeDrivers(): SalesCompositionGroup[] {
    return (this.analysis?.drivers.negative ?? []).slice(0, 4);
  }

  get topBranchMovements(): SalesCompositionBranch[] {
    return (this.analysis?.branches ?? []).slice(0, 8);
  }

  get filteredTariffs(): SalesCompositionTariff[] {
    const search = this.normalize(this.tariffSearch);
    return (this.analysis?.tariffs ?? []).filter((row) => {
      if (
        this.salesModeFilter !== 'ALL'
        && row.sales_mode !== this.salesModeFilter
      ) {
        return false;
      }
      if (!search) return true;
      return [
        row.tariff_name,
        row.group_label,
        row.plan_type ?? '',
      ].some((value) => this.normalize(value).includes(search));
    });
  }

  get filteredBranches(): SalesCompositionBranch[] {
    const search = this.normalize(this.branchSearch);
    if (!search) return this.analysis?.branches ?? [];
    return (this.analysis?.branches ?? []).filter((row) =>
      this.normalize(row.branch).includes(search)
    );
  }

  loadSnapshotsAndAnalysis(): void {
    this.isLoading = true;
    this.errorMessage = '';
    this.salesCompositionService.getSnapshots().subscribe({
      next: (response) => {
        this.snapshots = response.snapshots;
        if (this.snapshots.length === 0) {
          this.analysis = null;
          this.isLoading = false;
          return;
        }
        this.selectedSnapshotId = this.snapshots[0].snapshot_id;
        this.loadAnalysis(this.selectedSnapshotId);
      },
      error: (error) => {
        if (error?.status === 404) {
          this.analysis = null;
          this.isLoading = false;
          return;
        }
        this.isLoading = false;
        this.errorMessage = this.resolveError(
          error,
          'No se pudieron cargar los cortes de Composición de Venta.',
        );
      },
    });
  }

  loadAnalysis(snapshotId?: number | null): void {
    this.isLoading = true;
    this.errorMessage = '';
    this.salesCompositionService.getAnalysis(snapshotId).subscribe({
      next: (response) => {
        this.analysis = response;
        this.selectedSnapshotId = response.source.snapshot_id;
        this.isLoading = false;
      },
      error: (error) => {
        this.isLoading = false;
        if (error?.status === 404) {
          this.analysis = null;
          return;
        }
        this.errorMessage = this.resolveError(
          error,
          'No se pudo cargar el análisis de Composición de Venta.',
        );
      },
    });
  }

  onSnapshotChange(): void {
    if (!this.selectedSnapshotId) return;
    this.loadAnalysis(this.selectedSnapshotId);
  }

  setViewMode(mode: ViewMode): void {
    this.viewMode = mode;
  }

  toggleUpload(): void {
    this.uploadVisible = !this.uploadVisible;
    this.errorMessage = '';
    this.successMessage = '';
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
  }

  uploadCut(): void {
    if (!this.selectedFile) {
      this.errorMessage = 'Selecciona el XLSX exportado por GASCA.';
      return;
    }
    if (!this.uploadDateFrom || !this.uploadDateTo) {
      this.errorMessage = 'Selecciona el rango correspondiente al reporte.';
      return;
    }
    if (this.uploadDateFrom > this.uploadDateTo) {
      this.errorMessage = 'La fecha inicial no puede ser posterior a la final.';
      return;
    }

    this.isUploading = true;
    this.errorMessage = '';
    this.successMessage = '';
    this.salesCompositionService
      .upload(
        this.selectedFile,
        this.uploadDateFrom,
        this.uploadDateTo,
      )
      .subscribe({
        next: (response) => {
          this.analysis = response.analysis;
          this.selectedSnapshotId = response.analysis.source.snapshot_id;
          this.successMessage = response.message;
          this.selectedFile = null;
          this.uploadVisible = false;
          this.isUploading = false;
          this.refreshSnapshots();
        },
        error: (error) => {
          this.isUploading = false;
          this.errorMessage = this.resolveError(
            error,
            'No se pudo procesar el export de GASCA.',
          );
        },
      });
  }

  signalTitle(signal: SalesCompositionSignal): string {
    switch (signal.key) {
      case 'membership_change':
        return 'Cambio en venta de membresías';
      case 'contract_mix':
        return 'Cambio en mix de contrato';
      case 'largest_mix_shift':
        return 'Mayor movimiento de mix';
      case 'top_positive_driver':
        return 'Principal impulsor';
      case 'top_negative_driver':
        return 'Principal freno';
      case 'largest_branch_movement':
        return 'Mayor movimiento por sucursal';
      case 'data_quality_warning':
        return 'Revisar conciliación de la fuente';
      default:
        return 'Señal analítica';
    }
  }

  signalDetail(signal: SalesCompositionSignal): string {
    if (signal.key === 'membership_change') {
      return `${this.formatSignedCurrency(signal.delta_flow)} · ${this.formatSignedPercent(signal.growth_pct)}`;
    }
    if (signal.key === 'contract_mix') {
      return `${this.formatSignedPp(signal.delta_pp)} en participación de contratos`;
    }
    if (signal.key === 'largest_mix_shift') {
      return `${signal.label ?? '—'} · ${this.formatSignedPp(signal.delta_pp)}`;
    }
    if (
      signal.key === 'top_positive_driver'
      || signal.key === 'top_negative_driver'
    ) {
      return `${signal.label ?? '—'} · ${this.formatSignedCurrency(signal.delta_flow)} · ${this.formatPercent(signal.movement_share_pct)} del movimiento absoluto`;
    }
    if (signal.key === 'largest_branch_movement') {
      return `${signal.label ?? '—'} · ${this.formatSignedCurrency(signal.delta_flow)}`;
    }
    return 'Los subtotales del export no conciliaron completamente.';
  }

  mixBarWidth(group: SalesCompositionGroup): number {
    return Math.max(0, Math.min(group.current_mix_pct, 100));
  }

  deltaClass(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return 'delta-neutral';
    }
    if (value > 0) return 'delta-positive';
    if (value < 0) return 'delta-negative';
    return 'delta-neutral';
  }

  formatCurrency(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatSignedCurrency(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return '—';
    }
    const formatted = this.formatCurrency(Math.abs(value));
    return value > 0
      ? `+${formatted}`
      : value < 0
        ? `-${formatted}`
        : formatted;
  }

  formatPercent(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return '—';
    }
    return `${value.toFixed(1)}%`;
  }

  formatSignedPercent(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return '—';
    }
    return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
  }

  formatSignedPp(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return '—';
    }
    return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`;
  }

  formatNumber(value: number | null | undefined): string {
    if (
      value === null
      || value === undefined
      || !Number.isFinite(value)
    ) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value);
  }

  private refreshSnapshots(): void {
    this.salesCompositionService.getSnapshots().subscribe({
      next: (response) => {
        this.snapshots = response.snapshots;
      },
    });
  }

  private normalize(value: string): string {
    return String(value || '').trim().toLowerCase();
  }

  private resolveError(error: any, fallback: string): string {
    return String(
      error?.error?.message
      ?? error?.error?.detail
      ?? fallback,
    );
  }

  private todayIso(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private firstDayOfCurrentMonth(): string {
    const today = this.todayIso();
    return `${today.slice(0, 8)}01`;
  }
}
