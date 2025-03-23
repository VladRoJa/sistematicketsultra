// src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.ts

import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgxPaginationModule } from 'ngx-pagination';
import { TicketService } from '../services/ticket.service';
import { DepartamentoService } from '../services/departamento.service';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import * as ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';
import { FilterTableComponent, FiltrosTabla } from '../filter-table/filter-table-component';

// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';


// -------------- Interfaces -------------- //

/** Representa la estructura de un Ticket */
export interface Ticket {
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
  historial_fechas?: Array<{
    fecha: string;
    cambiadoPor: string;
    fechaCambio: string;
  }>;
}

/** Respuesta del backend */
export interface ApiResponse {
  mensaje: string;
  tickets: Ticket[];
  total_tickets: number;
}

/** Filtros de la tabla (opcional para métodos generales) */
interface TablaFiltros {
  estado?: string;
  criticidad?: string;
  departamento?: string;
  fechaCreacion?: string;
  fechaFinalizacion?: string;
}


// -------------- Componente -------------- //
@Component({
  selector: 'app-pantalla-ver-tickets',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    NgxPaginationModule,
    FilterTableComponent,
    MatButtonModule,
    MatMenuModule,
    MatIconModule,
    MatDividerModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  templateUrl: './pantalla-ver-tickets.component.html',
  styleUrls: ['./pantalla-ver-tickets.component.css']
})
export class PantallaVerTicketsComponent implements OnInit {

  // -------------- Tickets y Paginación -------------- //
  tickets: Ticket[] = [];
  filteredTickets: Ticket[] = [];
  totalTickets: number = 0;
  page: number = 1;
  itemsPerPage: number = 15;
  loading: boolean = false;

