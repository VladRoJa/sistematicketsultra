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
import { DialogoDetalleMovimientoComponent } from './dialogo-detalle-movimiento/dialogo-detalle-movimiento.component';
import {
  MovimientoInventarioVista,
  cantidadArticulosMovimiento,
  primerArticuloMovimiento,
} from './movimientos-vista.helper';
import { DialogoAnularMovimientoComponent } from './dialogo-anular-movimiento/dialogo-anular-movimiento.component';
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
  cargandoCatalogo = false;
  errorCatalogo = false;
  anulandoMovimientoId: number | null = null;

  displayedColumns: string[] = [
    'id', 'fecha', 'tipo', 'articulos', 'usuario', 'sucursal', 'observaciones', 'acciones'
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

  cargarInventarios(abrirAlCompletar = false): void {
    if (this.cargandoCatalogo) return;
    this.cargandoCatalogo = true;
    this.errorCatalogo = false;
    this.http.get<any[]>(`${environment.apiUrl}/inventario/`).subscribe({
      next: data => {
        this.cargandoCatalogo = false;
        this.inventariosDisponibles = Array.isArray(data) ? data : [];
        this.errorCatalogo = this.inventariosDisponibles.length === 0;
        if (this.errorCatalogo) {
          mostrarAlertaToast('El catálogo de inventario está vacío. No es posible registrar un movimiento.', 'error');
          return;
        }
        if (abrirAlCompletar) this.abrirDialogoMovimiento();
      },
      error: err => {
        this.cargandoCatalogo = false;
        this.errorCatalogo = true;
        this.inventariosDisponibles = [];
        const detalle = err?.error?.detail || err?.error?.error || `HTTP ${err?.status || 'sin respuesta'}`;
        mostrarAlertaToast(`No se pudo cargar el catálogo de inventario: ${detalle}`, 'error');
      }
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

  cantidadArticulos(mov: MovimientoInventarioVista): number {
    return cantidadArticulosMovimiento(mov);
  }

  primerArticulo(mov: MovimientoInventarioVista): string {
    return primerArticuloMovimiento(mov, this.inventariosDisponibles);
  }

  abrirDetalleMovimiento(mov: MovimientoInventarioVista): void {
    this.dialog.open(DialogoDetalleMovimientoComponent, {
      width: '1100px',
      maxWidth: '96vw',
      maxHeight: '90vh',
      data: {
        movimiento: mov,
        catalogo: this.inventariosDisponibles,
      },
    });
  }

  abrirDialogoMovimiento() {
    // La selección depende del catálogo completo; jamás abrir vacío.
    if (this.cargandoCatalogo) {
      mostrarAlertaToast('El catálogo aún está cargando. Intenta de nuevo.', 'warning');
      return;
    }
    if (!this.inventariosDisponibles.length || this.errorCatalogo) {
      this.cargarInventarios(true);
      return;
    }

    const dialogRef = this.dialog.open(DialogoRegistrarMovimientoComponent, {
      width: '900px',
      maxWidth: '96vw',
      maxHeight: '92vh',
      autoFocus: false,
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

  anularMovimiento(mov: MovimientoInventarioVista): void {
    if (mov.anulado || this.anulandoMovimientoId !== null) return;

    const dialogRef = this.dialog.open(DialogoAnularMovimientoComponent, {
      width: '560px',
      maxWidth: '96vw',
      autoFocus: false,
      data: mov,
    });

    dialogRef.afterClosed().subscribe((motivo: string | null) => {
      if (!motivo || mov.anulado || this.anulandoMovimientoId !== null) return;

      const token = localStorage.getItem('token');
      if (!token) {
        mostrarAlertaToast('Sesión no autorizada. No se anuló el movimiento.', 'error');
        return;
      }

      this.anulandoMovimientoId = mov.id;
      this.http.post(`${environment.apiUrl}/inventario/movimientos/${mov.id}/anular`,
        { motivo }, {
          headers: { Authorization: `Bearer ${token}` },
        }).subscribe({
          next: () => {
            this.anulandoMovimientoId = null;
            this.cargarMovimientos();
            mostrarAlertaToast('Movimiento anulado. Historial conservado.', 'success');
          },
          error: err => {
            this.anulandoMovimientoId = null;
            const detalle = err?.error?.detail || err?.error?.error ||
              'No se pudo anular el movimiento.';
            mostrarAlertaToast(detalle, 'error');
          },
        });
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
