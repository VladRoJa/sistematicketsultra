// frontend/src/app/planning/targets/planning-targets-home/planning-targets-home.component.ts

import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { finalize } from 'rxjs';

import {
  PlanningAccessResponse,
  PlanningTargetBatchSummary,
  PlanningTargetsService,
} from '../../services/planning-targets.service';

@Component({
  selector: 'app-planning-targets-home',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTableModule,
  ],
  templateUrl: './planning-targets-home.component.html',
  styleUrls: ['./planning-targets-home.component.css',]
})
export class PlanningTargetsHomeComponent implements OnInit {
  access: PlanningAccessResponse | null = null;
  batches: PlanningTargetBatchSummary[] = [];

  isLoadingAccess = false;
  isLoadingBatches = false;
  actionBatchId: number | null = null;

  displayedColumns: string[] = [
    'target_month',
    'version',
    'status',
    'scope',
    'model_config',
    'rows',
    'canonical',
    'actions',
  ];

  constructor(
    private readonly planningTargetsService: PlanningTargetsService,
    private readonly snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadAccess();
  }

  loadAccess(): void {
    this.isLoadingAccess = true;

    this.planningTargetsService
      .getAccess()
      .pipe(finalize(() => (this.isLoadingAccess = false)))
      .subscribe({
        next: (access) => {
          this.access = access;

          if (access.has_access) {
            this.loadBatches();
          }
        },
        error: () => {
          this.snackBar.open(
            'No se pudo consultar el acceso a Planeación Comercial.',
            'Cerrar',
            { duration: 4000 },
          );
        },
      });
  }

  loadBatches(): void {
    this.isLoadingBatches = true;

    this.planningTargetsService
      .listBatches()
      .pipe(finalize(() => (this.isLoadingBatches = false)))
      .subscribe({
        next: (response) => {
          this.batches = response.items || [];
        },
        error: () => {
          this.snackBar.open(
            'No se pudieron cargar los paquetes de metas.',
            'Cerrar',
            { duration: 4000 },
          );
        },
      });
  }

  refresh(): void {
    if (!this.access?.has_access) {
      this.loadAccess();
      return;
    }

    this.loadBatches();
  }

  canSubmit(batch: PlanningTargetBatchSummary): boolean {
    return Boolean(
      this.access?.can_submit &&
        ['BORRADOR', 'PROPUESTA'].includes(batch.batch_status),
    );
  }

  canApprove(batch: PlanningTargetBatchSummary): boolean {
    return Boolean(
      this.access?.can_approve && batch.batch_status === 'EN_REVISION',
    );
  }

  canReject(batch: PlanningTargetBatchSummary): boolean {
    return Boolean(
      this.access?.can_approve && batch.batch_status === 'EN_REVISION',
    );
  }

  canPublish(batch: PlanningTargetBatchSummary): boolean {
    return Boolean(
      this.access?.can_publish && batch.batch_status === 'APROBADA',
    );
  }

  submitBatch(batch: PlanningTargetBatchSummary): void {
    this.actionBatchId = batch.id;

    this.planningTargetsService
      .submitBatch(batch.id, 'Enviado a revisión desde frontend MVP.')
      .pipe(finalize(() => (this.actionBatchId = null)))
      .subscribe({
        next: () => {
          this.snackBar.open('Batch enviado a revisión.', 'Cerrar', {
            duration: 3000,
          });
          this.loadBatches();
        },
        error: () => {
          this.snackBar.open('No se pudo enviar a revisión.', 'Cerrar', {
            duration: 4000,
          });
        },
      });
  }

  approveBatch(batch: PlanningTargetBatchSummary): void {
    this.actionBatchId = batch.id;

    this.planningTargetsService
      .approveBatch(batch.id, 'Aprobado desde frontend MVP.')
      .pipe(finalize(() => (this.actionBatchId = null)))
      .subscribe({
        next: () => {
          this.snackBar.open('Batch aprobado.', 'Cerrar', {
            duration: 3000,
          });
          this.loadBatches();
        },
        error: () => {
          this.snackBar.open('No se pudo aprobar el batch.', 'Cerrar', {
            duration: 4000,
          });
        },
      });
  }

  rejectBatch(batch: PlanningTargetBatchSummary): void {
    this.actionBatchId = batch.id;

    this.planningTargetsService
      .rejectBatch(batch.id, 'Rechazado desde frontend MVP.')
      .pipe(finalize(() => (this.actionBatchId = null)))
      .subscribe({
        next: () => {
          this.snackBar.open('Batch rechazado.', 'Cerrar', {
            duration: 3000,
          });
          this.loadBatches();
        },
        error: () => {
          this.snackBar.open('No se pudo rechazar el batch.', 'Cerrar', {
            duration: 4000,
          });
        },
      });
  }

  publishBatch(batch: PlanningTargetBatchSummary): void {
    this.actionBatchId = batch.id;

    this.planningTargetsService
      .publishBatch(batch.id, 'Publicado hacia Track desde frontend MVP.')
      .pipe(finalize(() => (this.actionBatchId = null)))
      .subscribe({
        next: () => {
          this.snackBar.open('Batch publicado hacia Track.', 'Cerrar', {
            duration: 3000,
          });
          this.loadBatches();
        },
        error: () => {
          this.snackBar.open('No se pudo publicar hacia Track.', 'Cerrar', {
            duration: 4000,
          });
        },
      });
  }

  getStatusClass(status: string): string {
    const normalizedStatus = String(status || '').toLowerCase();
    return `status-${normalizedStatus}`;
  }

  formatMonth(value: string): string {
    if (!value) {
      return '—';
    }

    return value.slice(0, 7);
  }

  isActionLoading(batch: PlanningTargetBatchSummary): boolean {
    return this.actionBatchId === batch.id;
  }
}