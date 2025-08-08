// eliminar-ticket-dialog.component.ts
import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-eliminar-ticket-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule
  ],
  template: `
    <h2 class="dialog-title">Eliminar Ticket</h2>
    <p class="dialog-message">
      ¿Estás seguro de eliminar el ticket #{{ data.ticketId }}?
    </p>

    <div class="dialog-actions">
      <button mat-button (click)="onCancel()" class="btn-cancel">
        Cancelar
      </button>
      <button mat-raised-button color="warn" (click)="onConfirm()" class="btn-confirm">
        Sí, confirmar
      </button>
    </div>
  `,
  styles: [`
    .dialog-title {
      margin-bottom: 0.5rem;
      font-size: 1.25rem;
      font-weight: bold;
    }
    .dialog-message {
      margin-bottom: 1.5rem;
      line-height: 1.4;
    }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 1rem;
    }
    .btn-cancel {
      color: #555; /* Ajusta según tu preferencia */
    }
    .btn-confirm {
      background-color: #d9534f; /* Un tono rojo estilo “warn” */
      color: #fff;
    }
  `]
})
export class EliminarTicketDialogComponent {

  constructor(
    private dialogRef: MatDialogRef<EliminarTicketDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { ticketId: number }
  ) {}

  onConfirm() {
    // Cierra el diálogo y devuelve true para indicar confirmación
    this.dialogRef.close(true);
  }

  onCancel() {
    // Cierra el diálogo y devuelve false para indicar cancelación
    this.dialogRef.close(false);
  }
}
