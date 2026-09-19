import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';

import {
  PreventiveValidationBitacora,
  PreventiveValidationDetail,
  TicketService,
} from '../../services/ticket.service';
import { EvidenciaPreviewComponent } from './evidencia-preview.component';

interface PreventiveValidationDialogData {
  ticketId: number;
}

export interface PreventiveValidationDialogResult {
  action: 'accepted' | 'rejected';
  response?: any;
}

@Component({
  selector: 'app-preventive-validation-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './preventive-validation-dialog.component.html',
  styleUrls: ['./preventive-validation-dialog.component.css'],
})
export class PreventiveValidationDialogComponent implements OnInit {
  detail: PreventiveValidationDetail | null = null;
  loading = false;
  saving = false;
  errorMessage = '';

  rejectionMode = false;
  rejectionReason = '';

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public data: PreventiveValidationDialogData,
    private readonly ref: MatDialogRef<
      PreventiveValidationDialogComponent,
      PreventiveValidationDialogResult | undefined
    >,
    private readonly dialog: MatDialog,
    private readonly ticketService: TicketService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loadDetail();
  }

  get latestBitacora(): PreventiveValidationBitacora | null {
    return this.detail?.bitacoras?.[0] || null;
  }

  get previousBitacoras(): PreventiveValidationBitacora[] {
    return this.detail?.bitacoras?.slice(1) || [];
  }

  get canAccept(): boolean {
    return Boolean(
      this.detail?.requirements?.ready_to_validate
      && !this.saving
    );
  }

  get canReject(): boolean {
    return Boolean(
      this.rejectionReason.trim()
      && !this.saving
    );
  }

  loadDetail(): void {
    this.loading = true;
    this.errorMessage = '';

    this.ticketService
      .getPreventiveValidationDetail(this.data.ticketId)
      .subscribe({
        next: (detail) => {
          this.detail = detail;
          this.loading = false;
        },
        error: (error) => {
          this.loading = false;
          this.errorMessage =
            error?.error?.mensaje
            || error?.message
            || 'No se pudo cargar el detalle preventivo.';
        },
      });
  }

  openEvidence(ticketId?: number): void {
    const id = ticketId || this.detail?.ticket?.id;
    if (!id) return;

    this.dialog.open(EvidenciaPreviewComponent, {
      data: {
        ticketId: id,
        titulo: `Ticket #${id}`,
      },
      width: 'min(90vw, 1100px)',
      maxWidth: '90vw',
      maxHeight: '90vh',
      autoFocus: false,
      restoreFocus: false,
      panelClass: 'dlg-evidencia',
    });
  }

  openTicket(ticketId: number): void {
    if (!Number.isInteger(ticketId) || ticketId <= 0) {
      return;
    }

    this.ref.close();
    this.router.navigate(
      ['/main/ver-tickets'],
      {
        queryParams: {
          ticket_id: ticketId,
        },
      },
    );
  }

  showRejectForm(): void {
    this.rejectionMode = true;
    this.errorMessage = '';
  }

  cancelReject(): void {
    this.rejectionMode = false;
    this.rejectionReason = '';
  }

  accept(): void {
    if (!this.canAccept || !this.detail) return;

    this.saving = true;
    this.errorMessage = '';

    this.ticketService
      .cierreAceptarCreador(this.detail.ticket.id)
      .subscribe({
        next: (response) => {
          this.saving = false;
          this.ref.close({
            action: 'accepted',
            response,
          });
        },
        error: (error) => {
          this.saving = false;
          this.errorMessage =
            error?.error?.mensaje
            || error?.message
            || 'No se pudo aceptar el preventivo.';
        },
      });
  }

  reject(): void {
    if (!this.canReject || !this.detail) return;

    this.saving = true;
    this.errorMessage = '';

    this.ticketService
      .cierreRechazarCreador(
        this.detail.ticket.id,
        {
          motivo: this.rejectionReason.trim(),
        },
      )
      .subscribe({
        next: (response) => {
          this.saving = false;
          this.ref.close({
            action: 'rejected',
            response,
          });
        },
        error: (error) => {
          this.saving = false;
          this.errorMessage =
            error?.error?.mensaje
            || error?.message
            || 'No se pudo rechazar el preventivo.';
        },
      });
  }

  close(): void {
    this.ref.close();
  }

  formatDate(value: string | null | undefined): string {
    if (!value) return '—';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  }

  foundStateLabel(value: string | null | undefined): string {
    const labels: Record<string, string> = {
      BUENO: 'Bueno',
      REQUIERE_ATENCION: 'Requiere atención',
      FUERA_SERVICIO: 'Fuera de servicio',
    };
    return labels[String(value || '').trim().toUpperCase()] || '—';
  }

  checkResultLabel(value: string | null | undefined): string {
    const labels: Record<string, string> = {
      OK: 'OK',
      ATENCION: 'Atención',
      NO_APLICA: 'N/A',
    };
    return labels[String(value || '').trim().toUpperCase()] || '—';
  }

  trackBitacora(_: number, row: PreventiveValidationBitacora): number {
    return row.id;
  }

  trackCorrective(_: number, row: { id: number }): number {
    return row.id;
  }

}
