//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\modals\editar-fecha-solucion-modal.component.ts

import { Component, Inject } from '@angular/core';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatButtonModule } from '@angular/material/button';
import { FormsModule } from '@angular/forms';

@Component({
  standalone: true,
  selector: 'app-editar-fecha-solucion-modal',
  templateUrl: './editar-fecha-solucion-modal.component.html',
  styleUrls: ['./editar-fecha-solucion-modal.component.scss'],
  imports: [
    CommonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatButtonModule,
    FormsModule 
  ]
})


export class EditarFechaSolucionModalComponent {
  nuevaFecha: Date | null = null;
  motivo: string = '';
  loading: boolean = false;

  constructor(
    public dialogRef: MatDialogRef<EditarFechaSolucionModalComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { fechaActual: string }
  ) {
    // Si ya había fecha previa, precargarla
    this.nuevaFecha = data.fechaActual ? new Date(data.fechaActual) : null;
  }

  cerrar() {
    this.dialogRef.close();
  }

  guardar() {
    if (!this.nuevaFecha) {
      (window as any).mostrarAlertaToast?.('⚠️ Selecciona una fecha para continuar.');
      return;
    }
    if (!this.motivo.trim()) {
      (window as any).mostrarAlertaToast?.('⚠️ Escribe el motivo del cambio.');
      return;
    }
    this.loading = true;
    this.dialogRef.close({ fecha: this.nuevaFecha, motivo: this.motivo.trim() });
  }
}
