// frontend/src/app/planning/targets/planning-target-batch-detail/planning-target-batch-detail.component.ts

import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { finalize } from 'rxjs';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import {
  AddPlanningTargetBranchRowPayload,
  PlanningAccessResponse,
  PlanningBranchComparisonsResponse,
  PlanningTargetBatchDetail,
  PlanningTargetBranchRowDetail,
  PlanningTargetApprovalEventDetail,
  PlanningTargetsService,
  PlanningTrackBranchSummary,
} from '../../services/planning-targets.service';

import {
  PlanningTargetActionDialogComponent,
  PlanningTargetActionDialogData,
  PlanningTargetActionDialogResult,
} from '../planning-target-action-dialog/planning-target-action-dialog.component';



@Component({
  selector: 'app-planning-target-batch-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTableModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDialogModule,
  ],
  templateUrl: './planning-target-batch-detail.component.html',
  styleUrls: ['./planning-target-batch-detail.component.css',]
})
export class PlanningTargetBatchDetailComponent implements OnInit {
  batchId: number | null = null;
  batch: PlanningTargetBatchDetail | null = null;
  access: PlanningAccessResponse | null = null;
  activeBranches: PlanningTrackBranchSummary[] = [];
  branchComparisons: PlanningBranchComparisonsResponse | null = null;
  isLoadingBranches = false;
  isLoadingBranchPrefill = false;
  isLoadingBranchComparisons = false;
  branchPrefillSourceLabel = '';

  showAddBranchForm = false;
  isLoadingAccess = false;
  isAddingBranchRow = false;
  isRunningBatchAction = false;

  branchForm = {
  sucursalCanon: '',
  m2SinCirculaciones: 0,
  usuariosInicioMes: 0,
  proyeccionUsuariosCierreMes: 0,
  metaFaycgoMes: 0,
  metaClientesNuevosMes: 0,
  metaReactivacionesMes: 0,
  metaBajasMes: 0,
  metaNuevosDomiciliadosMes: 0,
  metaArpuMes: 0,
  metaVentaTiendaMes: 0,
  ingresoAgregadorasEstimado: null as number | null,
  usuariosAgregadorasEstimado: null as number | null,
  scenarioUsed: 'AJUSTADO',
  trendClassification: '',
  riskLevel: 'MEDIO',
  notes: '',
  };

  isLoading = false;

  branchDisplayedColumns: string[] = [
    'sucursal_canon',
    'status',
    'meta_faycgo_mes',
    'clientes_nuevos',
    'reactivaciones',
    'bajas',
    'domiciliados',
    'arpu',
    'venta_tienda',
    'published_target',
  ];

  eventsDisplayedColumns: string[] = [
    'created_at',
    'event_type',
    'from_status',
    'to_status',
    'actor',
    'comment',
  ];

  constructor(
    private readonly activatedRoute: ActivatedRoute,
    private readonly planningTargetsService: PlanningTargetsService,
    private readonly snackBar: MatSnackBar,
    private readonly dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.loadBatchIdFromRoute();
    this.loadAccess();
    this.loadActiveBranches();
    this.loadBatchDetail();
  }

  loadBatchIdFromRoute(): void {
    const rawBatchId = this.activatedRoute.snapshot.paramMap.get('batchId');
    const parsedBatchId = Number(rawBatchId);

    if (!Number.isInteger(parsedBatchId) || parsedBatchId <= 0) {
      this.batchId = null;
      return;
    }

    this.batchId = parsedBatchId;
  }

  loadBatchDetail(): void {
    if (!this.batchId) {
      this.snackBar.open('Batch inválido.', 'Cerrar', {
        duration: 4000,
      });
      return;
    }

    this.isLoading = true;

    this.planningTargetsService
      .getBatchDetail(this.batchId)
      .subscribe({
        next: (batch) => {
          this.batch = batch;
          this.isLoading = false;
        },
        error: () => {
          this.batch = null;
          this.isLoading = false;
          this.snackBar.open('No se pudo cargar el detalle del batch.', 'Cerrar', {
            duration: 4000,
          });
        },
      });
  }

loadAccess(): void {
  this.isLoadingAccess = true;

  this.planningTargetsService
    .getAccess()
    .pipe(finalize(() => (this.isLoadingAccess = false)))
    .subscribe({
      next: (access) => {
        this.access = access;
      },
      error: () => {
        this.access = null;
      },
    });
}

loadActiveBranches(): void {
  this.isLoadingBranches = true;

  this.planningTargetsService
    .listActiveBranches()
    .pipe(finalize(() => (this.isLoadingBranches = false)))
    .subscribe({
      next: (response) => {
        this.activeBranches = response.items || [];
      },
      error: () => {
        this.activeBranches = [];
        this.snackBar.open(
          'No se pudo cargar el catálogo de sucursales.',
          'Cerrar',
          { duration: 4000 },
        );
      },
    });
}

