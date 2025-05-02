// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\pantalla-ver-tickets.component.ts

import { Component, OnInit, ChangeDetectorRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgxPaginationModule } from 'ngx-pagination';
import { TicketService } from '../services/ticket.service';
import { DepartamentoService } from '../services/departamento.service';
import { HttpClient } from '@angular/common/http';
import { filtrarTicketsConFiltros, formatearFechaCorta, limpiarFiltroColumnaConMapa, regenerarFiltrosFiltradosDesdeTickets, toggleSeleccionarTodoConMapa } from '../utils/ticket-utils';


// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';

// Helpers nuevos (todo modular)
import * as TicketAcciones from './helpers/pantalla-ver-tickets.acciones';
import * as TicketFiltros from './helpers/pantalla-ver-tickets.filtros';
import * as TicketInit from './helpers/pantalla-ver-tickets.init';
import { cargarDepartamentos } from './helpers/pantalla-ver-tickets.departamentos';
import { aplicarFiltroColumnaConReset, obtenerFiltrosActivos } from './helpers/pantalla-ver-tickets.filtros';
import {filtrarOpcionesCategoria, filtrarOpcionesDescripcion, filtrarOpcionesUsuario, filtrarOpcionesEstado, filtrarOpcionesCriticidad, filtrarOpcionesDepto, filtrarOpcionesSubcategoria, filtrarOpcionesDetalle, toggleSeleccionarTodo, aplicarFiltroColumna, limpiarFiltroColumna} from './helpers/pantalla-ver-tickets.filtros';
import { ordenar } from './helpers/pantalla-ver-tickets.init';
import { aplicarFiltroPorRangoFechaCreacion, aplicarFiltroPorRangoFechaFinalizado, } from './helpers/pantalla-ver-tickets.fechas';



// Interfaces
export interface Ticket {
  fecha_finalizado_original: any;
  fecha_creacion_original: any;
  id: number;
  descripcion: string;
  username: string;
  estado: string;
  criticidad: number;
  fecha_creacion: string;
  fecha_finalizado: string | null;
  departamento: string;
  departamento_id: number;
  categoria: string;
  fecha_solucion?: string | null;
  subcategoria?: string | null;
  subsubcategoria?: string | null;
  historial_fechas?: Array<{
    fecha: string;
    cambiadoPor: string;
    fechaCambio: string;
  }>;
}

export interface ApiResponse {
  mensaje: string;
  tickets: Ticket[];
  total_tickets: number;
}

@Component({
  selector: 'app-pantalla-ver-tickets',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    NgxPaginationModule,
    MatButtonModule,
    MatMenuModule,
    MatIconModule,
    MatDividerModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatNativeDateModule,
    MatDatepickerModule,
  ],
  templateUrl: './pantalla-ver-tickets.component.html',
  styleUrls: ['./pantalla-ver-tickets.component.css']
})
export class PantallaVerTicketsComponent implements OnInit {
  // --- Variables ---
  tickets: Ticket[] = [];
  filteredTickets: Ticket[] = [];
  totalTickets: number = 0;
  page: number = 1;
  itemsPerPage: number = 15;
  loading: boolean = false;
  ticketsCompletos: Ticket[] = [];  
  visibleTickets: Ticket[] = [];    
  totalPagesCount: number = 0;
  diasConTicketsCreacion: Set<string> = new Set();
  diasConTicketsFinalizado: Set<string> = new Set();
  ticketsPorDiaFinalizado: Record<string, number> = {};
  ticketsPorDiaCreacion: Record<string, number> = {};
  user: any = null;
  usuarioEsAdmin: boolean = false;
  departamentos: any[] = [];

  // Filtros
  idsDisponibles: any[] = [];
  categoriasDisponibles: any[] = [];
  descripcionesDisponibles: any[] = [];
  usuariosDisponibles: any[] = [];
  estadosDisponibles: any[] = [];
  criticidadesDisponibles: any[] = [];
  fechasCreacionDisponibles: any[] = [];
  fechasFinalDisponibles: any[] = [];
  departamentosDisponibles: any[] = [];
  subcategoriasDisponibles: any[] = [];
  detallesDisponibles: any[] = [];

  categoriasFiltradas: any[] = [];
  descripcionesFiltradas: any[] = [];
  usuariosFiltrados: any[] = [];
  estadosFiltrados: any[] = [];
  criticidadesFiltradas: any[] = [];
  fechasCreacionFiltradas: any[] = [];
  fechasFinalFiltradas: any[] = [];
  departamentosFiltrados: any[] = [];
  subcategoriasFiltradas: any[] = [];
  detallesFiltrados: any[] = [];




  // Controles
  seleccionarTodoCategoria = false;
  seleccionarTodoDescripcion = false;
  seleccionarTodoUsuario = false;
  seleccionarTodoEstado = false;
  seleccionarTodoCriticidad = false;
  seleccionarTodoFechaC = false;
  seleccionarTodoFechaF = false;
  seleccionarTodoDepto = false;
  seleccionarTodoSubcategoria = false;
  seleccionarTodoDetalle = false;

