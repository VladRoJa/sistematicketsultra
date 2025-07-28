// frontend-angular\src\app\inventario\modales\registrar-movimiento-modal.component.ts


import { Component, Inject, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { HttpClient } from '@angular/common/http';
import { registrarMovimiento } from 'src/app/helpers/inventario/registrar-movimiento.helper';
import { MovimientoPayload } from 'src/app/helpers/inventario/registrar-movimiento.helper';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { obtenerSucursales } from 'src/app/helpers/sucursales/obtener-sucursales.helper';

@Component({
  selector: 'app-registrar-movimiento-modal',
  templateUrl: './registrar-movimiento-modal.component.html',
})
export class RegistrarMovimientoModalComponent implements OnInit {
  form!: FormGroup;
  sucursales: any[] = [];

  constructor(
    private fb: FormBuilder,
    private http: HttpClient,
    private dialogRef: MatDialogRef<RegistrarMovimientoModalComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { equipo: any, tipo?: string, ticket_id?: number }
  ) {}

  ngOnInit(): void {
    this.inicializarFormulario();
    this.cargarSucursales();
  }

  inicializarFormulario(): void {
    this.form = this.fb.group({
      tipo_movimiento: [this.data.tipo || '', Validators.required],
      sucursal_id: [null, Validators.required],
      cantidad: [1, [Validators.required, Validators.min(1)]],
      observaciones: [''],
      unidad_medida: [this.data.equipo?.unidad_medida || 'pieza', Validators.required]
    });
  }

  cargarSucursales(): void {
    obtenerSucursales(this.http).subscribe({
      next: (data: any[]) => this.sucursales = data,
      error: () => mostrarAlertaToast('❌ Error al cargar sucursales')
    });
  }

  guardar(): void {
    if (this.form.invalid) return;

    const usuario_id = parseInt(localStorage.getItem('user_id') || '0');
    if (!usuario_id) return mostrarAlertaToast('❌ Usuario no válido');

    const payload: MovimientoPayload = {
      tipo_movimiento: this.form.value.tipo_movimiento,
      sucursal_id: this.form.value.sucursal_id,
      usuario_id,
      observaciones: this.form.value.observaciones,
      ticket_id: this.data.ticket_id,
      inventarios: [{
        inventario_id: this.data.equipo.id,
        cantidad: this.form.value.cantidad,
        unidad_medida: this.form.value.unidad_medida
      }]
    };

    registrarMovimiento(this.http, payload).subscribe({
      next: (res) => {
        mostrarAlertaToast('✅ Movimiento registrado');
        this.dialogRef.close({ exito: true, data: res });
      },
      error: (err) => {
        console.error(err);
        mostrarAlertaToast('❌ Error al registrar movimiento');
      }
    });
  }

  cancelar(): void {
    this.dialogRef.close();
  }
}
