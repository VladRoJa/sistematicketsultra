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
import { HttpHeaders } from '@angular/common/http';




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
import {filtrarOpcionesDetalle, aplicarFiltroColumna, limpiarFiltroColumna, aplicarFiltroColumnaConReset, obtenerFiltrosActivos} from './helpers/pantalla-ver-tickets.filtros';
import { aplicarFiltroPorRangoFechaCreacion, aplicarFiltroPorRangoFechaFinalizado, aplicarFiltroPorRangoFechaEnProgreso  } from './helpers/pantalla-ver-tickets.fechas';
import { MatDialog } from '@angular/material/dialog';
import { asignarFechaSolucionYEnProgreso} from './helpers/pantalla-ver-tickets.fecha-solucion';
import { HistorialFechasModalComponent } from './modals/historial-fechas-modal.component';
import { refrescarDespuesDeCambioFiltro } from './helpers/refrescarDespuesDeCambioFiltro';
import { AsignarFechaModalComponent } from './modals/asignar-fecha-modal.component';
import { cambiarEstadoTicket } from './helpers/pantalla-ver-tickets.estado-ticket';
import { EditarFechaSolucionModalComponent } from './modals/editar-fecha-solucion-modal.component';
import { CatalogoService } from '../services/catalogo.service';
import { mostrarAlertaToast,solicitarMotivoRechazoCierre } from '../utils/alertas';
import { SucursalesService } from '../services/sucursales.service';
import { EvidenciaPreviewComponent } from './modals/evidencia-preview.component';
import { ModalCierreTicketComponent } from '../shared/modal-cierre-ticket/modal-cierre-ticket.component';
import { buscarAncestroNivel, filtrarTicketsConFiltros } from '../utils/ticket-utils';
import { MatSelectModule } from '@angular/material/select';
import { AuthService } from '../services/auth.service';
import { DialogoConfirmacionComponent } from '../shared/dialogo-confirmacion/dialogo-confirmacion.component';





