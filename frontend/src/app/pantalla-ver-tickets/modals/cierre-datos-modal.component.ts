// frontend-angular/src/app/pantalla-ver-tickets/modals/cierre-datos-modal.component.ts

import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';

export interface CierreDatosModalData {
  costo_solucion?: number | null;
  notas_cierre?: string | null;
}

@Component({
  selector: 'app-cierre-datos-modal',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatDialogModule,
  ],
  templateUrl: './cierre-datos-modal.component.html',
})
export class CierreDatosModalComponent {
  // siempre strings en el formulario
  costoSolucionStr: string = '';
  notasCierreStr: string = '';

  constructor(
    private dialogRef: MatDialogRef<CierreDatosModalComponent>,
    @Inject(MAT_DIALOG_DATA) public data: CierreDatosModalData
  ) {
    if (data?.costo_solucion != null) {
      this.costoSolucionStr = String(data.costo_solucion);
    }
    if (data?.notas_cierre) {
      this.notasCierreStr = String(data.notas_cierre);
    }
  }

  cancelar(): void {
    this.dialogRef.close(null);
  }

  aceptar(): void {
    // 🔹 trim seguro aunque venga null/undefined
    const raw = (this.costoSolucionStr ?? '').toString().trim();
    let costo: number | null = null;

    if (raw) {
      const parsed = Number(raw.replace(',', '.'));
      if (!Number.isNaN(parsed)) {
        costo = parsed;
      }
    }

    const notasLimpias =
      (this.notasCierreStr ?? '').toString().trim() || null;

    this.dialogRef.close({
      costo_solucion: costo,
      notas_cierre: notasLimpias,
    } as CierreDatosModalData);
  }
}
