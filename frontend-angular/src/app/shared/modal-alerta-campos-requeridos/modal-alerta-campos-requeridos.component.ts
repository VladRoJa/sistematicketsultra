//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\shared\modal-alerta-campos-requeridos\modal-alerta-campos-requeridos.component.ts

import { Component } from '@angular/core';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';

@Component({
  standalone: true,
  selector: 'app-modal-alerta-campos-requeridos',
  templateUrl: './modal-alerta-campos-requeridos.component.html',
  imports: [CommonModule, MatDialogModule, MatButtonModule]
})
export class ModalAlertaCamposRequeridosComponent {
  constructor(private dialogRef: MatDialogRef<ModalAlertaCamposRequeridosComponent>) {}

  cerrar() {
    this.dialogRef.close();
  }
}
