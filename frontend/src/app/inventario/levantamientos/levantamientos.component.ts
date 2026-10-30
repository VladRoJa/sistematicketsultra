import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { InventarioService } from '../../services/inventario.service';
import {
  DiagnosticoE4, FilaE4, ImportacionE4, LevantamientoE4,
  LevantamientoResumenE4, LevantamientosE4Service, OrigenCorteE4,
} from './levantamientos.service';

type FiltroFilas = 'TODAS' | 'NO' | 'SIN_REVISAR' | 'HALLAZGOS' | 'OBSERVACIONES';

@Component({
  selector: 'app-inventario-levantamientos',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  templateUrl: './levantamientos.component.html',
  styleUrls: ['./levantamientos.component.css'],
})
export class LevantamientosComponent implements OnInit {
  sucursales: { sucursal_id: number; sucursal: string }[] = [];
  filtroSucursal: number | null = null;
  pagina = 1;
  readonly porPagina = 20;
  total = 0;
  items: LevantamientoResumenE4[] = [];
  cargando = false;
  procesando = false;
  error = '';
  aviso = '';

  creando = false;
  nuevaSucursal: number | null = null;
  nuevoOrigen: OrigenCorteE4 = 'CSV_HISTORICO';
  nuevaFecha = '';
  nuevoResponsable = '';
  csv: File | null = null;
  private cicloKey: string | null = null;

  seleccionado: LevantamientoE4 | null = null;
  versiones: ImportacionE4[] = [];
  importacion: ImportacionE4 | null = null;
  filas: FilaE4[] = [];
  filtroFilas: FiltroFilas = 'TODAS';
  xlsx: File | null = null;
  private importKey: string | null = null;

  constructor(
    private readonly e4: LevantamientosE4Service,
    private readonly inventario: InventarioService,
  ) {}

  ngOnInit(): void {
    this.inventario.listarSucursales().subscribe({
      next: (items: { sucursal_id: number; sucursal: string }[]) => {
        this.sucursales = items.slice().sort((a, b) => a.sucursal.localeCompare(b.sucursal));
      },
      error: () => { this.error = 'No fue posible obtener el catálogo de sucursales.'; },
    });
    this.cargar();
  }

  nombreSucursal(id: number): string {
    const encontrada = this.sucursales.find(s => s.sucursal_id === id);
    return encontrada ? encontrada.sucursal : 'Sucursal ' + id;
  }

  cargar(): void {
    if (this.procesando) return;
    this.cargando = true;
    this.error = '';
    this.e4.listar(this.pagina, this.filtroSucursal).subscribe({
      next: data => {
        this.items = data.items;
        this.total = data.total;
        this.cargando = false;
      },
      error: err => {
        this.cargando = false;
        this.error = this.errorHttp(err, 'No fue posible consultar los levantamientos.');
      },
    });
  }

  cambiarFiltro(): void {
    this.pagina = 1;
    this.cargar();
  }

  cambiarPagina(delta: number): void {
    const nueva = this.pagina + delta;
    if (nueva < 1 || nueva > Math.max(1, Math.ceil(this.total / this.porPagina))) return;
    this.pagina = nueva;
    this.cargar();
  }

  abrirNuevo(): void {
    this.creando = true;
    this.error = '';
    this.aviso = '';
    this.cicloKey = null;
    this.nuevaSucursal = this.filtroSucursal;
  }

  cancelarNuevo(): void {
    if (this.procesando) return;
    this.creando = false;
  }

  seleccionarCsv(event: Event): void {
    this.csv = (event.target as HTMLInputElement).files?.[0] || null;
    this.cicloKey = null;
  }

  cambioCreacion(): void {
    this.cicloKey = null;
  }

  get puedeCrear(): boolean {
    return !this.procesando && this.nuevaSucursal != null && this.nuevaSucursal > 0 &&
      (this.nuevoOrigen !== 'CSV_HISTORICO' || !!this.csv);
  }

