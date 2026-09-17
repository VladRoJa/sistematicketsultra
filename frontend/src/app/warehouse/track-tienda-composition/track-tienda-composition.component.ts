import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import {
  TrackTiendaBranchItem,
  TrackTiendaCompositionItem,
  TrackTiendaCompositionResponse,
  TrackTiendaCompositionService,
  TrackTiendaDailyItem,
  TrackTiendaGenerationMode,
  TrackTiendaOperation,
  TrackTiendaProductItem,
} from './track-tienda-composition.service';

@Component({
  selector: 'app-track-tienda-composition',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './track-tienda-composition.component.html',
  styleUrls: ['./track-tienda-composition.component.css'],
})
export class TrackTiendaCompositionComponent implements OnInit {
  readonly pageTitle = 'Composición de venta Tienda';

  trackDate = '';
  generationMode: TrackTiendaGenerationMode = 'manual_preview';

  isLoading = false;
  isLoadingOperations = false;
  errorMessage = '';
  operationsErrorMessage = '';

  response: TrackTiendaCompositionResponse | null = null;
  operations: TrackTiendaOperation[] = [];

  selectedFamilia = '';
  selectedProductoCanonico = '';
  selectedSucursalCanon = '';
  detailTitle = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly tiendaService: TrackTiendaCompositionService,
  ) {}

  ngOnInit(): void {
    const queryParams = this.route.snapshot.queryParamMap;
    const requestedDate = String(queryParams.get('track_date') || '').trim();
    const requestedMode = String(
      queryParams.get('generation_mode') || 'manual_preview',
    ).trim();

    this.trackDate = requestedDate || this.buildTodayIsoDate();
    this.generationMode =
      requestedMode === 'official_closed_day'
        ? 'official_closed_day'
        : 'manual_preview';

    this.loadComposition();
  }

  loadComposition(): void {
    if (!this.trackDate || this.isLoading) {
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';
    this.operationsErrorMessage = '';
    this.clearDetail();

    this.tiendaService
      .getComposition({
        trackDate: this.trackDate,
        generationMode: this.generationMode,
      })
      .subscribe({
        next: (response) => {
          this.response = response;
          this.isLoading = false;
          this.syncUrl();
        },
        error: (error) => {
          this.response = null;
          this.isLoading = false;
          this.errorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'No se pudo consultar la composición de Tienda.';
        },
      });
  }

  onTrackDateChanged(): void {
    this.loadComposition();
  }

  goBackToTrack(): void {
    this.router.navigate(['/warehouse/track'], {
      queryParams: {
        track_date: this.trackDate,
        generation_mode: this.generationMode,
      },
    });
  }

  openCompositionItem(item: TrackTiendaCompositionItem): void {
    this.selectedFamilia = item.familia;
    this.selectedProductoCanonico = '';
    this.selectedSucursalCanon = '';
    this.detailTitle = item.familia;
    this.operations = [];
    this.loadOperations();
  }

  openProduct(item: TrackTiendaProductItem): void {
    this.selectedFamilia = item.familia;
    this.selectedProductoCanonico = item.producto_canonico;
    this.selectedSucursalCanon = '';
    this.detailTitle = `${item.familia} · ${item.producto_canonico}`;
    this.loadOperations();
  }

  openBranch(item: TrackTiendaBranchItem): void {
    this.selectedFamilia = '';
    this.selectedProductoCanonico = '';
    this.selectedSucursalCanon = item.sucursal_canon;
    this.detailTitle = item.sucursal_canon;
    this.loadOperations();
  }

  clearDetail(): void {
    this.selectedFamilia = '';
    this.selectedProductoCanonico = '';
    this.selectedSucursalCanon = '';
    this.detailTitle = '';
    this.operations = [];
    this.operationsErrorMessage = '';
  }

  loadOperations(): void {
    if (this.isLoadingOperations || !this.response) {
      return;
    }

    this.isLoadingOperations = true;
    this.operationsErrorMessage = '';

    this.tiendaService
      .getComposition({
        trackDate: this.trackDate,
        generationMode: this.generationMode,
        includeOperations: true,
        familia: this.selectedFamilia || null,
        productoCanonico: this.selectedProductoCanonico || null,
        sucursalCanon: this.selectedSucursalCanon || null,
        operationLimit: 500,
      })
      .subscribe({
        next: (response) => {
          this.operations = response.operations || [];
          this.isLoadingOperations = false;
        },
        error: (error) => {
          this.operations = [];
          this.isLoadingOperations = false;
          this.operationsErrorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'No se pudo consultar el detalle de operaciones.';
        },
      });
  }

  get filteredProducts(): TrackTiendaProductItem[] {
    const items = this.response?.products || [];

    if (!this.selectedFamilia) {
      return items;
    }

    return items.filter((item) => item.familia === this.selectedFamilia);
  }

  get composition(): TrackTiendaCompositionItem[] {
    return this.response?.composition || [];
  }

  get branches(): TrackTiendaBranchItem[] {
    return this.response?.branches || [];
  }

  get daily(): TrackTiendaDailyItem[] {
    return [...(this.response?.daily || [])].sort((left, right) =>
      right.fecha.localeCompare(left.fecha),
    );
  }

  get maxDailyTotal(): number {
    return Math.max(1, ...this.daily.map((item) => Number(item.total || 0)));
  }

  getCompositionBarWidth(item: TrackTiendaCompositionItem): number {
    return this.clampPercent(item.participacion_pct);
  }

  getDailyBarWidth(item: TrackTiendaDailyItem): number {
    const total = Number(item.total || 0);
    return this.clampPercent((total / this.maxDailyTotal) * 100);
  }

  isCompositionItemSelected(item: TrackTiendaCompositionItem): boolean {
    return !!this.selectedFamilia && item.familia === this.selectedFamilia;
  }

  formatProductKeys(keys: string[] | null | undefined): string {
    const values = (keys || []).filter((value) => !!String(value || '').trim());
    return values.length ? `Claves: ${values.join(', ')}` : 'Sin clave';
  }

  getWeekdayShort(value: string | null | undefined): string {
    const raw = String(value || '').trim();
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);

    if (!match) {
      return '';
    }

    const parsed = new Date(
      Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])),
    );
    const labels = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
    return labels[parsed.getUTCDay()] || '';
  }

  formatCurrency(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value || 0));
  }

  formatInteger(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(Number(value || 0));
  }

  formatDecimal(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(Number(value || 0));
  }

  formatPercent(value: number | null | undefined): string {
    return `${new Intl.NumberFormat('es-MX', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(Number(value || 0))}%`;
  }

  formatDate(value: string | null | undefined): string {
    const raw = String(value || '').trim();
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);

    if (!match) {
      return raw;
    }

    return `${match[3]}/${match[2]}/${match[1]}`;
  }

  get resolvedVersionLabel(): string {
    const version = this.response?.resolved_version;

    if (!version) {
      return '';
    }

    return `#${version.id} · ${this.formatVersionType(version.version_type)}`;
  }

  get reconciliationLabel(): string {
    if (!this.response) {
      return '';
    }

    return this.response.summary.is_reconciled
      ? 'Conciliado con Track ✓'
      : `Diferencia vs Track: ${this.formatCurrency(
          this.response.summary.difference,
        )}`;
  }

  private syncUrl(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      replaceUrl: true,
      queryParams: {
        track_date: this.trackDate,
        generation_mode: this.generationMode,
      },
    });
  }

  private formatVersionType(value: string): string {
    if (value === 'preview_operativo') {
      return 'Preview operativo';
    }

    if (value === 'base_nocturna_canonica') {
      return 'Base nocturna canónica';
    }

    if (value === 'cierre_canonico') {
      return 'Cierre canónico';
    }

    return value;
  }

  private clampPercent(value: number): number {
    if (!Number.isFinite(value)) {
      return 0;
    }

    return Math.max(0, Math.min(100, value));
  }

  private buildTodayIsoDate(): string {
    const today = new Date();
    const year = today.getFullYear();
    const month = `${today.getMonth() + 1}`.padStart(2, '0');
    const day = `${today.getDate()}`.padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}
