// src/app/inventario/movimientos/movimientos.component.ts

import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { FormControl, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatDialog } from '@angular/material/dialog';
import { DialogoRegistrarMovimientoComponent } from './dialogo-registrar-movimiento/dialogo-registrar-movimiento.component';
import { DialogoConfirmacionComponent } from 'src/app/shared/dialogo-confirmacion/dialogo-confirmacion.component';
import { MatIconModule } from '@angular/material/icon';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { environment } from 'src/environments/environment';
import { combineLatest, startWith } from 'rxjs';

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
    MatIconModule,
    ReactiveFormsModule,
  ],
  templateUrl: './movimientos.component.html',
  styleUrls: ['./movimientos.component.css']
})
export class MovimientosComponent implements OnInit {
  private http = inject(HttpClient);
  private dialog = inject(MatDialog);

  movimientos: any[] = [];
  movimientosFiltrados: any[] = [];
  inventariosDisponibles: any[] = [];
  usuarios: any[] = [];
  sucursales: any[] = [];

  filtroControl = new FormControl('');
  filtroTipo = new FormControl('');
  filtroSucursal = new FormControl('');
  filtroUsuario = new FormControl('');
  filtroFecha = new FormControl('');

  esAdmin = false;
  loading = false;

  displayedColumns: string[] = [
    'id', 'fecha', 'tipo', 'producto', 'cantidad', 'usuario', 'sucursal', 'observaciones', 'acciones'
  ];

  ngOnInit(): void {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    this.esAdmin = user?.rol === 'ADMINISTRADOR';
    this.cargarMovimientos();
    this.cargarInventarios();
    if (this.esAdmin) this.cargarSucursales();
    this.cargarUsuarios();
    this.configurarFiltros();
  }

  cargarMovimientos(): void {
    this.loading = true;
    this.http.get<any[]>(`${environment.apiUrl}/inventario/movimientos`).subscribe({
      next: data => {
        // Ya NO hagas transformaciones aquí
        this.movimientos = data;
        this.filtrar();
        this.loading = false;
      },
      error: err => {
        mostrarAlertaToast('Error al obtener movimientos', 'error');
        this.loading = false;
      }
    });
  }

  cargarInventarios(): void {
    this.http.get<any[]>(`${environment.apiUrl}/inventario/`).subscribe({
      next: data => this.inventariosDisponibles = data,
      error: err => {}
    });
  }

  cargarSucursales() {
    this.http.get<any[]>(`${environment.apiUrl}/inventario/sucursales`).subscribe({
      next: data => this.sucursales = data,
      error: err => {}
    });
  }

  cargarUsuarios() {
    this.http.get<any[]>(`${environment.apiUrl}/usuarios`).subscribe({
      next: data => this.usuarios = data,
      error: err => {}
    });
  }

  configurarFiltros() {
    combineLatest([
      this.filtroControl.valueChanges.pipe(startWith('')),
      this.filtroTipo.valueChanges.pipe(startWith('')),
      this.filtroSucursal.valueChanges.pipe(startWith('')),
      this.filtroUsuario.valueChanges.pipe(startWith('')),
      this.filtroFecha.valueChanges.pipe(startWith('')),
    ]).subscribe(([texto, tipo, sucursal, usuario, fecha]) => {
      this.filtrar(texto, tipo, sucursal, usuario, fecha);
    });
  }

