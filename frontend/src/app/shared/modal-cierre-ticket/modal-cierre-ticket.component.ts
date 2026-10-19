// frontend/src/app/shared/modal-cierre-ticket/modal-cierre-ticket.component.ts

import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-modal-cierre-ticket',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
  ],
  templateUrl: './modal-cierre-ticket.component.html',
  styleUrls: ['./modal-cierre-ticket.component.css'],
})
export class ModalCierreTicketComponent {
  costo: number | null = null;
  notas: string = '';

  constructor(
    public dialogRef: MatDialogRef<ModalCierreTicketComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { ticketId: number; modo?: string }
  ) {}

  get isMaintenanceRequest(): boolean {
    return this.data.modo === 'maintenance_request';
  }

  get dialogTitle(): string {
    return this.isMaintenanceRequest
      ? 'Solicitar conformidad de Mantenimiento'
      : `Finalizar ticket #${this.data.ticketId}`;
  }

  get dialogDescription(): string {
    return this.isMaintenanceRequest
      ? 'Registra la revisión realizada. El ticket se enviará al gerente para su conformidad.'
      : 'Registra el costo y las notas del cierre antes de continuar.';
  }

  get reviewLabel(): string {
    return this.isMaintenanceRequest ? 'Notas de revisión (obligatorias)' : 'Notas de cierre';
  }

  get costLabel(): string {
    return this.isMaintenanceRequest ? 'Costo (opcional)' : 'Costo de la solución';
  }

  get noticeTitle(): string {
    return this.isMaintenanceRequest ? 'Solicitud de conformidad' : 'Confirmación de cierre';
  }

  get noticeDescription(): string {
    return this.isMaintenanceRequest
      ? 'Al enviar, el gerente deberá dar conformidad antes del cierre definitivo.'
      : 'Al aceptar, el cierre se enviará directamente. Ya no se mostrará una segunda confirmación.';
  }

  get submitLabel(): string {
    return this.isMaintenanceRequest ? 'Solicitar conformidad' : 'Aceptar cierre';
  }

  get canSubmit(): boolean {
    return !this.isMaintenanceRequest
      || (this.notas.trim().length > 0 && this.notas.trim().length <= 2000);
  }

  aceptar(): void {
    if (!this.canSubmit) return;
    this.dialogRef.close({
      costo: this.costo,
      notas: this.notas?.trim() || null,
    });
  }

  cancelar(): void {
    this.dialogRef.close(null);
  }
}