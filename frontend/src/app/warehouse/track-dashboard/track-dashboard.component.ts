//   frontend\src\app\warehouse\track-dashboard\track-dashboard.component.ts


import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../services/auth.service';
import {
  TrackService,
  TrackGenerationMode,
  TrackPipelineResponse,
  TrackDailyMartResponse,
  TrackDailyMartRow,
  TrackResolvedVersion,
} from '../../services/track.service';

type ProgressTone = 'danger' | 'warning' | 'success' | 'neutral';
type SummaryTone = ProgressTone | 'default';
type TrackColumnGroupKey =
  | 'ocupacion'
  | 'crecimiento'
  | 'ventas_reactivaciones'
  | 'bajas_churn'
  | 'domiciliados'
  | 'arpu'
  | 'ingresos'
  | 'tienda';

type TrackSortDirection = 'asc' | 'desc';

type TrackViewMode = 'simplificada' | 'completa';

interface TrackViewModeOption {
  value: TrackViewMode;
  label: string;
  description: string;
}


type TrackSortKey =
  | 'sucursal_canon'

  // Ocupación
  | 'm2_sin_circulaciones'
  | 'usuarios_inicio_mes'
  | 'proyeccion_usuarios_cierre_mes'
  | 'usuarios_activos_actual'
  | 'ocupacion_inicio_mes'
  | 'meta_ocupacion_px_m2'
  | 'meta_ocupacion_mes'
  | 'ocupacion_actual'
  | 'diferencia_ocupacion_inicio'
  | 'avance_ocupacion'

  // Crecimiento
  | 'diferencia_inicio_mes'
  | 'diferencia_meta_crecimiento'
  | 'avance_meta_crecimiento'
  | 'alcance_usuarios_activos'

  // Ventas nuevas y reactivaciones
  | 'meta_clientes_nuevos_mes'
  | 'clientes_nuevos_ideal_mtd'
  | 'clientes_nuevos_real_mtd'
  | 'diferencia_clientes_nuevos_ideal'
  | 'avance_clientes_nuevos'
  | 'diferencia_clientes_nuevos'
  | 'meta_clientes_nuevos_dia'
  | 'meta_reactivaciones_mes'
  | 'reactivaciones_ideal_mtd'
  | 'reactivaciones_real_mtd'
  | 'diferencia_reactivaciones_ideal'
  | 'avance_reactivaciones'

  // Bajas & churn
  | 'meta_bajas_mes'
  | 'bajas_ideal_mtd'
  | 'bajas_reales_mtd'
  | 'diferencia_bajas_ideal'
  | 'meta_churn_mes'
  | 'churn_ideal_mtd'
  | 'churn_real_mtd'
  | 'diferencia_churn_ideal'

  // Domiciliados
  | 'meta_nuevos_domiciliados_mes'
  | 'domiciliados_ideal_mtd'
  | 'nuevos_domiciliados_real_mtd'
  | 'avance_domiciliados'
  | 'diferencia_domiciliados'
  | 'diferencia_domiciliados_ideal'
  | 'meta_domiciliados_dia'

  // Ingresos
  | 'meta_faycgo_mes'
  | 'ingreso_ideal_cierre_mtd'
  | 'ingreso_real_base_mtd'
  | 'ingreso_real_agregadora_mtd'
  | 'ingreso_real_mtd'
  | 'avance_ingreso'
  | 'avance_ingreso_ideal'
  | 'diferencia_ingreso'
  | 'diferencia_ingreso_ideal'
  | 'meta_ingreso_dia'

  // ARPU
  | 'meta_arpu_mes'
  | 'arpu_actual'
  | 'arpu_teorico'
  | 'diferencia_arpu'
  | 'avance_arpu'

  // Tienda
  | 'meta_venta_tienda_mes'
  | 'venta_tienda_real_mtd'
  | 'avance_tienda'
  | 'diferencia_tienda'
  | 'meta_tienda_dia';

interface TrackSortState {
  key: TrackSortKey;
  direction: TrackSortDirection;
}


interface TrackColumnGroupOption {
  key: TrackColumnGroupKey;
  label: string;
}

interface GenerationModeOption {
  value: TrackGenerationMode;
  label: string;
}

interface TrackSummaryCard {
  label: string;
  value: string;
  tone: SummaryTone;
  compact?: boolean;
}

interface TrackViewRow {
  rowKind: 'data' | 'subtotal' | 'total';
  displayLabel: string;

  sucursalCanon: string;

  // Ocupación
  m2SinCirculaciones: string;
  ocupacionInicioMes: string;
  metaOcupacionPxM2: string;
  metaOcupacionMes: string;
  ocupacionActual: string;
  diferenciaOcupacionInicioLabel: string;
  diferenciaOcupacionInicioTone: ProgressTone;
  avanceOcupacionLabel: string;
  avanceOcupacionTone: ProgressTone;

  // Crecimiento
  usuariosInicioMes: string;
  usuariosActivos: string;
  proyeccionUsuariosCierre: string;
  diferenciaInicioMesLabel: string;
  diferenciaInicioMesTone: ProgressTone;
  diferenciaMetaCrecimientoLabel: string;
  diferenciaMetaCrecimientoTone: ProgressTone;
  avanceMetaCrecimientoLabel: string;
  avanceMetaCrecimientoTone: ProgressTone;
  alcanceUsuariosActivosLabel: string;
  alcanceUsuariosActivosTone: ProgressTone;

  // Ventas nuevas y reactivaciones
  metaClientesNuevos: string;
  clientesNuevosIdealMtd: string;
  clientesNuevos: string;
  diferenciaClientesNuevosIdealLabel: string;
  diferenciaClientesNuevosIdealTone: ProgressTone;
  avanceClientesNuevosLabel: string;
  avanceClientesNuevosTone: ProgressTone;
  diferenciaClientesNuevosLabel: string;
  diferenciaClientesNuevosTone: ProgressTone;
  metaClientesNuevosDia: string;
  diferenciaClientesNuevosDiaLabel: string;
  diferenciaClientesNuevosDiaTone: ProgressTone;

  metaReactivaciones: string;
  reactivacionesIdealMtd: string;
  reactivacionesReales: string;
  diferenciaReactivacionesIdealLabel: string;
  diferenciaReactivacionesIdealTone: ProgressTone;
  avanceReactivacionesLabel: string;
  avanceReactivacionesTone: ProgressTone;

  // Bajas & churn
  metaBajas: string;
  bajasIdealMtd: string;
  bajasReales: string;
  diferenciaBajasIdealLabel: string;
  diferenciaBajasIdealTone: ProgressTone;
  metaChurnLabel: string;
  churnIdealLabel: string;
  churnRealLabel: string;
  diferenciaChurnIdealLabel: string;
  diferenciaChurnIdealTone: ProgressTone;

  // Domiciliados
  metaNuevosDomiciliados: string;
  domiciliadosIdealMtd: string;
  nuevosDomiciliados: string;
  avanceDomiciliadosLabel: string;
  avanceDomiciliadosTone: ProgressTone;
  diferenciaDomiciliadosLabel: string;
  diferenciaDomiciliadosTone: ProgressTone;
  metaDomiciliadosDia: string;
  diferenciaDomiciliadosDiaLabel: string;
  diferenciaDomiciliadosDiaTone: ProgressTone;
  diferenciaDomiciliadosIdealLabel: string;
  diferenciaDomiciliadosIdealTone: ProgressTone;

  // Ingresos
  metaFaycgo: string;
  ingresoIdealCierre: string;
  ingresoBase: string;
  ingresoAgregadoras: string;
  ingresoReal: string;
  avanceIngresoLabel: string;
  avanceIngresoTone: ProgressTone;
  avanceIngresoIdealLabel: string;
  avanceIngresoIdealTone: ProgressTone;
  diferenciaIngresoLabel: string;
  diferenciaIngresoTone: ProgressTone;
  diferenciaIngresoIdealLabel: string;
  diferenciaIngresoIdealTone: ProgressTone;
  metaIngresoDia: string;
  diferenciaIngresoDiaLabel: string;
  diferenciaIngresoDiaTone: ProgressTone;

  // ARPU
  metaArpu: string;
  arpuActual: string;
  arpuTeorico: string;
  diferenciaArpuLabel: string;
  diferenciaArpuTone: ProgressTone;
  avanceArpuLabel: string;
  avanceArpuTone: ProgressTone;

  // Tienda
  metaVentaTienda: string;
  ventaTiendaReal: string;
  avanceTiendaLabel: string;
  avanceTiendaTone: ProgressTone;
  diferenciaTiendaLabel: string;
  diferenciaTiendaTone: ProgressTone;
  metaTiendaDiaLabel: string;
  metaTiendaDiaTone: ProgressTone;
}

@Component({
  selector: 'app-track-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './track-dashboard.component.html',
  styleUrls: ['./track-dashboard.component.css'],
})
export class TrackDashboardComponent implements OnInit {
  readonly pageTitle = 'Track diario';
  readonly pageSubtitle =
    'Genera snapshots manuales y consulta resultados del track dentro de Warehouse.';

  readonly generationModeOptions: GenerationModeOption[] = [
    {
      value: 'manual_preview',
      label: 'Manual preview',
    },
    {
      value: 'official_closed_day',
      label: 'Official closed day',
    },
  ];

  readonly branchOpeningOrder: string[] = [
    'VILLAS_DEL_REY',
    'VILLA_VERDE',
    'INDEPENDENCIA',
    'TEC_MXL',
    'SEND_MXL',
    'SAN_LUIS',
    'PABELLON_RTO',
    'MISION_ENS',
    'PASEO_2000',
    'LOMA_BONITA',
    'SANTA_FE',
    'CARROUSEL_TJ',
    'PAPALOTE_TJ',
    'SEND_CUL',
    'SAN_ISIDRO_CUL',
    'AZAHARES_CUL',
    'STA_CATARINA',
    'SEND_SALTILLO',
    'SEND_CHIH',
    'PASEO_LA_PAZ',
    'IXTAPALUCA',
    'INSURGENTES',
    'TLALNEPANTLA',
    'METEPEC',
    'SALTILLO_VILLALTA',
    'LA_VIGA',
  ];

