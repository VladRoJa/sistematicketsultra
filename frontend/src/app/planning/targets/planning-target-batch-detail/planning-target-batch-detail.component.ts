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

import {
  AddPlanningTargetBranchRowPayload,
  PlanningAccessResponse,
  PlanningTargetBatchDetail,
  PlanningTargetBranchRowDetail,
  PlanningTargetApprovalEventDetail,
  PlanningTargetsService,
} from '../../services/planning-targets.service';

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
  ],
  templateUrl: './planning-target-batch-detail.component.html',
  styleUrls: ['./planning-target-batch-detail.component.css',]
})
export class PlanningTargetBatchDetailComponent implements OnInit {
  batchId: number | null = null;
  batch: PlanningTargetBatchDetail | null = null;
  access: PlanningAccessResponse | null = null;

showAddBranchForm = false;
isLoadingAccess = false;
isAddingBranchRow = false;

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
  ) {}

    ngOnInit(): void {
    this.loadBatchIdFromRoute();
    this.loadAccess();
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

    canAddBranchRow(): boolean {
    return Boolean(
        this.access?.can_edit &&
        this.batch &&
        ['BORRADOR', 'PROPUESTA'].includes(this.batch.status),
    );
    }

    toggleAddBranchForm(): void {
    this.showAddBranchForm = !this.showAddBranchForm;

    if (this.showAddBranchForm && !this.branchForm.scenarioUsed) {
        this.branchForm.scenarioUsed = 'AJUSTADO';
    }
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

  formatMonth(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }

    return value.slice(0, 7);
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
}