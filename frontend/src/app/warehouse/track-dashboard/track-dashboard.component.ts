//   frontend\src\app\warehouse\track-dashboard\track-dashboard.component.ts


import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  TrackService,
  TrackGenerationMode,
  TrackPipelineResponse,
  TrackDailyMartResponse,
  TrackDailyMartRow,
} from '../../services/track.service';

type ProgressTone = 'danger' | 'warning' | 'success' | 'neutral';
type SummaryTone = ProgressTone | 'default';
type TrackColumnGroupKey =
  | 'ocupacion'
  | 'ingresos'
  | 'crecimiento'
  | 'domiciliados';

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
}

interface TrackViewRow {
  rowKind: 'data' | 'subtotal' | 'total';
  displayLabel: string;

  sucursalCanon: string;
  usuariosInicioMes: string;
  usuariosActivos: string;
  proyeccionUsuariosCierre: string;
  m2SinCirculaciones: string;

  metaFaycgo: string;
  ingresoBase: string;
  ingresoAgregadoras: string;
  ingresoReal: string;
  avanceIngresoLabel: string;
  avanceIngresoTone: ProgressTone;
  diferenciaIngresoLabel: string;
  diferenciaIngresoTone: ProgressTone;

  metaClientesNuevos: string;
  clientesNuevos: string;
  avanceClientesNuevosLabel: string;
  avanceClientesNuevosTone: ProgressTone;
  diferenciaClientesNuevosLabel: string;
  diferenciaClientesNuevosTone: ProgressTone;

  metaReactivaciones: string;
  reactivacionesReales: string;

  metaBajas: string;
  bajasReales: string;

  metaNuevosDomiciliados: string;
  nuevosDomiciliados: string;
  avanceDomiciliadosLabel: string;
  avanceDomiciliadosTone: ProgressTone;
  diferenciaDomiciliadosLabel: string;
  diferenciaDomiciliadosTone: ProgressTone;

  metaArpu: string;
  arpuActual: string;
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

  readonly trackColumnGroupOptions: TrackColumnGroupOption[] = [
  { key: 'ocupacion', label: 'Ocupación' },
  { key: 'crecimiento', label: 'Crecimiento' },
  { key: 'domiciliados', label: 'Domiciliados' },
  { key: 'ingresos', label: 'Ingresos' },
];


  trackDate = this.buildTodayIsoDate();
  generationMode: TrackGenerationMode = 'manual_preview';

  isSubmitting = false;
  isLoadingMart = false;

  errorMessage = '';
  martErrorMessage = '';

  lastResponse: TrackPipelineResponse | null = null;
  rawMartRows: TrackDailyMartRow[] = [];
  viewRows: TrackViewRow[] = [];
  summaryCards: TrackSummaryCard[] = [];  

  totalRowsLabel = '0';
  selectedModeLabel = '';
  lastLoadedTrackDateLabel = '';

  constructor(private readonly trackService: TrackService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.syncSelectedModeLabel();
    this.loadDailyMart();
  }

  runTrackPipeline(): void {
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
    this.martErrorMessage = '';
    this.rawMartRows = [];
    this.viewRows = [];
    this.summaryCards = [];
    this.totalRowsLabel = '0';
    this.lastLoadedTrackDateLabel = this.trackDate;
    this.syncSelectedModeLabel();

    if (this.generationMode !== 'official_closed_day') {
      this.fetchDailyMart();
      return;
    }

    this.trackService
      .runAgregadorasIntegration({
        track_date: this.trackDate,
        requested_by: 'track_dashboard_consultar_resultado',
        trigger_source: 'track_dashboard_load_daily_mart',
      })
      .subscribe({
        next: (response) => {
          if (response.status !== 'ok') {
            this.martErrorMessage =
              response.message ||
              'No se pudo integrar agregadoras antes de consultar el Track.';
            this.isLoadingMart = false;
            return;
          }

          this.fetchDailyMart();
        },
        error: (error) => {
          this.martErrorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'Ocurrió un error al integrar agregadoras antes de consultar el Track.';
          this.isLoadingMart = false;
        },
      });
  }

  private fetchDailyMart(): void {
    this.trackService
      .getDailyMart(this.trackDate, this.generationMode)
      .subscribe({
        next: (response: TrackDailyMartResponse) => {
          if (response.status !== 'ok') {
            this.martErrorMessage =
              response.message || 'No se pudo consultar el Track daily mart.';
            this.isLoadingMart = false;
            return;
          }

          const baseRows = this.sortRowsByOpeningOrder(response.rows || []);

          this.summaryCards = this.buildSummaryCards(baseRows);
          this.rawMartRows = this.appendClosingRows(baseRows);
          const builtRows = this.rawMartRows.map((row) => this.buildViewRow(row));
          this.viewRows = builtRows;
          this.totalRowsLabel = this.formatInteger(response.total_rows || 0);
          this.lastLoadedTrackDateLabel = response.track_date || this.trackDate;
          this.isLoadingMart = false;
        },
        error: (error) => {
          this.martErrorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'Ocurrió un error al consultar el Track daily mart.';
          this.isLoadingMart = false;
        },
      });
  }

