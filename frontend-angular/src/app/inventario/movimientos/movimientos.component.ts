//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\movimientos\movimientos.component.ts

import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatDialog } from '@angular/material/dialog';
import { DialogoRegistrarMovimientoComponent } from './dialogo-registrar-movimiento/dialogo-registrar-movimiento.component';
import { MatIconModule } from '@angular/material/icon';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { mostrarAlertaStockInsuficiente } from 'src/app/utils/alertas';

@Component({
  selector: 'app-movimientos',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatTableModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
    MatIconModule
  ],
  templateUrl: './movimientos.component.html',
  styleUrls: ['./movimientos.component.css']
})
export class MovimientosComponent implements OnInit {
  private http = inject(HttpClient);
  private dialog = inject(MatDialog);

  movimientos: any[] = [];
  productosDisponibles: any[] = [];

  nuevoMovimiento = {
    tipo_movimiento: 'entrada',
    sucursal_id: 1,
    usuario_id: 1,
    observaciones: '',
    productos: [{ producto_id: '', cantidad: 1, unidad_medida: '' }]
  };

  reiniciarFormulario(): void {
    this.nuevoMovimiento = {
      tipo_movimiento: 'entrada',
      sucursal_id: null,
      usuario_id: null,
      observaciones: '',
      productos: [{
        producto_id: '',
        cantidad: 1,
        unidad_medida: ''
      }]
    };
  }

  ngOnInit(): void {
    this.cargarMovimientos();
    this.cargarProductos();
  }

  cargarMovimientos(): void {
    this.http.get<any[]>('http://localhost:5000/api/inventario/movimientos').subscribe({
      next: data => this.movimientos = data,
      error: err => console.error('Error al obtener movimientos', err)
    });
  }

  cargarProductos(): void {
    this.http.get<any[]>('http://localhost:5000/api/inventario/productos').subscribe({
      next: data => this.productosDisponibles = data,
      error: err => console.error('Error al obtener productos', err)
    });
  }

  agregarProductoCampo(): void {
    this.nuevoMovimiento.productos.push({ producto_id: '', cantidad: 1, unidad_medida: '' });
  }

  eliminarProductoCampo(index: number): void {
    this.nuevoMovimiento.productos.splice(index, 1);
  }

  registrarMovimiento(): void {
    const token = localStorage.getItem('token');
    if (!token) return alert('No autorizado');

    const user = JSON.parse(localStorage.getItem('user') || '{}');
    this.nuevoMovimiento.sucursal_id = user.id_sucursal;
    this.nuevoMovimiento.usuario_id = user.id;

    this.http.post('http://localhost:5000/api/inventario/movimientos', this.nuevoMovimiento, {
      headers: { Authorization: `Bearer ${token}` }
    }).subscribe({
      next: () => {
        this.cargarMovimientos();
        this.reiniciarFormulario();
      },
      error: err => {
        console.error('Error al registrar movimiento', err);
        const mensaje = err?.error?.error || '';

        if (mensaje.includes('Stock insuficiente')) {
          const productoFallidoId = this.nuevoMovimiento.productos[0].producto_id;
          const producto = this.productosDisponibles.find(p => p.id == productoFallidoId);
          const nombre = producto?.nombre || 'el producto seleccionado';

          mostrarAlertaStockInsuficiente(nombre);
        } else {
          mostrarAlertaToast('❌ Error al registrar movimiento.', 'error');
        }
      }
    });
  }

  eliminarMovimiento(id: number): void {
    const token = localStorage.getItem('token');
    if (!token) return alert('No autorizado');

    this.http.delete(`http://localhost:5000/api/inventario/movimientos/${id}`, {
      headers: { Authorization: `Bearer ${token}` }
    }).subscribe({
      next: () => this.cargarMovimientos(),
      error: err => {
        console.error('Error al eliminar movimiento', err);
        alert('Error al eliminar movimiento');
      }
    });
  }

  actualizarUnidad(index: number): void {
    const productoId = this.nuevoMovimiento.productos[index].producto_id;
    const producto = this.productosDisponibles.find(p => p.id == productoId);
    this.nuevoMovimiento.productos[index].unidad_medida = producto?.unidad_medida || '';
    this.nuevoMovimiento.productos[index].cantidad = Number(this.nuevoMovimiento.productos[index].cantidad || 0);
  }

  abrirDialogoMovimiento() {
    const dialogRef = this.dialog.open(DialogoRegistrarMovimientoComponent, {
      width: '800px',
      disableClose: false,
      data: {
        productosDisponibles: this.productosDisponibles
      }
    });

    dialogRef.afterClosed().subscribe(resultado => {
      if (resultado === 'ok') {
        this.cargarMovimientos();
        mostrarAlertaToast('✅ Movimiento registrado correctamente.');
      }
    });
  }
}