// Interfaces
export interface Ticket {
  departamento_nombre?: string;
  subcategoria_nivel3: any;
  jerarquia_clasificacion: any;
  detalle_nivel4: any;
  categoria_nivel2: any;
  fecha_finalizado_original: any;
  fecha_creacion_original: any;
  id: number;
  descripcion: string;
  username: string;
  estado: string;
  criticidad: number;
  fecha_creacion: string | null; 
  fecha_finalizado: string | null;
  departamento: string;
  departamento_id: number;
  categoria: string | null;
  fecha_solucion?: string | null;
  subcategoria?: string | null;
  detalle?: string | null;
  historial_fechas?: Array<{
    fecha: string;
    cambiadoPor: string;
    fechaCambio: string;
  }>;
  fecha_en_progreso: string | null;
  inventario?: {
    subcategoria: any;
    categoria: string;
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
  necesita_refaccion?: boolean;
  descripcion_refaccion?: string;
  sucursal_id_destino?: number | null;
  url_evidencia?: string | null;
  refaccion_definida_por_jefe?: boolean;
  estado_cierre?:
  | 'pendiente_jefe'
  | 'pendiente_creador'
  | 'rechazado_por_jefe'
  | 'rechazado_por_creador'
  | 'cerrado_por_gerente_desde_cero'
  | null;



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
    MatTooltipModule,
    MatSelectModule,

    
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
  loading: boolean = true;
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
  sucursalIdNombreMap: Record<number, string> = {};
  listaSucursales: any[] = [];
  ocultarFinalizados: boolean = true;


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
      inventario: [],
      sucursal: []
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
  sucursalesDisponibles: { valor: string, etiqueta?: string }[] = [];



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
  sucursalesFiltradas: { valor: string, etiqueta?: string }[] = [];
  
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
  seleccionarTodoSucursal = false;

  filtroCategoriaTexto = '';
  filtroDescripcionTexto = '';
  filtroDescripcionAplicadoTexto = '';
  filtroUsuarioTexto = '';
  filtroEstadoTexto = '';
  filtroCriticidadTexto = '';
  filtroFechaTexto = '';
  filtroFechaFinalTexto = '';
  filtroDeptoTexto = '';
  filtroSubcategoriaTexto = '';
  filtroDetalleTexto = '';
  filtroInventarioTexto = '';
  filtroSucursalTexto = '';

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
  usuarioActual: string = '';

  constructor(
    public ticketService: TicketService,
    public departamentoService: DepartamentoService,
    public changeDetectorRef: ChangeDetectorRef,
    public http: HttpClient,
    public dialog: MatDialog,
    public refrescoService: RefrescoService,
    public catalogoService: CatalogoService,
    private sucursalesService: SucursalesService,
    private authService: AuthService, 
    
  ) {}
ngAfterViewInit(): void {
  const triggers = [
    { ref: this.triggerFiltroCategoria,    key: 'categoria' },
    { ref: this.triggerFiltroDesc,         key: 'descripcion' },
    { ref: this.triggerFiltroUsuario,      key: 'username' },
    { ref: this.triggerFiltroEstado,       key: 'estado' },
    { ref: this.triggerFiltroCriticidad,   key: 'criticidad' },
    { ref: this.triggerFiltroDepartamento, key: 'departamento' },
    { ref: this.triggerFiltroSubcategoria, key: 'subcategoria' },
    { ref: this.triggerFiltroDetalle,      key: 'detalle' },
    { ref: this.triggerFiltroInventario,   key: 'inventario' },
  ];

  triggers.forEach(({ ref, key }) => {
    if (ref?.menuOpened) {
      ref.menuOpened.subscribe(() => {
        console.log(`🟢 Menu de ${key} abierto`);
        // 👉 Asegura que siempre calculemos opciones al abrir el menú
        const path = this.rutasFiltro[key];
        if (path) {
          if (key === 'subcategoria') {
            this.filtroSubcategoriaTexto = ''; // evita que un texto viejo esconda opciones
          }
          this.prepararOpcionesFiltro(key, path);
        }
        this.inicializarTemporales(key);
        this.filtrarOpcionesTexto(key);
      });
    }
  });
}


async ngOnInit() {
  this.loading = true;
  await TicketInit.obtenerUsuarioAutenticado(this); 

  // 👇 NUEVO: setear usuarioActual a partir de this.user
  this.usuarioActual = (this.user?.username || '').trim().toUpperCase();

  await cargarDepartamentos(this);  
  await this.cargarCatalogoCategorias();
  await this.cargarSucursalesParaTickets();

  this.usuarioEsAdmin = (
    this.user?.rol === 'ADMINISTRADOR' ||
    this.user?.sucursal_id === 1000 ||
    this.user?.sucursal_id === 100
  );

  this.usuarioEsEditorCorporativo = (
    this.user?.rol === 'EDITOR_CORPORATIVO' ||
    this.user?.sucursal_id === 100
  );

  TicketInit.cargarTickets(this);

  // 🔁 Escuchar eventos de refresco desde el servicio
  this.refrescoService.refrescarTabla$.subscribe(() => {
    TicketInit.cargarTickets(this); // recargar los tickets
  });

  console.log('Usuario:', this.user);
  console.log('usuarioActual:', this.usuarioActual);
  console.log('Editor corporativo:', this.usuarioEsEditorCorporativo);

  this.changeDetectorRef.detectChanges();

  (window as any).verTicketsComp = this;
}

private cargarSucursalesParaTickets(): Promise<void> {
  return new Promise((resolve) => {
    this.sucursalesService.obtenerSucursales().subscribe({
      next: (sucs) => {
        this.listaSucursales = sucs || [];
        this.sucursalIdNombreMap = {};

        this.listaSucursales.forEach((s: any) => {
          const id = Number(s.sucursal_id ?? s.id);
          const nombre = s.sucursal ?? s.nombre ?? s.nombre_sucursal;

          if (Number.isFinite(id) && nombre) {
            this.sucursalIdNombreMap[id] = nombre;
          }
        });

        resolve();
      },
      error: (err) => {
        console.error('Error al obtener sucursales:', err);
        this.listaSucursales = [];
        this.sucursalIdNombreMap = {};
        resolve();
      },
    });
  });
}

refrescarTicketsPreservandoFiltros(): void {
  const pageActual = this.page;

  this.ticketService.getTickets(1000, 0).subscribe({
    next: (data: any) => {
    const ticketsProcesados = (data?.tickets || []).map((ticket: Ticket) => {
      const clasificacionId = Number(ticket.clasificacion_id);

      const tieneClasificacionValida = Number.isFinite(clasificacionId);

      const catNivel2 = tieneClasificacionValida
        ? buscarAncestroNivel(clasificacionId, 2, this.categoriasCatalogo)
        : null;

      const catNivel3 = tieneClasificacionValida
        ? buscarAncestroNivel(clasificacionId, 3, this.categoriasCatalogo)
        : null;

      const catNivel4 = tieneClasificacionValida
        ? buscarAncestroNivel(clasificacionId, 4, this.categoriasCatalogo)
        : null;

      return {
        ...ticket,
        categoria: catNivel2?.nombre || ticket.categoria || '—',
        subcategoria: catNivel3?.nombre || ticket.subcategoria || '—',
        detalle: catNivel4?.nombre || ticket.detalle || '—',
      };
    });

      this.tickets = ticketsProcesados;
      this.ticketsCompletos = ticketsProcesados;

      this.hidratarSucursalEnTickets();
      this.hidratarDetalleEnTickets();

      this.aplicarFiltrosDeTablaConContexto();

      if (pageActual <= this.totalPagesCount) {
        this.page = pageActual;
      } else {
        this.page = Math.max(this.totalPagesCount, 1);
      }

      this.visibleTickets = this.filteredTickets.slice(
        (this.page - 1) * this.itemsPerPage,
        this.page * this.itemsPerPage
      );

      this.changeDetectorRef.detectChanges();
    },
    error: (err) => {
      console.error('No se pudieron refrescar tickets después de la acción:', err);
    },
  });
}

  // Métodos públicos conectados a helpers
  exportarTickets() { TicketAcciones.exportarTickets(this); }
  cambiarEstado(ticket: Ticket, estado: "pendiente" | "en progreso" | "finalizado") {
    if (estado === 'finalizado') {
      // Antes aquí se llamaba a TicketAcciones.cambiarEstado y pegaba al /update con estado=finalizado,
      // lo que el backend bloquea con 400.
      mostrarAlertaToast(
        'Este ticket ya no se puede finalizar directamente. Usa el flujo de cierre (doble aprobación).',
        'error'
      );
      return;
    }

    // Para otros estados seguimos usando la lógica existente
    TicketAcciones.cambiarEstado(this, ticket, estado);
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
  get soloLectura(): boolean {
    return this.authService.esLectorGlobal();
  }

  get puedeEditarTickets(): boolean {
    // Bloquea edición a LECTOR_GLOBAL y también a GERENTE
    return !this.authService.esLectorGlobal() && !this.authService.esGerente();
  }

  

/** Refrescar tabla/estado tras aprobar/rechazar */
private postAccionRefrescar(): void {
  this.refrescarTicketsPreservandoFiltros();
}


get filtroDescripcionActivo(): boolean {
  return this.filtroDescripcionAplicadoTexto.trim().length > 0;
}

private obtenerBaseParaFiltroDescripcion(): Ticket[] {
  this.hidratarSucursalEnTickets();
  this.hidratarDetalleEnTickets();

  const filtros = obtenerFiltrosActivos(this);
  delete filtros['descripcion'];

  const baseCompleta = Array.isArray(this.ticketsCompletos) && this.ticketsCompletos.length > 0
    ? this.ticketsCompletos
    : this.tickets;

  const baseModoVista = this.ocultarFinalizados
    ? baseCompleta.filter((ticket: Ticket) => {
        const estado = (ticket.estado || '').toString().trim().toLowerCase();
        return estado !== 'finalizado';
      })
    : [...baseCompleta];

  return Object.keys(filtros).length === 0
    ? baseModoVista
    : filtrarTicketsConFiltros(baseModoVista, filtros);
}

aplicarFiltroDescripcionTexto(trigger?: MatMenuTrigger): void {
  const textoOriginal = (this.filtroDescripcionTexto || '').trim();
  const textoNormalizado = this.normalizarTextoFiltro(textoOriginal);

  this.filtroDescripcionAplicadoTexto = textoOriginal;

  const base = this.obtenerBaseParaFiltroDescripcion();

  this.filteredTickets = textoNormalizado
    ? base.filter((ticket: Ticket) => {
        const descripcion = this.normalizarTextoFiltro(ticket.descripcion || '');
        return descripcion.includes(textoNormalizado);
      })
    : base;

  this.page = 1;
  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

  this.changeDetectorRef.detectChanges();
  trigger?.closeMenu?.();
}

limpiarFiltroDescripcionTexto(trigger?: MatMenuTrigger): void {
  this.filtroDescripcionTexto = '';
  this.filtroDescripcionAplicadoTexto = '';

  this.filteredTickets = this.obtenerBaseParaFiltroDescripcion();

  this.page = 1;
  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

  this.changeDetectorRef.detectChanges();
  trigger?.closeMenu?.();
}



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


  
filtrarOpcionesTexto(columna: string): void {
  const plural = this.obtenerPluralFiltro(columna);

  if (!plural) {
    return;
  }

  const texto = this.obtenerTextoFiltroColumna(columna);
  const textoNormalizado = this.normalizarTextoFiltro(texto);

  const disponibles = ((this as any)[`${plural}Disponibles`] || []) as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  const temporalesActuales = (this.temporalSeleccionados[columna] || []) as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  const seleccionTemporalPorValor = new Map<string, boolean>(
    temporalesActuales.map((opcion) => [
      String(opcion.valor),
      opcion.seleccionado,
    ])
  );

  const fuente = disponibles.map((opcion) => {
    const valorKey = String(opcion.valor);

    return {
      ...opcion,
      seleccionado: seleccionTemporalPorValor.has(valorKey)
        ? Boolean(seleccionTemporalPorValor.get(valorKey))
        : opcion.seleccionado !== false,
    };
  });

  const filtradas = textoNormalizado
    ? fuente.filter((opcion) => {
        const etiqueta = this.normalizarTextoFiltro(
          opcion.etiqueta ?? opcion.valor ?? ''
        );

        return etiqueta.includes(textoNormalizado);
      })
    : fuente;

  this.temporalSeleccionados[columna] = [...filtradas];
  (this as any)[`${plural}Filtradas`] = [...filtradas];

  this.changeDetectorRef.detectChanges();
}

private columnaTieneFiltroReal(columna: string): boolean {
  const plural = this.obtenerPluralFiltro(columna);

  if (!plural) {
    return false;
  }

  const disponibles = (this as any)[`${plural}Disponibles`] as Array<{
    valor: any;
    seleccionado: boolean;
  }>;

  if (!Array.isArray(disponibles) || disponibles.length === 0) {
    return false;
  }

  const seleccionadas = disponibles.filter(opcion => opcion.seleccionado).length;

  return seleccionadas > 0 && seleccionadas < disponibles.length;
}

private obtenerTextoFiltroColumna(columna: string): string {
  const textoMap: Record<string, string> = {
    categoria: this.filtroCategoriaTexto,
    descripcion: this.filtroDescripcionTexto,
    username: this.filtroUsuarioTexto,
    estado: this.filtroEstadoTexto,
    criticidad: this.filtroCriticidadTexto,
    departamento: this.filtroDeptoTexto,
    subcategoria: this.filtroSubcategoriaTexto,
    detalle: this.filtroDetalleTexto,
    inventario: this.filtroInventarioTexto,
    sucursal: this.filtroSucursalTexto,
  };

  return textoMap[columna] || '';
}

private normalizarTextoFiltro(value: any): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}
  
  aplicarFiltroPorRangoFechaCreacionConfirmada = () => {
    this.rangoFechaCreacionSeleccionado = {
      start: this.fechaCreacionTemp.start,
      end: this.fechaCreacionTemp.end
    };

    this.filtroCreacionActivo =
      !!this.rangoFechaCreacionSeleccionado.start ||
      !!this.rangoFechaCreacionSeleccionado.end;

    aplicarFiltroPorRangoFechaCreacion(this, this.rangoFechaCreacionSeleccionado);

    this.page = 1;
    this.totalTickets = this.filteredTickets.length;
    this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
    this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
    this.changeDetectorRef.detectChanges();
  };
    
  borrarFiltroRangoFechaCreacion = () => {
    this.rangoFechaCreacionSeleccionado = { start: null, end: null };
    this.fechaCreacionTemp = { start: null, end: null };
    this.filtroCreacionActivo = false;

    this.filteredTickets = this.obtenerBaseConModoYFechas();

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

    this.filtroProgresoActivo =
      !!this.rangoFechaProgresoSeleccionado.start ||
      !!this.rangoFechaProgresoSeleccionado.end ||
      this.incluirSinFechaProgreso;

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

    this.filtroFinalizadoActivo =
      !!this.rangoFechaFinalSeleccionado.start ||
      !!this.rangoFechaFinalSeleccionado.end ||
      this.incluirSinFechaFinalizado;

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

    this.filteredTickets = this.obtenerBaseConModoYFechas();

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

    this.filteredTickets = this.obtenerBaseConModoYFechas();

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
      width: '920px',
      maxWidth: '96vw',
      maxHeight: '90vh',
      data: ticket
    });
  }
  inicializarCategoriaTemp() {
  console.log('🟢 inicializarCategoriaTemp llamada desde el HTML');
  this.inicializarTemporales('categoria');
}


