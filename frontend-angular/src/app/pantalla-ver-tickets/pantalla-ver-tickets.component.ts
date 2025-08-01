// frontend-angular\src\app\pantalla-ver-tickets\pantalla-ver-tickets.component.ts

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
import { MatTooltipModule } from '@angular/material/tooltip';


// Helpers nuevos (todo modular)
import * as TicketAcciones from './helpers/pantalla-ver-tickets.acciones';
import * as TicketInit from './helpers/pantalla-ver-tickets.init';
import { cargarDepartamentos } from './helpers/pantalla-ver-tickets.departamentos';
import { aplicarFiltroColumnaConReset} from './helpers/pantalla-ver-tickets.filtros';
import {filtrarOpcionesDetalle, aplicarFiltroColumna, limpiarFiltroColumna} from './helpers/pantalla-ver-tickets.filtros';
import { aplicarFiltroPorRangoFechaCreacion, aplicarFiltroPorRangoFechaFinalizado, aplicarFiltroPorRangoFechaEnProgreso  } from './helpers/pantalla-ver-tickets.fechas';
import { MatDialog } from '@angular/material/dialog';
import { asignarFechaSolucionYEnProgreso} from './helpers/pantalla-ver-tickets.fecha-solucion';
import { HistorialFechasModalComponent } from './modals/historial-fechas-modal.component';
import { refrescarDespuesDeCambioFiltro } from './helpers/refrescarDespuesDeCambioFiltro';
import { AsignarFechaModalComponent } from './modals/asignar-fecha-modal.component';
import { cambiarEstadoTicket } from './helpers/pantalla-ver-tickets.estado-ticket';
import { EditarFechaSolucionModalComponent } from './modals/editar-fecha-solucion-modal.component';
import { CatalogoService } from '../services/catalogo.service';



// Interfaces
export interface Ticket {
  detalle_nivel4: any;
  categoria_nivel2: any;
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
  categoria: number | null;
  fecha_solucion?: string | null;
  subcategoria?: number | null;
  detalle?: number | null;
  historial_fechas?: Array<{
    fecha: string;
    cambiadoPor: string;
    fechaCambio: string;
  }>;
  fecha_en_progreso: string;
  inventario?: {
    codigo_interno: any;
    id: number;
    nombre: string;
    tipo: string;
    descripcion: string;
  };
  equipo?: string;  
  ubicacion?: string;    
  clasificacion_id?: number;  
  clasificacion_nombre?: string;  




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
    AsignarFechaModalComponent,
    MatTooltipModule

    
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
  usuarioEsAdmin: boolean = true;
  departamentos: any[] = [];
  usuarioEsEditorCorporativo: boolean = true;
  mostrarAvisoLimite: boolean = false;
  clasificacionesMap: Record<number, string> = {};
  incluirSinFechaProgreso: boolean = false;
  incluirSinFechaFinalizado: boolean = false;
  filtroProgresoActivo: boolean = false;
  filtroFinalizadoActivo: boolean = false;
  filtroCreacionActivo: boolean = false;
  categoriasCatalogo: { id: number, nombre: string, parent_id: number, nivel: number }[] = [];

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
      detalle: [],
      inventario: []
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
  inventariosDisponibles: any[] = [];


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
  inventariosFiltrados: any[] = [];
  
  // Modal asignar fecha solución
  showModalAsignarFecha: boolean = false;
  ticketParaAsignarFecha: Ticket | null = null;
  fechaSolucionTentativa: Date | null = null;
  

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
  seleccionarTodoInventario = false;

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
  filtroInventarioTexto = '';



  historialVisible: Record<number, boolean> = {};
  fechasSolucionDisponibles = new Set<string>();

  rangoFechaCreacionSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaFinalSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaProgresoSeleccionado = { start: null as Date | null, end: null as Date | null };



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
  @ViewChild('triggerFiltroInventario') triggerFiltroInventario: any;

