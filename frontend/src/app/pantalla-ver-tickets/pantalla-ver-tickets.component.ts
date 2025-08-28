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
import { mostrarAlertaToast } from '../utils/alertas';
import { SucursalesService } from '../services/sucursales.service';
import { EvidenciaPreviewComponent } from './modals/evidencia-preview.component';



// Filtro unificado (solo 'categoria' por ahora)
import {
  crearEstadoInicial,
  seleccionarCampo,
  aplicarFiltroActual,
  limpiarFiltroActual,
  filtrarTickets as filtrarTicketsUnificado,
  filtrarOpcionesPorTexto as filtrarOpcionesUnificado,
  alternarSeleccionTemporal,
  EstadoFiltroUnificado,
  aplicarFiltroColumnaConResetUnificado,
  limpiarFiltroColumnaUnificado,
  filtrarOpcionesPorTexto,

} from 'src/app/utils/filtro-unificado';
import { MatSelectModule } from '@angular/material/select';






// Interfaces
export interface Ticket {
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
  sucursalIdNombreMap: Record<number, string> = {};
  listaSucursales: any[] = [];


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


  mostrarFiltros: boolean = false; 


  historialVisible: Record<number, boolean> = {};
  fechasSolucionDisponibles = new Set<string>();

  rangoFechaCreacionSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaFinalSeleccionado = { start: null as Date | null, end: null as Date | null };
  rangoFechaProgresoSeleccionado = { start: null as Date | null, end: null as Date | null };




  // Estado del filtro unificado (UI global: rubro + opciones)
  filtroUnificado: EstadoFiltroUnificado = crearEstadoInicial();
  campoUnificadoActual: 'categoria' | 'estado' | 'departamento' | 'sucursal' | 'username' | 'criticidad' | 'subcategoria' | 'detalle' | null = null;
columnasUnificado: Array<{ key: 'categoria' | 'estado' | 'departamento' | 'sucursal' | 'username' | 'criticidad' | 'subcategoria' | 'detalle', label: string }> = [
  { key: 'categoria',    label: 'Categoría' },
  { key: 'estado',       label: 'Estado' },
  { key: 'departamento', label: 'Departamento' },
  { key: 'sucursal',     label: 'Sucursal' },
  { key: 'username',     label: 'Usuario' },
  { key: 'criticidad',   label: 'Criticidad' },
  { key: 'subcategoria', label: 'Subcategoría' },   // 👈 nuevo
  { key: 'detalle',      label: 'Detalle' },        // 👈 nuevo
];




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
    public catalogoService: CatalogoService,
    private sucursalesService: SucursalesService,
    
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

  this.sucursalesService.obtenerSucursales().subscribe({
  next: (sucs) => {
    this.listaSucursales = sucs || [];
    this.sucursalIdNombreMap = {};
    this.listaSucursales.forEach(s => {
      this.sucursalIdNombreMap[s.sucursal_id] = s.sucursal;
    });
    },
    error: (err) => console.error('Error al obtener sucursales:', err),
  });

    // 🔁 Escuchar eventos de refresco desde el servicio
    this.refrescoService.refrescarTabla$.subscribe(() => {
      TicketInit.cargarTickets(this); // recargar los tickets
    });

    console.log('Usuario:', this.user);
    console.log('Editor corporativo:', this.usuarioEsEditorCorporativo);

    this.changeDetectorRef.detectChanges();

