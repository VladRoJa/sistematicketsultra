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

  aceptar(): void {
    this.dialogRef.close({
      costo: this.costo,
      notas: this.notas?.trim() || null,
    });
  }

  cancelar(): void {
    this.dialogRef.close(null);
  }
}