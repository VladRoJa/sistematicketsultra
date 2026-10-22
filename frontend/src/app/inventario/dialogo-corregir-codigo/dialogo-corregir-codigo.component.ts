import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Inventario } from '../../models/inventario.model';
import { InventarioService } from '../../services/inventario.service';

export interface EventoCorreccionCodigo {
  id: number;
  usuario_id: number;
  codigo_anterior: string;
  codigo_nuevo: string;
  motivo: string;
  ocurrido_en_utc: string;
}

@Component({
  selector: 'app-dialogo-corregir-codigo',
  standalone: true,
  templateUrl: './dialogo-corregir-codigo.component.html',
  styleUrls: ['./dialogo-corregir-codigo.component.css'],
  imports: [
    CommonModule, FormsModule, ReactiveFormsModule,
    MatButtonModule, MatDialogModule, MatFormFieldModule, MatInputModule,
  ],
})
export class DialogoCorregirCodigoComponent implements OnInit {
  guardando = false;
  cargandoHistorial = false;
  error: string | null = null;
  historial: EventoCorreccionCodigo[] = [];

  readonly form = this.fb.group({
    codigo_nuevo: ['', [Validators.required, Validators.maxLength(50)]],
    motivo: ['', [Validators.required, Validators.minLength(10), Validators.maxLength(500)]],
  });

  constructor(
    private fb: FormBuilder,
    private inventarioService: InventarioService,
    private dialogRef: MatDialogRef<DialogoCorregirCodigoComponent>,
    @Inject(MAT_DIALOG_DATA) public articulo: Inventario,
  ) {}

  ngOnInit(): void {
    this.cargandoHistorial = true;
    this.inventarioService.obtenerHistorialCodigos(this.articulo.id).subscribe({
      next: (eventos) => {
        this.historial = eventos as EventoCorreccionCodigo[];
        this.cargandoHistorial = false;
      },
      error: () => {
        this.cargandoHistorial = false;
        this.error = 'No se pudo consultar el historial. No se realizaron cambios.';
      },
    });
  }

  guardar(): void {
    if (this.guardando || this.cargandoHistorial || this.error) {
      return;
    }

    const codigoNuevo = String(this.form.value.codigo_nuevo ?? '').trim().toUpperCase();
    const codigoAnterior = String(this.articulo.codigo_interno ?? '').trim().toUpperCase();
    const motivo = String(this.form.value.motivo ?? '').trim();

    if (this.form.invalid || !codigoNuevo || codigoNuevo === codigoAnterior || motivo.length < 10) {
      this.form.markAllAsTouched();
      this.error = 'Ingresa un código diferente y un motivo de al menos 10 caracteres.';
      return;
    }

    this.error = null;
    this.guardando = true;
    this.inventarioService.corregirCodigoInterno(this.articulo.id, {
      codigo_anterior: codigoAnterior,
      codigo_nuevo: codigoNuevo,
      motivo,
    }).subscribe({
      next: () => {
        this.guardando = false;
        this.dialogRef.close({ status: 'corregido' });
      },
      error: (err) => {
        this.guardando = false;
        this.error = err?.error?.error || err?.error?.detail ||
          'No se pudo corregir el código. No se modificaron existencias.';
      },
    });
  }

  cancelar(): void {
    if (!this.guardando) {
      this.dialogRef.close(null);
    }
  }
}