  readonly simplifiedTrackColumnGroupOptions: TrackColumnGroupOption[] = [
  { key: 'ocupacion', label: 'Ocupación' },
  { key: 'crecimiento', label: 'Crecimiento' },
  { key: 'domiciliados', label: 'Domiciliados' },
  { key: 'ingresos', label: 'Ingresos' },
  { key: 'tienda', label: 'Tienda' },
];

readonly completeTrackColumnGroupOptions: TrackColumnGroupOption[] = [
  { key: 'ocupacion', label: 'Ocupación' },
  { key: 'crecimiento', label: 'Crecimiento' },
  { key: 'ingresos', label: 'Ingresos totales' },
  { key: 'ventas_reactivaciones', label: 'Ventas y reactivaciones' },
  { key: 'bajas_churn', label: 'Bajas & Churn' },
  { key: 'domiciliados', label: 'Domiciliados' },
  { key: 'arpu', label: 'ARPU' },
  { key: 'tienda', label: 'Tienda' },
];

trackViewMode: TrackViewMode = 'simplificada';

readonly trackViewModeOptions: TrackViewModeOption[] = [
  {
    value: 'simplificada',
    label: 'Vista simplificada',
    description: 'Lectura operativa',
  },
  {
    value: 'completa',
    label: 'Vista completa',
    description: 'Análisis extendido',
  },
];

get trackColumnGroupOptions(): TrackColumnGroupOption[] {
  return this.isCompleteTrackView()
    ? this.completeTrackColumnGroupOptions
    : this.simplifiedTrackColumnGroupOptions;
}

setTrackViewMode(mode: TrackViewMode): void {
  if (this.trackViewMode === mode) {
    return;
  }

  this.trackViewMode = mode;
  this.selectedTrackColumnGroups = [];
}

isTrackViewModeActive(mode: TrackViewMode): boolean {
  return this.trackViewMode === mode;
}

isSimplifiedTrackView(): boolean {
  return this.trackViewMode === 'simplificada';
}

isCompleteTrackView(): boolean {
  return this.trackViewMode === 'completa';
}

getTrackViewModeButtonClass(mode: TrackViewMode): string {
  return this.isTrackViewModeActive(mode)
    ? 'track-view-mode__button track-view-mode__button--active'
    : 'track-view-mode__button';
}


  trackDate = this.buildTodayIsoDate();
  generationMode: TrackGenerationMode = 'manual_preview';

  isSubmitting = false;
  isLoadingMart = false;
  isDownloadingTrackExcel = false;
  errorMessage = '';
  martErrorMessage = '';

  lastResponse: TrackPipelineResponse | null = null;
  rawMartRows: TrackDailyMartRow[] = [];
  viewRows: TrackViewRow[] = [];
  dataMartRows: TrackDailyMartRow[] = [];
  activeSort: TrackSortState | null = null;
  summaryCards: TrackSummaryCard[] = [];  

  totalRowsLabel = '0';
  selectedModeLabel = '';
  lastLoadedTrackDateLabel = '';
  agregadorasFreshnessLabel = '';
  resolvedVersion: TrackResolvedVersion | null = null;
  trackVersionLabel = '';
  trackGeneratedAtLabel = '';

  constructor(
    private readonly trackService: TrackService,
    private readonly router: Router,
    private readonly authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.syncSelectedModeLabel();
    this.loadDailyMart();
  }

