// frontend/src/app/pm/pm-configuracion-programacion/dialogs/editar-frecuencia-dialog.component.ts


import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';

export interface EditarFrecuenciaDialogData {
  equipoLabel: string;
  frecuenciaActual: number;
}

@Component({
  selector: 'app-editar-frecuencia-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  templateUrl: './editar-frecuencia-dialog.component.html',
  styleUrls: ['./editar-frecuencia-dialog.component.css'],
})
export class EditarFrecuenciaDialogComponent {
  private dialogRef = inject(MatDialogRef<EditarFrecuenciaDialogComponent>);
  readonly data = inject<EditarFrecuenciaDialogData>(MAT_DIALOG_DATA);

  frecuencia: number = this.data.frecuenciaActual;
  mostrarError = false;

  cancelar(): void {
    this.dialogRef.close();
  }

  guardar(): void {
    if (!Number.isInteger(this.frecuencia) || this.frecuencia <= 0) {
      this.mostrarError = true;
      return;
    }

    this.dialogRef.close(this.frecuencia);
  }
}