    canAddBranchRow(): boolean {
    return Boolean(
        this.access?.can_edit &&
        this.batch &&
        ['BORRADOR', 'PROPUESTA'].includes(this.batch.status),
    );
    }

private openActionDialog(
  data: PlanningTargetActionDialogData,
  onConfirm: (comment: string) => void,
): void {
  const dialogRef = this.dialog.open<
    PlanningTargetActionDialogComponent,
    PlanningTargetActionDialogData,
    PlanningTargetActionDialogResult
  >(PlanningTargetActionDialogComponent, {
    width: '520px',
    maxWidth: '95vw',
    data,
  });

  dialogRef.afterClosed().subscribe((result) => {
    if (!result?.confirmed) {
      return;
    }

    onConfirm(result.comment);
  });
}

canSubmitBatch(): boolean {
  return Boolean(
    this.access?.can_submit &&
      this.batch &&
      ['BORRADOR', 'PROPUESTA'].includes(this.batch.status) &&
      this.getBranchRows().length > 0,
  );
}

canApproveBatch(): boolean {
  return Boolean(
    this.access?.can_approve &&
      this.batch?.status === 'EN_REVISION',
  );
}

canRejectBatch(): boolean {
  return Boolean(
    this.access?.can_approve &&
      this.batch?.status === 'EN_REVISION',
  );
}

canPublishBatch(): boolean {
  return Boolean(
    this.access?.can_publish &&
      this.batch?.status === 'APROBADA',
  );
}

hasAnyBatchAction(): boolean {
  return (
    this.canSubmitBatch() ||
    this.canApproveBatch() ||
    this.canRejectBatch() ||
    this.canPublishBatch()
  );
}

toggleAddBranchForm(): void {
  this.showAddBranchForm = !this.showAddBranchForm;

  if (this.showAddBranchForm) {
    if (!this.branchForm.scenarioUsed) {
      this.branchForm.scenarioUsed = 'AJUSTADO';
    }

  if (!this.branchForm.sucursalCanon && this.activeBranches.length > 0) {
    this.branchForm.sucursalCanon = this.activeBranches[0].sucursal_canon;
    this.prefillBranchData(this.branchForm.sucursalCanon);
    this.loadBranchComparisons(this.branchForm.sucursalCanon);
  }
  }
}

  onBranchSelected(): void {
    const sucursalCanon = this.branchForm.sucursalCanon;

    if (!sucursalCanon) {
      this.branchPrefillSourceLabel = '';
      this.branchComparisons = null;
      return;
    }

    this.prefillBranchData(sucursalCanon);
    this.loadBranchComparisons(sucursalCanon);
  }

