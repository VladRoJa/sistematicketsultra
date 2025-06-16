// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\pantalla-ver-tickets.component.ts

import { Component, OnInit, ChangeDetectorRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgxPaginationModule } from 'ngx-pagination';
import { TicketService } from '../services/ticket.service';
import { DepartamentoService } from '../services/departamento.service';
import { HttpClient } from '@angular/common/http';
import { RefrescoService } from '../services/refresco.service';
import * as FiltrosGenericos from './helpers/filtros-genericos';



// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule, MatMenuTrigger } from '@angular/material/menu';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';


// Helpers nuevos (todo modular)
import * as TicketAcciones from './helpers/pantalla-ver-tickets.acciones';
import * as TicketInit from './helpers/pantalla-ver-tickets.init';
import { cargarDepartamentos } from './helpers/pantalla-ver-tickets.departamentos';
import { aplicarFiltroColumnaConReset} from './helpers/pantalla-ver-tickets.filtros';
import {filtrarOpcionesDetalle, aplicarFiltroColumna, limpiarFiltroColumna} from './helpers/pantalla-ver-tickets.filtros';
import { aplicarFiltroPorRangoFechaCreacion, aplicarFiltroPorRangoFechaFinalizado, aplicarFiltroPorRangoFechaEnProgreso  } from './helpers/pantalla-ver-tickets.fechas';
import { MatDialog } from '@angular/material/dialog';
import { cancelarEdicionFechaSolucion, editarFechaSolucion, guardarFechaSolucion } from './helpers/pantalla-ver-tickets.fecha-solucion';
import { HistorialFechasModalComponent } from './modals/historial-fechas-modal.component';
import { refrescarDespuesDeCambioFiltro } from './helpers/refrescarDespuesDeCambioFiltro';


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
  fecha_en_progreso: string;

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
    HistorialFechasModalComponent,
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
  usuarioEsEditorCorporativo: boolean = false;
  mostrarAvisoLimite: boolean = false;

  incluirSinFechaProgreso: boolean = false;
  incluirSinFechaFinalizado: boolean = false;
  filtroProgresoActivo: boolean = false;
  filtroFinalizadoActivo: boolean = false;
  filtroCreacionActivo: boolean = false;

  // Temporales
  fechaCreacionTemp = { start: null as Date | null, end: null as Date | null };
  fechaProgresoTemp = { start: null as Date | null, end: null as Date | null };
  fechaFinalTemp = { start: null as Date | null, end: null as Date | null };
  temporalSeleccionados: {
  [key: string]: { valor: string, seleccionado: boolean }[];
    } = {
      categoria: [],
      descripcion: [],
      username: [],
      estado: [],
      criticidad: [],
      departamento: [],
      subcategoria: [],
      subsubcategoria: []
    };

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

  fechaSolucionSeleccionada: Record<number, Date | null> = {};
  motivoCambioFechaSolucion: Record<number, string> = {};
  editandoFechaSolucion: Record<number, boolean> = {};
  historialVisible: Record<number, boolean> = {};
  fechasSolucionDisponibles = new Set<string>();

  rangoFechaCreacionSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaFinalSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaProgresoSeleccionado = { start: null as Date | null, end: null as Date | null };


  confirmacionVisible: boolean = false;
  mensajeConfirmacion: string = '';
  accionPendiente: (() => void) | null = null;

  @ViewChild('triggerFiltroCategoria') triggerFiltroCategoria: any;
  @ViewChild('triggerFiltroDesc') triggerFiltroDesc: any;
  @ViewChild('triggerFiltroUsuario') triggerFiltroUsuario: any;
  @ViewChild('triggerFiltroEstado') triggerFiltroEstado: any;
  @ViewChild('triggerFiltroCriticidad') triggerFiltroCriticidad: any;
  @ViewChild('triggerFiltroFechaC') triggerFiltroFechaC: any;
  @ViewChild('triggerFiltroFechaP') triggerFiltroFechaP: any;
  @ViewChild('triggerFiltroFechaF') triggerFiltroFechaF: any;
  @ViewChild('triggerFiltroDepartamento') triggerFiltroDepartamento: any;
  @ViewChild('triggerFiltroSubcategoria') triggerFiltroSubcategoria: any;
  @ViewChild('triggerFiltroDetalle') triggerFiltroDetalle: any;


  constructor(
    public ticketService: TicketService,
    public departamentoService: DepartamentoService,
    public changeDetectorRef: ChangeDetectorRef,
    public http: HttpClient,
    public dialog: MatDialog,
    public refrescoService: RefrescoService
  ) {}
  ngAfterViewInit(): void {
    const triggers = [
      { ref: this.triggerFiltroCategoria, key: 'categoria' },
      { ref: this.triggerFiltroDesc, key: 'descripcion' },
      { ref: this.triggerFiltroUsuario, key: 'username' },
      { ref: this.triggerFiltroEstado, key: 'estado' },
      { ref: this.triggerFiltroCriticidad, key: 'criticidad' },
      { ref: this.triggerFiltroDepartamento, key: 'departamento' },
      { ref: this.triggerFiltroSubcategoria, key: 'subcategoria' },
      { ref: this.triggerFiltroDetalle, key: 'subsubcategoria' }
    ];

    triggers.forEach(({ ref, key }) => {
      if (ref?.menuOpened) {
        ref.menuOpened.subscribe(() => {
          console.log(`🟢 Menu de ${key} abierto`);
          this.inicializarTemporales(key);
        });
      }
    });
  }

  async ngOnInit() {
    await TicketInit.obtenerUsuarioAutenticado(this); 
    await cargarDepartamentos(this);                 
    TicketInit.cargarTickets(this);

    // ⬇️ Espera a que los tickets se hayan cargado (usa un pequeño delay para asegurarlo)
    setTimeout(() => {
      if (this.tickets.length > 0) {
        const extraerUnicos = (campo: string) =>
          [...new Set(this.tickets.map(t => t[campo]))].map(valor => ({
            valor,
            seleccionado: true
          }));

        this.categoriasDisponibles = extraerUnicos('categoria');
        this.estadosDisponibles = extraerUnicos('estado');
        this.usuariosDisponibles = extraerUnicos('username');
        console.log('👤 Usuarios:', this.usuariosDisponibles)
        this.descripcionesDisponibles = extraerUnicos('descripcion');
        this.criticidadesDisponibles = extraerUnicos('criticidad');
        this.departamentosDisponibles = extraerUnicos('departamento');
        this.subcategoriasDisponibles = extraerUnicos('subcategoria');
        this.detallesDisponibles = extraerUnicos('subsubcategoria');

        console.log('🧩 Tickets cargados:', this.tickets.map(t => t.id));
        console.log('📋 Categorías generadas:', this.categoriasDisponibles);

        const columnasConTexto = [
          'categoria',
          'descripcion',
          'username',
          'estado',
          'criticidad',
          'departamento',
          'subcategoria',
          'subsubcategoria'
        ];

        columnasConTexto.forEach(col => {
          this.inicializarTemporales(col);
          this.inicializarFiltradas(col);
        });

        this.changeDetectorRef.detectChanges();
      } else {
        console.warn('⚠️ No hay tickets cargados todavía.');
      }
    }, 300);

    // 🔁 Escuchar eventos de refresco desde el servicio
    this.refrescoService.refrescarTabla$.subscribe(() => {
      TicketInit.cargarTickets(this); // recargar los tickets
    });

    console.log('Usuario:', this.user);
    console.log('Editor corporativo:', this.usuarioEsEditorCorporativo);

    this.changeDetectorRef.detectChanges();
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
  totalPages() { return TicketAcciones.totalPages(this); }
  limpiarTodosLosFiltros() { TicketAcciones.limpiarTodosLosFiltros(this); }
  isFilterActive(columna: string) { return TicketAcciones.isFilterActive(this, columna); }
  exportandoExcel: boolean = false;
  limpiarFiltroColumna(columna: string): void {limpiarFiltroColumna(this, columna);}
  aplicarFiltroColumna = (columna: string) => aplicarFiltroColumnaConReset(this, columna);
  inicializarTemporales = (col: string) => FiltrosGenericos.inicializarTemporales(this, col);
  confirmarFiltroColumna = (col: string) => FiltrosGenericos.confirmarFiltroColumna(this, col);
  actualizarSeleccionTemporal = (col: string, i: number, valor: boolean) => FiltrosGenericos.actualizarSeleccionTemporal(this, col, i, valor);
  alternarSeleccionTemporal = (col: string, valor: boolean) => FiltrosGenericos.alternarSeleccionTemporal(this, col, valor);
  isTodoSeleccionado = (col: string) => FiltrosGenericos.isTodoSeleccionado(this, col);
  
  filtrarOpcionesTexto(columna: string) {
    const capitalizar = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

    // ↔️ Aliases para nombres “raros”
    const textoPropAlias: Record<string, string> = {
      departamento: 'filtroDeptoTexto',
      subsubcategoria: 'filtroDetalleTexto'
    };

    // Propiedad que realmente contiene el texto que escribe el usuario
    const textoProp = textoPropAlias[columna] ?? `filtro${capitalizar(columna)}Texto`;
    const filtroTexto = (this[textoProp] || '').toLowerCase();

    const pluralMap: Record<string, string> = {
      categoria: 'categorias',
      descripcion: 'descripciones',
      username: 'usuarios',
      estado: 'estados',
      criticidad: 'criticidades',
      departamento: 'departamentos',
      subcategoria: 'subcategorias',
      subsubcategoria: 'detalles'
    };

    const plural = pluralMap[columna];
    const disponibles = this[`${plural}Disponibles`];
    if (!Array.isArray(disponibles)) { return; }

    const filtradas = disponibles.filter((item: any) =>
      item.valor?.toLowerCase().includes(filtroTexto)
    );

    // Mantén sincronizados lista y selección temporal
    this[`${plural}Filtradas`] = filtradas;
    this.temporalSeleccionados[columna] = filtradas.map((item: any) => ({ ...item }));
  }






  onFechaChange(ticketId: number, fecha: Date | null): void {
    this.fechaSolucionSeleccionada[ticketId] = fecha; // ✅ Guarda el objeto Date o null directamente
  
    // 🔄 Asegura que se actualice la vista
    this.changeDetectorRef.detectChanges();
  }
  
  aplicarFiltroPorRangoFechaCreacionConfirmada = () => {
    this.rangoFechaCreacionSeleccionado = {
      start: this.fechaCreacionTemp.start,
      end: this.fechaCreacionTemp.end
    };

    aplicarFiltroPorRangoFechaCreacion(this, this.rangoFechaCreacionSeleccionado);

    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };
    
  borrarFiltroRangoFechaCreacion = () => {
    this.rangoFechaCreacionSeleccionado = { start: null, end: null };
    this.fechaCreacionTemp = { start: null, end: null }; // ⬅️ limpia también la temporal
    this.filteredTickets = [...this.tickets];

    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

    this.changeDetectorRef.detectChanges();
  };
  
  aplicarFiltroPorRangoFechaEnProgresoConfirmada = () => {
    this.rangoFechaProgresoSeleccionado = {
      start: this.fechaProgresoTemp.start,
      end: this.fechaProgresoTemp.end
    };

    // ⬇️ Solo en aplicar se toma en cuenta esta bandera
    this.filtroProgresoActivo = !!this.rangoFechaProgresoSeleccionado.start || !!this.rangoFechaProgresoSeleccionado.end || this.incluirSinFechaProgreso;

    aplicarFiltroPorRangoFechaEnProgreso(this, this.rangoFechaProgresoSeleccionado);

    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };


  aplicarFiltroPorRangoFechaFinalizadoConfirmada = () => {
    this.rangoFechaFinalSeleccionado = {
      start: this.fechaFinalTemp.start,
      end: this.fechaFinalTemp.end
    };

    // ⬇️ Activar sólo al aplicar
    this.filtroFinalizadoActivo = !!this.rangoFechaFinalSeleccionado.start || !!this.rangoFechaFinalSeleccionado.end || this.incluirSinFechaFinalizado;

    aplicarFiltroPorRangoFechaFinalizado(this, this.rangoFechaFinalSeleccionado);

    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };


  borrarFiltroRangoFechaEnProgreso = () => {
    this.rangoFechaProgresoSeleccionado = { start: null, end: null };
    this.fechaProgresoTemp = { start: null, end: null };
    this.incluirSinFechaProgreso = false;
    this.filtroProgresoActivo = false; 

    this.filteredTickets = [...this.tickets];
    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };


  borrarFiltroRangoFechaFinalizado = () => {
    this.rangoFechaFinalSeleccionado = { start: null, end: null };
    this.fechaFinalTemp = { start: null, end: null };
    this.incluirSinFechaFinalizado = false;
    this.filtroFinalizadoActivo = false; 

    this.filteredTickets = [...this.tickets];
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

  editarFechaSolucionWrapper(ticket: Ticket): void {
    editarFechaSolucion(this, ticket, this.changeDetectorRef);
  }

  guardarFechaSolucionWrapper(ticket: Ticket, fecha: Date): void {
    const motivo = this.motivoCambioFechaSolucion[ticket.id];
    if (!motivo || !motivo.trim()) {
      alert('Debes ingresar un motivo para el cambio de fecha.');
      return;
    }
    guardarFechaSolucion(this, ticket, fecha, motivo); // 🔧 NUEVO
  }

  cancelarEdicionFechaSolucionWrapper(ticket: Ticket): void {
    cancelarEdicionFechaSolucion(this, ticket);
  }
  abrirHistorialModal(ticket: Ticket): void {
    this.dialog.open(HistorialFechasModalComponent, {
      data: ticket,
      width: '500px'
    });
  }
  inicializarCategoriaTemp() {
  console.log('🟢 inicializarCategoriaTemp llamada desde el HTML');
  this.inicializarTemporales('categoria');
}

  onAbrirFiltro(columna: string, trigger: any) {
    console.log('🟢 Abriendo filtro para columna:', columna);
    this.inicializarTemporales(columna);
    this.filtrarOpcionesTexto(columna);
    setTimeout(() => trigger?.openMenu?.(), 0);
    
  }

  onCerrarFiltro(columna: string, trigger: any) {
    this.confirmarFiltroColumna(columna);
    setTimeout(() => trigger?.closeMenu?.(), 0);
  }

  cerrarYLimpiar(columna: string, trigger: any) {
    this.limpiarFiltroColumna(columna);
    refrescarDespuesDeCambioFiltro(this);
    setTimeout(() => trigger?.closeMenu?.(), 0);
  }

  inicializarFiltradas(columna: string) {
  const disponibles = this[`${columna}sDisponibles`];
  if (Array.isArray(disponibles)) {
    this[`${columna}sFiltradas`] = [...disponibles];
  } else {
    console.warn(`⚠️ No se encontraron disponibles para la columna '${columna}'`);
  }
}

  cerrarYAplicar(columna: string, trigger: MatMenuTrigger): void {
  this.confirmarFiltroColumna(columna);
  trigger.closeMenu();
}

  isItemSeleccionado(columna: string, valor: string): boolean {
  return this.temporalSeleccionados[columna]?.find(x => x.valor === valor)?.seleccionado ?? false;
}

  /** Sólo estas columnas muestran buscador de texto */
  permiteBusqueda(col: string): boolean {
    return col === 'categoria' || col === 'descripcion';
}

}
