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

// Interfaz para definir la estructura de un ticket
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

// Interfaz para la respuesta del backend
export interface ApiResponse {
  mensaje: string;
  tickets: Ticket[];
  total_tickets: number;
}

@Component({
  selector: 'app-pantalla-ver-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule, NgxPaginationModule],
  templateUrl: './pantalla-ver-tickets.component.html',
  styleUrls: ['./pantalla-ver-tickets.component.css']
})
export class PantallaVerTicketsComponent implements OnInit {

  // ---------------------------
  // Propiedades para tickets y paginación
  // ---------------------------
  tickets: Ticket[] = [];
  filteredTickets: Ticket[] = [];
  totalTickets: number = 0;
  page: number = 1;
  itemsPerPage: number = 15;
  loading: boolean = false;

  // ---------------------------
  // Propiedades para filtros (si se usan en el HTML)
  // ---------------------------
  filtroEstado: string = "";
  filtroDepartamento: string = "";
  filtroCriticidad: string = "";
  filtroFecha: string = "";
  filtroFechaFinalizacion: string = "";

  // ---------------------------
  // Propiedades del usuario y departamentos
  // ---------------------------
  user: any = null;
  usuarioEsAdmin: boolean = false;
  departamentos: any[] = [];

  // ---------------------------
  // Propiedades para confirmación y edición
  // ---------------------------
  confirmacionVisible: boolean = false;
  mensajeConfirmacion: string = "";
  accionPendiente: (() => void) | null = null;
  fechaSolucionSeleccionada: Record<number, string> = {};
  editandoFechaSolucion: Record<number, boolean> = {};
  historialVisible: Record<number, boolean> = {};

  // URL para la sesión (para obtener el usuario)
  private authUrl = 'http://localhost:5000/api/auth/session-info';
  private apiUrl = 'http://localhost:5000/api/tickets';

  constructor(
    private ticketService: TicketService,
    private departamentoService: DepartamentoService,
    private changeDetectorRef: ChangeDetectorRef,
    private http: HttpClient
  ) {}