  // -------------- Arrays para Checkboxes (Filtros) -------------- //
  idsDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  categoriasDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  descripcionesDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  usuariosDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  estadosDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  criticidadesDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  fechasCreacionDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  fechasFinalDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];
  departamentosDisponibles: Array<{ valor: string, seleccionado: boolean }> = [];

  // -------------- Nuevas Propiedades para Filtros (cuadros de búsqueda y “Seleccionar todo”) -------------- //
  // Para columna ID
  seleccionarTodoID: boolean = false;

  // Para Categoría
  filtroCategoriaTexto: string = "";
  seleccionarTodoCategoria: boolean = false;
  categoriasFiltradas: Array<{ valor: string, seleccionado: boolean }> = [];

  // Para Descripción
  filtroDescripcionTexto: string = "";
  seleccionarTodoDescripcion: boolean = false;
  descripcionesFiltradas: Array<{ valor: string, seleccionado: boolean }> = [];

  // Para Usuario
  filtroUsuarioTexto: string = "";
  seleccionarTodoUsuario: boolean = false;
  usuariosFiltrados: Array<{ valor: string, seleccionado: boolean }> = [];

  // Para Estado
  filtroEstadoTexto: string = "";
  seleccionarTodoEstado: boolean = false;
  estadosFiltrados: Array<{ valor: string, seleccionado: boolean }> = [];

  // Para Criticidad
  filtroCriticidadTexto: string = "";
  seleccionarTodoCriticidad: boolean = false;
  criticidadesFiltradas: Array<{ valor: string, seleccionado: boolean }> = [];

  // Para Fecha Creación
  filtroFechaTexto: string = "";
  seleccionarTodoFechaC: boolean = false;
  fechasCreacionFiltradas: Array<{ valor: string, seleccionado: boolean }> = [];

  // Para Fecha Finalizado
  filtroFechaFinalTexto: string = "";
  seleccionarTodoFechaF: boolean = false;
  fechasFinalFiltradas: Array<{ valor: string, seleccionado: boolean }> = [];

  // -------------- Propiedades de Usuario y Departamentos -------------- //
  user: any = null;
  usuarioEsAdmin: boolean = false;
  departamentos: any[] = [];

  // -------------- Confirmación y Edición -------------- //
  confirmacionVisible: boolean = false;
  mensajeConfirmacion: string = "";
  accionPendiente: (() => void) | null = null;
  fechaSolucionSeleccionada: Record<number, string> = {};
  editandoFechaSolucion: Record<number, boolean> = {};
  historialVisible: Record<number, boolean> = {};

  // -------------- Propiedades para Filtro de Departamento -------------- //
  filtroDeptoTexto: string = "";
  seleccionarTodoDepto: boolean = false;
  departamentosFiltrados: Array<{ valor: string, seleccionado: boolean }> = [];

  // -------------- Rutas -------------- //
  private authUrl = 'http://localhost:5000/api/auth/session-info';
  private apiUrl = 'http://localhost:5000/api/tickets';

  constructor(
    private ticketService: TicketService,
    private departamentoService: DepartamentoService,
    private changeDetectorRef: ChangeDetectorRef,
    private http: HttpClient
  ) {}

  // -------------- Ciclo de Vida -------------- //
  async ngOnInit() {
    await this.obtenerUsuarioAutenticado();
    this.cargarTickets();

    // Cargar departamentos
    this.departamentoService.obtenerDepartamentos().subscribe({
      next: (data) => {
        if (!Array.isArray(data)) {
          this.departamentos = Object.values(data);
        } else {
          this.departamentos = data;
        }
      },
      error: (error) => {
        console.error("❌ Error al obtener departamentos:", error);
      }
    });
  }

  // -------------- Usuario Autenticado -------------- //
  async obtenerUsuarioAutenticado() {
    const token = localStorage.getItem('token');
    if (!token) return;
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    });
    try {
      const data = await firstValueFrom(
        this.http.get<{ user: any }>(this.authUrl, { headers })
      );
      if (data?.user) {
        this.user = data.user;
        this.usuarioEsAdmin = (this.user.id_sucursal === 1000);
        console.log("✅ Usuario autenticado:", this.user);
      }
    } catch (error) {
      console.error("❌ Error obteniendo usuario autenticado:", error);
    }
  }

  // -------------- Cargar Tickets -------------- //
  cargarTickets(): void {
    this.loading = true;
    const offset = (this.page - 1) * this.itemsPerPage;
    this.ticketService.getTickets(this.itemsPerPage, offset).subscribe({
      next: (data: ApiResponse) => {
        if (!data || !data.tickets) {
          console.error("❌ No se recibieron tickets.");
          this.loading = false;
          return;
        }
        // Mapear y normalizar datos de cada ticket
        this.tickets = data.tickets.map(ticket => ({
          ...ticket,
          criticidad: ticket.criticidad || 1,
          estado: this.normalizarEstado(ticket.estado),
          departamento: this.departamentoService.obtenerNombrePorId(ticket.departamento_id),
          fecha_creacion: this.formatearFecha(ticket.fecha_creacion),
          fecha_finalizado: ticket.fecha_finalizado ? this.formatearFecha(ticket.fecha_finalizado) : null,
          historial_fechas: typeof ticket.historial_fechas === "string"
            ? JSON.parse(ticket.historial_fechas)
            : ticket.historial_fechas || []
        }));
        this.totalTickets = data.total_tickets;
        this.filteredTickets = [...this.tickets];
        // Construir las listas para los checkboxes de filtro
        this.construirListasDisponibles();
        // Inicializar las listas de filtrado específicas (para búsqueda)
        this.inicializarListasFiltradas();
        this.loading = false;
      },
      error: (error) => {
        console.error("❌ Error al cargar tickets:", error);
        this.loading = false;
      }
    });
  }

  // -------------- Construir Listas para Filtros -------------- //
  construirListasDisponibles() {
    // IDs
    const ids = Array.from(new Set(this.tickets.map(t => t.id)));
    this.idsDisponibles = ids.map(id => ({ valor: String(id), seleccionado: false }));

    // Categorías
    const cats = Array.from(new Set(this.tickets.map(t => t.categoria)));
    this.categoriasDisponibles = cats.map(c => ({ valor: c, seleccionado: false }));

    // Descripciones
    const descs = Array.from(new Set(this.tickets.map(t => t.descripcion)));
    this.descripcionesDisponibles = descs.map(d => ({ valor: d, seleccionado: false }));

    // Usuarios
    const users = Array.from(new Set(this.tickets.map(t => t.username)));
    this.usuariosDisponibles = users.map(u => ({ valor: u, seleccionado: false }));

    // Estados
    const ests = Array.from(new Set(this.tickets.map(t => t.estado)));
    this.estadosDisponibles = ests.map(e => ({ valor: e, seleccionado: false }));

    // Criticidades
    const crits = Array.from(new Set(this.tickets.map(t => t.criticidad)));
    this.criticidadesDisponibles = crits.map(c => ({ valor: String(c), seleccionado: false }));

    // Fechas de Creación
    const fcs = Array.from(new Set(this.tickets.map(t => t.fecha_creacion)));
    this.fechasCreacionDisponibles = fcs.map(fc => ({ valor: fc, seleccionado: false }));

    // Fechas Final
    const ffs = Array.from(new Set(this.tickets.map(t => t.fecha_finalizado ?? 'Sin Finalizar')));
    this.fechasFinalDisponibles = ffs.map(ff => ({ valor: ff, seleccionado: false }));

    // Departamentos
    const deps = Array.from(new Set(this.tickets.map(t => t.departamento)));
    this.departamentosDisponibles = deps.map(dep => ({ valor: dep, seleccionado: false }));

    // Inicializar la lista filtrada para Departamento
    this.departamentosFiltrados = [...this.departamentosDisponibles];
  }

  // -------------- Inicializar Listas para Filtros con Búsqueda -------------- //
  inicializarListasFiltradas(): void {
    // Para cada columna con cuadro de búsqueda, se inicializa la lista filtrada
    this.categoriasFiltradas = [...this.categoriasDisponibles];
    this.descripcionesFiltradas = [...this.descripcionesDisponibles];
    this.usuariosFiltrados = [...this.usuariosDisponibles];
    this.estadosFiltrados = [...this.estadosDisponibles];
    this.criticidadesFiltradas = [...this.criticidadesDisponibles];
    this.fechasCreacionFiltradas = [...this.fechasCreacionDisponibles];
    this.fechasFinalFiltradas = [...this.fechasFinalDisponibles];
  }

  // -------------- Normalizar y Formatear Fechas -------------- //
  normalizarEstado(estado: string): "pendiente" | "en progreso" | "finalizado" {
    const estadoLimpio = estado?.trim().toLowerCase();
    if (estadoLimpio === "abierto" || estadoLimpio === "pendiente") return "pendiente";
    if (estadoLimpio === "en progreso") return "en progreso";
    if (estadoLimpio === "finalizado") return "finalizado";
    return "pendiente";
  }

  formatearFecha(fechaString: string | null): string {
    if (!fechaString) return 'Sin finalizar';
    const fecha = new Date(fechaString);
    if (isNaN(fecha.getTime())) {
      console.error("❌ Fecha inválida detectada:", fechaString);
      return 'Fecha inválida';
    }
    // Ajuste de zona horaria
    fecha.setMinutes(fecha.getMinutes() + fecha.getTimezoneOffset());
    return fecha.toLocaleString('es-ES', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).replace(',', '').replace(/\//g, '-');
  }

  formatearFechaCorta(fechaString: string | null): string {
    if (!fechaString) return 'dd/mm/aa';
  
    // Parseamos directamente la cadena
    const fecha = new Date(fechaString);
  
    // Verificamos si la fecha es inválida
    if (isNaN(fecha.getTime())) {
      console.error("❌ Fecha inválida detectada:", fechaString);
      return 'Fecha inválida';
    }
  
    // Devolvemos solo día/mes/año (sin hora),
    // usando la configuración regional 'es-ES'.
    return fecha.toLocaleDateString('es-ES', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit'
    });
  }

    /**
   * Elimina acentos y diacríticos de una cadena usando normalize + RegEx.
   * "Eléctrica" -> "Electrica"
   */
  removeDiacritics(texto: string): string {
    return texto
      .normalize("NFD")                 // Normaliza la cadena a Unicode NFD
      .replace(/\p{Diacritic}/gu, "");  // Elimina caracteres diacríticos
  }

  

  // -------------- Paginación -------------- //
  nextPage(): void {
    if ((this.page * this.itemsPerPage) < this.totalTickets) {
      this.page++;
      this.cargarTickets();
    }
  }

  prevPage(): void {
    if (this.page > 1) {
      this.page--;
      this.cargarTickets();
    }
  }

  cambiarPagina(direccion: number) {
    const nuevaPagina = this.page + direccion;
    if (nuevaPagina > 0 && nuevaPagina <= this.totalPages()) {
      this.page = nuevaPagina;
      this.cargarTickets();
    }
  }

  totalPages(): number {
    return Math.ceil(this.totalTickets / this.itemsPerPage);
  }

  // -------------- Exportar a Excel -------------- //
  exportToExcel(): void {
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Tickets');
    worksheet.columns = [
      { header: 'ID', key: 'id', width: 10 },
      { header: 'Descripción', key: 'descripcion', width: 50 },
      { header: 'Usuario', key: 'username', width: 20 },
      { header: 'Estado', key: 'estado', width: 15 },
      { header: 'Criticidad', key: 'criticidad', width: 10 },
      { header: 'Fecha Creación', key: 'fecha_creacion', width: 20 },
      { header: 'Fecha Finalizado', key: 'fecha_finalizado', width: 20 },
      { header: 'Departamento', key: 'departamento', width: 25 },
      { header: 'Categoría', key: 'categoria', width: 25 }
    ];
    this.tickets.forEach(ticket => {
      worksheet.addRow({
        ...ticket,
        fecha_finalizado: ticket.fecha_finalizado || 'N/A'
      });
    });
    workbook.xlsx.writeBuffer().then(buffer => {
      saveAs(new Blob([buffer]), `tickets_${new Date().toISOString().slice(0, 10)}.xlsx`);
    });
  }

  // -------------- Funciones para Cambiar Estado y Finalizar Tickets -------------- //
  cambiarEstadoTicket(ticket: Ticket, nuevoEstado: "pendiente" | "en progreso" | "finalizado") {
    if (!this.usuarioEsAdmin) return;
    this.mostrarConfirmacion(
      `¿Estás seguro de cambiar el estado del ticket #${ticket.id} a ${nuevoEstado.toUpperCase()}?`,
      () => {
        const token = localStorage.getItem('token');
        if (!token) return;
        const headers = new HttpHeaders()
          .set('Authorization', `Bearer ${token}`)
          .set('Content-Type', 'application/json');
        let updateData: any = { estado: nuevoEstado };
        if (nuevoEstado === "finalizado") {
          updateData.fecha_finalizado = new Date().toISOString().slice(0, 19).replace("T", " ");
        }
        this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, updateData, { headers }).subscribe({
          next: () => {
            ticket.estado = nuevoEstado;
            if (nuevoEstado === "finalizado") {
              ticket.fecha_finalizado = updateData.fecha_finalizado;
            }
            this.changeDetectorRef.detectChanges();
          },
          error: (error) => console.error(`❌ Error actualizando ticket: ${error}`)
        });
      }
    );
  }

  finalizarTicket(ticket: Ticket) {
    if (!this.usuarioEsAdmin) return;
    this.mostrarConfirmacion(
      `¿Estás seguro de marcar como FINALIZADO el ticket #${ticket.id}?`,
      () => {
        const token = localStorage.getItem('token');
        if (!token) return;
        const headers = new HttpHeaders()
          .set('Authorization', `Bearer ${token}`)
          .set('Content-Type', 'application/json');
        const fechaFinalizado = new Date().toISOString().slice(0, 19).replace("T", " ");
        this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, { estado: "finalizado", fecha_finalizado: fechaFinalizado }, { headers }).subscribe({
          next: () => {
            console.log("✅ Ticket finalizado en el backend.");
            this.cargarTickets();
          },
          error: (error) => console.error(`❌ Error al finalizar el ticket ${ticket.id}:`, error)
        });
      }
    );
  }

  // -------------- Funciones para Editar Fecha de Solución -------------- //
  editarFechaSolucion(ticket: Ticket) {
    this.editandoFechaSolucion[ticket.id] = true;
    if (!this.fechaSolucionSeleccionada[ticket.id]) {
      this.fechaSolucionSeleccionada[ticket.id] = ticket.fecha_solucion || "";
    }
  }

  guardarFechaSolucion(ticket: Ticket) {
    if (!this.fechaSolucionSeleccionada[ticket.id]) return;
    const token = localStorage.getItem("token");
    if (!token) {
      console.error("❌ No hay token almacenado.");
      return;
    }
    const headers = new HttpHeaders()
      .set("Authorization", `Bearer ${token}`)
      .set("Content-Type", "application/json");
    // Fijamos la hora a 01:00:00 AM
    const fechaFormateada = `${this.fechaSolucionSeleccionada[ticket.id]} 01:00:00`;
    const datosEnviados = {
      estado: ticket.estado,
      fecha_solucion: fechaFormateada,
      historial_fechas: JSON.stringify([
        ...(ticket.historial_fechas || []),
        {
          fecha: fechaFormateada,
          cambiadoPor: this.user.username,
          fechaCambio: new Date().toISOString(),
        },
      ]),
    };
    this.http.put(`${this.apiUrl}/update/${ticket.id}`, datosEnviados, { headers }).subscribe({
      next: () => {
        ticket.fecha_solucion = fechaFormateada;
        this.editandoFechaSolucion[ticket.id] = false;
        if (!ticket.historial_fechas) {
          ticket.historial_fechas = [];
        }
        ticket.historial_fechas.push({
          fecha: fechaFormateada,
          cambiadoPor: this.user.username,
          fechaCambio: new Date().toISOString(),
        });
        console.log(`✅ Fecha de solución del ticket #${ticket.id} actualizada a las 1:00 AM.`);
      },
      error: (error) => {
        console.error(`❌ Error al actualizar la fecha de solución del ticket #${ticket.id}:`, error);
      },
    });
  }

  cancelarEdicion(ticket: Ticket) {
    this.editandoFechaSolucion[ticket.id] = false;
  }

  // -------------- Funciones para Indicador de Color (Fecha de Solución) -------------- //
  getIndicadorColor(ticket: Ticket): string {
    if (!ticket.fecha_solucion || !ticket.historial_fechas || ticket.historial_fechas.length === 0) {
      return 'transparent';
    }
    const fechaOriginalStr = ticket.historial_fechas[0].fecha;
    const fechaNuevaStr = ticket.fecha_solucion;
    const fechaOriginal = new Date(fechaOriginalStr);
    const fechaNueva = new Date(fechaNuevaStr);
    if (isNaN(fechaOriginal.getTime()) || isNaN(fechaNueva.getTime())) {
      return 'transparent';
    }
    const diffDays = Math.round((fechaNueva.getTime() - fechaOriginal.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays < 0) {
      return 'green';   // Se movió hacia atrás
    } else if (diffDays <= 5) {
      return 'yellow';  // Adelantó pocos días
    } else {
      return 'red';     // Adelantó más de 5 días
    }
  }

  // -------------- Funciones para Historial y Confirmación -------------- //
  toggleHistorial(ticketId: number) {
    this.historialVisible[ticketId] = !this.historialVisible[ticketId];
  }

  mostrarConfirmacion(mensaje: string, accion: () => void) {
    this.mensajeConfirmacion = mensaje;
    this.accionPendiente = accion;
    this.confirmacionVisible = true;
  }

  confirmarAccion() {
    if (this.accionPendiente) {
      this.accionPendiente();
    }
    this.confirmacionVisible = false;
  }

  cancelarAccion() {
    this.confirmacionVisible = false;
    this.accionPendiente = null;
  }

  // -------------- Funciones para Filtrado por Columna -------------- //

  aplicarFiltroColumna(columna: string) {
    console.log(`Aplicar filtro en columna: ${columna}`);
    this.filteredTickets = [...this.tickets];
    if (columna === 'id') {
      const seleccionadas = this.idsDisponibles.filter(i => i.seleccionado).map(i => i.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(String(t.id)));
      }
    }
    if (columna === 'categoria') {
      const seleccionadas = this.categoriasDisponibles.filter(cat => cat.seleccionado).map(cat => cat.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(t.categoria));
      }
    }
    if (columna === 'descripcion') {
      const seleccionadas = this.descripcionesDisponibles.filter(d => d.seleccionado).map(d => d.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(t.descripcion));
      }
    }
    if (columna === 'username') {
      const seleccionadas = this.usuariosDisponibles.filter(u => u.seleccionado).map(u => u.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(t.username));
      }
    }
    if (columna === 'estado') {
      const seleccionadas = this.estadosDisponibles.filter(e => e.seleccionado).map(e => e.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(t.estado));
      }
    }
    if (columna === 'criticidad') {
      const seleccionadas = this.criticidadesDisponibles.filter(c => c.seleccionado).map(c => c.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(String(t.criticidad)));
      }
    }
    if (columna === 'fecha_creacion') {
      const seleccionadas = this.fechasCreacionDisponibles.filter(fc => fc.seleccionado).map(fc => fc.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(t.fecha_creacion));
      }
    }
    if (columna === 'fecha_finalizado') {
      const seleccionadas = this.fechasFinalDisponibles.filter(ff => ff.seleccionado).map(ff => ff.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => {
          const val = t.fecha_finalizado ?? 'Sin Finalizar';
          return seleccionadas.includes(val);
        });
      }
    }
    if (columna === 'departamento') {
      const seleccionadas = this.departamentosDisponibles.filter(d => d.seleccionado).map(d => d.valor);
      if (seleccionadas.length > 0) {
        this.filteredTickets = this.filteredTickets.filter(t => seleccionadas.includes(t.departamento));
      }
    }
  }

  limpiarFiltroColumna(columna: string) {
    if (columna === 'id') {
      this.idsDisponibles.forEach(item => item.seleccionado = false);
      this.seleccionarTodoID = false;
    }
    if (columna === 'categoria') {
      this.categoriasDisponibles.forEach(item => item.seleccionado = false);
      this.filtroCategoriaTexto = "";
      // Reiniciar la lista filtrada para categoría
      this.categoriasFiltradas = [...this.categoriasDisponibles];
      this.seleccionarTodoCategoria = false;
    }
    if (columna === 'descripcion') {
      this.descripcionesDisponibles.forEach(item => item.seleccionado = false);
      this.filtroDescripcionTexto = "";
      this.descripcionesFiltradas = [...this.descripcionesDisponibles];
      this.seleccionarTodoDescripcion = false;
    }
    if (columna === 'username') {
      this.usuariosDisponibles.forEach(item => item.seleccionado = false);
      this.filtroUsuarioTexto = "";
      this.usuariosFiltrados = [...this.usuariosDisponibles];
      this.seleccionarTodoUsuario = false;
    }
    if (columna === 'estado') {
      this.estadosDisponibles.forEach(item => item.seleccionado = false);
      this.filtroEstadoTexto = "";
      this.estadosFiltrados = [...this.estadosDisponibles];
      this.seleccionarTodoEstado = false;
    }
    if (columna === 'criticidad') {
      this.criticidadesDisponibles.forEach(item => item.seleccionado = false);
      this.filtroCriticidadTexto = "";
      this.criticidadesFiltradas = [...this.criticidadesDisponibles];
      this.seleccionarTodoCriticidad = false;
    }
    if (columna === 'fecha_creacion') {
      this.fechasCreacionDisponibles.forEach(item => item.seleccionado = false);
      this.filtroFechaTexto = "";
      this.fechasCreacionFiltradas = [...this.fechasCreacionDisponibles];
      this.seleccionarTodoFechaC = false;
    }
    if (columna === 'fecha_finalizado') {
      this.fechasFinalDisponibles.forEach(item => item.seleccionado = false);
      this.filtroFechaFinalTexto = "";
      this.fechasFinalFiltradas = [...this.fechasFinalDisponibles];
      this.seleccionarTodoFechaF = false;
    }
    if (columna === 'departamento') {
      this.departamentosDisponibles.forEach(item => item.seleccionado = false);
      this.filtroDeptoTexto = "";
      this.departamentosFiltrados = [...this.departamentosDisponibles];
      this.seleccionarTodoDepto = false;
    }
    // Reiniciamos la lista filtrada general
    this.filteredTickets = [...this.tickets];
  }

  // Función general para "Seleccionar Todo" según columna
  toggleSeleccionarTodo(columna: string): void {
    if (columna === 'id') {
      this.idsDisponibles.forEach(item => item.seleccionado = this.seleccionarTodoID);
    } else if (columna === 'categoria') {
      this.categoriasFiltradas.forEach(item => item.seleccionado = this.seleccionarTodoCategoria);
    } else if (columna === 'descripcion') {
      this.descripcionesFiltradas.forEach(item => item.seleccionado = this.seleccionarTodoDescripcion);
    } else if (columna === 'username') {
      this.usuariosFiltrados.forEach(item => item.seleccionado = this.seleccionarTodoUsuario);
    } else if (columna === 'estado') {
      this.estadosFiltrados.forEach(item => item.seleccionado = this.seleccionarTodoEstado);
    } else if (columna === 'criticidad') {
      this.criticidadesFiltradas.forEach(item => item.seleccionado = this.seleccionarTodoCriticidad);
    } else if (columna === 'fecha_creacion') {
      this.fechasCreacionFiltradas.forEach(item => item.seleccionado = this.seleccionarTodoFechaC);
    } else if (columna === 'fecha_finalizado') {
      this.fechasFinalFiltradas.forEach(item => item.seleccionado = this.seleccionarTodoFechaF);
    } else if (columna === 'departamento') {
      // Evitamos recursión: Marcamos la lista filtrada
      this.departamentosFiltrados.forEach(item => item.seleccionado = this.seleccionarTodoDepto);
    }
  }

  // -------------- Funciones para Filtrar Opciones (Categoría, Descripción, etc.) -------------- //
 // Filtrar Opciones para Categoría (ignora acentos)