// Extras que puede definir el Jefe al fijar fecha compromiso (se limpian tras usar)
extrasCompromisoRefaccion: {
  necesita_refaccion?: boolean;
  descripcion_refaccion?: string;
  refaccion_definida_por_jefe?: boolean;
} | null = null;




private hidratarSucursalEnTickets(): void {
  const resolverNombreSucursal = (ticket: any): string => {
    const nombreDirecto =
      ticket?.sucursal_nombre_destino ||
      ticket?.sucursal_nombre ||
      ticket?.sucursal_destino?.sucursal ||
      ticket?.sucursal_destino?.nombre ||
      ticket?.sucursal?.sucursal ||
      ticket?.sucursal?.nombre;

    if (nombreDirecto) {
      return String(nombreDirecto);
    }

    const sucursalActual = ticket?.sucursal;

    if (
      typeof sucursalActual === 'string' &&
      sucursalActual.trim() !== '' &&
      !/^\d+$/.test(sucursalActual.trim())
    ) {
      return sucursalActual;
    }

    const idRaw =
      ticket?.sucursal_id_destino ??
      ticket?.sucursal_destino_id ??
      ticket?.sucursal_id ??
      ticket?.id_sucursal ??
      ticket?.sucursal;

    const id = Number(idRaw);

    if (Number.isFinite(id)) {
      return this.sucursalIdNombreMap[id] || String(id);
    }

    return idRaw != null ? String(idRaw) : '—';
  };

  const poner = (arr: any[] | undefined) => {
    if (!Array.isArray(arr)) return;

    arr.forEach((ticket: any) => {
      ticket.sucursal = resolverNombreSucursal(ticket);
    });
  };

  poner(this.ticketsCompletos);
  poner(this.tickets);
  poner(this.filteredTickets);
  poner(this.visibleTickets);
}

private obtenerPluralFiltro(columna: string): string | null {
  const pluralMap: Record<string, string> = {
    categoria: 'categorias',
    descripcion: 'descripciones',
    username: 'usuarios',
    estado: 'estados',
    criticidad: 'criticidades',
    departamento: 'departamentos',
    subcategoria: 'subcategorias',
    detalle: 'detalles',
    inventario: 'inventarios',
    sucursal: 'sucursales',
  };

  return pluralMap[columna] || null;
}

private obtenerSeleccionActivaDeFiltro(columna: string): Set<string> | null {
  if (!this.isFilterActive(columna)) {
    return null;
  }

  const plural = this.obtenerPluralFiltro(columna);
  if (!plural) {
    return null;
  }

  const disponibles = (this as any)[`${plural}Disponibles`] as Array<{
    valor: any;
    seleccionado: boolean;
  }>;

  if (!Array.isArray(disponibles)) {
    return null;
  }

  const seleccionados = disponibles
    .filter(opcion => opcion.seleccionado)
    .map(opcion => String(opcion.valor));

  return new Set(seleccionados);
}

private restaurarSeleccionActivaDeFiltro(
  columna: string,
  seleccionActiva: Set<string> | null
): void {
  const plural = this.obtenerPluralFiltro(columna);
  if (!plural) {
    return;
  }

  const disponibles = (this as any)[`${plural}Disponibles`] as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  if (!Array.isArray(disponibles)) {
    return;
  }

  const normalizados = disponibles.map(opcion => ({
    ...opcion,
    seleccionado: seleccionActiva
      ? seleccionActiva.has(String(opcion.valor))
      : true,
  }));

  (this as any)[`${plural}Disponibles`] = normalizados;
  (this as any)[`${plural}Filtradas`] = [...normalizados];
}

private obtenerTicketsParaOpcionesDeFiltro(columna: string): Ticket[] {
  this.hidratarSucursalEnTickets();
  this.hidratarDetalleEnTickets();

  const filtros = obtenerFiltrosActivos(this);
  delete filtros[columna];

  const base = this.obtenerBaseConModoYFechas();

  if (Object.keys(filtros).length === 0) {
    return [...base];
  }

  return filtrarTicketsConFiltros(base, filtros);
}

private prepararOpcionesFiltro(columna: string, path: string): void {
  const setGen = new Set<string>();
  const baseOpciones = this.obtenerTicketsParaOpcionesDeFiltro(columna);

  // 1) Recolector genérico: usa todos los filtros activos EXCEPTO la columna actual.
  (baseOpciones || []).forEach((t: any) => {
    let valor: any = t;
    for (const part of path.split('.')) valor = valor?.[part];

    if (columna === 'departamento') {
      const esId = valor != null && /^[0-9]+$/.test(String(valor));
      if (esId) valor = this.etiquetaDepartamentoPorId(valor);
    }

    if (valor == null || valor === '') valor = '—';
    setGen.add(String(valor));
  });

  // 2) Caso especial: DEPARTAMENTO (siempre por NOMBRE)
  if (columna === 'departamento') {
    const opciones = Array.from(setGen)
      .map(v => (/^[0-9]+$/.test(String(v)) ? this.etiquetaDepartamentoPorId(v) : String(v)))
      .sort((a, b) => a.localeCompare(b))
      .map(nombre => ({ valor: nombre, etiqueta: nombre, seleccionado: true }));

    this.departamentosDisponibles = opciones;
    this.departamentosFiltrados  = [...opciones];
    this.temporalSeleccionados['departamento'] = opciones.map(o => ({ ...o }));
    return;
  }

  // 3) Caso especial: SUBCATEGORÍA (usa exactamente lo que ves en la tabla)
if (columna === 'subcategoria') {
  const set = new Set<string>();

  (this.filteredTickets || []).forEach((t: any) => {
    const label = this.getSubcategoriaVisible(t) || '—';
    set.add(label);
  });

  // DEBUG 👇
  const debug = (this.filteredTickets || []).map((t: any) => ({
    id: t.id,
    dep: t.departamento,
    jer1: t.jerarquia_clasificacion?.[1] ?? null,
    invCat: t.inventario?.categoria ?? null,
    jer2: t.jerarquia_clasificacion?.[2] ?? null,
    subId: t.subcategoria ?? null,
    labelTabla: this.getSubcategoriaVisible(t),
  }));
  console.table(debug);
  console.log('[SUBCAT] únicos (set):', Array.from(set));
  // DEBUG ☝️

  const opciones = Array.from(set)
    .sort((a, b) => a.localeCompare(b))
    .map(nombre => ({ valor: nombre, etiqueta: nombre, seleccionado: true }));

  this.subcategoriasDisponibles = opciones;
  this.subcategoriasFiltradas  = [...opciones];
  this.temporalSeleccionados['subcategoria'] = opciones.map(o => ({ ...o }));
  return;
}


  // 4) Caso especial: DETALLE (toma nombre textual si viene en jerarquía)
  if (columna === 'detalle') {
    this.hidratarDetalleEnTickets();

    const set = new Set<string>();

    (baseOpciones || []).forEach((t: any) => {
      set.add(t.detalle_filtro || t.detalle_visible || '—');
    });


    
    const opciones = Array.from(set)
      .sort((a, b) => a.localeCompare(b))
      .map(nombre => ({ valor: nombre, etiqueta: nombre, seleccionado: true }));

    this.detallesDisponibles = opciones;
    this.detallesFiltrados = [...opciones];
    this.temporalSeleccionados['detalle'] = opciones.map(o => ({ ...o }));
    return;
  }

    // 5) Resto de columnas (flujo genérico)
    const etiquetaResolver = (col: string, v: string) => {
      if (col === 'categoria' || col === 'subcategoria' || col === 'detalle') {
        return this.etiquetaCatalogoPorId(v);
      }
      return v;
    };

  const opciones = Array.from(setGen)
    .sort((a, b) => etiquetaResolver(columna, a).localeCompare(etiquetaResolver(columna, b)))
    .map(v => ({
      valor: v,
      etiqueta: etiquetaResolver(columna, v),
      seleccionado: true
    }));

  const plural = this.obtenerPluralColumna(columna);
  (this as any)[`${plural}Disponibles`] = opciones;
  (this as any)[`${plural}Filtradas`]  = [...opciones];
  this.temporalSeleccionados[columna]  = opciones.map(o => ({ ...o }));

}





  private rutasFiltro: Record<string, string> = {
    categoria: 'categoria',
    descripcion: 'descripcion',
    username: 'username',
    estado: 'estado',
    criticidad: 'criticidad',
    departamento: 'departamento',
    subcategoria: 'subcategoria',
    detalle: 'detalle',
    inventario: 'inventario.nombre',
    sucursal: 'sucursal'
  };

