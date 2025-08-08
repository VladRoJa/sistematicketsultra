// asignar-fecha-modal.component.ts

import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { FormsModule } from '@angular/forms';
import { mostrarAlertaToast } from 'src/app/utils/alertas';

@Component({
  selector: 'app-asignar-fecha-modal',
  standalone: true,
  templateUrl: './asignar-fecha-modal.component.html',
  styleUrls: ['./asignar-fecha-modal.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatDatepickerModule,
    MatNativeDateModule
  ]
})
export class AsignarFechaModalComponent {
  @Input() fechaSeleccionada: Date | null = null;
  @Output() onGuardar = new EventEmitter<{ fecha: Date; motivo: string }>();
  @Output() onCancelar = new EventEmitter<void>();

  motivo: string = '';

  guardar(): void {
    if (!this.fechaSeleccionada || !this.motivo.trim()) {
      mostrarAlertaToast("Debes seleccionar una fecha y escribir un motivo.", "error");

      return;
    }
    this.onGuardar.emit({ fecha: this.fechaSeleccionada, motivo: this.motivo.trim() });
  }

  cancelar(): void {
    this.onCancelar.emit();
  }
}