  filtroCategoriaTexto = '';
  filtroDescripcionTexto = '';
  filtroUsuarioTexto = '';
  filtroEstadoTexto = '';
  filtroCriticidadTexto = '';
  filtroFechaTexto = '';
  filtroFechaFinalTexto = '';
  filtroDeptoTexto = '';
  filtroSubcategoriaTexto = '';
  filtroDetalleTexto = '';

  fechaSolucionSeleccionada: Record<number, string> = {};
  editandoFechaSolucion: Record<number, boolean> = {};
  historialVisible: Record<number, boolean> = {};
  fechasSolucionDisponibles = new Set<string>();

  rangoFechaCreacionSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaFinalSeleccionado = { start: null as Date | null, end: null as Date | null };

  confirmacionVisible: boolean = false;
  mensajeConfirmacion: string = '';
  accionPendiente: (() => void) | null = null;


  constructor(
    public ticketService: TicketService,
    public departamentoService: DepartamentoService,
    public changeDetectorRef: ChangeDetectorRef,
    public http: HttpClient
  ) {}

  async ngOnInit() {
    await TicketInit.obtenerUsuarioAutenticado(this);
    TicketInit.cargarTickets(this);
    cargarDepartamentos(this);
  }

  // Métodos públicos conectados a helpers
  exportarTickets() { TicketAcciones.exportarTickets(this); }
  cambiarEstado(ticket: Ticket, estado: "pendiente" | "en progreso" | "finalizado") { TicketAcciones.cambiarEstado(this, ticket, estado); }
  finalizar(ticket: Ticket) { TicketAcciones.finalizar(this, ticket); }
  editarFecha(ticket: Ticket) { TicketAcciones.editarFecha(this, ticket); }
  guardarFecha(ticket: Ticket) { TicketAcciones.guardarFecha(this, ticket); }
  cancelarEdicionFecha(ticket: Ticket) { TicketAcciones.cancelarEdicionFecha(this, ticket); }
  mostrarConfirmacion(mensaje: string, accion: () => void) { TicketAcciones.mostrarConfirmacionAccion(this, mensaje, accion); }
  confirmarAccion() { TicketAcciones.confirmarAccionPendiente(this); }
  cancelarAccion() { TicketAcciones.cancelarAccionPendiente(this); }  
  toggleHistorial(ticketId: number) { TicketAcciones.alternarHistorial(this, ticketId); }
  cambiarPagina(direccion: number) { TicketAcciones.cambiarPagina(this, direccion); }
  filtrarOpcionesCategoria = () => filtrarOpcionesCategoria(this);
  filtrarOpcionesDescripcion = () => filtrarOpcionesDescripcion(this);
  filtrarOpcionesUsuario = () => filtrarOpcionesUsuario(this);
  filtrarOpcionesEstado = () => filtrarOpcionesEstado(this);
  filtrarOpcionesCriticidad = () => filtrarOpcionesCriticidad(this);
  filtrarOpcionesDepto = () => filtrarOpcionesDepto(this);
  filtrarOpcionesSubcategoria = () => filtrarOpcionesSubcategoria(this);
  filtrarOpcionesDetalle = () => filtrarOpcionesDetalle(this);
  toggleSeleccionarTodo(columna: string) { toggleSeleccionarTodoConMapa(this, columna); }
  totalPages() { return TicketAcciones.totalPages(this); }
  limpiarTodosLosFiltros() { TicketAcciones.limpiarTodosLosFiltros(this); }
  isFilterActive(columna: string) { return TicketAcciones.isFilterActive(this, columna); }
  formatearFechaCorta = formatearFechaCorta;
  exportandoExcel: boolean = false;
  limpiarFiltroColumna(columna: string): void {limpiarFiltroColumna(this, columna);}
  aplicarFiltroColumna = (columna: string) => aplicarFiltroColumnaConReset(this, columna);
  onFechaChange(ticketId: number, fecha: Date | null): void {
    if (fecha) {
      const year = fecha.getFullYear();
      const month = String(fecha.getMonth() + 1).padStart(2, '0');
      const day = String(fecha.getDate()).padStart(2, '0');
      this.fechaSolucionSeleccionada[ticketId] = `${year}-${month}-${day}`;
    } else {
      this.fechaSolucionSeleccionada[ticketId] = "";
    }
  }
  aplicarFiltroPorRangoFechaCreacion = (rango: { start: Date | null, end: Date | null }) => {
    aplicarFiltroPorRangoFechaCreacion(this, rango);
    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };
  
  borrarFiltroRangoFechaCreacion = () => TicketFiltros.borrarFiltroRangoFechaCreacion(this);
  borrarFiltroRangoFechaFinalizado = () => TicketFiltros.borrarFiltroRangoFechaFinalizado(this);
  aplicarFiltroPorRangoFechaFinalizado = (rango: { start: Date | null, end: Date | null }) => {
    aplicarFiltroPorRangoFechaFinalizado(this, rango);
    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };
  
  // 🔵 Días que deben marcarse visualmente en el calendario
  dateClassCreacion = (d: Date): string => {
    const fecha = d.toISOString().split('T')[0];
    return this.diasConTicketsCreacion.has(fecha) ? 'dia-con-ticket' : '';
  };
  
  dateClassFinalizado = (d: Date): string => {
    const fecha = d.toISOString().split('T')[0];
    return this.diasConTicketsFinalizado.has(fecha) ? 'dia-con-ticket' : '';
  };
}
