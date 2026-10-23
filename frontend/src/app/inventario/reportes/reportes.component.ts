// src/app/inventario/reportes/reportes.component.ts

import { Component, OnDestroy, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterModule } from '@angular/router';
import { Subscription } from 'rxjs';
import { environment } from 'src/environments/environment';
import { mostrarAlertaToast } from 'src/app/utils/alertas';


interface SucursalReporte {
  sucursal_id: number;
  sucursal: string;
}

interface CategoriaReporte {
  categoria: string;
  referencias_con_stock: number;
}

interface CategoriaVista extends CategoriaReporte {
  porcentaje: number;
  participacion: number;
  claseColor: string;
}

interface SucursalStock extends SucursalReporte {
  referencias_con_stock: number;
  referencias_sin_stock: number;
}

interface MovimientoReciente {
  movimiento_id: number;
  fecha_local: string | null;
  tipo: string;
  estado: 'activo' | 'anulado';
  sucursal_id: number;
  sucursal: string;
  usuario: string;
}

interface ResumenInventario {
  alcance: { sucursal_id: number | null; excluye_demo: boolean };
  periodo: { dias: number; desde: string; hasta: string; zona_horaria: string };
  indicadores: {
    referencias_con_stock: number;
    referencias_sin_stock: number;
    entradas_vigentes_periodo: number;
    salidas_vigentes_periodo: number;
    anulaciones_periodo: number;
  };
  por_sucursal: SucursalStock[];
  por_categoria: CategoriaReporte[];
  movimientos_recientes: MovimientoReciente[];
}

@Component({
  selector: 'app-reportes',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    FormsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    RouterModule,
  ],
  templateUrl: './reportes.component.html',
  styleUrls: ['./reportes.component.css'],
})
export class ReportesComponent implements OnInit, OnDestroy {
  readonly opcionesPeriodo: Array<7 | 30 | 90> = [7, 30, 90];
  sucursales: SucursalReporte[] = [];
  sucursalSeleccionada: number | null = null;
  periodoDias: 7 | 30 | 90 = 30;
  esGlobal = false;
  puedeElegirSucursal = false;
  cargandoResumen = false;
  errorResumen = '';
  resumen: ResumenInventario | null = null;
  categoriasVista: CategoriaVista[] = [];
  sucursalesVista: SucursalStock[] = [];
  busquedaSucursal = '';
  verTodasSucursales = false;
  private peticionResumen?: Subscription;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    let rol = '';
    try {
      const usuario = JSON.parse(localStorage.getItem('user') || '{}');
      rol = String(usuario?.rol || '').trim().toUpperCase();
    } catch {
      rol = '';
    }