  runTrackPipeline(): void {
    if (!this.puedeEjecutarTrack()) {
      this.errorMessage = 'No tienes permisos para ejecutar procesos del Track.';
      return;
    }
    if (this.isSubmitting) {
      return;
    }

    this.isSubmitting = true;
    this.errorMessage = '';
    this.lastResponse = null;

    this.trackService
      .runDailyPipeline(this.trackDate, this.generationMode)
      .subscribe({
        next: (response) => {
          this.lastResponse = response;

          if (response.status !== 'ok') {
            this.errorMessage =
              response.message || 'No se pudo ejecutar el pipeline del Track.';
            this.isSubmitting = false;
            return;
          }

          this.isSubmitting = false;
          this.loadDailyMart();
        },
        error: (error) => {
          this.errorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'Ocurrió un error al ejecutar el pipeline del Track.';
          this.isSubmitting = false;
        },
      });
  }

loadDailyMart(): void {
  if (this.isLoadingMart) {
    return;
  }

  this.isLoadingMart = true;
  this.resetLoadedMartState();
  this.syncSelectedModeLabel();

  this.fetchDailyMart();
}

downloadTrackExcel(): void {
  if (this.isDownloadingTrackExcel) {
    return;
  }

  this.isDownloadingTrackExcel = true;
  this.martErrorMessage = '';

  this.trackService
    .downloadDailyMartExcel(this.trackDate, this.generationMode)
    .subscribe({
      next: (blob: Blob) => {
        this.saveBlobAsFile(blob, this.buildTrackExcelFilename());
        this.isDownloadingTrackExcel = false;
      },
      error: (error) => {
        this.martErrorMessage =
          error?.error?.message ||
          error?.error?.detail ||
          'Ocurrió un error al descargar el Excel del Track.';

        this.isDownloadingTrackExcel = false;
      },
    });
}

getTrackExcelButtonLabel(): string {
  if (this.isDownloadingTrackExcel) {
    return 'Descargando...';
  }

  return 'Descargar Excel';
}

private buildTrackExcelFilename(): string {
  return `Track_${this.trackDate}_${this.generationMode}.xlsx`;
}

private saveBlobAsFile(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();

  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

  private fetchDailyMart(): void {
    this.trackService
      .getDailyMart(this.trackDate, this.generationMode)
      .subscribe({
        next: (response: TrackDailyMartResponse) => {
          if (response.status !== 'ok') {
            this.martErrorMessage =
              response.message || 'No se pudo consultar el Track daily mart.';
            this.agregadorasFreshnessLabel = '';  
            this.resolvedVersion = null;
            this.trackVersionLabel = '';
            this.trackGeneratedAtLabel = '';
            this.isLoadingMart = false;
            return;
          }

          const baseRows = this.sortRowsByOpeningOrder(response.rows || []);
          const visibleRows = baseRows;

          this.resolvedVersion = response.resolved_version || null;
          this.trackVersionLabel = this.buildTrackVersionLabel(this.resolvedVersion);
          this.trackGeneratedAtLabel = this.buildTrackGeneratedAtLabel(this.resolvedVersion);

          this.agregadorasFreshnessLabel =
            this.buildAgregadorasFreshnessLabel(visibleRows);

          this.summaryCards = this.buildSummaryCards(visibleRows);
          this.dataMartRows = visibleRows;
          this.rebuildTrackViewRows();

          this.totalRowsLabel = this.formatInteger(visibleRows.length);
          this.lastLoadedTrackDateLabel = response.track_date || this.trackDate;
          this.isLoadingMart = false;
        },
        error: (error) => {
          this.martErrorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'Ocurrió un error al consultar el Track daily mart.';
            this.resolvedVersion = null;
            this.trackVersionLabel = '';
            this.trackGeneratedAtLabel = '';
          this.isLoadingMart = false;
        },
      });
  }

  private resetLoadedMartState(): void {
    this.martErrorMessage = '';
    this.rawMartRows = [];
    this.dataMartRows = [];
    this.activeSort = null;
    this.viewRows = [];
    this.summaryCards = [];
    this.totalRowsLabel = '0';
    this.lastLoadedTrackDateLabel = this.trackDate;
    this.resolvedVersion = null;
    this.trackVersionLabel = '';
    this.trackGeneratedAtLabel = '';
    this.agregadorasFreshnessLabel = '';
  }

sortTrackTable(key: TrackSortKey): void {
  if (!this.activeSort || this.activeSort.key !== key) {
    this.activeSort = {
      key,
      direction: 'asc',
    };
  } else if (this.activeSort.direction === 'asc') {
    this.activeSort = {
      key,
      direction: 'desc',
    };
  } else {
    this.activeSort = null;
  }

  this.rebuildTrackViewRows();
}

resetTrackSort(): void {
  this.activeSort = null;
  this.rebuildTrackViewRows();
}

hasActiveTrackSort(): boolean {
  return this.activeSort !== null;
}

getActiveTrackSortLabel(): string {
  if (!this.activeSort) {
    return 'Orden de apertura';
  }

  const directionLabel = this.activeSort.direction === 'asc'
    ? 'menor a mayor'
    : 'mayor a menor';

  return `Orden especial: ${this.getTrackSortColumnLabel(this.activeSort.key)} · ${directionLabel}`;
}

getTrackSortIndicator(key: TrackSortKey): string {
  if (!this.activeSort || this.activeSort.key !== key) {
    return '↕';
  }

  return this.activeSort.direction === 'asc' ? '↑' : '↓';
}

getTrackSortHeaderClass(key: TrackSortKey): string {
  const activeClass =
    this.activeSort?.key === key ? ' track-sort-header--active' : '';

  return `track-sort-header${activeClass}`;
}

private rebuildTrackViewRows(): void {
  const sortedDataRows = this.getSortedDataRows(this.dataMartRows);

  this.rawMartRows = this.appendClosingRows(sortedDataRows);
  this.viewRows = this.rawMartRows.map((row) => this.buildViewRow(row));
}

private getSortedDataRows(rows: TrackDailyMartRow[]): TrackDailyMartRow[] {
  if (!this.activeSort) {
    return this.sortRowsByOpeningOrder(rows);
  }

  const directionMultiplier = this.activeSort.direction === 'asc' ? 1 : -1;

  return [...rows].sort((left, right) => {
    const leftValue = this.getTrackSortValue(left, this.activeSort!.key);
    const rightValue = this.getTrackSortValue(right, this.activeSort!.key);

    const comparison = this.compareTrackSortValues(leftValue, rightValue);

    if (comparison !== 0) {
      return comparison * directionMultiplier;
    }

    return this.getOpeningOrderIndex(left) - this.getOpeningOrderIndex(right);
  });
}

puedeEjecutarTrack(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return ['ADMIN', 'ADMINISTRADOR', 'SUPER_ADMIN'].includes(rol);
}

canViewRegionalIntelligence(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'LECTOR_GLOBAL',
    'GERENTE_REGIONAL',
  ].includes(rol);
}

private compareTrackSortValues(
  leftValue: string | number,
  rightValue: string | number,
): number {
  if (typeof leftValue === 'string' || typeof rightValue === 'string') {
    return String(leftValue).localeCompare(String(rightValue), 'es-MX');
  }

  return leftValue - rightValue;
}

private getOpeningOrderIndex(row: TrackDailyMartRow): number {
  const index = this.branchOpeningOrder.indexOf(row.sucursal_canon);

  return index >= 0 ? index : Number.MAX_SAFE_INTEGER;
}

private getTrackSortValue(
  row: TrackDailyMartRow,
  key: TrackSortKey,
): string | number {
  switch (key) {
    case 'sucursal_canon':
      return row.sucursal_canon || '';

    // Ocupación
    case 'ocupacion_inicio_mes':
      return this.calculateOccupancyRatio(
        row.usuarios_inicio_mes,
        row.m2_sin_circulaciones,
      );

    case 'meta_ocupacion_px_m2':
      return 2;

    case 'meta_ocupacion_mes':
      return this.calculateOccupancyRatio(
        row.proyeccion_usuarios_cierre_mes,
        row.m2_sin_circulaciones,
      );

    case 'ocupacion_actual':
      return this.calculateOccupancyRatio(
        row.usuarios_activos_actual,
        row.m2_sin_circulaciones,
      );

    case 'diferencia_ocupacion_inicio':
      return this.calculateDifference(
        this.calculateOccupancyRatio(row.usuarios_activos_actual, row.m2_sin_circulaciones),
        this.calculateOccupancyRatio(row.usuarios_inicio_mes, row.m2_sin_circulaciones),
      );

    case 'avance_ocupacion':
      return this.calculateProgressPercent(
        row.usuarios_activos_actual,
        row.proyeccion_usuarios_cierre_mes,
      );

    // Crecimiento
    case 'diferencia_inicio_mes':
      return this.calculateDifference(
        row.usuarios_activos_actual,
        row.usuarios_inicio_mes,
      );

    case 'diferencia_meta_crecimiento':
      return this.calculateDifference(
        row.usuarios_activos_actual,
        row.proyeccion_usuarios_cierre_mes,
      );

    case 'avance_meta_crecimiento':
      return this.calculateRelativeDifferencePercent(
        row.usuarios_activos_actual,
        row.proyeccion_usuarios_cierre_mes,
      );

    case 'alcance_usuarios_activos':
      return this.calculateRelativeDifferencePercent(
        row.usuarios_activos_actual,
        row.usuarios_inicio_mes,
      );

    // Ventas nuevas y reactivaciones
    case 'clientes_nuevos_ideal_mtd':
      return this.calculateIdealMtdTarget(
        row.meta_clientes_nuevos_mes,
        row.track_date,
      );

    case 'diferencia_clientes_nuevos_ideal':
      return this.calculateDifference(
        row.clientes_nuevos_real_mtd,
        this.calculateIdealMtdTarget(
          row.meta_clientes_nuevos_mes,
          row.track_date,
        ),
      );

    case 'avance_clientes_nuevos':
      return this.calculateProgressPercent(
        row.clientes_nuevos_real_mtd,
        row.meta_clientes_nuevos_mes,
      );

    case 'diferencia_clientes_nuevos':
      return this.calculateDifference(
        row.clientes_nuevos_real_mtd,
        row.meta_clientes_nuevos_mes,
      );

    case 'meta_clientes_nuevos_dia':
      return this.calculateRemainingToIdealTarget(
        row.clientes_nuevos_real_mtd,
        this.calculateIdealMtdTarget(
          row.meta_clientes_nuevos_mes,
          row.track_date,
        ),
      );

    case 'reactivaciones_ideal_mtd':
      return this.calculateIdealMtdTarget(
        row.meta_reactivaciones_mes,
        row.track_date,
      );

    case 'diferencia_reactivaciones_ideal':
      return this.calculateDifference(
        this.calculateIdealMtdTarget(
          row.meta_reactivaciones_mes,
          row.track_date,
        ),
        row.reactivaciones_real_mtd,
      );

    case 'avance_reactivaciones':
      return this.calculateProgressPercent(
        row.reactivaciones_real_mtd,
        row.meta_reactivaciones_mes,
      );

    // Bajas & churn
    case 'bajas_ideal_mtd':
      return this.calculateIdealMtdTarget(
        row.meta_bajas_mes,
        row.track_date,
      );

    case 'diferencia_bajas_ideal':
      return this.calculateDifference(
        row.bajas_reales_mtd,
        this.calculateIdealMtdTarget(row.meta_bajas_mes, row.track_date),
      );

    case 'meta_churn_mes':
      return this.calculateChurnPercent(
        row.meta_bajas_mes,
        row.proyeccion_usuarios_cierre_mes,
      );

    case 'churn_ideal_mtd':
      return this.calculateChurnPercent(
        this.calculateIdealMtdTarget(row.meta_bajas_mes, row.track_date),
        row.usuarios_inicio_mes,
      );

    case 'churn_real_mtd':
      return this.calculateChurnPercent(
        row.bajas_reales_mtd,
        row.usuarios_inicio_mes,
      );

    case 'diferencia_churn_ideal':
      return this.calculateDifference(
        this.calculateChurnPercent(row.bajas_reales_mtd, row.usuarios_inicio_mes),
        this.calculateChurnPercent(
          this.calculateIdealMtdTarget(row.meta_bajas_mes, row.track_date),
          row.usuarios_inicio_mes,
        ),
      );

    // Domiciliados
    case 'domiciliados_ideal_mtd':
      return this.calculateIdealMtdTarget(
        row.meta_nuevos_domiciliados_mes,
        row.track_date,
      );

    case 'avance_domiciliados':
      return this.calculateProgressPercent(
        row.nuevos_domiciliados_real_mtd,
        row.meta_nuevos_domiciliados_mes,
      );

    case 'diferencia_domiciliados':
      return this.calculateDifference(
        row.nuevos_domiciliados_real_mtd,
        row.meta_nuevos_domiciliados_mes,
      );

    case 'diferencia_domiciliados_ideal':
      return this.calculateDifference(
        row.nuevos_domiciliados_real_mtd,
        this.calculateIdealMtdTarget(
          row.meta_nuevos_domiciliados_mes,
          row.track_date,
        ),
      );

    case 'meta_domiciliados_dia':
      return this.calculateRemainingToIdealTarget(
        row.nuevos_domiciliados_real_mtd,
        this.calculateIdealMtdTarget(
          row.meta_nuevos_domiciliados_mes,
          row.track_date,
        ),
      );

    // Ingresos
    case 'ingreso_ideal_cierre_mtd':
      return this.calculateIdealMtdTarget(row.meta_faycgo_mes, row.track_date);

    case 'avance_ingreso':
      return this.calculateProgressPercent(
        row.ingreso_real_mtd,
        row.meta_faycgo_mes,
      );

    case 'avance_ingreso_ideal':
      return this.calculateProgressPercent(
        row.ingreso_real_mtd,
        this.calculateIdealMtdTarget(row.meta_faycgo_mes, row.track_date),
      );

    case 'diferencia_ingreso':
      return this.calculateDifference(
        row.ingreso_real_mtd,
        row.meta_faycgo_mes,
      );

    case 'diferencia_ingreso_ideal':
      return this.calculateDifference(
        row.ingreso_real_mtd,
        this.calculateIdealMtdTarget(row.meta_faycgo_mes, row.track_date),
      );

    case 'meta_ingreso_dia':
      return this.calculateRemainingToIdealTarget(
        row.ingreso_real_mtd,
        this.calculateIdealMtdTarget(row.meta_faycgo_mes, row.track_date),
      );

    // ARPU
    case 'arpu_actual':
      return this.calculateArpuActual(
        row.ingreso_real_mtd,
        row.usuarios_activos_actual,
      );

    case 'arpu_teorico':
      return this.calculateArpuActual(
        row.meta_faycgo_mes,
        row.proyeccion_usuarios_cierre_mes,
      );

    case 'diferencia_arpu':
      return this.calculateDifference(
        this.calculateArpuActual(
          row.ingreso_real_mtd,
          row.usuarios_activos_actual,
        ),
        row.meta_arpu_mes,
      );

    case 'avance_arpu':
      return this.calculateProgressPercent(
        this.calculateArpuActual(
          row.ingreso_real_mtd,
          row.usuarios_activos_actual,
        ),
        row.meta_arpu_mes,
      );

    // Tienda
    case 'avance_tienda':
      return this.calculateProgressPercent(
        row.venta_tienda_real_mtd,
        row.meta_venta_tienda_mes,
      );

    case 'diferencia_tienda':
      return this.calculateDifference(
        row.venta_tienda_real_mtd,
        row.meta_venta_tienda_mes,
      );

    case 'meta_tienda_dia':
      return this.calculateRemainingToIdealTarget(
        row.venta_tienda_real_mtd,
        this.calculateIdealMtdTarget(row.meta_venta_tienda_mes, row.track_date),
      );

    default:
      return Number(row[key as keyof TrackDailyMartRow] ?? 0);
  }
}

private getTrackSortColumnLabel(key: TrackSortKey): string {
  const labels: Record<TrackSortKey, string> = {
    sucursal_canon: 'Club',

    // Ocupación
    m2_sin_circulaciones: 'M² sin circulaciones',
    usuarios_inicio_mes: 'Usuarios inicio mes',
    proyeccion_usuarios_cierre_mes: 'Proyección cierre',
    usuarios_activos_actual: 'Usuarios activos',
    ocupacion_inicio_mes: 'Ocupación inicio mes',
    meta_ocupacion_px_m2: 'Meta ocupación 2 px m²',
    meta_ocupacion_mes: 'Meta ocupación',
    ocupacion_actual: 'Ocupación actual',
    diferencia_ocupacion_inicio: 'Dif. inicio mes vs día actual',
    avance_ocupacion: '% alcance meta ocupación',

    // Crecimiento
    diferencia_inicio_mes: 'DIF inicio mes',
    diferencia_meta_crecimiento: 'Dif. meta vs real',
    avance_meta_crecimiento: '% alcance meta crecimiento',
    alcance_usuarios_activos: 'Alcance usuarios activos',

    // Ventas nuevas y reactivaciones
    meta_clientes_nuevos_mes: 'Meta socios nuevos',
    clientes_nuevos_ideal_mtd: 'Alcance ideal socios nuevos',
    clientes_nuevos_real_mtd: 'Socios nuevos reales',
    diferencia_clientes_nuevos_ideal: 'Diferencia ideal vs real',
    avance_clientes_nuevos: '% avance socios nuevos',
    diferencia_clientes_nuevos: 'Dif. socios nuevos vs meta',
    meta_clientes_nuevos_dia: 'Meta del día socios nuevos',
    meta_reactivaciones_mes: 'Meta reactivaciones',
    reactivaciones_ideal_mtd: 'Reactivaciones ideales',
    reactivaciones_real_mtd: 'Reactivaciones reales',
    diferencia_reactivaciones_ideal: 'Meta del día reactivaciones',
    avance_reactivaciones: '% avance reactivaciones',

    // Bajas & churn
    meta_bajas_mes: 'Meta bajas',
    bajas_ideal_mtd: 'Bajas ideales',
    bajas_reales_mtd: 'Bajas reales',
    diferencia_bajas_ideal: 'Dif. ideal vs real',
    meta_churn_mes: 'Meta churn',
    churn_ideal_mtd: 'Churn ideal',
    churn_real_mtd: 'Churn real',
    diferencia_churn_ideal: 'Dif. churn ideal vs real',

    // Domiciliados
    meta_nuevos_domiciliados_mes: 'Meta domiciliados',
    domiciliados_ideal_mtd: 'Domiciliados ideales',
    nuevos_domiciliados_real_mtd: 'Nuevos domiciliados',
    avance_domiciliados: 'Avance domiciliados',
    diferencia_domiciliados: 'Dif. domiciliados vs meta',
    diferencia_domiciliados_ideal: 'Dif. ideal domiciliados',
    meta_domiciliados_dia: 'Meta del día domiciliados',

    // Ingresos
    meta_faycgo_mes: 'Meta FAYCGO',
    ingreso_ideal_cierre_mtd: 'Ingreso ideal al cierre',
    ingreso_real_base_mtd: 'Ingreso base',
    ingreso_real_agregadora_mtd: 'Ingreso agregadoras',
    ingreso_real_mtd: 'Ingreso real total',
    avance_ingreso: 'Avance ingreso mensual',
    avance_ingreso_ideal: '% alcance meta al día',
    diferencia_ingreso: 'Dif. ingreso vs meta mensual',
    diferencia_ingreso_ideal: 'Dif. ingreso vs meta al día',
    meta_ingreso_dia: 'Meta del día ingreso',

    // ARPU
    meta_arpu_mes: 'Meta ARPU',
    arpu_actual: 'ARPU actual',
    arpu_teorico: 'ARPU teórico',
    diferencia_arpu: 'Dif. ARPU',
    avance_arpu: '% alcance ARPU',

    // Tienda
    meta_venta_tienda_mes: 'Meta tienda',
    venta_tienda_real_mtd: 'Venta tienda',
    avance_tienda: 'Avance tienda',
    diferencia_tienda: 'Dif. tienda vs meta',
    meta_tienda_dia: 'Meta del día tienda',
  };

  return labels[key];
}

onGenerationModeChanged(): void {
  this.syncSelectedModeLabel();
  this.resetLoadedMartState();
}

onTrackDateChanged(): void {
  this.resetLoadedMartState();
}  
 
goToPreviousTrackDate(): void {
  this.shiftTrackDateByDays(-1);
}

goToNextTrackDate(): void {
  this.shiftTrackDateByDays(1);
}

shouldDisablePreviousTrackDateButton(): boolean {
  return this.isLoadingMart;
}

shouldDisableNextTrackDateButton(): boolean {
  return this.isLoadingMart || this.trackDate >= this.getTodayIsoDate();
}

private shiftTrackDateByDays(days: number): void {
  if (this.isLoadingMart) {
    return;
  }

  const parsedDate = this.parseIsoDate(this.trackDate);

  if (!parsedDate) {
    return;
  }

  parsedDate.setUTCDate(parsedDate.getUTCDate() + days);

  const nextTrackDate = this.formatDateAsIso(parsedDate);
  const todayIsoDate = this.getTodayIsoDate();

  if (nextTrackDate > todayIsoDate) {
    return;
  }

  this.trackDate = nextTrackDate;
  this.applyHistoricalModeForSelectedDate();
  this.loadDailyMart();
}

private applyHistoricalModeForSelectedDate(): void {
  if (this.isSelectedTrackDateInPast()) {
    this.generationMode = 'official_closed_day';
  } else {
    this.generationMode = 'manual_preview';
  }

  this.syncSelectedModeLabel();
}

private parseIsoDate(value: string): Date | null {
  const trimmed = (value || '').trim();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }

  const [year, month, day] = trimmed.split('-').map(Number);

  return new Date(Date.UTC(year, month - 1, day));
}

private formatDateAsIso(value: Date): string {
  const year = value.getUTCFullYear();
  const month = String(value.getUTCMonth() + 1).padStart(2, '0');
  const day = String(value.getUTCDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

openBranchHistory(row: TrackViewRow): void {
  if (row.rowKind !== 'data') {
    return;
  }

  this.router.navigate(
    ['/warehouse/track/sucursal', row.sucursalCanon],
    {
      queryParams: {
        generation_mode: this.generationMode,
        target_month: this.buildTargetMonthFromTrackDate(),
      },
    },
  );
}

goToRegionalIntelligence(): void {
  this.router.navigate(['/warehouse/track-intelligence/regional'], {
    queryParams: {
      track_date: this.trackDate,
      generation_mode: this.generationMode,
    },
  });
}

onTrackRowClicked(row: TrackViewRow): void {
  if (row.rowKind !== 'data') {
    return;
  }

  this.openBranchHistory(row);
}

shouldDisableTrackDateInput(): boolean {
  return this.isLoadingMart;
}

shouldDisableGenerationModeSelect(): boolean {
  return this.isLoadingMart;
}

shouldDisableGenerateTrackButton(): boolean {
  return this.isSubmitting || this.isSelectedTrackDateInPast();
}

getGenerateTrackButtonClass(): string {
  return this.isSubmitting
    ? 'primary-button primary-button--loading'
    : 'primary-button';
}

getGenerateTrackButtonLabel(): string {
  if (this.isSubmitting) {
    return 'Generando...';
  }

  if (this.isSelectedTrackDateInPast()) {
    return 'Solo día actual';
  }

  return 'Generar Track';
}

isGenerateTrackButtonLoading(): boolean {
  return this.isSubmitting;
}

isSelectedTrackDateInPast(): boolean {
  if (!this.trackDate) {
    return false;
  }

  return this.trackDate < this.getTodayIsoDate();
}

private calculateRemainingToIdealTarget(
  realValue: number | null | undefined,
  idealValue: number | null | undefined,
): number {
  const real = Number(realValue ?? 0);
  const ideal = Number(idealValue ?? 0);

  if (Number.isNaN(real) || Number.isNaN(ideal)) {
    return 0;
  }

  return Math.max(ideal - real);
}

private getRemainingTargetTone(value: number | null | undefined): ProgressTone {
  const numericValue = Number(value ?? 0);

  if (numericValue <= 0) {
    return 'success';
  }

  return 'danger';
}

private getTodayIsoDate(): string {
  const now = new Date();

  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Tijuana',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });

  return formatter.format(now);
}

private buildTargetMonthFromTrackDate(): string {
  const rawValue = (this.trackDate || '').trim();

  if (/^\d{4}-\d{2}-\d{2}$/.test(rawValue)) {
    return rawValue.slice(0, 7);
  }

  const today = new Date();
  const year = today.getFullYear();
  const month = `${today.getMonth() + 1}`.padStart(2, '0');

  return `${year}-${month}`;
}


  getSummaryCardClass(card: TrackSummaryCard): string {
    const compactClass = card.compact ? ' summary-card--compact' : '';

    return `summary-card summary-card--${card.tone}${compactClass}`;
  }

  getProgressBadgeClass(tone: ProgressTone): string {
    return `progress-badge progress-badge--${tone}`;
  }

  private buildViewRow(row: TrackDailyMartRow): TrackViewRow {
  const ingresoProgress = this.calculateProgressPercent(
    row.ingreso_real_mtd,
    row.meta_faycgo_mes,
  );

  const clientesProgress = this.calculateProgressPercent(
    row.clientes_nuevos_real_mtd,
    row.meta_clientes_nuevos_mes,
  );

  const reactivacionesProgress = this.calculateProgressPercent(
    row.reactivaciones_real_mtd,
    row.meta_reactivaciones_mes,
  );

  const domiciliadosProgress = this.calculateProgressPercent(
    row.nuevos_domiciliados_real_mtd,
    row.meta_nuevos_domiciliados_mes,
  );

  const avanceTienda = this.calculateProgressPercent(
    row.venta_tienda_real_mtd,
    row.meta_venta_tienda_mes,
  );

  const arpuActual = this.calculateArpuActual(
    row.ingreso_real_mtd,
    row.usuarios_activos_actual,
  );

  const avanceArpu = this.calculateProgressPercent(
    arpuActual,
    row.meta_arpu_mes,
  );

  const arpuTeorico = this.calculateArpuActual(
    row.meta_faycgo_mes,
    row.proyeccion_usuarios_cierre_mes,
  );

  const diferenciaArpu = this.calculateDifference(
    arpuActual,
    row.meta_arpu_mes,
  );

  // Ocupación
  const ocupacionInicioMes = this.calculateOccupancyRatio(
    row.usuarios_inicio_mes,
    row.m2_sin_circulaciones,
  );

  const metaOcupacionMes = this.calculateOccupancyRatio(
    row.proyeccion_usuarios_cierre_mes,
    row.m2_sin_circulaciones,
  );

  const ocupacionActual = this.calculateOccupancyRatio(
    row.usuarios_activos_actual,
    row.m2_sin_circulaciones,
  );

  const diferenciaOcupacionInicio = this.calculateDifference(
    ocupacionActual,
    ocupacionInicioMes,
  );

  const avanceOcupacion = this.calculateProgressPercent(
    row.usuarios_activos_actual,
    row.proyeccion_usuarios_cierre_mes,
  );

  // Crecimiento
  const diferenciaInicioMes = this.calculateDifference(
    row.usuarios_activos_actual,
    row.usuarios_inicio_mes,
  );

  const diferenciaMetaCrecimiento = this.calculateDifference(
    row.usuarios_activos_actual,
    row.proyeccion_usuarios_cierre_mes,
  );

  const avanceMetaCrecimiento = this.calculateRelativeDifferencePercent(
    row.usuarios_activos_actual,
    row.proyeccion_usuarios_cierre_mes,
  );

  const alcanceUsuariosActivos = this.calculateRelativeDifferencePercent(
    row.usuarios_activos_actual,
    row.usuarios_inicio_mes,
  );

  // Ventas nuevas y reactivaciones
  const clientesNuevosIdealMtd = this.calculateIdealMtdTarget(
    row.meta_clientes_nuevos_mes,
    row.track_date,
  );

  const diferenciaClientesNuevosIdeal = this.calculateDifference(
    row.clientes_nuevos_real_mtd,
    clientesNuevosIdealMtd,
  );

  const metaClientesNuevosDia = this.calculateIdealMtdTarget(
    row.meta_clientes_nuevos_mes,
    row.track_date,
  );

  const metaClientesNuevosPendienteDia = this.calculateRemainingToIdealTarget(
    row.clientes_nuevos_real_mtd,
    metaClientesNuevosDia,
  );

  const reactivacionesIdealMtd = this.calculateIdealMtdTarget(
    row.meta_reactivaciones_mes,
    row.track_date,
  );

  const diferenciaReactivacionesIdeal = this.calculateDifference(
    reactivacionesIdealMtd,
    row.reactivaciones_real_mtd,
  );

  // Bajas & churn
  const bajasIdealMtd = this.calculateIdealMtdTarget(
    row.meta_bajas_mes,
    row.track_date,
  );

  const diferenciaBajasIdeal = this.calculateDifference(
    row.bajas_reales_mtd,
    bajasIdealMtd,
  );

  const metaChurn = this.calculateChurnPercent(
    row.meta_bajas_mes,
    row.proyeccion_usuarios_cierre_mes,
  );

  const churnIdeal = this.calculateChurnPercent(
    bajasIdealMtd,
    row.usuarios_inicio_mes,
  );

  const churnReal = this.calculateChurnPercent(
    row.bajas_reales_mtd,
    row.usuarios_inicio_mes,
  );

  const diferenciaChurnIdeal = this.calculateDifference(
    churnReal,
    churnIdeal,
  );

  // Domiciliados
  const domiciliadosIdealMtd = this.calculateIdealMtdTarget(
    row.meta_nuevos_domiciliados_mes,
    row.track_date,
  );

  const diferenciaDomiciliados = this.calculateDifference(
    row.nuevos_domiciliados_real_mtd,
    row.meta_nuevos_domiciliados_mes,
  );

  const diferenciaDomiciliadosIdeal = this.calculateDifference(
    row.nuevos_domiciliados_real_mtd,
    domiciliadosIdealMtd,
  );

  const metaDomiciliadosDia = this.calculateIdealMtdTarget(
    row.meta_nuevos_domiciliados_mes,
    row.track_date,
  );

  const metaDomiciliadosPendienteDia = this.calculateRemainingToIdealTarget(
    row.nuevos_domiciliados_real_mtd,
    metaDomiciliadosDia,
  );

  // Ingresos
  const diferenciaIngreso = this.calculateDifference(
    row.ingreso_real_mtd,
    row.meta_faycgo_mes,
  );

  const ingresoIdealCierreMtd = this.calculateIdealMtdTarget(
    row.meta_faycgo_mes,
    row.track_date,
  );

  const avanceIngresoIdeal = this.calculateProgressPercent(
    row.ingreso_real_mtd,
    ingresoIdealCierreMtd,
  );

  const diferenciaIngresoIdeal = this.calculateDifference(
    row.ingreso_real_mtd,
    ingresoIdealCierreMtd,
  );

  const metaIngresoPendienteDia = this.calculateRemainingToIdealTarget(
    row.ingreso_real_mtd,
    ingresoIdealCierreMtd,
  );

  // Tienda
  const diferenciaTienda = this.calculateDifference(
    row.venta_tienda_real_mtd,
    row.meta_venta_tienda_mes,
  );

  const metaTiendaDia = this.calculateIdealMtdTarget(
    row.meta_venta_tienda_mes,
    row.track_date,
  );

  const metaTiendaPendienteDia = this.calculateRemainingToIdealTarget(
    row.venta_tienda_real_mtd,
    metaTiendaDia,
  );

  return {
    rowKind: this.getRowKindForSucursal(row.sucursal_canon),
    displayLabel: this.getDisplayLabelForRow(row.sucursal_canon),

    sucursalCanon: row.sucursal_canon,

    // Ocupación
    m2SinCirculaciones: this.formatDecimal(row.m2_sin_circulaciones, 1),
    ocupacionInicioMes: this.formatDecimal(ocupacionInicioMes, 1),
    metaOcupacionPxM2: this.formatDecimal(2, 1),
    metaOcupacionMes: this.formatDecimal(metaOcupacionMes, 1),
    ocupacionActual: this.formatDecimal(ocupacionActual, 1),
    diferenciaOcupacionInicioLabel: this.formatSignedDecimal(diferenciaOcupacionInicio, 1),
    diferenciaOcupacionInicioTone: this.getDifferenceTone(diferenciaOcupacionInicio),
    avanceOcupacionLabel: this.formatPercentWithDecimals(avanceOcupacion, 2),
    avanceOcupacionTone: this.getProgressTone(avanceOcupacion),

    // Crecimiento
    usuariosInicioMes: this.formatInteger(row.usuarios_inicio_mes),
    usuariosActivos: this.formatInteger(row.usuarios_activos_actual),
    proyeccionUsuariosCierre: this.formatInteger(
      row.proyeccion_usuarios_cierre_mes,
    ),
    diferenciaInicioMesLabel: this.formatSignedInteger(diferenciaInicioMes),
    diferenciaInicioMesTone: this.getDifferenceTone(diferenciaInicioMes),
    diferenciaMetaCrecimientoLabel: this.formatSignedInteger(
      diferenciaMetaCrecimiento,
    ),
    diferenciaMetaCrecimientoTone: this.getDifferenceTone(
      diferenciaMetaCrecimiento,
    ),
    avanceMetaCrecimientoLabel: this.formatPercentWithDecimals(
      avanceMetaCrecimiento,
      2,
    ),
    avanceMetaCrecimientoTone: this.getDifferenceTone(avanceMetaCrecimiento),
    alcanceUsuariosActivosLabel: this.formatPercentWithDecimals(
      alcanceUsuariosActivos,
      2,
    ),
    alcanceUsuariosActivosTone: this.getDifferenceTone(alcanceUsuariosActivos),

    // Ventas nuevas y reactivaciones
    metaClientesNuevos: this.formatInteger(row.meta_clientes_nuevos_mes),
    clientesNuevosIdealMtd: this.formatInteger(
      Math.round(clientesNuevosIdealMtd),
    ),
    clientesNuevos: this.formatInteger(row.clientes_nuevos_real_mtd),
    diferenciaClientesNuevosIdealLabel: this.formatSignedInteger(
      diferenciaClientesNuevosIdeal,
    ),
    diferenciaClientesNuevosIdealTone: this.getDifferenceTone(
      diferenciaClientesNuevosIdeal,
    ),
    avanceClientesNuevosLabel: this.formatPercentWithDecimals(
      clientesProgress,
      2,
    ),
    avanceClientesNuevosTone: this.getProgressTone(clientesProgress),
    diferenciaClientesNuevosLabel: this.formatSignedInteger(
      this.calculateDifference(
        row.clientes_nuevos_real_mtd,
        row.meta_clientes_nuevos_mes,
      ),
    ),
    diferenciaClientesNuevosTone: this.getDifferenceTone(
      this.calculateDifference(
        row.clientes_nuevos_real_mtd,
        row.meta_clientes_nuevos_mes,
      ),
    ),
    metaClientesNuevosDia: this.formatInteger(Math.round(metaClientesNuevosDia)),
    diferenciaClientesNuevosDiaLabel: this.formatInteger(
      Math.ceil(metaClientesNuevosPendienteDia),
    ),
    diferenciaClientesNuevosDiaTone: this.getRemainingTargetTone(
      metaClientesNuevosPendienteDia,
    ),

    metaReactivaciones: this.formatInteger(row.meta_reactivaciones_mes),
    reactivacionesIdealMtd: this.formatInteger(
      Math.round(reactivacionesIdealMtd),
    ),
    reactivacionesReales: this.formatInteger(row.reactivaciones_real_mtd),
    diferenciaReactivacionesIdealLabel: this.formatSignedInteger(
      diferenciaReactivacionesIdeal,
    ),
    diferenciaReactivacionesIdealTone: this.getRemainingTargetTone(
      diferenciaReactivacionesIdeal,
    ),
    avanceReactivacionesLabel: this.formatPercentWithDecimals(
      reactivacionesProgress,
      2,
    ),
    avanceReactivacionesTone: this.getProgressTone(reactivacionesProgress),

    // Bajas & churn
    metaBajas: this.formatInteger(row.meta_bajas_mes),
    bajasIdealMtd: this.formatInteger(Math.round(bajasIdealMtd)),
    bajasReales: this.formatInteger(row.bajas_reales_mtd),
    diferenciaBajasIdealLabel: this.formatSignedInteger(diferenciaBajasIdeal),
    diferenciaBajasIdealTone: this.getInverseDifferenceTone(diferenciaBajasIdeal),
    metaChurnLabel: this.formatPercentWithDecimals(metaChurn, 2),
    churnIdealLabel: this.formatPercentWithDecimals(churnIdeal, 2),
    churnRealLabel: this.formatPercentWithDecimals(churnReal, 2),
    diferenciaChurnIdealLabel: this.formatSignedPercentWithDecimals(
      diferenciaChurnIdeal,
      2,
    ),
    diferenciaChurnIdealTone: this.getInverseDifferenceTone(
      diferenciaChurnIdeal,
    ),

    // Domiciliados
    metaNuevosDomiciliados: this.formatInteger(
      row.meta_nuevos_domiciliados_mes,
    ),
    domiciliadosIdealMtd: this.formatInteger(Math.round(domiciliadosIdealMtd)),
    nuevosDomiciliados: this.formatInteger(row.nuevos_domiciliados_real_mtd),
    avanceDomiciliadosLabel: this.formatPercentWithDecimals(
      domiciliadosProgress,
      2,
    ),
    avanceDomiciliadosTone: this.getProgressTone(domiciliadosProgress),
    diferenciaDomiciliadosLabel: this.formatSignedInteger(
      diferenciaDomiciliados,
    ),
    diferenciaDomiciliadosTone: this.getDifferenceTone(diferenciaDomiciliados),
    metaDomiciliadosDia: this.formatInteger(Math.round(metaDomiciliadosDia)),
    diferenciaDomiciliadosDiaLabel: this.formatInteger(
      Math.ceil(metaDomiciliadosPendienteDia),
    ),
    diferenciaDomiciliadosDiaTone: this.getRemainingTargetTone(
      metaDomiciliadosPendienteDia,
    ),
    diferenciaDomiciliadosIdealLabel: this.formatSignedInteger(
      diferenciaDomiciliadosIdeal,
    ),
    diferenciaDomiciliadosIdealTone: this.getDifferenceTone(
      diferenciaDomiciliadosIdeal,
    ),

    // Ingresos
    metaFaycgo: this.formatCurrency(row.meta_faycgo_mes),
    ingresoIdealCierre: this.formatCurrency(ingresoIdealCierreMtd),
    ingresoBase: this.formatCurrency(row.ingreso_real_base_mtd),
    ingresoAgregadoras: this.formatCurrency(row.ingreso_real_agregadora_mtd),
    ingresoReal: this.formatCurrency(row.ingreso_real_mtd),
    avanceIngresoLabel: this.formatPercentWithDecimals(ingresoProgress, 2),
    avanceIngresoTone: this.getProgressTone(ingresoProgress),
    avanceIngresoIdealLabel: this.formatPercentWithDecimals(avanceIngresoIdeal, 2),
    avanceIngresoIdealTone: this.getProgressTone(avanceIngresoIdeal),
    diferenciaIngresoLabel: this.formatSignedCurrency(diferenciaIngreso),
    diferenciaIngresoTone: this.getDifferenceTone(diferenciaIngreso),
    diferenciaIngresoIdealLabel: this.formatSignedCurrency(diferenciaIngresoIdeal),
    diferenciaIngresoIdealTone: this.getDifferenceTone(diferenciaIngresoIdeal),
    metaIngresoDia: this.formatCurrency(metaIngresoPendienteDia),
    diferenciaIngresoDiaLabel: this.formatCurrency(metaIngresoPendienteDia),
    diferenciaIngresoDiaTone: this.getRemainingTargetTone(
      metaIngresoPendienteDia,
    ),

    // ARPU
    metaArpu: this.formatCurrency(row.meta_arpu_mes),
    arpuActual: this.formatCurrency(arpuActual),
    arpuTeorico: this.formatCurrency(arpuTeorico),
    diferenciaArpuLabel: this.formatSignedCurrency(diferenciaArpu),
    diferenciaArpuTone: this.getDifferenceTone(diferenciaArpu),
    avanceArpuLabel: this.formatPercentWithDecimals(avanceArpu, 2),
    avanceArpuTone: this.getProgressTone(avanceArpu),

    // Tienda
    metaVentaTienda: this.formatCurrency(row.meta_venta_tienda_mes),
    ventaTiendaReal: this.formatCurrency(row.venta_tienda_real_mtd),
    avanceTiendaLabel: this.formatPercentWithDecimals(avanceTienda, 2),
    avanceTiendaTone: this.getProgressTone(avanceTienda),
    diferenciaTiendaLabel: this.formatSignedCurrency(diferenciaTienda),
    diferenciaTiendaTone: this.getDifferenceTone(diferenciaTienda),
    metaTiendaDiaLabel: this.formatCurrency(metaTiendaPendienteDia),
    metaTiendaDiaTone: this.getRemainingTargetTone(metaTiendaPendienteDia),
  };
}

  private buildSummaryCards(rows: TrackDailyMartRow[]): TrackSummaryCard[] {
    const totalIngresoReal = this.sumNumber(rows, 'ingreso_real_mtd');
    const totalMetaIngreso = this.sumNumber(rows, 'meta_faycgo_mes');

    const totalClientesReales = this.sumNumber(rows, 'clientes_nuevos_real_mtd');
    const totalMetaClientes = this.sumNumber(rows, 'meta_clientes_nuevos_mes');

    const totalDomiciliadosReales = this.sumNumber(
      rows,
      'nuevos_domiciliados_real_mtd',
    );
    const totalMetaDomiciliados = this.sumNumber(
      rows,
      'meta_nuevos_domiciliados_mes',
    );
    const totalVentaTiendaReal = this.sumNumber(rows, 'venta_tienda_real_mtd');
    const totalMetaVentaTienda = this.sumNumber(rows, 'meta_venta_tienda_mes');

    const tiendaProgress = this.calculateProgressPercent(
      totalVentaTiendaReal,
      totalMetaVentaTienda,
    );


    const totalUsuariosActivos = this.sumNumber(rows, 'usuarios_activos_actual');
    const totalMetaUsuarios = this.sumNumber(
      rows,
      'proyeccion_usuarios_cierre_mes',
    );

    const sociosActivosProgress = this.calculateProgressPercent(
      totalUsuariosActivos,
      totalMetaUsuarios,
    );

    const ingresoProgress = this.calculateProgressPercent(
      totalIngresoReal,
      totalMetaIngreso,
    );

    const clientesProgress = this.calculateProgressPercent(
      totalClientesReales,
      totalMetaClientes,
    );

    const domiciliadosProgress = this.calculateProgressPercent(
      totalDomiciliadosReales,
      totalMetaDomiciliados,
    );


    const diffUsuariosVsMeta = totalUsuariosActivos - totalMetaUsuarios;
    const diffIngresoVsMeta = totalIngresoReal - totalMetaIngreso;

    return [
      {
        label: 'Socios activos / meta',
        value: `${this.formatInteger(totalUsuariosActivos)} / ${this.formatInteger(totalMetaUsuarios)}`,
        tone: this.getProgressTone(sociosActivosProgress),
      },
      {
        label: 'Dif. socios vs meta',
        value: this.formatSignedInteger(diffUsuariosVsMeta),
        tone: this.getDifferenceTone(diffUsuariosVsMeta),
      },
      {
        label: 'Avance socios',
        value: this.formatPercent(sociosActivosProgress),
        tone: this.getProgressTone(sociosActivosProgress),
        compact: true,
      },
      {
        label: 'Ingreso real / meta',
        value: `${this.formatCurrency(totalIngresoReal)} / ${this.formatCurrency(totalMetaIngreso)}`,
        tone: this.getProgressTone(ingresoProgress),
      },
      {
        label: 'Dif. ingreso vs meta',
        value: this.formatSignedCurrency(diffIngresoVsMeta),
        tone: this.getDifferenceTone(diffIngresoVsMeta),
      },
      {
        label: 'Avance ingreso',
        value: this.formatPercent(ingresoProgress),
        tone: this.getProgressTone(ingresoProgress),
        compact: true,
      },
      {
        label: 'Socios nuevos',
        value: `${this.formatInteger(totalClientesReales)} / ${this.formatInteger(totalMetaClientes)}`,
        tone: this.getProgressTone(clientesProgress),
      },
      {
        label: 'Domiciliados',
        value: `${this.formatInteger(totalDomiciliadosReales)} / ${this.formatInteger(totalMetaDomiciliados)}`,
        tone: this.getProgressTone(domiciliadosProgress),
      },
      {
        label: 'Tienda',
        value: `${this.formatCurrency(totalVentaTiendaReal)} / ${this.formatCurrency(totalMetaVentaTienda)}`,
        tone: this.getProgressTone(tiendaProgress),
      },
    ];
  }

  private filterRowsWithFaycgoMeta(rows: TrackDailyMartRow[]): TrackDailyMartRow[] {
    return rows.filter((row) => this.hasFaycgoMeta(row));
  }

  private hasFaycgoMeta(row: TrackDailyMartRow): boolean {
    const metaFaycgo = Number(row.meta_faycgo_mes ?? 0);

    return !Number.isNaN(metaFaycgo) && metaFaycgo > 0;
  }

  private isMainOpeningGroupBranch(sucursalCanon: string): boolean {
    const branchIndex = this.branchOpeningOrder.indexOf(sucursalCanon);

    return branchIndex >= 0 && branchIndex < 21;
  }

  private appendClosingRows(rows: TrackDailyMartRow[]): TrackDailyMartRow[] {
    const firstGroup = rows.filter((row) =>
      this.isMainOpeningGroupBranch(row.sucursal_canon),
    );

    const secondGroup = rows.filter((row) =>
      !this.isMainOpeningGroupBranch(row.sucursal_canon),
    );

    const subtotal21Gyms = this.buildAggregateRawRow(
      'SUBTOTAL_21_GYMS',
      firstGroup,
    );

    const subtotalNuevos = this.buildAggregateRawRow(
      'SUBTOTAL_NUEVOS',
      secondGroup,
    );

    const totalGeneral = this.buildAggregateRawRow(
      'TOTAL_GENERAL',
      rows,
    );

    return [
      ...rows,
      subtotal21Gyms,
      subtotalNuevos,
      totalGeneral,
    ];
  }

  private buildAggregateRawRow(
    label: string,
    rows: TrackDailyMartRow[],
  ): TrackDailyMartRow {
    const totalIngresoReal = this.sumNumber(rows, 'ingreso_real_mtd');
    const totalUsuariosActivos = this.sumNumber(rows, 'usuarios_activos_actual');
    const totalMetaFaycgo = this.sumNumber(rows, 'meta_faycgo_mes');

    const totalProyeccionUsuariosCierre = this.sumNumber(
      rows,
      'proyeccion_usuarios_cierre_mes',
    );

    const totalMetaArpu = this.averagePositiveNumber(rows, 'meta_arpu_mes');

    return {
      track_date: this.trackDate,
      generation_mode: this.generationMode,
      sucursal_canon: label,
      target_month: null,
      m2_sin_circulaciones: this.sumNumber(rows, 'm2_sin_circulaciones'),
      usuarios_inicio_mes: this.sumNumber(rows, 'usuarios_inicio_mes'),
      proyeccion_usuarios_cierre_mes: totalProyeccionUsuariosCierre,
      meta_faycgo_mes: totalMetaFaycgo,
      meta_clientes_nuevos_mes: this.sumNumber(rows, 'meta_clientes_nuevos_mes'),
      meta_reactivaciones_mes: this.sumNumber(rows, 'meta_reactivaciones_mes'),
      meta_bajas_mes: this.sumNumber(rows, 'meta_bajas_mes'),
      meta_nuevos_domiciliados_mes: this.sumNumber(
        rows,
        'meta_nuevos_domiciliados_mes',
      ),
      meta_arpu_mes: totalMetaArpu,
      meta_venta_tienda_mes: this.sumNumber(rows, 'meta_venta_tienda_mes'),
      venta_tienda_real_mtd: this.sumNumber(rows, 'venta_tienda_real_mtd'),
      usuarios_activos_actual: totalUsuariosActivos,
      reactivaciones_real_mtd: this.sumNumber(rows, 'reactivaciones_real_mtd'),
      bajas_reales_mtd: this.sumNumber(rows, 'bajas_reales_mtd'),
      ingreso_real_base_mtd: this.sumNumber(rows, 'ingreso_real_base_mtd'),
      ingreso_real_agregadora_mtd: this.sumNumber(
        rows,
        'ingreso_real_agregadora_mtd',
      ),
      ingreso_real_mtd: totalIngresoReal,
      clientes_nuevos_real_mtd: this.sumNumber(rows, 'clientes_nuevos_real_mtd'),
      nuevos_domiciliados_real_mtd: this.sumNumber(
        rows,
        'nuevos_domiciliados_real_mtd',
      ),
      source_business_date_desempeno: null,
      source_business_date_ingresos: null,
      source_business_date_nuevos: null,
      source_business_date_domiciliados: null,
      source_snapshot_id_desempeno: null,
      source_snapshot_id_ingresos: null,
      source_snapshot_id_nuevos: null,
      source_snapshot_id_domiciliados: null,
      source_business_date_tienda: null,
      source_snapshot_id_tienda: null,
    };
  }

  private getDisplayLabelForRow(sucursalCanon: string): string {
    if (sucursalCanon === 'SUBTOTAL_21_GYMS') {
      return 'Subtotales 21 Gyms';
    }

    if (sucursalCanon === 'SUBTOTAL_NUEVOS') {
      return 'Subtotales Nuevos';
    }

    if (sucursalCanon === 'TOTAL_GENERAL') {
      return 'Total General';
    }

    return sucursalCanon;
  }

  private getRowKindForSucursal(
    sucursalCanon: string,
  ): 'data' | 'subtotal' | 'total' {
    if (sucursalCanon === 'TOTAL_GENERAL') {
      return 'total';
    }

    if (
      sucursalCanon === 'SUBTOTAL_21_GYMS' ||
      sucursalCanon === 'SUBTOTAL_NUEVOS'
    ) {
      return 'subtotal';
    }

    return 'data';
  }

  private sortRowsByOpeningOrder(rows: TrackDailyMartRow[]): TrackDailyMartRow[] {
    const orderMap = new Map<string, number>(
      this.branchOpeningOrder.map((branch, index) => [branch, index]),
    );

    return [...rows].sort((left, right) => {
      const leftIndex =
        orderMap.get(left.sucursal_canon) ?? Number.MAX_SAFE_INTEGER;
      const rightIndex =
        orderMap.get(right.sucursal_canon) ?? Number.MAX_SAFE_INTEGER;

      if (leftIndex !== rightIndex) {
        return leftIndex - rightIndex;
      }

      return left.sucursal_canon.localeCompare(right.sucursal_canon);
    });
  }

  private sumNumber(
    rows: TrackDailyMartRow[],
    field: keyof TrackDailyMartRow,
  ): number {
    return rows.reduce((accumulator, row) => {
      const rawValue = row[field];
      const numericValue =
        typeof rawValue === 'number' && !Number.isNaN(rawValue) ? rawValue : 0;

      return accumulator + numericValue;
    }, 0);
  }

private averagePositiveNumber(
  rows: TrackDailyMartRow[],
  field: keyof TrackDailyMartRow,
): number {
  const values = rows
    .map((row) => Number(row[field] ?? 0))
    .filter((value) => Number.isFinite(value) && value > 0);

  if (!values.length) {
    return 0;
  }

  const total = values.reduce((acc, value) => acc + value, 0);

  return total / values.length;
}

  private syncSelectedModeLabel(): void {
    const option = this.generationModeOptions.find(
      (item) => item.value === this.generationMode,
    );

    this.selectedModeLabel = option?.label || this.generationMode;
  }

private buildTrackVersionLabel(
  resolvedVersion: TrackResolvedVersion | null,
): string {
  if (!resolvedVersion) {
    return '';
  }

  return `#${resolvedVersion.id} · ${this.formatTrackVersionTypeLabel(
    resolvedVersion.version_type,
  )}`;
}


private buildTrackGeneratedAtLabel(
  resolvedVersion: TrackResolvedVersion | null,
): string {
  if (!resolvedVersion) {
    return '';
  }

  const generatedAt =
    resolvedVersion.finished_at_utc ||
    resolvedVersion.generated_at_utc ||
    resolvedVersion.started_at_utc;

  if (!generatedAt) {
    return '';
  }

  const formattedDateTime = this.formatIsoDateTimeLabel(generatedAt);

  if (resolvedVersion.version_type === 'preview_operativo') {
    return `Preview generada: ${formattedDateTime}`;
  }

  if (resolvedVersion.version_type === 'base_nocturna_canonica') {
    return `Base nocturna generada: ${formattedDateTime}`;
  }

  if (resolvedVersion.version_type === 'cierre_canonico') {
    return `Cierre canónico generado: ${formattedDateTime}`;
  }

  return `Versión generada: ${formattedDateTime}`;
}


private formatTrackVersionTypeLabel(versionType: string): string {
  if (versionType === 'preview_operativo') {
    return 'Preview operativo';
  }

  if (versionType === 'base_nocturna_canonica') {
    return 'Base nocturna canónica';
  }

  if (versionType === 'cierre_canonico') {
    return 'Cierre canónico';
  }

  return versionType;
}


private formatIsoDateTimeLabel(value: string): string {
  const parsedDate = new Date(value);

  if (Number.isNaN(parsedDate.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('es-MX', {
    timeZone: 'America/Tijuana',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(parsedDate);
}
  private buildAgregadorasFreshnessLabel(rows: TrackDailyMartRow[]): string {
    const uniqueDates = Array.from(
      new Set(
        rows
          .map((row) => row.source_business_date_agregadoras || null)
          .filter((value): value is string => !!value)
      )
    );

    if (uniqueDates.length === 0) {
      return '';
    }

    if (uniqueDates.length > 1) {
      return 'Agregadoras con fechas mixtas';
    }

    return `Agregadoras al ${this.formatIsoDateLabel(uniqueDates[0])}`;
  }

  private formatIsoDateLabel(value: string): string {
    const trimmed = (value || '').trim();

    if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
      return value;
    }

    const [year, month, day] = trimmed.split('-');
    return `${day}/${month}/${year}`;
  }

private calculateIdealMtdTarget(
  monthlyTarget: number | null | undefined,
  trackDate: string | null | undefined,
): number {
  const target = Number(monthlyTarget ?? 0);

  if (target <= 0) {
    return 0;
  }

  const dateParts = this.parseIsoDateParts(trackDate || this.trackDate);

  if (!dateParts) {
    return 0;
  }

  const daysInMonth = this.getDaysInMonth(dateParts.year, dateParts.month);
  const elapsedDay = Math.min(
    Math.max(dateParts.day, 1),
    daysInMonth,
  );

  return (target * elapsedDay) / daysInMonth;
}

private parseIsoDateParts(
  value: string | null | undefined,
): { year: number; month: number; day: number } | null {
  const text = String(value || '').trim();

  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return null;
  }

  const [yearText, monthText, dayText] = text.split('-');

  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);

  if (
    Number.isNaN(year) ||
    Number.isNaN(month) ||
    Number.isNaN(day)
  ) {
    return null;
  }

  return { year, month, day };
}

private getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

  private calculateProgressPercent(
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

  private calculateArpuActual(
    ingresoReal: number | null | undefined,
    usuariosActivos: number | null | undefined,
  ): number {
    const ingreso = ingresoReal ?? 0;
    const usuarios = usuariosActivos ?? 0;

    if (usuarios <= 0) {
      return 0;
    }

    return ingreso / usuarios;
  }

  private getProgressTone(percent: number): ProgressTone {
    if (percent >= 100) {
      return 'success';
    }

    if (percent >= 70) {
      return 'warning';
    }

    if (percent > 0) {
      return 'danger';
    }

    return 'neutral';
  }

  private formatInteger(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value ?? 0);
  }

  private formatDecimal(
    value: number | null | undefined,
    decimals: number,
  ): string {
    return new Intl.NumberFormat('es-MX', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value ?? 0);
  }

  private formatCurrency(value: number | null | undefined): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value ?? 0);
  }

  private formatPercent(value: number | null | undefined): string {
    return (
      new Intl.NumberFormat('es-MX', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(value ?? 0) + '%'
    );
  }

getTrackMonthShortLabel(): string {
  const parsed = this.parseIsoDateParts(this.trackDate);

  if (!parsed) {
    return 'mes';
  }

  const monthLabels = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
  ];

  return monthLabels[parsed.month - 1] || 'mes';
}

  getTrackDayMonthShortLabel(): string {
    const parsed = this.parseIsoDateParts(this.trackDate);

    if (!parsed) {
      return 'día actual';
    }

    return `${parsed.day} ${this.getTrackMonthShortLabel()}`;
  }

  private calculateOccupancyRatio(
    usersValue: number | null | undefined,
    m2Value: number | null | undefined,
  ): number {
    const users = Number(usersValue ?? 0);
    const m2 = Number(m2Value ?? 0);

    if (!Number.isFinite(users) || !Number.isFinite(m2) || m2 <= 0) {
      return 0;
    }

    return users / m2;
  }

  private calculateDifference(
  realValue: number | null | undefined,
  targetValue: number | null | undefined,
): number {
  const real = realValue ?? 0;
  const target = targetValue ?? 0;

  return real - target;
}

private calculateRelativeDifferencePercent(
  realValue: number | null | undefined,
  baseValue: number | null | undefined,
): number {
  const real = Number(realValue ?? 0);
  const base = Number(baseValue ?? 0);

  if (!Number.isFinite(real) || !Number.isFinite(base) || base <= 0) {
    return 0;
  }

  return ((real - base) / base) * 100;
}

private calculateChurnPercent(
  bajasValue: number | null | undefined,
  usersValue: number | null | undefined,
): number {
  const bajas = Number(bajasValue ?? 0);
  const users = Number(usersValue ?? 0);

  if (!Number.isFinite(bajas) || !Number.isFinite(users) || users <= 0) {
    return 0;
  }

  return (bajas / users) * 100;
}

private formatPercentWithDecimals(
  value: number | null | undefined,
  decimals: number,
): string {
  return (
    new Intl.NumberFormat('es-MX', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value ?? 0) + '%'
  );
}

private formatSignedPercentWithDecimals(
  value: number | null | undefined,
  decimals: number,
): string {
  const normalizedValue = value ?? 0;
  const formatted = this.formatPercentWithDecimals(Math.abs(normalizedValue), decimals);

  if (normalizedValue > 0) {
    return `+${formatted}`;
  }

  if (normalizedValue < 0) {
    return `-${formatted}`;
  }

  return formatted;
}

private getDifferenceTone(value: number): ProgressTone {
  if (value > 0) {
    return 'success';
  }

  if (value < 0) {
    return 'danger';
  }

  return 'neutral';
}

private getInverseDifferenceTone(value: number): ProgressTone {
  if (value < 0) {
    return 'success';
  }

  if (value > 0) {
    return 'danger';
  }

  return 'neutral';
}

private formatSignedDecimal(value: number | null | undefined, decimals = 1): string {
  const normalizedValue = Number(value ?? 0);
  const formatted = this.formatDecimal(Math.abs(normalizedValue), decimals);

  if (normalizedValue > 0) {
    return `+${formatted}`;
  }

  if (normalizedValue < 0) {
    return `-${formatted}`;
  }

  return formatted;
}

private formatSignedInteger(value: number | null | undefined): string {
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

private formatSignedCurrency(value: number | null | undefined): string {
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

  private buildTodayIsoDate(): string {
    const today = new Date();
    const year = today.getFullYear();
    const month = `${today.getMonth() + 1}`.padStart(2, '0');
    const day = `${today.getDate()}`.padStart(2, '0');

    return `${year}-${month}-${day}`;
  }

showAllTrackColumnGroups(): void {
  this.selectedTrackColumnGroups = [];
}

toggleTrackColumnGroup(groupKey: TrackColumnGroupKey): void {
  const isSelected = this.selectedTrackColumnGroups.includes(groupKey);

  if (isSelected) {
    const nextSelectedGroups = this.selectedTrackColumnGroups.filter(
      (key) => key !== groupKey
    );

    this.selectedTrackColumnGroups = nextSelectedGroups;
    return;
  }

  this.selectedTrackColumnGroups = [
    ...this.selectedTrackColumnGroups,
    groupKey,
  ];
}

isTrackColumnGroupVisible(groupKey: TrackColumnGroupKey): boolean {
  if (this.areAllTrackColumnGroupsVisible()) {
    return true;
  }

  return this.selectedTrackColumnGroups.includes(groupKey);
}

isTrackColumnGroupActive(groupKey: TrackColumnGroupKey): boolean {
  return this.selectedTrackColumnGroups.includes(groupKey);
}

areAllTrackColumnGroupsVisible(): boolean {
  return this.selectedTrackColumnGroups.length === 0;
}

getTrackColumnGroupAllButtonClass(): string {
  return this.areAllTrackColumnGroupsVisible()
    ? 'secondary-button track-column-groups__button track-column-groups__button--active'
    : 'secondary-button track-column-groups__button';
}

getTrackColumnGroupButtonClass(groupKey: TrackColumnGroupKey): string {
  return this.isTrackColumnGroupActive(groupKey)
    ? 'secondary-button track-column-groups__button track-column-groups__button--active'
    : 'secondary-button track-column-groups__button';
}


selectedTrackColumnGroups: TrackColumnGroupKey[] = [];

shouldStretchTrackTableToPanel(): boolean {
  return this.getVisibleTrackTableColumnCount() <= 7;
}

getVisibleTrackTableColumnCount(): number {
  let totalColumns = 1; // Club siempre visible

  if (this.isSimplifiedTrackView()) {
    if (this.isTrackColumnGroupVisible('ocupacion')) {
      totalColumns += 5;
    }

    if (this.isTrackColumnGroupVisible('crecimiento')) {
      totalColumns += 9;
    }

    if (this.isTrackColumnGroupVisible('domiciliados')) {
      totalColumns += 5;
    }

    if (this.isTrackColumnGroupVisible('ingresos')) {
      totalColumns += 9;
    }

    if (this.isTrackColumnGroupVisible('tienda')) {
      totalColumns += 5;
    }

    return totalColumns;
  }

  if (this.isTrackColumnGroupVisible('ocupacion')) {
    totalColumns += 7;
  }

  if (this.isTrackColumnGroupVisible('crecimiento')) {
    totalColumns += 7;
  }

  if (this.isTrackColumnGroupVisible('ingresos')) {
    totalColumns += 8;
  }

  if (this.isTrackColumnGroupVisible('ventas_reactivaciones')) {
    totalColumns += 10;
  }

  if (this.isTrackColumnGroupVisible('bajas_churn')) {
    totalColumns += 8;
  }

  if (this.isTrackColumnGroupVisible('domiciliados')) {
    totalColumns += 3;
  }

  if (this.isTrackColumnGroupVisible('arpu')) {
    totalColumns += 5;
  }

  if (this.isTrackColumnGroupVisible('tienda')) {
    totalColumns += 4;
  }

  return totalColumns;
}

getTrackTableWrapperClass(): string {
  return this.shouldStretchTrackTableToPanel()
    ? 'track-table-wrapper track-table-wrapper--stretch'
    : 'track-table-wrapper';
}

getTrackTableClass(): string {
  return this.shouldStretchTrackTableToPanel()
    ? 'track-table track-table--stretch'
    : 'track-table';
}
}