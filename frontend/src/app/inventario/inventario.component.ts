import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule, MatMenuTrigger } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';

import { SessionService } from '../core/auth/session.service';
import { Inventario } from '../models/inventario.model';
import { InventarioService } from '../services/inventario.service';
import { DialogoConfirmacionComponent } from '../shared/dialogo-confirmacion/dialogo-confirmacion.component';
import {
  FiltroColumna,
  alternarSeleccionTemporal,
  confirmarSeleccion,
  filtrarTabla,
  inicializarFiltros,
  obtenerOpcionesVisibles,
} from 'src/app/utils/tabla-filtros.helper';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { DialogoInventarioComponent } from './dialogo-inventario/dialogo-inventario.component';

const INVENTORY_GLOBAL_WRITE_ROLES = new Set([
  'ADMIN',
  'ADMINISTRADOR',
  'SUPER_ADMIN',
  'MANTENIMIENTO',
  'SISTEMAS',
  'TECNICO',
]);

@Component({
  selector: 'app-inventario',
  standalone: true,
  templateUrl: './inventario.component.html',
  styleUrls: ['./inventario.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatMenuModule,
    MatProgressSpinnerModule,
    MatTableModule,
    DialogoConfirmacionComponent,
    DialogoInventarioComponent,
  ],
})
export class InventarioComponent implements OnInit {
  inventarios: Inventario[] = [];
  inventariosFiltrados: Inventario[] = [];
  filtros: Record<string, FiltroColumna> = {};

  readonly columnasFiltrables = [
    'nombre',
    'descripcion',
    'marca',
    'proveedor',
    'categoria',
    'unidad',
    'grupo_muscular',
    'codigo_interno',
    'subcategoria',
  ];

  readonly etiquetasColumnas: Record<string, string> = {
    nombre: 'Nombre',
    descripcion: 'Descripción',
    marca: 'Marca',
    proveedor: 'Proveedor',
    categoria: 'Categoría',
    unidad: 'Unidad',
    grupo_muscular: 'Grupo muscular',
    codigo_interno: 'Código interno',
    subcategoria: 'Subcategoría',
  };

  readonly camposBusquedaGlobal = [
    'id',
    'tipo',
    'nombre',
    'descripcion',
    'marca',
    'proveedor',
    'categoria',
    'subcategoria',
    'unidad',
    'grupo_muscular',
    'codigo_interno',
  ];

  filtroColumnaActual: string | null = null;
  displayedColumns: string[] = [];

  loading = false;
  archivoProcesando = false;
  error: string | null = null;
  busquedaGlobal = '';
  puedeAdministrarInventario = false;
  totalCategorias = 0;
  totalConCodigo = 0;

  @ViewChild('menuTrigger', { static: false }) menuTrigger?: MatMenuTrigger;
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  constructor(
    private inventarioService: InventarioService,
    private dialog: MatDialog,
    private session: SessionService,
  ) {}

  ngOnInit(): void {
    this.configurarPermisos();
    this.cargarInventario();
  }

  get cantidadFiltrosActivos(): number {
    return this.columnasFiltrables.filter((col) => this.isFilterActive(col)).length;
  }

  get hayFiltrosAplicados(): boolean {
    return this.cantidadFiltrosActivos > 0 || this.busquedaGlobal.trim().length > 0;
  }

  private configurarPermisos(): void {
    const rol = String(this.session.getRol() || '').trim().toUpperCase();
    this.puedeAdministrarInventario = INVENTORY_GLOBAL_WRITE_ROLES.has(rol);
    this.actualizarColumnasVisibles();
  }

  private actualizarColumnasVisibles(): void {
    this.displayedColumns = [
      'id',
      ...this.columnasFiltrables,
      ...(this.puedeAdministrarInventario ? ['acciones'] : []),
    ];
  }

  cargarInventario(): void {
    this.loading = true;
    this.error = null;

    this.inventarioService.obtenerInventario().subscribe({
      next: (data) => {
        const normalizados: Inventario[] = data.map((it: any) => {
          const categoria =
            it?.categoria_inventario?.nombre ??
            it?.categoria_inventario_nombre ??
            it?.categoria ??
            it?.tipo ??
            '';

          const subcategoria =
            it?.categoria_inventario?.subcategoria ??
            it?.subcategoria_inventario ??
            it?.subcategoria ??
            '';

          const unidad = it?.unidad_medida ?? it?.unidad ?? '';

          return {
            ...it,
            categoria,
            subcategoria,
            unidad,
            unidad_medida: it?.unidad_medida ?? unidad,
          };
        });

        this.inventarios = normalizados.sort((a, b) => a.id - b.id);
        this.filtros = inicializarFiltros(
          this.inventarios,
          this.columnasFiltrables,
        );
        this.actualizarResumen();
        this.refrescarVista();
        this.loading = false;
      },
      error: (err) => {
        this.error =
          err?.error?.detail ||
          err?.error?.error ||
          'No se pudo cargar el inventario.';
        this.loading = false;
        console.error('Error al cargar inventario', err);
      },
    });
  }

