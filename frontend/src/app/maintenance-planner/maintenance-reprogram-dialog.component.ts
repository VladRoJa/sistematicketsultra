import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';

import {
  MaintenancePreventiveService,
  MaintenanceReprogramReason,
} from '../services/maintenance-preventive.service';

export interface MaintenanceReprogramDialogData {
  fechaActual: string | null;
  fechaSugerida?: string | null;
}

export interface MaintenanceReprogramDialogResult {
  fecha: Date;
  reasonId: number;
  comentario: string | null;
}

@Component({
  selector: 'app-maintenance-reprogram-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
  ],
  templateUrl: './maintenance-reprogram-dialog.component.html',
  styleUrls: ['./maintenance-reprogram-dialog.component.css'],
})
export class MaintenanceReprogramDialogComponent implements OnInit {
  reasons: MaintenanceReprogramReason[] = [];
  selectedReasonId: number | null = null;
  comentario = '';
  nuevaFecha = '';
  loading = false;
  errorMessage = '';

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public readonly data: MaintenanceReprogramDialogData,
    private readonly ref: MatDialogRef<
      MaintenanceReprogramDialogComponent,
      MaintenanceReprogramDialogResult | undefined
    >,
    private readonly maintenanceService: MaintenancePreventiveService,
  ) {}

  ngOnInit(): void {
    this.nuevaFecha =
      this.toDateOnly(this.data.fechaSugerida)
      || this.toDateOnly(this.data.fechaActual)
      || '';
    this.loadReasons();
  }

  get selectedReason(): MaintenanceReprogramReason | null {
    return this.reasons.find(
      (reason) => reason.id === this.selectedReasonId,
    ) || null;
  }

  get canSave(): boolean {
    return Boolean(
      !this.loading
      && this.nuevaFecha
      && this.selectedReasonId
      && (
        !this.selectedReason?.requiere_comentario
        || this.comentario.trim()
      )
    );
  }

  loadReasons(): void {
    this.loading = true;
    this.errorMessage = '';

    this.maintenanceService.getReprogramReasons().subscribe({
      next: (response) => {
        this.reasons = response.reasons || [];
        this.loading = false;

        if (!this.reasons.length) {
          this.errorMessage =
            'No hay motivos de reprogramación activos.';
        }
      },
      error: (error) => {
        this.loading = false;
        this.reasons = [];
        this.errorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudieron cargar los motivos de reprogramación.';
      },
    });
  }

  save(): void {
    if (!this.canSave || !this.selectedReasonId) {
      return;
    }

    const date = this.parseDateOnly(this.nuevaFecha);
    if (!date) {
      this.errorMessage = 'La nueva fecha es inválida.';
      return;
    }

    this.ref.close({
      fecha: date,
      reasonId: this.selectedReasonId,
      comentario: this.comentario.trim() || null,
    });
  }

  close(): void {
    this.ref.close();
  }

  private toDateOnly(value: string | null | undefined): string | null {
    const raw = String(value || '').trim();
    if (!raw) return null;

    const dateOnly = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (dateOnly) {
      return dateOnly[1] + '-' + dateOnly[2] + '-' + dateOnly[3];
    }

    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return null;

    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Tijuana',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    return formatter.format(parsed);
  }

  private parseDateOnly(value: string): Date | null {
    const [year, month, day] = String(value || '')
      .split('-')
      .map(Number);

    if (!year || !month || !day) {
      return null;
    }

    return new Date(year, month - 1, day, 7, 0, 0);
  }
}
