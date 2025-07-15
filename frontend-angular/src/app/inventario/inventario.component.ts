import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { InventarioService } from '../services/inventario.service';
import { MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule, MatMenuTrigger } from '@angular/material/menu';
import { DialogoConfirmacionComponent } from '../shared/dialogo-confirmacion/dialogo-confirmacion.component';
import { DialogoInventarioComponent } from './dialogo-inventario/dialogo-inventario.component';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { Inventario } from '../models/inventario.model';
import { MatCheckboxModule } from '@angular/material/checkbox';
import {
  inicializarFiltros,
  obtenerOpcionesVisibles,
  alternarSeleccionTemporal,
  confirmarSeleccion,
  filtrarTabla,
  FiltroColumna
} from 'src/app/utils/tabla-filtros.helper';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-inventario',
  standalone: true,
  templateUrl: './inventario.component.html',
  styleUrls: ['./inventario.component.css'],
  imports: [
    CommonModule,
    MatTableModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatMenuModule,
    MatCheckboxModule, // <-- Necesario para los checkboxes en los filtros
    DialogoConfirmacionComponent,
    DialogoInventarioComponent,
    FormsModule
  ]
})
export class InventarioComponent implements OnInit {
  inventarios: Inventario[] = [];
  inventariosFiltrados: Inventario[] = [];
  filtros: Record<string, FiltroColumna> = {};
  columnasFiltrables = [
    'nombre', 'descripcion', 'tipo', 'marca', 'proveedor',
    'categoria', 'unidad', 'grupo_muscular', 'codigo_interno'
  ];
  filtroColumnaActual: string | null = null;

  displayedColumns: string[] = [
    'id',
    ...[
      'nombre', 'descripcion', 'tipo', 'marca', 'proveedor',
      'categoria', 'unidad', 'grupo_muscular', 'codigo_interno'
    ],
    'acciones'
  ];

  loading = false;
  error: string | null = null;

  @ViewChild('menuTrigger', { static: false }) menuTrigger!: MatMenuTrigger;

  constructor(
    private inventarioService: InventarioService,
    private dialog: MatDialog
  ) { }

  ngOnInit(): void {
    this.cargarInventario();
  }

  cargarInventario(): void {
    this.loading = true;
    this.error = null;
    this.inventarioService.obtenerInventario().subscribe({
      next: data => {
        this.inventarios = data;
        this.filtros = inicializarFiltros(this.inventarios, this.columnasFiltrables);
        this.inventariosFiltrados = [...this.inventarios];
        this.loading = false;
      },
      error: err => {
        this.error = 'Error al cargar inventario';
        this.loading = false;
        console.error(this.error, err);
      }
    });
  }

  abrirDialogoAgregar(): void {
    const dialogRef = this.dialog.open(DialogoInventarioComponent, {
      width: '460px',
      data: { modo: 'crear' }
    });

    dialogRef.afterClosed().subscribe(resultado => {
      if (resultado?.status === 'creado') {
        this.cargarInventario();
        mostrarAlertaToast('Inventario agregado correctamente.');
      }
    });
  }

  abrirDialogoEditar(item: Inventario): void {
    const dialogRef = this.dialog.open(DialogoInventarioComponent, {
      width: '460px',
      data: { modo: 'editar', item }
    });

    dialogRef.afterClosed().subscribe(resultado => {
      if (resultado?.status === 'actualizado') {
        this.cargarInventario();
        mostrarAlertaToast('Inventario actualizado correctamente.');
      }
    });
  }

  eliminarInventario(id: number): void {
    const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
      data: {
        titulo: 'Eliminar inventario',
        mensaje: '¿Seguro que quieres eliminar este registro?',
        textoAceptar: 'Sí, eliminar',
        textoCancelar: 'Cancelar'
      }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.loading = true;
        this.inventarioService.eliminarInventario(id).subscribe({
          next: () => {
            mostrarAlertaToast('Inventario eliminado correctamente.');
            this.cargarInventario();
          },
          error: err => {
            let mensaje = err?.error?.error || 'No se pudo eliminar el inventario.';
            if (mensaje.includes('movimientos registrados')) {
              mensaje = 'No puedes eliminar este inventario porque tiene movimientos asociados. Elimina primero sus movimientos si es necesario.';
            }
            mostrarAlertaToast(mensaje, 'error');
            this.loading = false;
            console.error('Error al eliminar inventario', err);
          }
        });
      }
    });
  }

  // -------- Filtros Excel ---------
  abrirMenuFiltro(col: string) {
    this.filtroColumnaActual = col;
  }

  buscar(col: string, texto: string) {
    this.filtros[col].texto = texto;
  }

  seleccionarTodo(col: string, valor: boolean) {
    alternarSeleccionTemporal(this.filtros[col], valor);
  }

  alternarSeleccionIndividual(col: string, i: number, valor: boolean) {
    this.filtros[col].temporales[i].seleccionado = valor;
  }

  aplicarFiltro(col: string) {
    confirmarSeleccion(this.filtros[col]);
    this.inventariosFiltrados = filtrarTabla(this.inventarios, this.filtros);
    this.actualizarOpcionesDeFiltros();
    this.menuTrigger.closeMenu();
  }

  limpiarFiltro(col: string) {
    this.filtros[col].opciones.forEach(op => op.seleccionado = true);
    this.filtros[col].texto = '';
    this.filtros[col].temporales = this.filtros[col].opciones.map(o => ({ ...o }));
    this.inventariosFiltrados = filtrarTabla(this.inventarios, this.filtros);
    this.actualizarOpcionesDeFiltros();
    this.menuTrigger.closeMenu();
  }

  isTodoSeleccionado(col: string): boolean {
    const visibles = obtenerOpcionesVisibles(this.filtros[col]);
    return visibles.length > 0 && visibles.every(item => item.seleccionado);
  }

  obtenerOpcionesVisibles(filtro: FiltroColumna) {
    return obtenerOpcionesVisibles(filtro);
  }

  isFilterActive(col: string): boolean {
    // Retorna true si hay algún filtro aplicado (no todos seleccionados)
    return this.filtros[col]?.opciones.some(o => !o.seleccionado);
  }

    actualizarOpcionesDeFiltros() {
    // Recorre cada columna y recalcula los valores posibles basados en los datos filtrados actuales
    for (const col of this.columnasFiltrables) {
      const valoresUnicos = Array.from(new Set(this.inventariosFiltrados.map(row => String(row[col] ?? '')).filter(x => x !== '')));
      // Preserva selección de los que ya estaban seleccionados
      this.filtros[col].opciones = valoresUnicos.map(valor => {
        // Si ya existe en opciones y estaba seleccionado, mantenlo seleccionado
        const ya = this.filtros[col].opciones.find(o => o.valor === valor);
        return { valor, seleccionado: ya ? ya.seleccionado : true };
      });
      this.filtros[col].temporales = this.filtros[col].opciones.map(o => ({ ...o }));
      // Si hay texto en buscador, filtra temporales:
      if (this.filtros[col].texto) {
        const texto = this.filtros[col].texto.toLowerCase();
        this.filtros[col].temporales = this.filtros[col].temporales.filter(o => o.valor.toLowerCase().includes(texto));
      }
    }
  }
}
