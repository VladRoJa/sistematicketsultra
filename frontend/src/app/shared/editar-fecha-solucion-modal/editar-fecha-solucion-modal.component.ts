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
    this.nuevaFecha = this.parseInitialDate(data.fechaActual);
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

  private parseInitialDate(value: string | null): Date | null {
    const normalized = String(value || '').trim();
    if (!normalized) {
      return null;
    }

    const dateOnlyMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateOnlyMatch) {
      const year = Number(dateOnlyMatch[1]);
      const month = Number(dateOnlyMatch[2]);
      const day = Number(dateOnlyMatch[3]);
      return new Date(year, month - 1, day, 7, 0, 0);
    }

    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
}