  prefillBranchData(sucursalCanon: string): void {
    this.isLoadingBranchPrefill = true;
    this.branchPrefillSourceLabel = '';

    this.planningTargetsService
      .getBranchPrefill(sucursalCanon, this.getTargetMonthForPrefill())
      .pipe(finalize(() => (this.isLoadingBranchPrefill = false)))
      .subscribe({
        next: (response) => {
          if (response.m2_sin_circulaciones !== null && response.m2_sin_circulaciones !== undefined) {
            this.branchForm.m2SinCirculaciones = Number(response.m2_sin_circulaciones);
          }

          if (response.usuarios_inicio_mes !== null && response.usuarios_inicio_mes !== undefined) {
            this.branchForm.usuariosInicioMes = Number(response.usuarios_inicio_mes);
          }

          if (
            response.proyeccion_usuarios_cierre_mes !== null &&
            response.proyeccion_usuarios_cierre_mes !== undefined
          ) {
            this.branchForm.proyeccionUsuariosCierreMes = Number(
              response.proyeccion_usuarios_cierre_mes,
            );
          }

          if (response.meta_faycgo_mes !== null && response.meta_faycgo_mes !== undefined) {
            this.branchForm.metaFaycgoMes = Number(response.meta_faycgo_mes);
          }

          if (
            response.meta_clientes_nuevos_mes !== null &&
            response.meta_clientes_nuevos_mes !== undefined
          ) {
            this.branchForm.metaClientesNuevosMes = Number(
              response.meta_clientes_nuevos_mes,
            );
          }

          if (
            response.meta_reactivaciones_mes !== null &&
            response.meta_reactivaciones_mes !== undefined
          ) {
            this.branchForm.metaReactivacionesMes = Number(
              response.meta_reactivaciones_mes,
            );
          }

          if (response.meta_bajas_mes !== null && response.meta_bajas_mes !== undefined) {
            this.branchForm.metaBajasMes = Number(response.meta_bajas_mes);
          }

          if (
            response.meta_nuevos_domiciliados_mes !== null &&
            response.meta_nuevos_domiciliados_mes !== undefined
          ) {
            this.branchForm.metaNuevosDomiciliadosMes = Number(
              response.meta_nuevos_domiciliados_mes,
            );
          }

          if (response.meta_arpu_mes !== null && response.meta_arpu_mes !== undefined) {
            this.branchForm.metaArpuMes = Number(response.meta_arpu_mes);
          }

          if (
            response.meta_venta_tienda_mes !== null &&
            response.meta_venta_tienda_mes !== undefined
          ) {
            this.branchForm.metaVentaTiendaMes = Number(
              response.meta_venta_tienda_mes,
            );
          }

          if (response.source && response.source_track_date) {
            this.branchPrefillSourceLabel = `Precargado desde ${response.source} (${response.source_track_date})`;
          } else {
            this.branchPrefillSourceLabel = 'Sin datos disponibles para precargar.';
          }
        },
        error: () => {
          this.branchPrefillSourceLabel = 'No se pudo precargar información de la sucursal.';
          this.snackBar.open(
            'No se pudo precargar información de la sucursal.',
            'Cerrar',
            { duration: 4000 },
          );
        },
      });
  }

  loadBranchComparisons(sucursalCanon: string): void {
    const targetMonth = this.getTargetMonthForPrefill();

    if (!targetMonth) {
      this.branchComparisons = null;
      return;
    }

    this.isLoadingBranchComparisons = true;

    this.planningTargetsService
      .getBranchComparisons(sucursalCanon, targetMonth)
      .pipe(finalize(() => (this.isLoadingBranchComparisons = false)))
      .subscribe({
        next: (response) => {
          this.branchComparisons = response;
        },
        error: () => {
          this.branchComparisons = null;
          this.snackBar.open(
            'No se pudieron cargar los comparativos de la sucursal.',
            'Cerrar',
            { duration: 4000 },
          );
        },
      });
  }

    addBranchRow(): void {
    if (!this.batchId || !this.batch) {
        this.snackBar.open('Batch inválido.', 'Cerrar', {
        duration: 4000,
        });
        return;
    }

    if (!this.canAddBranchRow()) {
        this.snackBar.open('No puedes agregar sucursales en este estado.', 'Cerrar', {
        duration: 4000,
        });
        return;
    }

    const payload = this.buildBranchRowPayload();

    if (!payload) {
        return;
    }

    this.isAddingBranchRow = true;

    this.planningTargetsService
        .addBranchRowToBatch(this.batchId, payload)
        .pipe(finalize(() => (this.isAddingBranchRow = false)))
        .subscribe({
        next: () => {
            this.snackBar.open('Sucursal agregada al paquete.', 'Cerrar', {
            duration: 3000,
            });
            this.showAddBranchForm = false;
            this.resetBranchForm();
            this.loadBatchDetail();
        },
        error: () => {
            this.snackBar.open(
            'No se pudo agregar la sucursal. Revisa si ya existe en el batch o si la clave es correcta.',
            'Cerrar',
            { duration: 5000 },
            );
        },
        });
    }