  private actualizarResumen(): void {
    this.totalCategorias = new Set(
      this.inventarios
        .map((item) => String(item.categoria || '').trim())
        .filter(Boolean),
    ).size;

    this.totalConCodigo = this.inventarios.filter((item) =>
      this.esCodigoInternoValido(item.codigo_interno),
    ).length;
  }

  private esCodigoInternoValido(value: any): boolean {
    const codigo = String(value ?? '').trim().toLowerCase();
    if (!codigo) {
      return false;
    }

    return !new Set(['nan', 'n/a', 'na', 'none', 'null', '-']).has(codigo);
  }

  private normalizarBusqueda(value: any): string {
    return String(value ?? '').trim().toLowerCase();
  }

  private refrescarVista(): void {
    const filtradosPorColumnas = filtrarTabla(this.inventarios, this.filtros);
    const termino = this.normalizarBusqueda(this.busquedaGlobal);

    if (!termino) {
      this.inventariosFiltrados = filtradosPorColumnas;
      return;
    }

    this.inventariosFiltrados = filtradosPorColumnas.filter((item) =>
      this.camposBusquedaGlobal.some((campo) =>
        this.normalizarBusqueda(item[campo]).includes(termino),
      ),
    );
  }

  aplicarBusquedaGlobal(): void {
    this.refrescarVista();
  }

  limpiarBusquedaGlobal(): void {
    if (!this.busquedaGlobal) {
      return;
    }

    this.busquedaGlobal = '';
    this.refrescarVista();
  }

  limpiarTodosLosFiltros(): void {
    this.busquedaGlobal = '';
    this.filtros = inicializarFiltros(
      this.inventarios,
      this.columnasFiltrables,
    );
    this.filtroColumnaActual = null;
    this.refrescarVista();
  }

  obtenerEtiquetaColumna(col: string): string {
    return this.etiquetasColumnas[col] || col;
  }

  mostrarValor(value: any): string {
    const texto = String(value ?? '').trim();
    return texto || '—';
  }

  abrirDialogoAgregar(): void {
    if (!this.puedeAdministrarInventario) {
      return;
    }

    const dialogRef = this.dialog.open(DialogoInventarioComponent, {
      width: '620px',
      maxWidth: '94vw',
      data: { modo: 'crear' },
    });

    dialogRef.afterClosed().subscribe((resultado) => {
      if (resultado?.status === 'creado') {
        this.cargarInventario();
        mostrarAlertaToast('Inventario agregado correctamente.');
      }
    });
  }

  abrirDialogoEditar(item: Inventario): void {
    if (!this.puedeAdministrarInventario) {
      return;
    }

    const dialogRef = this.dialog.open(DialogoInventarioComponent, {
      width: '620px',
      maxWidth: '94vw',
      data: { modo: 'editar', item },
    });

    dialogRef.afterClosed().subscribe((resultado) => {
      if (resultado?.status === 'actualizado') {
        this.cargarInventario();
        mostrarAlertaToast('Inventario actualizado correctamente.');
      }
    });
  }

