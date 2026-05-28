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

import {
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
  ],
  templateUrl: './planning-target-batch-detail.component.html',
  styleUrls: ['./planning-target-batch-detail.component.css',]
})
export class PlanningTargetBatchDetailComponent implements OnInit {
  batchId: number | null = null;
  batch: PlanningTargetBatchDetail | null = null;

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