onAbrirFiltro(columna: string, trigger: any) {
  console.log('🟢 Abriendo filtro para columna:', columna);

  if (columna === 'sucursal') {
    this.hidratarSucursalEnTickets();
  }

  if (columna === 'detalle') {
    this.hidratarDetalleEnTickets();
  }

  const seleccionActiva = this.obtenerSeleccionActivaDeFiltro(columna);

  if (this.rutasFiltro[columna]) {
    this.prepararOpcionesFiltro(columna, this.rutasFiltro[columna]);
    this.restaurarSeleccionActivaDeFiltro(columna, seleccionActiva);
  }

  // 👇 evita que un texto previo esconda opciones
  if (columna === 'subcategoria') {
    this.filtroSubcategoriaTexto = '';
  }

  this.inicializarTemporales(columna);
  this.filtrarOpcionesTexto(columna);
  setTimeout(() => trigger?.openMenu?.(), 0);
}

cerrarYAplicar(columna: string, trigger: MatMenuTrigger): void {
  if (columna === 'detalle') {
    this.hidratarDetalleEnTickets();
  }

  this.confirmarFiltroColumna(columna);
  this.sincronizarDisponiblesDesdeTemporal(columna);

  if (!this.columnaTieneFiltroReal(columna)) {
    this.limpiarTextoFiltroColumnaLocal(columna);
  }

  this.aplicarFiltrosDeTablaConContexto();

  trigger.closeMenu();
}

private obtenerValoresSeleccionadosDesdeTemporal(columna: string): Set<string> {
  const temporales = this.temporalSeleccionados[columna] || [];

  return new Set(
    temporales
      .filter((opcion: any) => opcion.seleccionado)
      .map((opcion: any) => String(opcion.valor))
  );
}

private sincronizarDisponiblesDesdeValoresSeleccionados(
  columna: string,
  valoresSeleccionados: Set<string>
): void {
  const plural = this.obtenerPluralFiltro(columna);

  if (!plural) {
    return;
  }

  const disponibles = ((this as any)[`${plural}Disponibles`] || []) as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  if (!Array.isArray(disponibles) || disponibles.length === 0) {
    return;
  }

  const normalizados = disponibles.map((opcion) => ({
    valor: opcion.valor,
    etiqueta: opcion.etiqueta ?? opcion.valor,
    seleccionado: valoresSeleccionados.has(String(opcion.valor)),
  }));

  (this as any)[`${plural}Disponibles`] = normalizados;
  (this as any)[`${plural}Filtradas`] = [...normalizados];
  this.temporalSeleccionados[columna] = normalizados.map((opcion: any) => ({ ...opcion }));
}

private aplicarFiltrosDeTablaConContexto(): void {
  this.hidratarSucursalEnTickets();
  this.hidratarDetalleEnTickets();

  const filtrosActivos = obtenerFiltrosActivos(this);

  Object.keys(filtrosActivos).forEach((key) => {
    const valores = filtrosActivos[key];

    if (!Array.isArray(valores) || valores.length === 0) {
      delete filtrosActivos[key];
    }
  });

  const filtrosInventario = filtrosActivos['inventario'] || [];
  const filtrosDetalle = filtrosActivos['detalle'] || [];

  delete filtrosActivos['inventario'];
  delete filtrosActivos['detalle'];
  delete filtrosActivos['descripcion'];

  const base = this.obtenerBaseConModoYFechas();

  let resultado =
    Object.keys(filtrosActivos).length === 0
      ? [...base]
      : filtrarTicketsConFiltros(base, filtrosActivos);

  if (Array.isArray(filtrosInventario) && filtrosInventario.length > 0) {
    const valoresInventario = new Set(
      filtrosInventario.map((valor: any) => this.normalizarTextoFiltro(valor))
    );

    resultado = resultado.filter((ticket: any) => {
      const inventarioTicket = this.normalizarTextoFiltro(
        ticket.inventario?.nombre || '—'
      );

      return valoresInventario.has(inventarioTicket);
    });
  }

  if (Array.isArray(filtrosDetalle) && filtrosDetalle.length > 0) {
    const valoresDetalle = new Set(
      filtrosDetalle.map((valor: any) => this.normalizarTextoFiltro(valor))
    );

    resultado = resultado.filter((ticket: any) => {
      const detalleTicket = this.normalizarTextoFiltro(
        ticket.detalle_filtro ||
        ticket.detalle_visible ||
        this.getDetalleVisible(ticket)
      );

      return valoresDetalle.has(detalleTicket);
    });
  }

  const textoDescripcion = this.normalizarTextoFiltro(
    this.filtroDescripcionAplicadoTexto || ''
  );

  if (textoDescripcion) {
    resultado = resultado.filter((ticket: Ticket) => {
      const descripcion = this.normalizarTextoFiltro(ticket.descripcion || '');
      return descripcion.includes(textoDescripcion);
    });
  }

  this.filteredTickets = resultado;
  this.actualizarVistaTicketsFiltrados();
}

private limpiarTextoFiltroColumnaLocal(columna: string): void {
  if (columna === 'categoria') this.filtroCategoriaTexto = '';
  if (columna === 'descripcion') {
    this.filtroDescripcionTexto = '';
    this.filtroDescripcionAplicadoTexto = '';
  }
  if (columna === 'username') this.filtroUsuarioTexto = '';
  if (columna === 'estado') this.filtroEstadoTexto = '';
  if (columna === 'criticidad') this.filtroCriticidadTexto = '';
  if (columna === 'departamento') this.filtroDeptoTexto = '';
  if (columna === 'subcategoria') this.filtroSubcategoriaTexto = '';
  if (columna === 'detalle') this.filtroDetalleTexto = '';
  if (columna === 'inventario') this.filtroInventarioTexto = '';
  if (columna === 'sucursal') this.filtroSucursalTexto = '';
}

private aplicarFiltroInventarioConReset(valoresSeleccionados: Set<string>): void {
  this.page = 1;
  this.hidratarSucursalEnTickets();

  this.sincronizarDisponiblesDesdeValoresSeleccionados(
    'inventario',
    valoresSeleccionados
  );

  if (!this.columnaTieneFiltroReal('inventario')) {
    this.filtroInventarioTexto = '';
    this.reaplicarFiltrosSinColumna('inventario');
    return;
  }

  const filtrosActivos = obtenerFiltrosActivos(this);
  const filtrosSinInventario = { ...filtrosActivos };
  delete filtrosSinInventario['inventario'];

  const base = this.obtenerBaseConModoYFechas();

  const baseFiltrada =
    Object.keys(filtrosSinInventario).length === 0
      ? [...base]
      : filtrarTicketsConFiltros(base, filtrosSinInventario);

  const valoresNormalizados = new Set(
    Array.from(valoresSeleccionados).map((valor) =>
      this.normalizarTextoFiltro(valor)
    )
  );

  this.filteredTickets = baseFiltrada.filter((ticket: any) => {
    const inventarioTicket = this.normalizarTextoFiltro(
      ticket.inventario?.nombre || '—'
    );

    return valoresNormalizados.has(inventarioTicket);
  });

  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

  this.changeDetectorRef.detectChanges();
}

private reaplicarFiltrosSinColumna(columna: string): void {
  const filtrosActivos = obtenerFiltrosActivos(this);
  delete filtrosActivos[columna];

  const base = this.obtenerBaseConModoYFechas();

  this.filteredTickets =
    Object.keys(filtrosActivos).length === 0
      ? [...base]
      : filtrarTicketsConFiltros(base, filtrosActivos);

  this.page = 1;
  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

  this.changeDetectorRef.detectChanges();
}

private aplicarFiltroDetalleConReset(): void {
  this.page = 1;
  this.hidratarDetalleEnTickets();
  this.hidratarSucursalEnTickets();

  const filtrosActivos = obtenerFiltrosActivos(this);

  const valoresDetalle = new Set(
    ((filtrosActivos['detalle'] || []) as any[]).map((valor) =>
      this.normalizarTextoFiltro(valor)
    )
  );

  const filtrosSinDetalle = { ...filtrosActivos };
  delete filtrosSinDetalle['detalle'];

  const base = Array.isArray(this.ticketsCompletos) && this.ticketsCompletos.length > 0
    ? this.ticketsCompletos
    : this.tickets;

  const baseFiltrada =
    Object.keys(filtrosSinDetalle).length === 0
      ? [...base]
      : filtrarTicketsConFiltros(base, filtrosSinDetalle);

  this.filteredTickets =
    valoresDetalle.size === 0
      ? baseFiltrada
      : baseFiltrada.filter((ticket: any) => {
          const detalleTicket = this.normalizarTextoFiltro(
            ticket.detalle_filtro ||
            ticket.detalle_visible ||
            this.getDetalleVisible(ticket)
          );

          return valoresDetalle.has(detalleTicket);
        });

  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

  this.changeDetectorRef.detectChanges();
}