filtrarOpcionesCategoria(): void {
  if (!this.filtroCategoriaTexto) {
    this.categoriasFiltradas = [...this.categoriasDisponibles];
  } else {
    const textoNormalizado = this.removeDiacritics(this.filtroCategoriaTexto.toLowerCase());
    this.categoriasFiltradas = this.categoriasDisponibles.filter(cat => {
      const valorNormalizado = this.removeDiacritics(cat.valor.toLowerCase());
      return valorNormalizado.includes(textoNormalizado);
    });
  }
}

// Filtrar Opciones para Descripción (ignora acentos)
filtrarOpcionesDescripcion(): void {
  if (!this.filtroDescripcionTexto) {
    this.descripcionesFiltradas = [...this.descripcionesDisponibles];
  } else {
    const textoNormalizado = this.removeDiacritics(this.filtroDescripcionTexto.toLowerCase());
    this.descripcionesFiltradas = this.descripcionesDisponibles.filter(desc => {
      const valorNormalizado = this.removeDiacritics(desc.valor.toLowerCase());
      return valorNormalizado.includes(textoNormalizado);
    });
  }
}

// Filtrar Opciones para Usuario (ignora acentos)
filtrarOpcionesUsuario(): void {
  if (!this.filtroUsuarioTexto) {
    this.usuariosFiltrados = [...this.usuariosDisponibles];
  } else {
    const textoNormalizado = this.removeDiacritics(this.filtroUsuarioTexto.toLowerCase());
    this.usuariosFiltrados = this.usuariosDisponibles.filter(usr => {
      const valorNormalizado = this.removeDiacritics(usr.valor.toLowerCase());
      return valorNormalizado.includes(textoNormalizado);
    });
  }
}