  constructor(
    public ticketService: TicketService,
    public departamentoService: DepartamentoService,
    public changeDetectorRef: ChangeDetectorRef,
    public http: HttpClient,
    public dialog: MatDialog,
    public refrescoService: RefrescoService,
    public catalogoService: CatalogoService
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
      { ref: this.triggerFiltroDetalle, key: 'detalle' },
      { ref: this.triggerFiltroInventario, key: 'inventario' }
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
    await this.cargarCatalogoCategorias();               
    TicketInit.cargarTickets(this);

    this.usuarioEsAdmin = (
    this.user?.rol === 'ADMINISTRADOR' ||
    this.user?.sucursal_id === 1000 ||
    this.user?.sucursal_id === 100
  );

  this.usuarioEsEditorCorporativo = (
    this.user?.rol === 'EDITOR_CORPORATIVO' ||
    this.user?.sucursal_id === 100
  );

  this.http.get<any>(`/api/catalogos/clasificaciones/todos`).subscribe(res => {
  const lista = res.data || [];
  this.clasificacionesMap = {};
  lista.forEach((c: any) => {
    this.clasificacionesMap[c.id] = c.nombre;
  });
  // Si quieres forzar un refresco de la vista (opcional):
  this.changeDetectorRef.detectChanges();
});




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
  cambiarEstado(ticket: Ticket, estado: "pendiente" | "en progreso" | "finalizado") {
    if (estado === 'finalizado') {
      this.mostrarConfirmacion('¿Estás seguro de finalizar este ticket?', () => {
        TicketAcciones.cambiarEstado(this, ticket, estado);
      });
    } else {
      TicketAcciones.cambiarEstado(this, ticket, estado);
    }
  }
  finalizar(ticket: Ticket) { TicketAcciones.finalizar(this, ticket); }
  mostrarConfirmacion(mensaje: string, accion: () => void) { TicketAcciones.mostrarConfirmacionAccion(this, mensaje, accion); } 
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


    cargarCatalogoCategorias(): Promise<void> {
      return new Promise((resolve, reject) => {
        this.catalogoService.getCategorias().subscribe({
          next: (res) => {
            // 🔴 Cambia esto (haz el mapeo manual)
            this.categoriasCatalogo = res.map((cat: any) => ({
              id: cat.id,
              nombre: cat.nombre,
              parent_id: cat.parent_id,
              nivel: cat.nivel
            }));
            resolve();
          },
          error: (err) => {
            this.categoriasCatalogo = [];
            reject(err);
          }
        });
      });
    }


  
  filtrarOpcionesTexto(columna: string) {
    const capitalizar = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

    // ↔️ Aliases para nombres “raros”
    const textoPropAlias: Record<string, string> = {
      departamento: 'filtroDeptoTexto',
      detalle: 'filtroDetalleTexto'
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
      detalle: 'detalles',
      inventario: 'inventarios'
    };

    const plural = pluralMap[columna];
    const disponibles = this[`${plural}Disponibles`];
    if (!Array.isArray(disponibles)) { return; }

      const filtradas = disponibles.filter((item: any) =>
        (item.etiqueta || '').toLowerCase().includes(filtroTexto)
      )

    // Mantén sincronizados lista y selección temporal
    this[`${plural}Filtradas`] = filtradas;
    this.temporalSeleccionados[columna] = filtradas.map((item: any) => ({ ...item }));
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
    console.log(this.temporalSeleccionados['subcategoria'])
    console.log('🟢 Abriendo filtro para columna:', columna);
    this.inicializarTemporales(columna);
    this.filtrarOpcionesTexto(columna);
    setTimeout(() => trigger?.openMenu?.(), 0);
      if (columna === 'subcategoria') {
    console.log('🔵 temporalSeleccionados subcategoria', this.temporalSeleccionados['subcategoria']);
  }
    
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

  cambiarEstadoEnProgreso(ticket: Ticket) {
  if (!ticket.fecha_solucion) {
    // Si NO tiene fecha de solución, abrir el modal
    this.ticketParaAsignarFecha = ticket;
    this.fechaSolucionTentativa = null;
    this.showModalAsignarFecha = true;
  } else {
    // Si ya tiene, solo cambiar el estado normalmente
    this.cambiarEstado(ticket, 'en progreso');
  }
}

onGuardarFechaSolucion(event: { fecha: Date, motivo: string }) {
  if (!this.ticketParaAsignarFecha) return;
  if (!event.motivo || !event.motivo.trim()) {
    alert('Debes ingresar un motivo para el cambio de fecha.');
    return;
  }

  asignarFechaSolucionYEnProgreso(
    this,
    this.ticketParaAsignarFecha,
    event.fecha,
    event.motivo,
    () => {
      this.showModalAsignarFecha = false;
      this.ticketParaAsignarFecha = null;
    }
  );
}


onCancelarAsignarFecha() {
  this.showModalAsignarFecha = false;
  this.ticketParaAsignarFecha = null;
}

abrirEditarFechaSolucion(ticket: Ticket) {
  const dialogRef = this.dialog.open(EditarFechaSolucionModalComponent, {
    width: '360px',
    data: { fechaActual: ticket.fecha_solucion }
  });

  dialogRef.afterClosed().subscribe(result => {
    if (result && result.fecha && result.motivo) {
      // Aquí llamas tu helper actualizador
      asignarFechaSolucionYEnProgreso(this, ticket, result.fecha, result.motivo);
    }
  });
}


public getNombreEquipoOInventario(ticket: Ticket): string {
  console.log(ticket)
  if (ticket.inventario?.nombre) return ticket.inventario.nombre;
  if (ticket.equipo) return ticket.equipo;
  return '—';
}

// ticket.inventario?.nombre + " " + últimos 2 dígitos del ticket.inventario?.codigo_interno

getNombreCortoAparato(ticket: Ticket): string {
  // Log para ver qué estructura trae el inventario
  console.log('ticket.inventario:', ticket.inventario);

  if (!ticket.inventario || !ticket.inventario.codigo_interno)
    return ticket.inventario?.nombre || "—";

  const codigo = ticket.inventario.codigo_interno;
  const numerador = codigo.slice(-2);
  return `${ticket.inventario.nombre} ${numerador}`;
}


}