      (window as any).verTicketsComp = this;
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


  
// Reemplazo completo dentro de PantallaVerTicketsComponent
filtrarOpcionesTexto(columna: string) {
  const capitalizar = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

  // Aliases para nombres “raros”
  const textoPropAlias: Record<string, string> = {
    departamento: 'filtroDeptoTexto',
    detalle: 'filtroDetalleTexto',
    inventario: 'filtroInventarioTexto',
    sucursal: 'filtroSucursalTexto',
  };

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

  const textoProp = textoPropAlias[columna] ?? `filtro${capitalizar(columna)}Texto`;
  const filtroTexto = (this[textoProp] || '').toLowerCase();
  const plural = pluralMap[columna];

  if (!plural) return;

  // ⚠️ CLAVE: Tomar como base la lista YA FILTRADA (si existe), NO los "Disponibles"
  const base =
    (Array.isArray(this[`${plural}Filtradas`]) && this[`${plural}Filtradas`].length)
      ? this[`${plural}Filtradas`]
      : (this[`${plural}Disponibles`] || []);

  if (!Array.isArray(base)) return;

  const normaliza = (x: any) => ((x?.etiqueta ?? x?.valor) ?? '')
    .toString()
    .toLowerCase();

  const filtradas = filtroTexto
    ? base.filter((item: any) => normaliza(item).includes(filtroTexto))
    : [...base];

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

private hidratarSucursalEnTickets(): void {
  const poner = (arr: any[] | undefined) => {
    if (!Array.isArray(arr)) return;
    arr.forEach((t: any) => {
      const id = t?.sucursal_id_destino ?? t?.sucursal_id;
      t.sucursal = this.sucursalIdNombreMap[id] || (id != null ? String(id) : '—');
    });
  };
  poner(this.tickets);
  poner(this.filteredTickets);
  poner(this.visibleTickets);
}


private prepararOpcionesFiltro(columna: string, path: string): void {
  const setGen = new Set<string>();

  // 1) Recolector genérico (se ignora si entramos a un caso especial)
  (this.filteredTickets || []).forEach((t: any) => {
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
    const set = new Set<string>();
    (this.filteredTickets || []).forEach((t: any) => {
      let label: string | null = null;
      if (t.jerarquia_clasificacion?.[3]) {
        label = t.jerarquia_clasificacion[3];
      } else if (t.detalle != null) {
        label = this.etiquetaCatalogoPorId(t.detalle);
      }
      set.add(label || '—');
    });

    const opciones = Array.from(set)
      .sort((a, b) => a.localeCompare(b))
      .map(nombre => ({ valor: nombre, etiqueta: nombre, seleccionado: true }));

    this.detallesDisponibles = opciones;
    this.detallesFiltrados  = [...opciones];
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

  if (this.rutasFiltro[columna]) {
    this.prepararOpcionesFiltro(columna, this.rutasFiltro[columna]);
  }

  // 👇 evita que un texto previo esconda opciones
  if (columna === 'subcategoria') this.filtroSubcategoriaTexto = '';

  this.inicializarTemporales(columna);
  this.filtrarOpcionesTexto(columna);
  setTimeout(() => trigger?.openMenu?.(), 0);
}


onCerrarFiltro(columna: string, trigger?: any): void {
  if (columna === 'categoria' || columna === 'estado' || columna === 'departamento') {
    aplicarFiltroColumnaConResetUnificado(this, columna);
    if (columna === 'categoria') this.refrescarPanelUnificado('categoria'); // opcional
    trigger?.closeMenu?.();
    return;
  }
  this.confirmarFiltroColumna(columna);
  setTimeout(() => trigger?.closeMenu?.(), 0);
}

cerrarYAplicar(columna: string, trigger: MatMenuTrigger): void {
  this.confirmarFiltroColumna(columna);

  if (columna === 'departamento') {
    const sel = (this.departamentosDisponibles || [])
      .filter((x: any) => x.seleccionado)
      .map((x: any) => x.valor);
    console.log('DEP seleccionados al aplicar:', sel);
  }

  if (columna === 'categoria' || columna === 'estado' || columna === 'departamento') {
    aplicarFiltroColumnaConResetUnificado(this, columna);
  } else {
    this.aplicarFiltroColumnaConReset(columna);
  }
  trigger.closeMenu();
}



cerrarYLimpiar(columna: string, trigger?: any): void {
  if (columna === 'categoria' || columna === 'estado' || columna === 'departamento') {
    limpiarFiltroColumnaUnificado(this, columna);
    trigger?.closeMenu?.();
    return;
  }
  (this as any).limpiarFiltroColumna?.(columna);
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
    mostrarAlertaToast('Debes ingresar un motivo para el cambio de fecha.');
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
  const estado = (ticket.estado ?? '').toString().trim().toLowerCase();
  if (estado === 'finalizado') {
    return; // ⛔ no abrir modal si ya está finalizado
  }

  const dialogRef = this.dialog.open(EditarFechaSolucionModalComponent, {
    width: '360px',
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

getSubcategoriaVisible(ticket: Ticket): string {

  const invSub = ticket?.inventario?.subcategoria?.toString().trim();
  if (invSub) return invSub;


  const dep = (ticket.departamento || '').toLowerCase();
  const cat = (ticket.jerarquia_clasificacion?.[1] || '').toLowerCase();

  if (
    dep === 'sistemas' &&
    cat === 'dispositivos' &&
    !!ticket.inventario?.categoria
  ) {
    return ticket.inventario.categoria;
  }

  return ticket.jerarquia_clasificacion?.[2] || '—';
}


getNombreSucursal(ticket: Ticket): string {
  const id = (ticket as any).sucursal_id_destino as number | undefined | null;
  if (!id) return '—';
  return this.sucursalIdNombreMap[id] || `${id}`;
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





//filtros unificados

/** Inicializa el filtro unificado SOLO para 'categoria'.
 *  Debes llamarlo cuando ya existan this.ticketsCompletos.
 */
initFiltroUnificadoSoloCategoria(): void {
  if (!Array.isArray(this.ticketsCompletos) || this.ticketsCompletos.length === 0) return;

  // Usamos tu mapeo real: id -> nombre de catálogo
  const formatters = {
    categoria: (valor: string) => this.etiquetaCatalogoPorId(valor), // ya existe en este componente
  };

  seleccionarCampo(this.filtroUnificado, this.ticketsCompletos as any, 'categoria', formatters);
}

/** Setea el texto de búsqueda sobre las opciones del checklist unificado (categoria). */
buscarCategoriaUnificada(texto: string): void {
  this.filtroUnificado.textoBusqueda = texto ?? '';
}

/** Opciones visibles (aplican texto de búsqueda sobre las opciones disponibles). */
get opcionesCategoriaUnificada() {
  return filtrarOpcionesUnificado(
    this.filtroUnificado.opcionesDisponibles,
    this.filtroUnificado.textoBusqueda
  );
}

/** Alterna un valor en la selección temporal del checklist (categoria). */
alternarSeleccionCategoriaUnificada(valor: string): void {
  alternarSeleccionTemporal(this.filtroUnificado, valor);
}


/** Limpia el filtro aplicado de 'categoria' y refresca la tabla. */
limpiarCategoriaUnificada(): void {
  const campo = this.campoUnificadoActual; 
  this.filtroUnificado.seleccionTemporal.clear();
  this.filtroUnificado.textoBusqueda = '';

  limpiarFiltroColumnaUnificado(this, campo);
  this.refrescarPanelUnificado(campo);
}



initFiltroUnificadoSoloEstado(): void {
  if (!Array.isArray(this.ticketsCompletos) || this.ticketsCompletos.length === 0) return;
  this.campoUnificadoActual = 'estado';
  seleccionarCampo(this.filtroUnificado, this.ticketsCompletos as any, 'estado');
  // ⬆️ Listo. No asignes a opcionesCategoriaUnificada (es un getter).
}




aplicarCategoriaUnificada(): void {
  const campo = this.campoUnificadoActual;
  if (!campo) return;

const pluralMap: Record<string, string> = {
  categoria:'categorias',
  estado:'estados',
  departamento:'departamentos',
  sucursal:'sucursales',
  username:'usuarios',
  criticidad:'criticidades',
  subcategoria:'subcategorias',   // 👈
  detalle:'detalles',             // 👈
};
  const plural = pluralMap[campo];

  let disponibles = (this as any)[`${plural}Disponibles`] as Array<{valor:any; etiqueta?:string; seleccionado:boolean}> || [];
  if (!disponibles.length) {
    disponibles = (this.filtroUnificado.opcionesDisponibles || []).map(o => ({
      valor: o.valor, etiqueta: o.etiqueta, seleccionado: true
    }));
    (this as any)[`${plural}Disponibles`] = [...disponibles];
    (this as any)[`${plural}Filtradas`]  = [...disponibles];
  }

  // 🔴 Normaliza solo para DEPARTAMENTO: usa NOMBRE como valor
  if (campo === 'departamento') {
    disponibles = disponibles.map(op => {
      const etiqueta = typeof op.valor === 'number'
        ? this.etiquetaDepartamentoPorId(op.valor)   // id -> nombre
        : String(op.valor);
      return { ...op, valor: etiqueta, etiqueta };
    });
    (this as any)[`${plural}Disponibles`] = [...disponibles];
    (this as any)[`${plural}Filtradas`]  = [...disponibles];
  }

  const setSel = this.filtroUnificado.seleccionTemporal;
  this.temporalSeleccionados[campo] = disponibles.map(op => ({
    ...op,
    seleccionado: setSel.has(String(op.valor))
  }));

  console.log('UNIFICADO aplicar -> campo:', campo,
              'seleccion:', Array.from(setSel),
              'disponibles normalizados:', disponibles);

  aplicarFiltroColumnaConResetUnificado(this, campo);
  this.refrescarPanelUnificado(campo);
}





private refrescarPanelUnificado(
  campo: 'categoria' | 'estado' | 'departamento' | 'sucursal' | 'username' | 'criticidad' | 'subcategoria' | 'detalle'
): void {
  if (campo === 'sucursal') this.hidratarSucursalEnTickets();

  if (campo === 'subcategoria') { this.construirOpcionesSubcategoria('filtered'); return; }
  if (campo === 'detalle')      { this.construirOpcionesDetalle('filtered');      return; }

  const formatters =
    campo === 'categoria'    ? { categoria:    (v: string) => this.etiquetaCatalogoPorId(v) } :
    campo === 'departamento' ? { departamento: (v: string) => this.etiquetaDepartamentoPorId(v) } :
    undefined;

  seleccionarCampo(this.filtroUnificado, this.filteredTickets as any, campo, formatters);

  const pluralMap: Record<string, string> = {
    categoria: 'categorias', estado: 'estados', departamento: 'departamentos',
    username: 'usuarios', sucursal: 'sucursales', criticidad: 'criticidades',
    subcategoria: 'subcategorias', detalle: 'detalles',
  };
  const plural = pluralMap[campo];
  const disponibles = (this as any)[`${plural}Disponibles`] as Array<{ valor: any; seleccionado: boolean }> || [];
  this.filtroUnificado.seleccionTemporal = new Set(
    disponibles.filter(op => op.seleccionado).map(op => String(op.valor))
  );
}





private rebuildPanelCategoriasDesdeFiltered(): void {
  const set = new Set<string>();
  (this.filteredTickets || []).forEach((t: any) => {
    if (t?.categoria != null) set.add(String(t.categoria));
  });

  const opciones = Array.from(set)
    .sort((a, b) =>
      this.etiquetaCatalogoPorId(a).localeCompare(this.etiquetaCatalogoPorId(b))
    )
    .map(v => ({ valor: v, etiqueta: this.etiquetaCatalogoPorId(v) }));

  this.filtroUnificado.opcionesDisponibles = opciones;
  // preselecciona todas las visibles (o carga desde tus aplicadas si quieres)
  this.filtroUnificado.seleccionTemporal = new Set(opciones.map(o => o.valor));

  this.changeDetectorRef.detectChanges();
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


onCambioCampoUnificado(
  campo: 'categoria' | 'estado' | 'departamento' | 'sucursal' | 'username' | 'criticidad' | 'subcategoria' | 'detalle' | null
) {
  this.campoUnificadoActual = campo;

  // reset estado unificado + tabla…
  this.filtroUnificado.filtrosAplicados.clear();
  this.filtroUnificado.seleccionTemporal.clear();
  this.filtroUnificado.textoBusqueda = '';
  this.filteredTickets = [...this.ticketsCompletos];
  this.page = 1;
  this.totalTickets = this.filteredTickets.length;
  this.totalPagesCount = Math.ceil(this.totalTickets / this.itemsPerPage);
  this.visibleTickets = this.filteredTickets.slice(0, this.itemsPerPage);

  if (!campo) {
    this.filtroUnificado.opcionesDisponibles = [];
    this.changeDetectorRef.detectChanges();
    return;
  }

  if (campo === 'sucursal') this.hidratarSucursalEnTickets();

  // 👇 casos especiales: construir con lo que se ve en la tabla
  if (campo === 'subcategoria') {
    this.construirOpcionesSubcategoria('all');
    this.changeDetectorRef.detectChanges();
    return;
  }
  if (campo === 'detalle') {
    this.construirOpcionesDetalle('all');
    this.changeDetectorRef.detectChanges();
    return;
  }

  // Resto: usa tu util como ya lo tenías
  const formatters =
    campo === 'categoria' ? { categoria: (v: string) => this.etiquetaCatalogoPorId(v) } :
    campo === 'departamento' ? { departamento: (v: string) => this.etiquetaDepartamentoPorId(v) } :
    undefined;

  seleccionarCampo(this.filtroUnificado, this.ticketsCompletos as any, campo, formatters);
  this.changeDetectorRef.detectChanges();
}




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





toggleFiltros(): void {
  this.mostrarFiltros = !this.mostrarFiltros;
   this.filtroUnificado.textoBusqueda = '';
}


private construirOpcionesSubcategoria(origen: 'all' | 'filtered' = 'all'): void {
  const base = origen === 'filtered' ? (this.filteredTickets || []) : (this.ticketsCompletos || []);
  const set = new Set<string>();
  base.forEach((t: any) => set.add(this.getSubcategoriaVisible(t) || '—'));

  const opciones = Array.from(set)
    .sort((a, b) => a.localeCompare(b))
    .map(nombre => ({ valor: nombre, etiqueta: nombre }));

  this.filtroUnificado.opcionesDisponibles = opciones;
  this.filtroUnificado.seleccionTemporal = new Set(opciones.map(o => o.valor));

  console.log(`[FU] Subcategoría (${origen}) opciones:`, opciones);
}

private construirOpcionesDetalle(origen: 'all' | 'filtered' = 'all'): void {
  const base = origen === 'filtered' ? (this.filteredTickets || []) : (this.ticketsCompletos || []);
  const set = new Set<string>();
  base.forEach((t: any) => {
    const nombre = t?.jerarquia_clasificacion?.[3]
      ?? (t?.detalle != null ? this.etiquetaCatalogoPorId(t.detalle) : '—');
    set.add(nombre || '—');
  });

  const opciones = Array.from(set)
    .sort((a, b) => a.localeCompare(b))
    .map(nombre => ({ valor: nombre, etiqueta: nombre }));

  this.filtroUnificado.opcionesDisponibles = opciones;
  this.filtroUnificado.seleccionTemporal = new Set(opciones.map(o => o.valor));

  console.log(`[FU] Detalle (${origen}) opciones:`, opciones);
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


}