private sincronizarDisponiblesDesdeTemporal(columna: string): void {
  const plural = this.obtenerPluralFiltro(columna);

  if (!plural) {
    return;
  }

  const temporales = (this.temporalSeleccionados[columna] || []) as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  if (!Array.isArray(temporales)) {
    return;
  }

  const disponiblesActuales = ((this as any)[`${plural}Disponibles`] || []) as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  const baseMaestra = disponiblesActuales.length > 0
    ? disponiblesActuales
    : temporales;

  const textoActivo = this.normalizarTextoFiltro(
    this.obtenerTextoFiltroColumna(columna)
  ).length > 0;

  const valoresTemporales = new Set(
    temporales.map((opcion) => String(opcion.valor))
  );

  const seleccionTemporalPorValor = new Map<string, boolean>(
    temporales.map((opcion) => [
      String(opcion.valor),
      Boolean(opcion.seleccionado),
    ])
  );

  const normalizados = baseMaestra.map((opcion: any) => {
    const valorKey = String(opcion.valor);

    let seleccionado = Boolean(opcion.seleccionado);

    if (textoActivo) {
      seleccionado = valoresTemporales.has(valorKey)
        ? Boolean(seleccionTemporalPorValor.get(valorKey))
        : false;
    } else if (seleccionTemporalPorValor.has(valorKey)) {
      seleccionado = Boolean(seleccionTemporalPorValor.get(valorKey));
    }

    return {
      valor: opcion.valor,
      etiqueta: opcion.etiqueta ?? opcion.valor,
      seleccionado,
    };
  });

  (this as any)[`${plural}Disponibles`] = normalizados;
  (this as any)[`${plural}Filtradas`] = [...normalizados];
  this.temporalSeleccionados[columna] = normalizados.map((opcion: any) => ({ ...opcion }));
}

cerrarYLimpiar(columna: string, trigger?: any): void {
  const plural = this.obtenerPluralFiltro(columna);

  if (plural) {
    const disponibles = ((this as any)[`${plural}Disponibles`] || []) as Array<{
      valor: any;
      etiqueta?: string;
      seleccionado: boolean;
    }>;

    const normalizados = disponibles.map((opcion: any) => ({
      ...opcion,
      seleccionado: true,
    }));

    (this as any)[`${plural}Disponibles`] = normalizados;
    (this as any)[`${plural}Filtradas`] = [...normalizados];
    this.temporalSeleccionados[columna] = normalizados.map((opcion: any) => ({ ...opcion }));
  }

  this.limpiarTextoFiltroColumnaLocal(columna);
  this.reaplicarFiltrosSinColumna(columna);

  trigger?.closeMenu?.();
}



aplicarFiltroColumnaConReset = (col: string) => aplicarFiltroColumnaConReset(this, col);

  isItemSeleccionado(columna: string, valor: string): boolean {
  return this.temporalSeleccionados[columna]?.find(x => x.valor === valor)?.seleccionado ?? false;
}

  /** Sólo estas columnas muestran buscador de texto */
permiteBusqueda(col: string): boolean {
  return ['categoria','descripcion','inventario','estado','departamento','subcategoria','detalle','sucursal','username','criticidad'].includes(col);
}


cambiarEstadoEnProgreso(ticket: Ticket) {
  if (!ticket.fecha_solucion) {
    this.ticketParaAsignarFecha = ticket;
    this.fechaSolucionTentativa = null;
    this.showModalAsignarFecha = true;
  } else {
    this.cambiarEstado(ticket, 'en progreso');
  }
}


onGuardarFechaSolucion(event: {
  fecha: Date;
  motivo: string;
  necesita_refaccion?: boolean;
  descripcion_refaccion?: string;
  refaccion_definida_por_jefe?: boolean;
}) {
  if (!this.ticketParaAsignarFecha) return;

  if (!event.motivo || !event.motivo.trim()) {
    mostrarAlertaToast('Debes ingresar un motivo para el cambio de fecha.', 'error');
    return;
  }

  const id = this.ticketParaAsignarFecha.id;
  const tieneExtras = !!event.refaccion_definida_por_jefe;

  // Guardamos aquí solo para el parcheo visual inmediato (el helper lo usa para pintar el ícono),
  // pero ya NO volveremos a mandar estos campos en el segundo PUT (/update/:id).
  this.extrasCompromisoRefaccion = tieneExtras
    ? {
        necesita_refaccion: !!event.necesita_refaccion,
        descripcion_refaccion: event.necesita_refaccion ? (event.descripcion_refaccion || '') : '',
        refaccion_definida_por_jefe: true,
      }
    : null;

  // Continuación del flujo: poner "en progreso" y refrescar tabla
  const continuar = () => {
    asignarFechaSolucionYEnProgreso(
      this,
      this.ticketParaAsignarFecha!,
      event.fecha,
      event.motivo,
      () => {
        this.showModalAsignarFecha = false;
        this.ticketParaAsignarFecha = null;
        this.extrasCompromisoRefaccion = null;
      }
    );
  };

  // Si hay refacción definida por el jefe, primero fija el compromiso/refacción
  if (tieneExtras) {
    // 07:00 local → ISO (tu backend lo guarda en UTC)
    const fechaSolucion07ISO = new Date(
      event.fecha.getFullYear(),
      event.fecha.getMonth(),
      event.fecha.getDate(),
      7, 0, 0
    ).toISOString();

    const bodyCompromiso = {
      fecha_solucion: fechaSolucion07ISO,
      necesita_refaccion: !!event.necesita_refaccion,
      descripcion_refaccion: event.necesita_refaccion ? (event.descripcion_refaccion || '') : '',
      // El backend marca refaccion_definida_por_jefe=true si recibe necesita_refaccion (no es obligatorio enviarlo)
      // refaccion_definida_por_jefe: true,
    };

    this.ticketService.setCompromiso(id, bodyCompromiso).subscribe({
      next: () => continuar(),
      error: (err) => {
        this.extrasCompromisoRefaccion = null;  // limpia para no parchar UI
        mostrarAlertaToast('No se pudo guardar el compromiso/refacción.', 'error');
        console.error(err);
      }
    });
  } else {
    // Sin refacción extra → directo a "en progreso"
    continuar();
  }
}





onCancelarAsignarFecha() {
  this.showModalAsignarFecha = false;
  this.ticketParaAsignarFecha = null;
}

