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

@Component({
  selector: 'app-editar-producto-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  templateUrl: './editar-producto-dialog.component.html',
})
export class EditarProductoDialogComponent {
  form: FormGroup;

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<EditarProductoDialogComponent>,
    private http: HttpClient,
    @Inject(MAT_DIALOG_DATA) public data: any
  ) {
    const producto = data.producto;

    this.form = this.fb.group({
      nombre: [producto.nombre, Validators.required],
      descripcion: [producto.descripcion],
      unidad_medida: [producto.unidad_medida, Validators.required],
      categoria: [producto.categoria, Validators.required],
      subcategoria: [producto.subcategoria],
    });
  }

  guardar(): void {
    if (this.form.valid) {
      const producto = this.data.producto;
      const datosActualizados = { id: producto.id, ...this.form.value };
    
      const token = localStorage.getItem('token');
      if (!token) return alert("No autorizado");
    
      const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });
    
      this.http.put(`http://localhost:5000/api/inventario/productos/${producto.id}`, datosActualizados, { headers })
        .subscribe({
          next: () => {
            alert("Producto actualizado correctamente");
            this.dialogRef.close('actualizado');
          },
          error: (err) => {
            console.error("Error al actualizar producto", err);
            alert("No se pudo actualizar el producto");
          }
        });
    }
  }
    

  cancelar(): void {
    this.dialogRef.close(null);
  }

  eliminarProducto(): void {
    const confirmar = confirm("¿Estás seguro que deseas eliminar este producto?");
    if (!confirmar) return;

    const token = localStorage.getItem('token');
    if (!token) {
      alert("No autorizado");
      return;
    }

    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    this.http.delete(`http://localhost:5000/api/inventario/productos/${this.data.id}`, { headers })
      .subscribe({
        next: () => {
          alert("Producto eliminado correctamente");
          this.dialogRef.close('eliminado');
        },
        error: (err) => {
          console.error('Error al eliminar producto', err);
          alert("No se pudo eliminar el producto");
        }
      });
  }
}
