// src/app/inventario/productos/eliminar-producto-dialog.component.ts

import { Component, Inject } from '@angular/core';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-eliminar-producto-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule
  ],
  templateUrl: './eliminar-producto-dialog.component.html'
})
export class EliminarProductoDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<EliminarProductoDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { nombre: string }
  ) {}

  confirmar(): void {
    this.dialogRef.close(true);
  }

  cancelar(): void {
    this.dialogRef.close(false);
  }
}