    // La API conserva la autoridad sobre el alcance; esto solo controla el selector.
    this.esGlobal = ['ADMIN', 'ADMINISTRADOR', 'SUPER_ADMIN',
      'MANTENIMIENTO', 'SISTEMAS', 'TECNICO'].includes(rol);
    this.puedeElegirSucursal = this.esGlobal;
    if (this.esGlobal) this.cargarSucursales();
    this.cargarResumen();
  }

  ngOnDestroy(): void {
    this.peticionResumen?.unsubscribe();
  }

  cargarSucursales(): void {
    const token = localStorage.getItem('token');
    if (!token) return;
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });
    this.http.get<SucursalReporte[]>(`${environment.apiUrl}/inventario/sucursales`, { headers }).subscribe({
      next: data => {
        this.sucursales = Array.isArray(data) ? data : [];
      },
      error: () => {
        this.sucursales = [];
        mostrarAlertaToast('No se pudo cargar el selector de sucursales', 'error');
      },
    });
  }

  cambiarSucursal(sucursalId: number | null): void {
    this.sucursalSeleccionada = sucursalId;
    this.cargarResumen();
  }

  cambiarPeriodo(dias: 7 | 30 | 90): void {
    this.periodoDias = dias;
    this.cargarResumen();
  }

  cambiarBusquedaSucursal(texto: string): void {
    this.busquedaSucursal = texto;
  }

  alternarSucursales(): void {
    this.verTodasSucursales = !this.verTodasSucursales;
  }

  seleccionarSucursalDesdeRanking(id: number): void {
    this.cambiarSucursal(id);
  }

  get sucursalesFiltradas(): SucursalStock[] {
    const termino = this.busquedaSucursal.trim().toLocaleLowerCase('es');
    const resultado = termino
      ? this.sucursalesVista.filter(s => s.sucursal.toLocaleLowerCase('es').includes(termino))
      : this.sucursalesVista;
    return this.verTodasSucursales || termino ? resultado : resultado.slice(0, 8);
  }

  get sucursalesOcultas(): number {
    if (this.busquedaSucursal.trim() || this.verTodasSucursales) return 0;
    return Math.max(0, this.sucursalesVista.length - 8);
  }

  anchoSucursal(cantidad: number): number {
    const maximo = this.sucursalesVista[0]?.referencias_con_stock || 0;
    return maximo > 0 ? Math.max(0, Math.min(100, cantidad / maximo * 100)) : 0;
  }

  get etiquetaListadoSucursales(): string {
    return this.verTodasSucursales
      ? 'Mostrar principales'
      : 'Ver todas las sucursales (' + this.sucursalesVista.length + ')';
  }

  get iconoListadoSucursales(): string {
    return this.verTodasSucursales ? 'expand_less' : 'expand_more';
  }

  posicionEnRanking(sucursalId: number): number {
    return this.sucursalesVista.findIndex(s => s.sucursal_id === sucursalId) + 1;
  }

  movimientoEsSalida(tipo: string): boolean {
    return tipo === 'salida';
  }

  iconoMovimiento(tipo: string): string {
    return this.movimientoEsSalida(tipo) ? 'north_east' : 'south_west';
  }

  movimientoAnulado(estado: string): boolean {
    return estado === 'anulado';
  }

  etiquetaEstadoMovimiento(estado: string): string {
    return this.movimientoAnulado(estado) ? 'Anulado' : 'Activo';
  }

  get movimientosVigentes(): number {
    const i = this.resumen?.indicadores;
    return i ? i.entradas_vigentes_periodo + i.salidas_vigentes_periodo : 0;
  }

  cargarResumen(): void {
    this.peticionResumen?.unsubscribe();
    this.errorResumen = '';
    this.resumen = null;
    this.categoriasVista = [];
    this.sucursalesVista = [];
    this.busquedaSucursal = '';
    this.verTodasSucursales = false;

    const token = localStorage.getItem('token');
    if (!token) {
      this.cargandoResumen = false;
      this.errorResumen = 'Tu sesión no está disponible. Vuelve a iniciar sesión.';
      return;
    }

    this.cargandoResumen = true;
    const params: Record<string, string> = { periodo_dias: String(this.periodoDias) };
    if (this.sucursalSeleccionada !== null) {
      params['sucursal_id'] = String(this.sucursalSeleccionada);
    }
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });
    this.peticionResumen = this.http.get<ResumenInventario>(
      `${environment.apiUrl}/inventario/reportes/resumen`,
      { headers, params },
    ).subscribe({
      next: data => {
        this.resumen = data;
        this.categoriasVista = this.prepararCategorias(data.por_categoria);
        this.sucursalesVista = [...data.por_sucursal].sort(
          (a, b) => b.referencias_con_stock - a.referencias_con_stock ||
            a.sucursal.localeCompare(b.sucursal)
        );
        // El propio resumen define las sucursales visibles para usuarios acotados.
        if (!this.esGlobal && this.sucursales.length === 0 && this.sucursalSeleccionada === null) {
          this.sucursales = data.por_sucursal.map(
            ({ sucursal_id, sucursal }) => ({ sucursal_id, sucursal })
          );
          this.puedeElegirSucursal = this.sucursales.length > 1;
        }
        this.cargandoResumen = false;
      },
      error: err => {
        this.cargandoResumen = false;
        const detalle = err?.error?.detail || err?.error?.error;
        this.errorResumen = err?.status === 403
          ? 'No tienes permiso para consultar esta sucursal.'
          : (detalle || 'No se pudo cargar el resumen de Inventario.');
      },
    });
  }

  private prepararCategorias(categorias: CategoriaReporte[]): CategoriaVista[] {
    const total = categorias.reduce((suma, cat) => suma + cat.referencias_con_stock, 0);
    return categorias.map((cat, indice) => ({
      ...cat,
      porcentaje: total ? Math.round(cat.referencias_con_stock / total * 100) : 0,
      participacion: total ? cat.referencias_con_stock / total * 100 : 0,
      claseColor: 'category-' + (indice % 6),
    }));
  }

  etiquetaTipo(tipo: string): string {
    if (tipo === 'entrada') return 'Entrada';
    if (tipo === 'salida') return 'Salida';
    return tipo || 'Movimiento';
  }

  formatearFechaLocal(valor: string | null): string {
    if (!valor || valor.length < 16) return '—';
    const [fecha, hora] = valor.split('T');
    const [anio, mes, dia] = fecha.split('-');
    return `${dia}/${mes}/${anio} ${hora.slice(0, 5)}`;
  }

  descargarInventario() {
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('No autorizado', 'error');
      return;
    }
    let url = `${environment.apiUrl}/reportes/exportar-inventario`;
    if (this.sucursalSeleccionada) {
      url += `?sucursal_id=${this.sucursalSeleccionada}`;
    }
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.get(url, { headers, responseType: 'blob', observe: 'response' }).subscribe({
      next: (response) => {
        if (!response.body) {
          mostrarAlertaToast('El reporte se recibió vacío.', 'error');
          return;
        }

        // El backend determina el alcance real y el nombre del archivo.
        const disposition = response.headers.get('Content-Disposition') || '';
        const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
          || 'reporte_inventario.xlsx';
        const objectUrl = window.URL.createObjectURL(response.body);
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = filename;
        a.click();
        window.URL.revokeObjectURL(objectUrl);
        mostrarAlertaToast('Inventario exportado.');
      },
      error: () => mostrarAlertaToast('Error al exportar inventario', 'error')
    });
  }

  descargarMovimientos() {
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('No autorizado', 'error');
      return;
    }
    let url = `${environment.apiUrl}/reportes/exportar-movimientos`;
    if (this.sucursalSeleccionada) {
      url += `?sucursal_id=${this.sucursalSeleccionada}`;
    }
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.get(url, { headers, responseType: 'blob', observe: 'response' }).subscribe({
      next: (response) => {
        if (!response.body) {
          mostrarAlertaToast('El reporte se recibió vacío.', 'error');
          return;
        }
        const disposition = response.headers.get('Content-Disposition') || '';
        const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
          || 'reporte_movimientos.xlsx';
        const objectUrl = window.URL.createObjectURL(response.body);
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = filename;
        a.click();
        window.URL.revokeObjectURL(objectUrl);
        mostrarAlertaToast('Movimientos exportados.');
      },
      error: () => mostrarAlertaToast('Error al exportar movimientos', 'error')
    });
  }
}
