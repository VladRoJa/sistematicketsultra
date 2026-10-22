import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MovimientoInventarioVista } from '../movimientos-vista.helper';

@Component({
  selector: 'app-dialogo-anular-movimiento',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatDialogModule],
  templateUrl: './dialogo-anular-movimiento.component.html',
  styleUrls: ['./dialogo-anular-movimiento.component.css'],
})
export class DialogoAnularMovimientoComponent {
  motivo = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.minLength(10), Validators.maxLength(1000)],
  });

  constructor(
    @Inject(MAT_DIALOG_DATA) public movimiento: MovimientoInventarioVista,
    private dialogRef: MatDialogRef<DialogoAnularMovimientoComponent>,
  ) {}

  cancelar(): void {
    this.dialogRef.close(null);
  }

  confirmar(): void {
    const motivoLimpio = this.motivo.value.trim();
    if (motivoLimpio.length < 10 || motivoLimpio.length > 1000) {
      this.motivo.markAsTouched();
      return;
    }
    this.dialogRef.close(motivoLimpio);
  }
}
