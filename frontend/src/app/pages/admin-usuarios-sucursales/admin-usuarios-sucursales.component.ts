//frontend\src\app\pages\admin-usuarios-sucursales\admin-usuarios-sucursales.component.ts


import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule } from '@angular/forms';

import { AdminUsuariosService } from '../../services/admin-usuarios.service';

type SucursalOption = { id: number; nombre: string };

@Component({
  selector: 'app-admin-usuarios-sucursales',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './admin-usuarios-sucursales.component.html',
})
export class AdminUsuariosSucursalesComponent implements OnInit {
  form: FormGroup;

  // ✅ por ahora hardcodeamos 3 sucursales para probar UI; en F4.3 lo conectamos a /api/sucursales
  sucursales: SucursalOption[] = [
    { id: 1, nombre: 'Sucursal 1' },
    { id: 2, nombre: 'Sucursal 2' },
    { id: 3, nombre: 'Sucursal 3' },
  ];

  // userId de prueba; en F4.3 lo seleccionas desde UI real
  userId = 1;

  loading = false;
  errorMsg: string | null = null;
  okMsg: string | null = null;

  constructor(
    private fb: FormBuilder,
    private adminUsuariosService: AdminUsuariosService
  ) {
    this.form = this.fb.group({
      sucursales_ids: this.fb.control<number[]>([]),
    });
  }

  ngOnInit(): void {
    this.cargarSucursalesAsignadas();
  }

  isSucursalSeleccionada(id: number): boolean {
    const ids = this.form.value.sucursales_ids ?? [];
    return ids.includes(id);
  }

  toggleSucursal(id: number): void {
    const current: number[] = this.form.value.sucursales_ids ?? [];
    const next = current.includes(id)
      ? current.filter(x => x !== id)
      : [...current, id];

    this.form.patchValue({ sucursales_ids: next });
  }

  cargarSucursalesAsignadas(): void {
    this.loading = true;
    this.errorMsg = null;
    this.okMsg = null;

    this.adminUsuariosService.getSucursalesDeUsuario(this.userId).subscribe({
      next: (resp) => {
        this.form.patchValue({ sucursales_ids: resp.sucursales_ids ?? [] });
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = err?.error?.mensaje ?? 'Error al cargar sucursales del usuario';
      },
    });
  }

  aplicar(): void {
    this.loading = true;
    this.errorMsg = null;
    this.okMsg = null;

    const payload = { sucursales_ids: (this.form.value.sucursales_ids ?? []) as number[] };

    this.adminUsuariosService.actualizarSucursalesDeUsuario(this.userId, payload).subscribe({
      next: (resp) => {
        this.form.patchValue({ sucursales_ids: resp.sucursales_ids ?? [] });
        this.loading = false;
        this.okMsg = 'Cambios guardados';
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = err?.error?.mensaje ?? 'Error al guardar sucursales';
      },
    });
  }
}