abrirEditarFechaSolucion(ticket: Ticket) {
  const estado = (ticket.estado ?? '').toString().trim().toLowerCase();
  if (estado !== 'en progreso') return; // ✅ solo editable en progreso

  const dialogRef = this.dialog.open(EditarFechaSolucionModalComponent, {
    width: '560px',
    maxWidth: '92vw',
    data: { fechaActual: ticket.fecha_solucion }
  });

  dialogRef.afterClosed().subscribe(result => {
    if (result && result.fecha && result.motivo) {
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
  if (!ticket.inventario || !ticket.inventario.nombre)
    return "—";

  // Normaliza a lowercase para evitar errores por mayúsculas/minúsculas
  const dep = (ticket.departamento || '').toLowerCase();
  const cat = (ticket.jerarquia_clasificacion?.[1] || '').toLowerCase();

  // Mostrar nombre + últimos 2 dígitos SOLO si es Mantenimiento/Aparatos
  if (dep === 'mantenimiento' && cat === 'aparatos' && ticket.inventario.codigo_interno) {
    const codigo = ticket.inventario.codigo_interno;
    const numerador = codigo.slice(-2);
    return `${ticket.inventario.nombre} ${numerador}`;
  }

  // Para sistemas/dispositivos y otros, solo nombre
  return ticket.inventario.nombre;
}

getSubcategoriaVisible(t: Ticket): string {
  if (t?.subcategoria) return t.subcategoria;
  // Fallback legacy por si algún ticket viejo no trae el campo
  const invSub = t?.inventario?.subcategoria?.toString().trim();
  if (invSub) return invSub;
  const dep = (t.departamento || '').toLowerCase();
  const cat = (t.jerarquia_clasificacion?.[1] || '').toLowerCase();
  if (dep === 'sistemas' && cat === 'dispositivos' && t.inventario?.categoria) {
    return t.inventario.categoria;
  }
  return t.jerarquia_clasificacion?.[2] || '—';
}


getNombreSucursal(ticket: Ticket): string {
  const ticketAny = ticket as any;

  const nombreDirecto =
    ticketAny.sucursal_nombre_destino ||
    ticketAny.sucursal_nombre ||
    ticketAny.sucursal_destino?.sucursal ||
    ticketAny.sucursal_destino?.nombre ||
    ticketAny.sucursal?.sucursal ||
    ticketAny.sucursal?.nombre;

  if (nombreDirecto) {
    return String(nombreDirecto);
  }

  const sucursalActual = ticketAny.sucursal;

  if (
    typeof sucursalActual === 'string' &&
    sucursalActual.trim() !== '' &&
    !/^\d+$/.test(sucursalActual.trim())
  ) {
    return sucursalActual;
  }

  const idRaw =
    ticketAny.sucursal_id_destino ??
    ticketAny.sucursal_destino_id ??
    ticketAny.sucursal_id ??
    ticketAny.id_sucursal ??
    ticketAny.sucursal;

  const id = Number(idRaw);

  if (Number.isFinite(id)) {
    return this.sucursalIdNombreMap[id] || String(id);
  }

  return idRaw != null ? String(idRaw) : '—';
}



get kpiTicketsActivosBd(): number {
  return (this.ticketsCompletos || []).filter((ticket: Ticket) => {
    return this.normalizarEstadoTicket(ticket) !== 'finalizado';
  }).length;
}

get kpiTicketsAbiertosBd(): number {
  return (this.ticketsCompletos || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'abierto'
  ).length;
}

get kpiTicketsEnProgresoBd(): number {
  return (this.ticketsCompletos || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'en progreso'
  ).length;
}

get kpiTicketsPorValidarBd(): number {
  return (this.ticketsCompletos || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'por_validar'
  ).length;
}

get kpiTicketsFinalizadosBd(): number {
  return (this.ticketsCompletos || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'finalizado'
  ).length;
}

get kpiTicketsCriticosBd(): number {
  return (this.ticketsCompletos || []).filter((ticket: Ticket) => {
    const estado = this.normalizarEstadoTicket(ticket);
    return estado !== 'finalizado' && this.esTicketCritico(ticket);
  }).length;
} 

private aplicarFiltroRapidoColumna(columna: string, valores: string[]): void {
  const plural = this.obtenerPluralFiltro(columna);

  if (!plural) {
    return;
  }

  const disponibles = ((this as any)[`${plural}Disponibles`] || []) as Array<{
    valor: any;
    etiqueta?: string;
    seleccionado: boolean;
  }>;

  if (!Array.isArray(disponibles) || disponibles.length === 0) {
    return;
  }

  const valoresSet = new Set(valores.map(valor => String(valor)));

  const actualizados = disponibles.map(opcion => ({
    ...opcion,
    seleccionado: valoresSet.has(String(opcion.valor)),
  }));

  (this as any)[`${plural}Disponibles`] = actualizados;
  (this as any)[`${plural}Filtradas`] = [...actualizados];
  this.temporalSeleccionados[columna] = actualizados.map((opcion: any) => ({ ...opcion }));

  this.aplicarFiltrosDeTablaConContexto();
  this.changeDetectorRef.detectChanges();
}

private parseTicketDate(value: any): Date | null {
  if (!value) {
    return null;
  }

  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value;
  }

  const texto = String(value).trim();

  if (!texto) {
    return null;
  }

  // ISO: 2026-05-15T...
  if (/^\d{4}-\d{2}-\d{2}/.test(texto)) {
    const fecha = new Date(texto);
    return Number.isNaN(fecha.getTime()) ? null : fecha;
  }

  // dd/mm/yyyy o dd/mm/yy con hora opcional
  const match = texto.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);

  if (match) {
    const dia = Number(match[1]);
    const mes = Number(match[2]);
    let anio = Number(match[3]);

    if (anio < 100) {
      anio += 2000;
    }

    const fecha = new Date(anio, mes - 1, dia);
    return Number.isNaN(fecha.getTime()) ? null : fecha;
  }

  const fallback = new Date(texto);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

private normalizarDia(fecha: Date): Date {
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate());
}

private fechaEnRango(fecha: Date | null, start: Date | null, end: Date | null): boolean {
  if (!fecha) {
    return false;
  }

  const dia = this.normalizarDia(fecha);
  const desde = start ? this.normalizarDia(start) : null;
  const hasta = end ? this.normalizarDia(end) : null;

  if (desde && dia < desde) {
    return false;
  }

  if (hasta && dia > hasta) {
    return false;
  }

  return true;
}

private ticketCumpleFiltrosFecha(ticket: Ticket): boolean {
  if (this.filtroCreacionActivo) {
    const fechaCreacion = this.parseTicketDate(
      ticket.fecha_creacion_original ?? ticket.fecha_creacion
    );

    if (!this.fechaEnRango(
      fechaCreacion,
      this.rangoFechaCreacionSeleccionado.start,
      this.rangoFechaCreacionSeleccionado.end
    )) {
      return false;
    }
  }

  if (this.filtroProgresoActivo) {
    const fechaProgreso = this.parseTicketDate(ticket.fecha_en_progreso);

    if (!fechaProgreso && this.incluirSinFechaProgreso) {
      // permitido
    } else if (!this.fechaEnRango(
      fechaProgreso,
      this.rangoFechaProgresoSeleccionado.start,
      this.rangoFechaProgresoSeleccionado.end
    )) {
      return false;
    }
  }

  if (this.filtroFinalizadoActivo) {
    const fechaFinalizado = this.parseTicketDate(
      ticket.fecha_finalizado_original ?? ticket.fecha_finalizado
    );

    if (!fechaFinalizado && this.incluirSinFechaFinalizado) {
      // permitido
    } else if (!this.fechaEnRango(
      fechaFinalizado,
      this.rangoFechaFinalSeleccionado.start,
      this.rangoFechaFinalSeleccionado.end
    )) {
      return false;
    }
  }

  return true;
}

private obtenerBaseConModoYFechas(): Ticket[] {
  const base = Array.isArray(this.ticketsCompletos) && this.ticketsCompletos.length > 0
    ? this.ticketsCompletos
    : this.tickets;

  return base.filter((ticket: Ticket) => {
    const estado = this.normalizarEstadoTicket(ticket);

    // Si estás filtrando por fecha finalizado, permitimos ver finalizados.
  const hayFiltroFechaActivo =
    this.filtroCreacionActivo ||
    this.filtroProgresoActivo ||
    this.filtroFinalizadoActivo;

  const debeOcultarFinalizados =
    this.ocultarFinalizados && !hayFiltroFechaActivo;

  if (debeOcultarFinalizados && estado === 'finalizado') {
    return false;
  }

    return this.ticketCumpleFiltrosFecha(ticket);
  });
}

private obtenerPluralColumna(columna: string): string {
  const pluralMap: Record<string, string> = {
    categoria: 'categorias',
    descripcion: 'descripciones',
    username: 'usuarios',
    estado: 'estados',
    criticidad: 'criticidades',
    departamento: 'departamentos',
    subcategoria: 'subcategorias',
    detalle: 'detalles',
    inventario: 'inventarios',
    sucursal: 'sucursales'
  };
  return pluralMap[columna] ?? `${columna}s`;
}


// Devuelve el nombre de catálogo por id (o el id si no lo encuentra)
private etiquetaCatalogoPorId(id: any): string {
  const num = Number(id);
  const item = this.categoriasCatalogo.find(c => c.id === num);
  return item?.nombre ?? String(id);
}


private resetearFiltrosParaCard(incluirFinalizados: boolean): void {
  this.ocultarFinalizados = !incluirFinalizados;
  this.limpiarTodosLosFiltros();
}

private sincronizarFiltroCardEstado(estado: string): void {
  const estadoNormalizado = this.normalizarTextoFiltro(estado);

  const opcionesBase =
    Array.isArray(this.estadosDisponibles) && this.estadosDisponibles.length > 0
      ? this.estadosDisponibles
      : Array.from(
          new Set(
            (this.ticketsCompletos || [])
              .map((ticket: Ticket) => ticket.estado)
              .filter(Boolean)
          )
        ).map((valor) => ({
          valor,
          etiqueta: valor,
          seleccionado: true,
        }));

  const actualizados = opcionesBase.map((opcion: any) => ({
    ...opcion,
    seleccionado: this.normalizarTextoFiltro(opcion.valor) === estadoNormalizado,
  }));

  this.estadosDisponibles = actualizados;
  this.estadosFiltrados = [...actualizados];
  this.temporalSeleccionados['estado'] = actualizados.map((opcion: any) => ({
    ...opcion,
  }));
}

private sincronizarFiltroCardCriticidadCriticos(): void {
  const opcionesBase =
    Array.isArray(this.criticidadesDisponibles) && this.criticidadesDisponibles.length > 0
      ? this.criticidadesDisponibles
      : Array.from(
          new Set(
            (this.ticketsCompletos || [])
              .map((ticket: Ticket) => ticket.criticidad)
              .filter((valor) => valor !== null && valor !== undefined)
          )
        ).map((valor) => ({
          valor,
          etiqueta: String(valor),
          seleccionado: true,
        }));

  const actualizados = opcionesBase.map((opcion: any) => ({
    ...opcion,
    seleccionado: Number(opcion.valor) >= 4,
  }));

  this.criticidadesDisponibles = actualizados;
  this.criticidadesFiltradas = [...actualizados];
  this.temporalSeleccionados['criticidad'] = actualizados.map((opcion: any) => ({
    ...opcion,
  }));
}

filtrarCardActivos(): void {
  this.resetearFiltrosParaCard(false);
}

filtrarCardEstado(estado: string): void {
  const estadoNormalizado = this.normalizarTextoFiltro(estado);
  const esFinalizado = estadoNormalizado === 'finalizado';

  // Cada card parte de cero.
  this.resetearFiltrosParaCard(esFinalizado);

  // Sincroniza header/checklist de Estado para que parezca filtro real.
  this.sincronizarFiltroCardEstado(estado);

  const base = Array.isArray(this.ticketsCompletos) && this.ticketsCompletos.length > 0
    ? this.ticketsCompletos
    : this.tickets;

  this.filteredTickets = base.filter((ticket: Ticket) => {
    return this.normalizarTextoFiltro(ticket.estado) === estadoNormalizado;
  });

  this.actualizarVistaTicketsFiltrados();
}

filtrarCardCriticos(): void {
  // Críticos vuelve a la vista operativa: sin finalizados.
  this.resetearFiltrosParaCard(false);

  // Sincroniza header/checklist de Criticidad.
  this.sincronizarFiltroCardCriticidadCriticos();

  const base = Array.isArray(this.ticketsCompletos) && this.ticketsCompletos.length > 0
    ? this.ticketsCompletos
    : this.tickets;

  this.filteredTickets = base.filter((ticket: Ticket) => {
    const estado = this.normalizarEstadoTicket(ticket);
    return estado !== 'finalizado' && this.esTicketCritico(ticket);
  });

  this.actualizarVistaTicketsFiltrados();
}


abrirConfirmacion(titulo: string, mensaje: string): Promise<boolean> {
  const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
    width: '460px',
    data: {
      titulo,
      mensaje,
      textoAceptar: 'Aceptar',
      textoCancelar: 'Cancelar'
    }
  });

  return dialogRef.afterClosed().toPromise();
}