    buildBranchRowPayload(): AddPlanningTargetBranchRowPayload | null {
    const sucursalCanon = this.branchForm.sucursalCanon.trim().toUpperCase();

    if (!sucursalCanon) {
        this.snackBar.open('Captura la sucursal canónica.', 'Cerrar', {
        duration: 4000,
        });
        return null;
    }

    const numericFields = [
        ['m2 sin circulaciones', this.branchForm.m2SinCirculaciones],
        ['usuarios inicio mes', this.branchForm.usuariosInicioMes],
        ['proyección usuarios cierre mes', this.branchForm.proyeccionUsuariosCierreMes],
        ['meta FAYCGO mes', this.branchForm.metaFaycgoMes],
        ['clientes nuevos', this.branchForm.metaClientesNuevosMes],
        ['reactivaciones', this.branchForm.metaReactivacionesMes],
        ['bajas', this.branchForm.metaBajasMes],
        ['nuevos domiciliados', this.branchForm.metaNuevosDomiciliadosMes],
        ['ARPU', this.branchForm.metaArpuMes],
        ['venta tienda', this.branchForm.metaVentaTiendaMes],
    ] as Array<[string, number]>;

    const invalidField = numericFields.find(([, value]) => {
        const numericValue = Number(value);
        return Number.isNaN(numericValue) || numericValue < 0;
    });

    if (invalidField) {
        this.snackBar.open(
        `El campo ${invalidField[0]} debe ser numérico y no negativo.`,
        'Cerrar',
        { duration: 4000 },
        );
        return null;
    }

    return {
        sucursal_canon: sucursalCanon,
        m2_sin_circulaciones: Number(this.branchForm.m2SinCirculaciones),
        usuarios_inicio_mes: Number(this.branchForm.usuariosInicioMes),
        proyeccion_usuarios_cierre_mes: Number(
        this.branchForm.proyeccionUsuariosCierreMes,
        ),
        meta_faycgo_mes: Number(this.branchForm.metaFaycgoMes),
        meta_clientes_nuevos_mes: Number(this.branchForm.metaClientesNuevosMes),
        meta_reactivaciones_mes: Number(this.branchForm.metaReactivacionesMes),
        meta_bajas_mes: Number(this.branchForm.metaBajasMes),
        meta_nuevos_domiciliados_mes: Number(
        this.branchForm.metaNuevosDomiciliadosMes,
        ),
        meta_arpu_mes: Number(this.branchForm.metaArpuMes),
        meta_venta_tienda_mes: Number(this.branchForm.metaVentaTiendaMes),
        ingreso_agregadoras_estimado:
        this.branchForm.ingresoAgregadorasEstimado === null
            ? null
            : Number(this.branchForm.ingresoAgregadorasEstimado),
        usuarios_agregadoras_estimado:
        this.branchForm.usuariosAgregadorasEstimado === null
            ? null
            : Number(this.branchForm.usuariosAgregadorasEstimado),
        scenario_used: this.branchForm.scenarioUsed || null,
        trend_classification: this.branchForm.trendClassification || null,
        risk_level: this.branchForm.riskLevel || null,
        status: 'PROPUESTA',
        previous_branch_row_id: null,
        notes: this.branchForm.notes || null,
    };
    }