// Filtrar Opciones para Estado (ignora acentos)
filtrarOpcionesEstado(): void {
  if (!this.filtroEstadoTexto) {
    this.estadosFiltrados = [...this.estadosDisponibles];
  } else {
    const textoNormalizado = this.removeDiacritics(this.filtroEstadoTexto.toLowerCase());
    this.estadosFiltrados = this.estadosDisponibles.filter(est => {
      const valorNormalizado = this.removeDiacritics(est.valor.toLowerCase());
      return valorNormalizado.includes(textoNormalizado);
    });
  }
}

// Filtrar Opciones para Criticidad (aunque es numérico, se trata como string)
filtrarOpcionesCriticidad(): void {
  if (!this.filtroCriticidadTexto) {
    this.criticidadesFiltradas = [...this.criticidadesDisponibles];
  } else {
    const textoNormalizado = this.removeDiacritics(this.filtroCriticidadTexto.toLowerCase());
    this.criticidadesFiltradas = this.criticidadesDisponibles.filter(crit => {
      const valorNormalizado = this.removeDiacritics(crit.valor.toLowerCase());
      return valorNormalizado.includes(textoNormalizado);
    });
  }
}

// Filtrar Opciones para Fecha Creación (no requiere remoción de diacríticos)
filtrarOpcionesFechaC(): void {
  if (!this.filtroFechaTexto) {
    this.fechasCreacionFiltradas = [...this.fechasCreacionDisponibles];
  } else {
    const texto = this.filtroFechaTexto.toLowerCase();
    this.fechasCreacionFiltradas = this.fechasCreacionDisponibles.filter(fc =>
      fc.valor.toLowerCase().includes(texto)
    );
  }
}