async solicitarCierre(ticket: Ticket) {
  if (!ticket?.id) {
    mostrarAlertaToast('Ticket inválido.', 'error');
    return;
  }

  // 🔹 1. Abrir modal de cierre y esperar datos
  const dialogRef = this.dialog.open(ModalCierreTicketComponent, {
    width: '560px',
    data: { ticketId: ticket.id }
  });

  const result = await dialogRef.afterClosed().toPromise();

  // Usuario canceló el modal
  if (!result) {
    return;
  }

  const { costo, notas } = result;

  // 🔹 2. El modal ya actúa como confirmación; se elimina confirmación secundaria
  this.ticketService.cierreSolicitar(ticket.id, {
    costo_solucion: costo,
    notas_cierre: notas
  }).subscribe({
    next: (resp) => {
      mostrarAlertaToast(resp?.mensaje || 'Cierre solicitado.', 'success');
      this.refrescarTicketsPreservandoFiltros();
    },
    error: (err) => {
      mostrarAlertaToast(err?.error?.mensaje || 'Error al solicitar cierre', 'error');
    }
  });
}


private esAdminParaCierreDesdeCero(): boolean {
  const rol = (this.user?.rol || '').toString().trim().toUpperCase();
  return ['ADMIN', 'ADMINISTRADOR', 'SUPER_ADMIN'].includes(rol);
}

private esGerenteParaCierreDesdeCero(): boolean {
  const rol = (this.user?.rol || '').toString().trim().toUpperCase();
  return rol === 'GERENTE';
}

private ticketPerteneceASucursalDelGerente(ticket: Ticket): boolean {
  const sucursalUsuario = Number(this.user?.sucursal_id);
  const sucursalTicket = Number(
    ticket.sucursal_id_destino ?? (ticket as any).sucursal_id
  );

  if (!sucursalUsuario || !sucursalTicket) return false;

  return sucursalUsuario === sucursalTicket;
}

puedeMostrarBotonCerrarDesdeCero(ticket: Ticket): boolean {
  if (!ticket?.id) return false;

  const estado = (ticket.estado || '').toString().trim().toLowerCase();

  const esEstadoPermitido = estado === 'abierto' || estado === 'en progreso';
  const noEstaFinalizado = !ticket.fecha_finalizado;

  if (!esEstadoPermitido || !noEstaFinalizado) return false;

  if (this.esAdminParaCierreDesdeCero()) return true;

  if (this.esGerenteParaCierreDesdeCero()) {
    return this.ticketPerteneceASucursalDelGerente(ticket);
  } 

  return false;
}

async cerrarDesdeCeroPorGerente(ticket: Ticket): Promise<void> {
  if (!ticket?.id) {
    mostrarAlertaToast('Ticket inválido.', 'error');
    return;
  }

  if (!this.puedeMostrarBotonCerrarDesdeCero(ticket)) {
    mostrarAlertaToast('No tienes permisos para cerrar este ticket desde cero.', 'error');
    return;
  }

  // 🔹 1. Abrir modal de cierre gerente y esperar datos
  const dialogRef = this.dialog.open(ModalCierreTicketComponent, {
    width: '560px',
    data: {
      ticketId: ticket.id,
      modo: 'cierre_desde_cero'
    }
  });

  const result = await dialogRef.afterClosed().toPromise();

  // Usuario canceló el modal
  if (!result) {
    return;
  }

  const motivo = (result.motivo || result.notas || '').toString().trim();

  if (!motivo) {
    mostrarAlertaToast('El motivo de cierre es obligatorio.', 'error');
    return;
  }

  // 🔹 2. El modal ya actúa como confirmación; se elimina confirmación secundaria
  this.ticketService.cierreGerenteDesdeCero(ticket.id, { motivo }).subscribe({
    next: (resp) => {
      mostrarAlertaToast(resp?.mensaje || 'Ticket finalizado correctamente.', 'success');
      this.refrescarTicketsPreservandoFiltros();
    },
    error: (err) => {
      mostrarAlertaToast(
        err?.error?.mensaje || 'No se pudo cerrar el ticket desde cero.',
        'error'
      );
    }
  });
}

async aceptarCierre(ticket: Ticket) {
  const ok = await this.abrirConfirmacion(
    'Aceptar cierre',
    `¿Confirmas que el ticket #${ticket.id} fue resuelto correctamente?`
  );

  if (!ok) return;

  this.ticketService.cierreAceptarCreador(ticket.id).subscribe({
    next: (resp) => {
      mostrarAlertaToast(resp?.mensaje || 'Cierre aceptado.', 'success');
      this.refrescarTicketsPreservandoFiltros();
    },
    error: (err) => {
      mostrarAlertaToast(err?.error?.mensaje || 'No se pudo aceptar el cierre.', 'error');
    }
  });
}



async rechazarCierre(ticket: Ticket): Promise<void> {
  if (!ticket?.id) {
    mostrarAlertaToast('Ticket inválido.', 'error');
    return;
  }

  if (!this.puedeMostrarBotonesValidarCierre(ticket)) {
    mostrarAlertaToast('No tienes permisos para rechazar este cierre.', 'error');
    return;
  }

  const motivo = await solicitarMotivoRechazoCierre(
    ticket.id,
    ticket.descripcion
  );

  if (!motivo) return;

  const ok = await this.abrirConfirmacion(
    'Rechazar cierre',
    `¿Seguro que deseas rechazar el cierre del ticket #${ticket.id}?\n\n` +
    `Motivo: ${motivo}`
  );

  if (!ok) return;

  this.ticketService.cierreRechazarCreador(ticket.id, { motivo }).subscribe({
    next: (resp) => {
      mostrarAlertaToast(resp?.mensaje || 'Cierre rechazado.', 'success');
      this.refrescarTicketsPreservandoFiltros();
    },
    error: (err) => {
      mostrarAlertaToast(
        err?.error?.mensaje || 'No se pudo rechazar el cierre.',
        'error'
      );
    }
  });
}