  eliminarInventario(id: number): void {
    if (!this.puedeAdministrarInventario) {
      return;
    }

    const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
      data: {
        titulo: 'Eliminar inventario',
        mensaje: '¿Seguro que quieres eliminar este registro?',
        textoAceptar: 'Sí, eliminar',
        textoCancelar: 'Cancelar',
      },
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (!result) {
        return;
      }

      this.loading = true;
      this.inventarioService.eliminarInventario(id).subscribe({
        next: () => {
          mostrarAlertaToast('Inventario eliminado correctamente.');
          this.cargarInventario();
        },
        error: (err) => {
          let mensaje =
            err?.error?.detail ||
            err?.error?.error ||
            'No se pudo eliminar el inventario.';

          if (mensaje.includes('movimientos registrados')) {
            mensaje =
              'No puedes eliminar este inventario porque tiene movimientos asociados.';
          }

          mostrarAlertaToast(mensaje, 'error');
          this.loading = false;
          console.error('Error al eliminar inventario', err);
        },
      });
    });
  }

  abrirMenuFiltro(col: string): void {
    this.filtroColumnaActual = col;
  }

  buscar(col: string, texto: string): void {
    this.filtros[col].texto = texto;
  }

  seleccionarTodo(col: string, valor: boolean): void {
    alternarSeleccionTemporal(this.filtros[col], valor);
  }

  alternarSeleccionIndividual(col: string, i: number, valor: boolean): void {
    this.filtros[col].temporales[i].seleccionado = valor;
  }

  aplicarFiltro(col: string): void {
    confirmarSeleccion(this.filtros[col]);
    this.inventariosFiltrados = filtrarTabla(this.inventarios, this.filtros);
    this.actualizarOpcionesDeFiltros();
    this.refrescarVista();
    this.menuTrigger?.closeMenu();
  }

  limpiarFiltro(col: string): void {
    this.filtros[col].opciones.forEach((op) => (op.seleccionado = true));
    this.filtros[col].texto = '';
    this.filtros[col].temporales = this.filtros[col].opciones.map((op) => ({
      ...op,
    }));
    this.inventariosFiltrados = filtrarTabla(this.inventarios, this.filtros);
    this.actualizarOpcionesDeFiltros();
    this.refrescarVista();
    this.menuTrigger?.closeMenu();
  }

  isTodoSeleccionado(col: string): boolean {
    const visibles = obtenerOpcionesVisibles(this.filtros[col]);
    return visibles.length > 0 && visibles.every((item) => item.seleccionado);
  }

  obtenerOpcionesVisibles(filtro: FiltroColumna) {
    return obtenerOpcionesVisibles(filtro);
  }

  isFilterActive(col: string): boolean {
    return Boolean(
      this.filtros[col]?.opciones.some((op) => !op.seleccionado),
    );
  }

  actualizarOpcionesDeFiltros(): void {
    for (const col of this.columnasFiltrables) {
      const valoresUnicos = Array.from(
        new Set(
          this.inventariosFiltrados
            .map((row) => String(row[col] ?? ''))
            .filter((value) => value !== ''),
        ),
      );

      this.filtros[col].opciones = valoresUnicos.map((valor) => {
        const existente = this.filtros[col].opciones.find(
          (op) => op.valor === valor,
        );
        return {
          valor,
          seleccionado: existente ? existente.seleccionado : true,
        };
      });

      this.filtros[col].temporales = this.filtros[col].opciones.map((op) => ({
        ...op,
      }));

      if (this.filtros[col].texto) {
        const texto = this.filtros[col].texto.toLowerCase();
        this.filtros[col].temporales = this.filtros[col].temporales.filter(
          (op) => op.valor.toLowerCase().includes(texto),
        );
      }
    }
  }

  abrirDialogoImportar(): void {
    if (!this.puedeAdministrarInventario || this.archivoProcesando) {
      return;
    }

    this.fileInput?.nativeElement.click();
  }

  importarExcel(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (
      !this.puedeAdministrarInventario ||
      !input.files ||
      input.files.length === 0
    ) {
      return;
    }

    const archivo = input.files[0];
    this.archivoProcesando = true;

    this.inventarioService.importarInventario(archivo).subscribe({
      next: (res) => {
        mostrarAlertaToast(
          res?.message || 'Inventario importado correctamente.',
        );
        this.archivoProcesando = false;
        input.value = '';
        this.cargarInventario();
      },
      error: (err) => {
        mostrarAlertaToast(
          err?.error?.detail ||
            err?.error?.error ||
            err?.error?.message ||
            'Error al importar inventario.',
          'error',
        );
        this.archivoProcesando = false;
        input.value = '';
      },
    });
  }

  descargarPlantilla(): void {
    if (this.archivoProcesando) {
      return;
    }

    this.archivoProcesando = true;
    this.inventarioService.descargarPlantilla().subscribe({
      next: (blob) => {
        this.descargarBlob(blob, 'plantilla_inventario.xlsx');
        this.archivoProcesando = false;
      },
      error: () => {
        mostrarAlertaToast('No se pudo descargar la plantilla.', 'error');
        this.archivoProcesando = false;
      },
    });
  }

  exportarInventario(): void {
    if (!this.puedeAdministrarInventario || this.archivoProcesando) {
      return;
    }

    this.archivoProcesando = true;
    this.inventarioService.exportarInventario().subscribe({
      next: (blob) => {
        this.descargarBlob(blob, 'inventario.xlsx');
        this.archivoProcesando = false;
      },
      error: (err) => {
        mostrarAlertaToast(
          err?.error?.detail ||
            err?.error?.error ||
            'No se pudo exportar el inventario.',
          'error',
        );
        this.archivoProcesando = false;
      },
    });
  }

  private descargarBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }
}