  filtrar(texto: string = '', tipo: string = '', sucursal: string = '', usuario: string = '', fecha: string = '') {
    texto = (texto || '').toLowerCase();
    this.movimientosFiltrados = this.movimientos.filter(mov => {
      // Buscar texto en nombre de los productos del movimiento
      const productoNombres = (mov.inventarios || []).map((p: any) => this.getNombreProducto(p).toLowerCase()).join(' ');
      const coincideTexto = !texto || productoNombres.includes(texto) ||
        (this.obtenerNombreUsuario(mov.usuario, mov.usuario_id).toLowerCase().includes(texto)) ||
        (this.obtenerNombreSucursal(mov.sucursal, mov.sucursal_id).toLowerCase().includes(texto)) ||
        (mov.tipo || '').toLowerCase().includes(texto) ||
        (mov.observaciones || '').toLowerCase().includes(texto);

      const coincideTipo = !tipo || mov.tipo === tipo;
      const coincideSucursal = !sucursal || mov.sucursal_id == sucursal;
      const coincideUsuario = !usuario || mov.usuario_id == usuario;
      const coincideFecha = !fecha || (mov.fecha && mov.fecha.startsWith(fecha));

      return coincideTexto && coincideTipo && coincideSucursal && coincideUsuario && coincideFecha;
    });
  }

  abrirDialogoMovimiento() {
    const dialogRef = this.dialog.open(DialogoRegistrarMovimientoComponent, {
      width: '800px',
      disableClose: false,
      data: {
        inventariosDisponibles: this.inventariosDisponibles
      }
    });

    dialogRef.afterClosed().subscribe(resultado => {
      if (resultado === 'ok') {
        this.cargarMovimientos();
        mostrarAlertaToast('✅ Movimiento registrado correctamente.');
      }
    });
  }

  eliminarMovimiento(id: number): void {
    const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
      data: {
        titulo: '¿Eliminar movimiento?',
        mensaje: 'Esta acción no se puede deshacer. ¿Seguro que quieres eliminar este movimiento?',
        textoAceptar: 'Eliminar',
        textoCancelar: 'Cancelar'
      }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        const token = localStorage.getItem('token');
        this.http.delete(`${environment.apiUrl}/inventario/movimientos/${id}`, {
          headers: { Authorization: `Bearer ${token}` }
        }).subscribe({
          next: () => {
            this.cargarMovimientos();
            mostrarAlertaToast('✅ Movimiento eliminado correctamente.', 'success');
          },
          error: err => {
            mostrarAlertaToast('❌ Error al eliminar movimiento.', 'error');
          }
        });
      }
    });
  }

  obtenerNombreUsuario(usuario: any, usuario_id: any): string {
    if (typeof usuario === 'string') return usuario;
    if (usuario?.username) return usuario.username;
    const usr = this.usuarios.find(u => u.id == usuario_id);
    return usr ? usr.username : usuario_id || '-';
  }

  obtenerNombreSucursal(sucursal: any, sucursal_id: any): string {
    if (typeof sucursal === 'string') return sucursal;
    if (sucursal?.nombre) return sucursal.nombre;
    if (sucursal?.sucursal) return sucursal.sucursal;
    const suc = this.sucursales.find(s => s.sucursal_id == sucursal_id);
    return suc ? suc.sucursal : sucursal_id || '-';
  }

  getNombreProducto(p: any): string {
    const prod = this.inventariosDisponibles.find(i =>
      i.id == p.inventario_id || i.id == p.id
    );
    return prod ? prod.nombre : 'Sin nombre';
  }

  getMarcaProducto(p: any): string {
  const prod = this.inventariosDisponibles.find(i =>
    i.id == p.inventario_id || i.id == p.id
  );
  return prod ? prod.marca || '-' : '-';
}

getProveedorProducto(p: any): string {
  const prod = this.inventariosDisponibles.find(i =>
    i.id == p.inventario_id || i.id == p.id
  );
  return prod ? prod.proveedor || '-' : '-';
}

getCategoriaProducto(p: any): string {
  const prod = this.inventariosDisponibles.find(i =>
    i.id == p.inventario_id || i.id == p.id
  );
  return prod ? prod.categoria || '-' : '-';
}

getDescripcionLarga(p: any): string {
  const prod = this.inventariosDisponibles.find(i =>
    i.id == p.inventario_id || i.id == p.id
  );
  if (!prod) return '';
  // Usa el mismo formato que en tu backend
  return `${prod.nombre || ''} — ${prod.marca || ''} · ${prod.proveedor || ''} · ${prod.categoria || ''}`;
}
}