    resetBranchForm(): void {
    this.branchForm = {
        sucursalCanon: '',
        m2SinCirculaciones: 0,
        usuariosInicioMes: 0,
        proyeccionUsuariosCierreMes: 0,
        metaFaycgoMes: 0,
        metaClientesNuevosMes: 0,
        metaReactivacionesMes: 0,
        metaBajasMes: 0,
        metaNuevosDomiciliadosMes: 0,
        metaArpuMes: 0,
        metaVentaTiendaMes: 0,
        ingresoAgregadorasEstimado: null,
        usuariosAgregadorasEstimado: null,
        scenarioUsed: 'AJUSTADO',
        trendClassification: '',
        riskLevel: 'MEDIO',
        notes: '',
    };
    this.branchPrefillSourceLabel = '';
    this.branchComparisons = null;
    }

submitBatch(): void {
  if (!this.batchId || !this.canSubmitBatch()) {
    this.snackBar.open(
      'No se puede enviar este paquete a revisión.',
      'Cerrar',
      { duration: 4000 },
    );
    return;
  }

  this.openActionDialog(
    {
      title: 'Enviar paquete a revisión',
      actionLabel: 'Enviar a revisión',
      description:
        'El paquete quedará disponible para aprobación o rechazo. Asegúrate de que las sucursales capturadas sean correctas.',
      defaultComment: 'Enviado a revisión desde detalle.',
      requireComment: false,
      confirmColor: 'primary',
    },
    (comment) => this.runSubmitBatch(comment),
  );
}

approveBatch(): void {
  if (!this.batchId || !this.canApproveBatch()) {
    this.snackBar.open(
      'No se puede aprobar este paquete en su estado actual.',
      'Cerrar',
      { duration: 4000 },
    );
    return;
  }

  this.openActionDialog(
    {
      title: 'Aprobar paquete mensual',
      actionLabel: 'Aprobar',
      description:
        'Al aprobar este paquete, quedará listo para publicarse hacia Track. Esta acción quedará registrada en auditoría.',
      defaultComment: 'Aprobado desde detalle.',
      requireComment: false,
      confirmColor: 'primary',
    },
    (comment) => this.runApproveBatch(comment),
  );
}

rejectBatch(): void {
  if (!this.batchId || !this.canRejectBatch()) {
    this.snackBar.open(
      'No se puede rechazar este paquete en su estado actual.',
      'Cerrar',
      { duration: 4000 },
    );
    return;
  }

  this.openActionDialog(
    {
      title: 'Rechazar paquete mensual',
      actionLabel: 'Rechazar',
      description:
        'El paquete quedará rechazado y deberá ajustarse antes de poder aprobarse.',
      warning:
        'El motivo es obligatorio porque esta decisión afecta la trazabilidad del proceso.',
      defaultComment: '',
      requireComment: true,
      confirmColor: 'warn',
    },
    (comment) => this.runRejectBatch(comment),
  );
}

publishBatch(): void {
  if (!this.batchId || !this.canPublishBatch()) {
    this.snackBar.open(
      'No se puede publicar este paquete hacia Track.',
      'Cerrar',
      { duration: 4000 },
    );
    return;
  }

  this.openActionDialog(
    {
      title: 'Publicar metas hacia Track',
      actionLabel: 'Publicar a Track',
      description:
        'Al publicar, estas metas quedarán activas para Track y reemplazarán metas activas anteriores del mismo mes y sucursal.',
      warning:
        'Esta acción afecta datos canónicos. Revisa que el paquete aprobado sea correcto antes de publicar.',
      defaultComment: 'Publicado hacia Track desde detalle.',
      requireComment: true,
      confirmColor: 'primary',
    },
    (comment) => this.runPublishBatch(comment),
  );
}
    
  refresh(): void {
    this.loadBatchDetail();
  }

  getBranchRows(): PlanningTargetBranchRowDetail[] {
    return this.batch?.branch_rows || [];
  }

  getApprovalEvents(): PlanningTargetApprovalEventDetail[] {
    return this.batch?.approval_events || [];
  }

  getStatusClass(status: string | null | undefined): string {
    const normalizedStatus = String(status || '').toLowerCase();
    return `status-${normalizedStatus}`;
  }

  getTargetMonthForPrefill(): string | undefined {
    return this.batch?.target_month || undefined;
  }

  formatMonth(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }

    return value.slice(0, 7);
  }

  formatMonthLabel(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }

    const [year, month] = value.slice(0, 7).split('-').map(Number);

    if (!year || !month) {
      return value;
    }

    const date = new Date(year, month - 1, 1);

    return new Intl.DateTimeFormat('es-MX', {
      month: 'long',
      year: 'numeric',
    }).format(date);
  }

  formatMoney(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }

    const numericValue = Number(value);

    if (Number.isNaN(numericValue)) {
      return String(value);
    }

    return numericValue.toLocaleString('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 2,
    });
  }

  formatNumber(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }

    const numericValue = Number(value);

    if (Number.isNaN(numericValue)) {
      return String(value);
    }

    return numericValue.toLocaleString('es-MX');
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString('es-MX');
  }

  getComparisonValue(
    periodKey: 'current_month' | 'previous_month' | 'same_month_last_year',
    fieldKey: keyof NonNullable<PlanningBranchComparisonsResponse['items']['current_month']>,
  ): string | number | null {
    const row = this.branchComparisons?.items?.[periodKey];

    if (!row) {
      return null;
    }

    return row[fieldKey] ?? null;
  }

  formatComparisonMoney(
    periodKey: 'current_month' | 'previous_month' | 'same_month_last_year',
    fieldKey: keyof NonNullable<PlanningBranchComparisonsResponse['items']['current_month']>,
  ): string {
    return this.formatMoney(this.getComparisonValue(periodKey, fieldKey));
  }

  formatComparisonNumber(
    periodKey: 'current_month' | 'previous_month' | 'same_month_last_year',
    fieldKey: keyof NonNullable<PlanningBranchComparisonsResponse['items']['current_month']>,
  ): string {
    return this.formatNumber(this.getComparisonValue(periodKey, fieldKey));
  }

  hasComparisonPeriod(
    periodKey: 'current_month' | 'previous_month' | 'same_month_last_year',
  ): boolean {
    return Boolean(this.branchComparisons?.items?.[periodKey]);
  }

getBranchLabel(sucursalCanon: string | null | undefined): string {
  if (!sucursalCanon) {
    return '—';
  }

  const branch = this.activeBranches.find(
    (item) => item.sucursal_canon === sucursalCanon,
  );

  if (!branch) {
    return sucursalCanon;
  }

  return branch.track_label;
}

  getModelLabel(): string {
    const modelConfig = this.batch?.model_config;

    if (!modelConfig) {
      return 'Sin modelo';
    }

    return `${modelConfig.name} v${modelConfig.version}`;
  }

  hasPublishedTarget(row: PlanningTargetBranchRowDetail): boolean {
    return Boolean(row.published_track_monthly_target_id);
  }

  private runApproveBatch(comment: string): void {
  if (!this.batchId) {
    return;
  }

  this.isRunningBatchAction = true;

  this.planningTargetsService
    .approveBatch(this.batchId, comment)
    .pipe(finalize(() => (this.isRunningBatchAction = false)))
    .subscribe({
      next: () => {
        this.snackBar.open('Paquete aprobado.', 'Cerrar', {
          duration: 3000,
        });
        this.loadBatchDetail();
      },
      error: () => {
        this.snackBar.open('No se pudo aprobar el paquete.', 'Cerrar', {
          duration: 4000,
        });
      },
    });
}

private runRejectBatch(comment: string): void {
  if (!this.batchId) {
    return;
  }

  this.isRunningBatchAction = true;

  this.planningTargetsService
    .rejectBatch(this.batchId, comment)
    .pipe(finalize(() => (this.isRunningBatchAction = false)))
    .subscribe({
      next: () => {
        this.snackBar.open('Paquete rechazado.', 'Cerrar', {
          duration: 3000,
        });
        this.loadBatchDetail();
      },
      error: () => {
        this.snackBar.open('No se pudo rechazar el paquete.', 'Cerrar', {
          duration: 4000,
        });
      },
    });
}

private runPublishBatch(comment: string): void {
  if (!this.batchId) {
    return;
  }

  this.isRunningBatchAction = true;

  this.planningTargetsService
    .publishBatch(this.batchId, comment)
    .pipe(finalize(() => (this.isRunningBatchAction = false)))
    .subscribe({
      next: () => {
        this.snackBar.open('Paquete publicado hacia Track.', 'Cerrar', {
          duration: 3000,
        });
        this.loadBatchDetail();
      },
      error: () => {
        this.snackBar.open('No se pudo publicar hacia Track.', 'Cerrar', {
          duration: 4000,
        });
      },
    });
}

private runSubmitBatch(comment: string): void {
  if (!this.batchId) {
    return;
  }

  this.isRunningBatchAction = true;

  this.planningTargetsService
    .submitBatch(this.batchId, comment)
    .pipe(finalize(() => (this.isRunningBatchAction = false)))
    .subscribe({
      next: () => {
        this.snackBar.open('Paquete enviado a revisión.', 'Cerrar', {
          duration: 3000,
        });
        this.loadBatchDetail();
      },
      error: () => {
        this.snackBar.open('No se pudo enviar a revisión.', 'Cerrar', {
          duration: 4000,
        });
      },
    });
}
}