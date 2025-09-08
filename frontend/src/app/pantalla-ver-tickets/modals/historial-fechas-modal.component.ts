// src/app/pantalla-ver-tickets/modals/historial-fechas-modal.component.ts

import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { Ticket } from '../pantalla-ver-tickets.component';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';


@Component({
  standalone: true, 
  selector: 'app-historial-fechas-modal',
  templateUrl: './historial-fechas-modal.component.html',
  styleUrls: ['./historial-fechas-modal.component.scss'],
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatDividerModule,
    MatIconModule
  ]
})
export class HistorialFechasModalComponent {
  tz = 'America/Tijuana';
  fmtDate = 'dd/MM/yy';
  fmtDateTime = 'dd/MM/yyyy hh:mm a';

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: Ticket,
    private dialogRef: MatDialogRef<HistorialFechasModalComponent>
  ) {}

  cerrar(): void { this.dialogRef.close(); }
}