  crear(): void {
    if (!this.puedeCrear) return;
    this.procesando = true;
    this.error = '';
    const key = this.cicloKey || crypto.randomUUID();
    this.cicloKey = key;
    this.e4.crear(this.nuevaSucursal!, this.nuevoOrigen, key,
      this.nuevoResponsable, this.nuevaFecha, this.csv).subscribe({
      next: respuesta => {
        this.procesando = false;
        this.creando = false;
        this.csv = null;
        this.cicloKey = null;
        this.aviso = respuesta.replayed
          ? 'Se recuperó el levantamiento existente.'
          : 'Corte registrado. Ya puedes adjuntar el Excel del gerente.';
        this.abrir(respuesta.levantamiento.id);
        this.cargar();
      },
      error: err => {
        this.procesando = false;
        this.error = this.errorHttp(err, 'No se pudo registrar el corte.');
      },
    });
  }

  abrir(id: number): void {
    this.error = '';
    this.importacion = null;
    this.filas = [];
    this.xlsx = null;
    this.e4.detalle(id).subscribe({
      next: data => {
        this.seleccionado = data.levantamiento;
        this.versiones = data.versiones;
        const vigente = data.versiones.find(v => v.id === data.levantamiento.ultima_importacion_id);
        if (vigente) this.abrirVersion(vigente.id);
      },
      error: err => {
        this.error = this.errorHttp(err, 'No se pudo abrir el levantamiento.');
      },
    });
  }

  seleccionarExcel(event: Event): void {
    this.xlsx = (event.target as HTMLInputElement).files?.[0] || null;
    this.importKey = null;
  }

  importar(): void {
    if (!this.seleccionado || !this.xlsx || this.procesando) return;
    this.procesando = true;
    this.error = '';
    const id = this.seleccionado.id;
    const key = this.importKey || crypto.randomUUID();
    this.importKey = key;
    this.e4.importar(id, key, this.xlsx).subscribe({
      next: respuesta => {
        this.procesando = false;
        this.xlsx = null;
        this.importKey = null;
        this.aviso = respuesta.replayed
          ? 'El archivo ya estaba registrado; se conservó su versión.'
          : 'Excel archivado. Consulta los resultados de validación.';
        this.abrir(id);
        this.cargar();
      },
      error: err => {
        this.procesando = false;
        this.error = this.errorHttp(err, 'No fue posible recibir el archivo.');
      },
    });
  }

  abrirVersion(id: number): void {
    if (!this.seleccionado) return;
    this.error = '';
    this.e4.detalleImportacion(this.seleccionado.id, id).subscribe({
      next: data => {
        this.importacion = data.importacion;
        this.filas = data.filas;
        this.filtroFilas = 'TODAS';
      },
      error: err => {
        this.error = this.errorHttp(err, 'No fue posible leer la versión.');
      },
    });
  }

  get filasVisibles(): FilaE4[] {
    if (this.filtroFilas === 'TODAS') return this.filas;
    if (this.filtroFilas === 'HALLAZGOS') return this.filas.filter(f => f.hoja === 'HALLAZGOS');
    if (this.filtroFilas === 'OBSERVACIONES') {
      return this.filas.filter(f => !!f.datos_crudos['observaciones']);
    }
    return this.filas.filter(f => f.hoja === 'APARATOS' && f.respuesta === this.filtroFilas);
  }

  problemasImportacion(): DiagnosticoE4[] {
    return this.importacion?.diagnosticos || [];
  }

  descargar(): void {
    if (!this.seleccionado || !this.importacion) return;
    const archivo = this.importacion;
    this.e4.original(this.seleccionado.id, archivo.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = archivo.filename;
        link.click();
        URL.revokeObjectURL(url);
      },
      error: err => { this.error = this.errorHttp(err, 'No fue posible descargar el original.'); },
    });
  }

  private errorHttp(err: { status?: number; error?: { detail?: string } }, defecto: string): string {
    if (err.error?.detail) return err.error.detail;
    if (err.status === 403) return 'El servidor no autoriza este perfil para E4.';
    return defecto;
  }
}
