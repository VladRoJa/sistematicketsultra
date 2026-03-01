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

  // TODO(F4.3): cargar desde /api/sucursales
  sucursales: SucursalOption[] = [
    { id: 1, nombre: 'Sucursal 1' },
    { id: 2, nombre: 'Sucursal 2' },
    { id: 3, nombre: 'Sucursal 3' },
  ];

  // TODO(F4.3): seleccionar usuario desde UI / route param
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

  get selectedIds(): number[] {
    return (this.form.value.sucursales_ids ?? []) as number[];
  }

  isSucursalSeleccionada(id: number): boolean {
    return this.selectedIds.includes(id);
  }

  toggleSucursal(id: number): void {
    const next = this.isSucursalSeleccionada(id)
      ? this.selectedIds.filter(x => x !== id)
      : [...this.selectedIds, id];

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

    this.adminUsuariosService.actualizarSucursalesDeUsuario(this.userId, {
      sucursales_ids: this.selectedIds,
    }).subscribe({
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