esCreador(ticket: Ticket): boolean {
  return !!ticket && ticket.username === this.usuarioActual;
}

esPendienteCierreCreador(ticket: Ticket): boolean {
  return !!ticket &&
         ticket.estado_cierre === 'pendiente_creador' &&
         this.esCreador(ticket);
}

puedeMostrarBotonEnProgreso(ticket: Ticket): boolean {
  const estado = (ticket?.estado || '').trim().toLowerCase();
  return this.puedeEditarTickets && estado === 'abierto';
}

puedeMostrarBotonFinalizar(ticket: Ticket): boolean {
  const estado = (ticket?.estado || '').trim().toLowerCase();
  return this.puedeEditarTickets &&
         estado === 'en progreso' &&
         ticket?.estado_cierre !== 'pendiente_creador';
}

private esAdminParaValidarCierre(): boolean {
  const rol = (this.user?.rol || '').toString().trim().toUpperCase();
  return ['ADMIN', 'ADMINISTRADOR', 'SUPER_ADMIN'].includes(rol);
}

private esGerenteParaValidarCierre(): boolean {
  const rol = (this.user?.rol || '').toString().trim().toUpperCase();
  return rol === 'GERENTE';
}

private ticketPerteneceASucursalDelUsuario(ticket: Ticket): boolean {
  const sucursalUsuario = Number(this.user?.sucursal_id);
  const sucursalTicket = Number(
    ticket.sucursal_id_destino ?? (ticket as any).sucursal_id
  );

  if (!sucursalUsuario || !sucursalTicket) return false;

  return sucursalUsuario === sucursalTicket;
}

puedeMostrarBotonesValidarCierre(ticket: Ticket): boolean {
  if (!ticket?.id) return false;

  const estado = (ticket.estado || '').toString().trim().toLowerCase();
  const estadoCierre = (ticket.estado_cierre || '').toString().trim().toLowerCase();

  const estaPendienteDeValidacion =
    estado === 'por_validar' &&
    estadoCierre === 'pendiente_creador';

  if (!estaPendienteDeValidacion) return false;

  if (this.esAdminParaValidarCierre()) return true;

  if (this.esGerenteParaValidarCierre()) {
    return this.ticketPerteneceASucursalDelUsuario(ticket);
  }

  return false;
}







private etiquetaCampoUnificado: Record<'categoria' | 'estado' | 'departamento' | 'username' | 'sucursal' | 'criticidad' | 'subcategoria' | 'detalle', string> = {
  categoria: 'categoría',
  estado: 'estado',
  departamento: 'departamento',
  username: 'usuario',
  sucursal: 'sucursal',
  criticidad: 'criticidad',
  subcategoria: 'subcategoría', // 👈
  detalle: 'detalle',           // 👈
};

private etiquetaDepartamentoPorId(id: any): string {
  const num = Number(id);
  if (Number.isNaN(num)) return String(id);

  // 1) intenta en catálogo de departamentos
  const dep = (this.departamentos || []).find((d: any) =>
    d.id === num || d.departamento_id === num || d?.id_departamento === num
  );
  if (dep?.nombre) return dep.nombre;
  if (dep?.departamento) return dep.departamento;

  // 2) fallback: busca en los tickets
  const t = (this.ticketsCompletos || []).find((x: any) => x.departamento_id === num);
  return t?.departamento ?? String(id);
}

private actualizarVistaTicketsFiltrados(): void {
  this.page = 1;
  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);
  this.changeDetectorRef.detectChanges();
}

private normalizarEstadoTicket(ticket: Ticket): string {
  return (ticket?.estado || '').toString().trim().toLowerCase();
}

private esTicketCritico(ticket: Ticket): boolean {
  const criticidad = Number(ticket?.criticidad);
  return criticidad >= 4;
}

get kpiTicketsFiltrados(): number {
  return this.filteredTickets?.length || 0;
}

get kpiTicketsAbiertos(): number {
  return (this.filteredTickets || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'abierto'
  ).length;
}

get kpiTicketsEnProgreso(): number {
  return (this.filteredTickets || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'en progreso'
  ).length;
}

get kpiTicketsPorValidar(): number {
  return (this.filteredTickets || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'por_validar'
  ).length;
}

get kpiTicketsFinalizados(): number {
  return (this.filteredTickets || []).filter(
    ticket => this.normalizarEstadoTicket(ticket) === 'finalizado'
  ).length;
}

get kpiTicketsCriticos(): number {
  return (this.filteredTickets || []).filter(
    ticket => this.esTicketCritico(ticket)
  ).length;
}
//para cargar imagenes

/** Abre la evidencia en otra pestaña (si existe) */
openEvidencia(t: Ticket): void {
  const url = (t?.url_evidencia || '').trim();
  if (!url) {
    try { mostrarAlertaToast?.('Este ticket no tiene evidencia'); } catch {}
    return;
  }
  this.dialog.open(EvidenciaPreviewComponent, {
    data: { url, titulo: `Ticket #${t.id}` },
    width: 'min(90vw, 1100px)',
    maxWidth: '90vw',
    autoFocus: false,
    restoreFocus: false,
    panelClass: 'dlg-evidencia'
  });
}

/** Separa el prefijo [ALGO] (ej. [BUG]) del resto del texto de descripción */
getBugParts(desc: string): { prefix: string; rest: string } {
  const text = (desc || '').trim();
  const m = text.match(/^\s*(\[[^\]]+\])\s*(.*)$/);
  return m ? { prefix: m[1], rest: m[2] ?? '' } : { prefix: '', rest: text };
}

// Estado de expansión por ticket
isDescExpanded: Record<number, boolean> = {};

// Alternar expandido/colapsado
toggleDesc(id: number): void {
  this.isDescExpanded[id] = !this.isDescExpanded[id];
}



private norm(s?: string): string {
  return (s ?? '')
    .toString()
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

/** Lo que se debe mostrar en la columna DETALLE */
getDetalleVisible(t: Ticket): string {
  // Detecta Sistemas→Dispositivos usando los mismos campos que muestra la tabla
  const dep = this.norm(t.departamento);
  const catTabla = this.norm((t as any)?.categoria || t.jerarquia_clasificacion?.[1]);

  if (dep === 'sistemas' && catTabla === 'dispositivos') {
    return '—'; // en este flujo no hay detalle
  }

  // Si el backend mandó el nombre del nivel 4 en la jerarquía, úsalo
  const jerDet = t.jerarquia_clasificacion?.[3];
  if (jerDet) return jerDet;

  // Si viene id/valor en t.detalle, resuélvelo
  if (t.detalle != null && t.detalle !== '') {
    const num = Number(t.detalle);
    if (!Number.isNaN(num)) return this.etiquetaCatalogoPorId(num);
    return String(t.detalle);
  }

  return '—';
}

private hidratarDetalleEnTickets(): void {
  const poner = (arr: any[] | undefined) => {
    if (!Array.isArray(arr)) {
      return;
    }

    arr.forEach((ticket: any) => {
      if (ticket.__detalle_raw === undefined) {
        ticket.__detalle_raw = ticket.detalle;
      }

      const detalleVisible = this.getDetalleVisible({
        ...ticket,
        detalle: ticket.__detalle_raw,
      } as Ticket);

      ticket.detalle_visible = detalleVisible || '—';
      ticket.detalle_filtro = detalleVisible || '—';
    });
  };

  poner(this.ticketsCompletos);
  poner(this.tickets);
  poner(this.filteredTickets);
  poner(this.visibleTickets);
}

necesitaRef(t: any): boolean {
  // 1) Campo canónico del backend → devuelve enseguida si existe
  if (typeof t?.necesita_refaccion === 'boolean') return t.necesita_refaccion;

  // 2) Alias comunes por si viniera camelCase o con datos “raros”
  let v: any = t?.necesita_refaccion ?? t?.necesitaRefaccion ?? t?.necesitaRef;

  // Arrays tipo [true] o ["1"] → usa el primero
  if (Array.isArray(v)) v = v[0];

  // Numéricos
  if (typeof v === 'number') return v !== 0;

  // Bools sueltos
  if (v === true) return true;
  if (v === false || v == null) return false;

  // Strings normalizados
  const s = String(v)
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .trim().toLowerCase()
    .replace(/[\[\]\(\)\{\}"'\s]/g, '');

  if (!s) return false;

  // Marcas típicas de “verdadero”
  return new Set(['true','1','si','sí','y','yes','x','✓','v']).has(s);
}


}
