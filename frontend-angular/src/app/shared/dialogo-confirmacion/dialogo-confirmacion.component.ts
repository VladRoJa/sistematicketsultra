//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\shared\dialogo-confirmacion\dialogo-confirmacion.component.ts

import { Component, Inject } from '@angular/core';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-dialogo-confirmacion',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule],
  templateUrl: './dialogo-confirmacion.component.html'
})
export class DialogoConfirmacionComponent {
  constructor(
    public dialogRef: MatDialogRef<DialogoConfirmacionComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { titulo: string; mensaje: string; textoAceptar?: string; textoCancelar?: string }
  ) {}

  confirmar(): void {
    this.dialogRef.close(true);
  }

  cancelar(): void {
    this.dialogRef.close(false);
  }
}