// Filtrar Opciones para Fecha Finalizado (no requiere remoción de diacríticos)
filtrarOpcionesFechaF(): void {
  if (!this.filtroFechaFinalTexto) {
    this.fechasFinalFiltradas = [...this.fechasFinalDisponibles];
  } else {
    const texto = this.filtroFechaFinalTexto.toLowerCase();
    this.fechasFinalFiltradas = this.fechasFinalDisponibles.filter(ff =>
      ff.valor.toLowerCase().includes(texto)
    );
  }
}

// Filtrar Opciones para Departamento (ignora acentos)
filtrarOpcionesDepto(): void {
  if (!this.filtroDeptoTexto) {
    this.departamentosFiltrados = [...this.departamentosDisponibles];
  } else {
    const textoNormalizado = this.removeDiacritics(this.filtroDeptoTexto.toLowerCase());
    this.departamentosFiltrados = this.departamentosDisponibles.filter(dep => {
      const valorNormalizado = this.removeDiacritics(dep.valor.toLowerCase());
      return valorNormalizado.includes(textoNormalizado);
    });
  }
}

  // -------------- Función para Ordenar -------------- //
  ordenar(columna: string, direccion: 'asc' | 'desc') {
    console.log(`Ordenar por ${columna} en dirección ${direccion}`);
    this.filteredTickets.sort((a, b) => {
      const valA = (a as any)[columna] || '';
      const valB = (b as any)[columna] || '';
      if (valA < valB) return direccion === 'asc' ? -1 : 1;
      if (valA > valB) return direccion === 'asc' ? 1 : -1;
      return 0;
    });
  }
}
