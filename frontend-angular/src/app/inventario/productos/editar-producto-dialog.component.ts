// src/app/inventario/productos/editar-producto-dialog.component.ts

import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

@Component({
  selector: 'app-editar-inventario-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  templateUrl: './editar-inventario-dialog.component.html',
})
export class EditarInventarioDialogComponent {
  form: FormGroup;

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<EditarInventarioDialogComponent>,
    private http: HttpClient,
    @Inject(MAT_DIALOG_DATA) public data: any
  ) {
    const inventario = data.inventario;

    this.form = this.fb.group({
      nombre:       [inventario.nombre, Validators.required],
      descripcion:  [inventario.descripcion],
      tipo:         [inventario.tipo, Validators.required],
      marca:        [inventario.marca],
      proveedor:    [inventario.proveedor],
      categoria:    [inventario.categoria, Validators.required],
      unidad:       [inventario.unidad, Validators.required],
      stock_actual: [inventario.stock_actual, [Validators.required, Validators.min(0)]],
      sucursal_id:  [inventario.sucursal_id, Validators.required]
      // Agrega más campos aquí si tu modelo lo requiere
    });
  }

  guardar(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const inventario = this.data.inventario;
    const datosActualizados = { ...this.form.value };

    const token = localStorage.getItem('token');
    if (!token) return alert("No autorizado");

    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.put(`${environment.apiUrl}/inventario/${inventario.id}`, datosActualizados, { headers })
      .subscribe({
        next: () => {
          alert("Inventario actualizado correctamente");
          this.dialogRef.close('actualizado');
        },
        error: (err) => {
          console.error("Error al actualizar inventario", err);
          alert("No se pudo actualizar el inventario");
        }
      });
  }

  cancelar(): void {
    this.dialogRef.close(null);
  }

  eliminarInventario(): void {
    const confirmar = confirm("¿Estás seguro que deseas eliminar este registro de inventario?");
    if (!confirmar) return;

    const token = localStorage.getItem('token');
    if (!token) {
      alert("No autorizado");
      return;
    }

    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    this.http.delete(`${environment.apiUrl}/inventario/${this.data.inventario.id}`, { headers })
      .subscribe({
        next: () => {
          alert("Inventario eliminado correctamente");
          this.dialogRef.close('eliminado');
        },
        error: (err) => {
          console.error('Error al eliminar inventario', err);
          alert("No se pudo eliminar el inventario");
        }
      });
  }
}
