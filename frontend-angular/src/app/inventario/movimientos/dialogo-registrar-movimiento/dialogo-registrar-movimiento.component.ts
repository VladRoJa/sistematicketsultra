//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\movimientos\dialogo-registrar-movimiento\dialogo-registrar-movimiento.component.ts

import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { mostrarAlertaToast, mostrarAlertaStockInsuficiente } from 'src/app/utils/alertas';

@Component({
  standalone: true,
  selector: 'app-dialogo-registrar-movimiento',
  templateUrl: './dialogo-registrar-movimiento.component.html',
  styleUrls: ['./dialogo-registrar-movimiento.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule
  ]
})
export class DialogoRegistrarMovimientoComponent {
  productosDisponibles: any[] = [];

  nuevoMovimiento = {
    tipo_movimiento: 'entrada',
    observaciones: '',
    productos: [
      { producto_id: '', unidad_medida: '', cantidad: 1 }
    ]
  };

  constructor(
    private dialogRef: MatDialogRef<DialogoRegistrarMovimientoComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private http: HttpClient
  ) {
    this.productosDisponibles = data.productosDisponibles || [];
  }

  actualizarUnidad(index: number) {
    const producto = this.productosDisponibles.find(
      p => p.id === Number(this.nuevoMovimiento.productos[index].producto_id)
    );
    if (producto) {
      this.nuevoMovimiento.productos[index].unidad_medida = producto.unidad_medida || '';
    }
  }

  agregarProductoCampo() {
    this.nuevoMovimiento.productos.push({ producto_id: '', unidad_medida: '', cantidad: 1 });
  }

  eliminarProductoCampo(index: number) {
    this.nuevoMovimiento.productos.splice(index, 1);
  }

  registrarMovimiento() {
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('🔒 No autorizado.', 'error');
      return;
    }
  
    const user = JSON.parse(localStorage.getItem('user') || '{}');
  
    // ✅ Validación de stock en frontend
    for (const item of this.nuevoMovimiento.productos) {
      const producto = this.productosDisponibles.find(p => p.id == item.producto_id);
      const stockDisponible = producto?.stock || producto?.existencia || 0;
  
      if (
        this.nuevoMovimiento.tipo_movimiento === 'salida' &&
        item.cantidad > stockDisponible
      ) {
        mostrarAlertaStockInsuficiente(producto?.nombre || 'el producto seleccionado');
        return;
      }
    }
  
    const movimientoAEnviar = {
      ...this.nuevoMovimiento,
      sucursal_id: user.id_sucursal,
      usuario_id: user.id
    };
  
    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
  
    this.http.post('http://localhost:5000/api/inventario/movimientos', movimientoAEnviar, { headers }).subscribe({
      next: () => {
        console.log('✅ Movimiento registrado');
        this.dialogRef.close('ok');
      },
      error: (err) => {
        const mensaje = err?.error?.error || '';
  
        if (!mensaje.includes('Stock insuficiente')) {
          console.error('❌ Error al registrar movimiento', err);
          mostrarAlertaToast('❌ Error al registrar movimiento.', 'error');
        }
      }
    });
  }
  
}