  async ngOnInit() {
    await this.obtenerUsuarioAutenticado();
    this.cargarTickets();

    // Cargar departamentos para mapear nombres (si se requieren para filtros)
    this.departamentoService.obtenerDepartamentos().subscribe({
      next: (data) => {
        // Si data no es un array, convertirlo a array
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

  /**
   * Obtiene la información del usuario autenticado usando HttpClient y firstValueFrom.
   */
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
        // Usuario admin si id_sucursal es 1000
        this.usuarioEsAdmin = this.user.id_sucursal === 1000;
        console.log("✅ Usuario autenticado:", this.user);
      }
    } catch (error) {
      console.error("❌ Error obteniendo usuario autenticado:", error);
    }
  }

  /**
   * Carga los tickets desde el backend usando TicketService y mapea los datos.
   */
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
        // Mapear cada ticket para normalizar datos y formatear fechas
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
        this.loading = false;
      },
      error: (error) => {
        console.error("❌ Error al cargar tickets:", error);
        this.loading = false;
      }
    });
  }

  /**
   * Normaliza el estado del ticket a "pendiente", "en progreso" o "finalizado".
   */
  normalizarEstado(estado: string): "pendiente" | "en progreso" | "finalizado" {
    const estadoLimpio = estado?.trim().toLowerCase();
    if (estadoLimpio === "abierto" || estadoLimpio === "pendiente") return "pendiente";
    if (estadoLimpio === "en progreso") return "en progreso";
    if (estadoLimpio === "finalizado") return "finalizado";
    return "pendiente";
  }

  /**
   * Formatea una fecha completa para mostrarla de forma legible.
   */
  formatearFecha(fechaString: string | null): string {
    if (!fechaString) return 'Sin finalizar';
    const fecha = new Date(fechaString);
    if (isNaN(fecha.getTime())) {
      console.error("❌ Fecha inválida detectada:", fechaString);
      return 'Fecha inválida';
    }
    fecha.setMinutes(fecha.getMinutes() + fecha.getTimezoneOffset() );
    return fecha.toLocaleString('es-ES', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).replace(',', '').replace(/\//g, '-');
  }

  /**
   * Formatea una fecha de forma corta (solo dd-mm-aa).
   */
/**
 * Muestra la fecha en formato "dd/mm/aa", sin que JavaScript aplique conversiones horarias.
 * Asume que la cadena puede venir en uno de los siguientes formatos:
 *  1) "YYYY-MM-DD HH:mm:ss"
 *  2) "YYYY-MM-DD" (sin hora)
 *  3) "Sat, 01 Mar 2025 01:00:00 GMT" (u otro estilo con GMT)
 */
formatearFechaCorta(fechaString: string | null): string {
  if (!fechaString) return 'dd/mm/aa';



  // 1) Si contiene 'GMT' (ej. "Sat, 01 Mar 2025 01:00:00 GMT"), haremos un parse básico
  if (fechaString.includes('GMT')) {
    // Ejemplo de cadena: "Sat, 01 Mar 2025 01:00:00 GMT"
    // Dividimos por espacios
    const partes = fechaString.split(' ');
    // Suele tener [DiaSemana, DiaNumero, MesTexto, Año, HoraGMT, GMT]
    // Ej: ["Sat,", "01", "Mar", "2025", "01:00:00", "GMT"]
    if (partes.length < 5) return 'Fecha inválida';

    const dia = partes[1];      // "01"
    const mesTexto = partes[2]; // "Mar"
    const anio = partes[3];     // "2025"

    // Convertir mesTexto a número (ej. "Mar" → "03")
    const meses: any = {
      Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06',
      Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12'
    };
    const mesNumero = meses[mesTexto] || '01';

    // Retornamos "dd/mm/aa"
    return `${dia}/${mesNumero}/${anio.slice(-2)}`;
  }

  // 2) Si contiene espacio (ej. "YYYY-MM-DD HH:mm:ss"), tomamos solo la parte "YYYY-MM-DD"
  //    Si NO contiene espacio, podría ser solo "YYYY-MM-DD"
  const [datePart] = fechaString.split(" ");
  // datePart debería ser "YYYY-MM-DD"
  if (!datePart) return 'Fecha inválida';

  const [year, month, day] = datePart.split("-");
  if (!year || !month || !day) return 'Fecha inválida';

  // Devolvemos "dd/mm/aa"
  return `${day}/${month}/${year.slice(-2)}`;
}

  
  /**
   * Avanza a la siguiente página de tickets.
   */
  nextPage(): void {
    if ((this.page * this.itemsPerPage) < this.totalTickets) {
      this.page++;
      this.cargarTickets();
    }
  }

  /**
   * Retrocede a la página anterior de tickets.
   */
  prevPage(): void {
    if (this.page > 1) {
      this.page--;
      this.cargarTickets();
    }
  }

  /**
   * Cambia la página manualmente (por ejemplo, desde controles numéricos).
   */
  cambiarPagina(direccion: number) {
    const nuevaPagina = this.page + direccion;
    if (nuevaPagina > 0 && nuevaPagina <= this.totalPages()) {
      this.page = nuevaPagina;
      this.cargarTickets();
    }
  }

  /**
   * Calcula el total de páginas basado en totalTickets e itemsPerPage.
   */
  totalPages(): number {
    return Math.ceil(this.totalTickets / this.itemsPerPage);
  }

  /**
   * Exporta la lista de tickets a Excel.
   */
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

  // ---------------------------
  // Funciones para cambiar estado y finalizar ticket
  // ---------------------------

  
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
  
        // Preparamos el objeto de actualización
        let updateData: any = { estado: nuevoEstado };
  
        // Si el estado es "finalizado", añadimos la fecha de finalización
        if (nuevoEstado === "finalizado") {
          updateData.fecha_finalizado = new Date().toISOString().slice(0, 19).replace("T", " ");
        }
  
        // Realizamos la petición PUT al backend
        this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, updateData, { headers }).subscribe({
          next: () => {
            // Actualizamos localmente el estado del ticket
            ticket.estado = nuevoEstado;
            if (nuevoEstado === "finalizado") {
              ticket.fecha_finalizado = updateData.fecha_finalizado;
            }
            // Forzamos la actualización de la UI
            this.changeDetectorRef.detectChanges();
          },
          error: (error) => console.error(`❌ Error actualizando ticket: ${error}`)
        });
      }
    );
  }
  

  finalizarTicket(ticket: Ticket) {
    // Solo los administradores pueden finalizar tickets
    if (!this.usuarioEsAdmin) return;
  
    // Mostrar el modal de confirmación con el mensaje y la acción pendiente
    this.mostrarConfirmacion(
      `¿Estás seguro de marcar como FINALIZADO el ticket #${ticket.id}?`,
      () => {
        // Acción a ejecutar si el usuario confirma
        const token = localStorage.getItem('token');
        if (!token) return;
  
        // Configurar headers con el token para la autorización
        const headers = new HttpHeaders()
          .set('Authorization', `Bearer ${token}`)
          .set('Content-Type', 'application/json');
  
        // Obtener la fecha actual en formato 'YYYY-MM-DD HH:MM:SS'
        const fechaFinalizado = new Date().toISOString().slice(0, 19).replace("T", " ");
  
        // Realizar la llamada PUT al backend para actualizar el estado y la fecha_finalizado
        this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, 
          { estado: "finalizado", fecha_finalizado: fechaFinalizado }, 
          { headers }
        ).subscribe({
          next: () => {
            console.log("✅ Ticket finalizado en el backend.");
            // Recargar la lista de tickets para reflejar los cambios
            this.cargarTickets();
          },
          error: (error) => console.error(`❌ Error al finalizar el ticket ${ticket.id}:`, error)
        });
      }
    );
  }
  
  

  // ---------------------------
  // Funciones para editar fecha de solución
  // ---------------------------
  editarFechaSolucion(ticket: Ticket) {
    this.editandoFechaSolucion[ticket.id] = true;
    // Inicializar la fecha seleccionada si no existe
    if (!this.fechaSolucionSeleccionada[ticket.id]) {
      this.fechaSolucionSeleccionada[ticket.id] = ticket.fecha_solucion || "";
    }
  }

  guardarFechaSolucion(ticket: Ticket) {
    // Verificar que el usuario haya seleccionado alguna fecha
    if (!this.fechaSolucionSeleccionada[ticket.id]) return;
  
    const token = localStorage.getItem("token");
    if (!token) {
      console.error("❌ No hay token almacenado.");
      return;
    }
  
    console.log(`📤 Fecha enviada al backend para ticket #${ticket.id}: ${this.fechaSolucionSeleccionada[ticket.id]}`);
  
    // Configurar headers para la petición
    const headers = new HttpHeaders()
      .set("Authorization", `Bearer ${token}`)
      .set("Content-Type", "application/json");
  
    console.log(`📤 Fecha antes de ajustes: ${this.fechaSolucionSeleccionada[ticket.id]}`);
    
    
    // Ajuste: Fijar la hora a la 1:00:00 AM en lugar de 00:01:00
    const fechaFormateada = `${this.fechaSolucionSeleccionada[ticket.id]} 01:00:00`;
  
    // Construir los datos que se enviarán al backend
    const datosEnviados = {
      estado: ticket.estado,          // Mantiene el estado actual del ticket
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
  
    // Realizar la petición PUT para actualizar el ticket en el backend
    this.http.put(`${this.apiUrl}/update/${ticket.id}`, datosEnviados, { headers }).subscribe({
      next: () => {
        // Actualizar la fecha_solución localmente
        ticket.fecha_solucion = fechaFormateada;
        // Salir del modo edición
        this.editandoFechaSolucion[ticket.id] = false;
  
        // Actualizar el historial en el ticket (por si la UI lo muestra)
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
  
  getIndicadorColor(ticket: Ticket): string {
    // Si no hay historial, no se muestra color
    if (!ticket.fecha_solucion || !ticket.historial_fechas || ticket.historial_fechas.length === 0) {
      return 'transparent';
    }
  
    // Suponemos que la primera entrada del historial es la fecha original
    const fechaOriginalStr = ticket.historial_fechas[0].fecha;
    const fechaNuevaStr = ticket.fecha_solucion;
  
    const fechaOriginal = new Date(fechaOriginalStr);
    const fechaNueva = new Date(fechaNuevaStr);
  
    if (isNaN(fechaOriginal.getTime()) || isNaN(fechaNueva.getTime())) {
      return 'transparent';
    }
  
    // Diferencia en días (redondeada)
    const diffDays = Math.round((fechaNueva.getTime() - fechaOriginal.getTime()) / (1000 * 60 * 60 * 24));
  
    if (diffDays < 0) {
      // Se movió hacia atrás → verde
      return 'green';
    } else if (diffDays <= 5) {
      // Se movió hacia adelante hasta 5 días → amarillo
      return 'yellow';
    } else {
      // Más de 5 días hacia adelante → rojo
      return 'red';
    }
  }
  

  cancelarEdicion(ticket: Ticket) {
    this.editandoFechaSolucion[ticket.id] = false;
  }

  // ---------------------------
  // Funciones para mostrar historial y confirmación de acciones
  // ---------------------------
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

  // ---------------------------
  // Función para filtrar tickets localmente
  // ---------------------------
  filtrarTickets() {
    this.filteredTickets = this.tickets.filter(ticket =>
      (this.filtroEstado ? ticket.estado === this.filtroEstado : true) &&
      (this.filtroDepartamento ? ticket.departamento === this.filtroDepartamento : true) &&
      (this.filtroFecha ? new Date(ticket.fecha_creacion).toISOString().split('T')[0] === this.filtroFecha : true) &&
      (this.filtroFechaFinalizacion
        ? ticket.fecha_finalizado && new Date(ticket.fecha_finalizado).toISOString().split('T')[0] === this.filtroFechaFinalizacion
        : true) &&
      (this.filtroCriticidad ? ticket.criticidad === parseInt(this.filtroCriticidad, 10) : true)
    );
  }


}
