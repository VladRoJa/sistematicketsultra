import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';

import {
  MaintenancePlannerHistoryItem,
  MaintenancePlannerService,
  MaintenancePlannerTicket,
} from './maintenance-planner.service';

export interface MaintenancePlannerTicketDialogData {
  ticket: MaintenancePlannerTicket;
  canSchedule: boolean;
  initialDate?: string | null;
}

@Component({
  selector: 'app-maintenance-planner-ticket-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, MatDialogModule],
  templateUrl: './maintenance-planner-ticket-dialog.component.html',
  styleUrls: ['./maintenance-planner-ticket-dialog.component.css'],
})
export class MaintenancePlannerTicketDialogComponent {
  readonly ticket = this.data.ticket;
  readonly canSchedule = this.data.canSchedule;

  scheduleDate = this.data.initialDate
    || this.ticket.fecha_solucion_date
    || this.todayDateOnly();
  scheduleReason = '';
  saving = false;
  errorMessage = '';

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MaintenancePlannerTicketDialogData,
    private readonly dialogRef: MatDialogRef<MaintenancePlannerTicketDialogComponent>,
    private readonly plannerService: MaintenancePlannerService,
  ) {}

  get history(): MaintenancePlannerHistoryItem[] {
    return [...(this.ticket.historial_fechas || [])].sort((a, b) => {
      const dateA = this.historyTimestamp(a);
      const dateB = this.historyTimestamp(b);
      return dateB.localeCompare(dateA);
    });
  }

  saveCommitment(): void {
    if (
      !this.canSchedule
      || !this.scheduleDate
      || !this.scheduleReason.trim()
      || this.saving
    ) {
      return;
    }

    this.saving = true;
    this.errorMessage = '';

    this.plannerService
      .updateCommitment(
        this.ticket,
        this.scheduleDate,
        this.scheduleReason,
      )
      .subscribe({
        next: () => {
          this.saving = false;
          this.dialogRef.close({ updated: true });
        },
        error: (error) => {
          this.saving = false;
          this.errorMessage =
            error?.error?.mensaje
            || error?.error?.message
            || 'No se pudo actualizar la fecha compromiso.';
        },
      });
  }

  close(): void {
    this.dialogRef.close({ updated: false });
  }

  historyTargetDate(item: MaintenancePlannerHistoryItem): string | null {
    return String(item.fecha || item.fecha_solucion || '').trim() || null;
  }

  historyChangedAt(item: MaintenancePlannerHistoryItem): string | null {
    return String(item.fechaCambio || item.fecha_cambio || '').trim() || null;
  }

  historyUser(item: MaintenancePlannerHistoryItem): string {
    return String(
      item.cambiadoPor
      || item.usuario
      || item.username
      || '—'
    );
  }

  historyReason(item: MaintenancePlannerHistoryItem): string {
    return String(
      item.motivo
      || item.comentario
      || item.razon
      || 'Sin comentario'
    );
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  formatDate(value: string | null | undefined): string {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  private historyTimestamp(item: MaintenancePlannerHistoryItem): string {
    return String(
      item.fechaCambio
      || item.fecha_cambio
      || item.fecha
      || item.fecha_solucion
      || ''
    );
  }

  private todayDateOnly(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}
