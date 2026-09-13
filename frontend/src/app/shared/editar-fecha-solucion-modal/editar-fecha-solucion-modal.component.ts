import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

export interface EditarFechaSolucionDialogData {
  fechaActual: string | null;
}

export interface EditarFechaSolucionDialogResult {
  fecha: Date;
  motivo: string;
}

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
    FormsModule,
  ],
})
export class EditarFechaSolucionModalComponent {
  nuevaFecha: Date | null = null;
  motivo = '';
  loading = false;

  constructor(
    public readonly dialogRef: MatDialogRef<
      EditarFechaSolucionModalComponent,
      EditarFechaSolucionDialogResult | undefined
    >,
    @Inject(MAT_DIALOG_DATA)
    public readonly data: EditarFechaSolucionDialogData,
  ) {
    this.nuevaFecha = data.fechaActual ? new Date(data.fechaActual) : null;
  }

  cerrar(): void {
    this.dialogRef.close();
  }

  guardar(): void {
    if (!this.nuevaFecha) {
      (window as any).mostrarAlertaToast?.('⚠️ Selecciona una fecha para continuar.');
      return;
    }

    const motivo = this.motivo.trim();
    if (!motivo) {
      (window as any).mostrarAlertaToast?.('⚠️ Escribe el motivo del cambio.');
      return;
    }

    this.loading = true;
    this.dialogRef.close({ fecha: this.nuevaFecha, motivo });
  }
}