  onGenerationModeChanged(): void {
    this.syncSelectedModeLabel();
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

shouldDisableTrackDateInput(): boolean {
  return this.isLoadingMart;
}

shouldDisableGenerationModeSelect(): boolean {
  return this.isLoadingMart;
}

shouldDisableGenerateTrackButton(): boolean {
  return this.isSubmitting;
}

getGenerateTrackButtonClass(): string {
  return this.isSubmitting
    ? 'primary-button primary-button--loading'
    : 'primary-button';
}

getGenerateTrackButtonLabel(): string {
  return this.isSubmitting ? 'Generando...' : 'Generar Track';
}

isGenerateTrackButtonLoading(): boolean {
  return this.isSubmitting;
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


  getSummaryCardClass(tone: SummaryTone): string {
    return `summary-card summary-card--${tone}`;
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
    const domiciliadosProgress = this.calculateProgressPercent(
      row.nuevos_domiciliados_real_mtd,
      row.meta_nuevos_domiciliados_mes,
    );

    const diferenciaIngreso = this.calculateDifference(
      row.ingreso_real_mtd,
      row.meta_faycgo_mes,
    );

    const diferenciaClientesNuevos = this.calculateDifference(
      row.clientes_nuevos_real_mtd,
      row.meta_clientes_nuevos_mes,
    );

    const diferenciaDomiciliados = this.calculateDifference(
      row.nuevos_domiciliados_real_mtd,
      row.meta_nuevos_domiciliados_mes,
    );

    const arpuActual = this.calculateArpuActual(
      row.ingreso_real_mtd,
      row.usuarios_activos_actual,
    );

    return {
      rowKind: this.getRowKindForSucursal(row.sucursal_canon),
      displayLabel: this.getDisplayLabelForRow(row.sucursal_canon),

      sucursalCanon: row.sucursal_canon,
      usuariosInicioMes: this.formatInteger(row.usuarios_inicio_mes),
      usuariosActivos: this.formatInteger(row.usuarios_activos_actual),
      proyeccionUsuariosCierre: this.formatInteger(
        row.proyeccion_usuarios_cierre_mes,
      ),
      m2SinCirculaciones: this.formatDecimal(row.m2_sin_circulaciones, 1),

      metaFaycgo: this.formatCurrency(row.meta_faycgo_mes),
      ingresoBase: this.formatCurrency(row.ingreso_real_base_mtd),
      ingresoAgregadoras: this.formatCurrency(row.ingreso_real_agregadora_mtd),
      ingresoReal: this.formatCurrency(row.ingreso_real_mtd),
      avanceIngresoLabel: this.formatPercent(ingresoProgress),
      avanceIngresoTone: this.getProgressTone(ingresoProgress),

      metaClientesNuevos: this.formatInteger(row.meta_clientes_nuevos_mes),
      clientesNuevos: this.formatInteger(row.clientes_nuevos_real_mtd),
      avanceClientesNuevosLabel: this.formatPercent(clientesProgress),
      avanceClientesNuevosTone: this.getProgressTone(clientesProgress),
      diferenciaClientesNuevosLabel: this.formatSignedInteger(
        diferenciaClientesNuevos,
      ),
      diferenciaClientesNuevosTone: this.getDifferenceTone(
        diferenciaClientesNuevos,
      ),

      diferenciaIngresoLabel: this.formatSignedCurrency(diferenciaIngreso),
      diferenciaIngresoTone: this.getDifferenceTone(diferenciaIngreso),

      metaReactivaciones: this.formatInteger(row.meta_reactivaciones_mes),
      reactivacionesReales: this.formatInteger(row.reactivaciones_real_mtd),

      metaBajas: this.formatInteger(row.meta_bajas_mes),
      bajasReales: this.formatInteger(row.bajas_reales_mtd),

      metaNuevosDomiciliados: this.formatInteger(
        row.meta_nuevos_domiciliados_mes,
      ),
      nuevosDomiciliados: this.formatInteger(row.nuevos_domiciliados_real_mtd),
      avanceDomiciliadosLabel: this.formatPercent(domiciliadosProgress),
      avanceDomiciliadosTone: this.getProgressTone(domiciliadosProgress),
      diferenciaDomiciliadosLabel: this.formatSignedInteger(
        diferenciaDomiciliados,
      ),
      diferenciaDomiciliadosTone: this.getDifferenceTone(
        diferenciaDomiciliados,
      ),

      metaArpu: this.formatCurrency(row.meta_arpu_mes),
      arpuActual: this.formatCurrency(arpuActual),
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

    const totalUsuariosActivos = this.sumNumber(rows, 'usuarios_activos_actual');

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

    return [
      {
        label: 'Socios activos',
        value: this.formatInteger(totalUsuariosActivos),
        tone: 'default',
      },
      {
        label: 'Ingreso real total',
        value: this.formatCurrency(totalIngresoReal),
        tone: 'default',
      },
      {
        label: 'Avance ingreso',
        value: this.formatPercent(ingresoProgress),
        tone: this.getProgressTone(ingresoProgress),
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
    ];
  }


  private appendClosingRows(rows: TrackDailyMartRow[]): TrackDailyMartRow[] {
    const firstGroup = rows.slice(0, 21);
    const secondGroup = rows.slice(21);

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

    const totalMetaArpu =
      totalProyeccionUsuariosCierre > 0
        ? totalMetaFaycgo / totalProyeccionUsuariosCierre
        : 0;

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

  private syncSelectedModeLabel(): void {
    const option = this.generationModeOptions.find(
      (item) => item.value === this.generationMode,
    );

    this.selectedModeLabel = option?.label || this.generationMode;
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

  private calculateDifference(
  realValue: number | null | undefined,
  targetValue: number | null | undefined,
): number {
  const real = realValue ?? 0;
  const target = targetValue ?? 0;

  return real - target;
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

  if (this.isTrackColumnGroupVisible('ocupacion')) {
    totalColumns += 4;
  }

  if (this.isTrackColumnGroupVisible('ingresos')) {
    totalColumns += 6;
  }

  if (this.isTrackColumnGroupVisible('crecimiento')) {
    totalColumns += 8;
  }

  if (this.isTrackColumnGroupVisible('domiciliados')) {
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