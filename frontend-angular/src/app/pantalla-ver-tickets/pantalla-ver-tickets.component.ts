//pantalla-ver-tickets.componets.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TicketService } from '../services/ticket.service';
import * as ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';
import { NgxPaginationModule } from 'ngx-pagination';
import { DepartamentoService } from '../services/departamento.service';
import { ChangeDetectorRef } from '@angular/core';


interface Ticket {
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
  fecha_solucion?: string | null;  // ✅ Nueva propiedad opcional
  historial_fechas?: Array<{             
    fecha: string;
    cambiadoPor: string;
    fechaCambio: string;
  }>;
} 

interface ApiResponse {
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


  //propiedades

  tickets: Ticket[] = [];
  filteredTickets: Ticket[] = [];
  departamentos: { id: number, nombre: string }[] = []; 
  usuariosDisponibles: string[] = [];
  usuarioEsAdmin: boolean = false;
  filtroEstado: string = "";
  filtroDepartamento: string = "";
  filtroUsuario: string = "";
  filtroFecha: string = "";
  filtroFechaFinalizacion: string = "";
  filtroCriticidad: string = "";
  page: number = 1;
  itemsPerPage: number = 15;
  loading: boolean = false;
  user: any = null; 
  confirmacionVisible: boolean = false;
  accionPendiente: (() => void) | null = null;
  mensajeConfirmacion: string = "";
  fechaSolucionSeleccionada: { [id: number]: string } = {}; 
  editandoFechaSolucion: { [id: number]: boolean } = {};
  passwordEdicion: string = "";
  historialVisible: { [id: number]: boolean } = {};
  totalTickets: number = 0;



  private apiUrl = 'http://localhost:5000/api/tickets'; 
  private authUrl = 'http://localhost:5000/api/auth/session-info';


  constructor(
    private ticketService: TicketService,
    private http: HttpClient,
    private departamentoService: DepartamentoService,
    private changeDetectorRef: ChangeDetectorRef

  ) { }

  ngOnInit() {
    this.obtenerUsuarioAutenticado().then(() => this.cargarTickets());
    this.departamentos = this.departamentoService.obtenerDepartamentos();
  }

  async obtenerUsuarioAutenticado() {
    const token = localStorage.getItem('token');
    if (!token) return;

    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');
    
    try {
      const response = await this.http.get<{ user: any }>(this.authUrl, { headers }).toPromise();
      if (response?.user) {
        this.user = response.user;
        this.usuarioEsAdmin = this.user.id_sucursal === 1000;
        console.log("✅ Usuario autenticado:", this.user);
      }
    } catch (error) {
      console.error("❌ Error obteniendo usuario autenticado:", error);
    }
  }

  private normalizarEstado(estado: string): "pendiente" | "en progreso" | "finalizado" {
    const estadoLimpio = estado?.trim().toLowerCase();
    if (estadoLimpio === "abierto" || estadoLimpio === "pendiente") return "pendiente";
    if (estadoLimpio === "en progreso") return "en progreso";
    if (estadoLimpio === "finalizado") return "finalizado";
    return "pendiente"; // Valor por defecto si no coincide con ninguno
  }
  

  cargarTickets() {
    this.loading = true;
    const token = localStorage.getItem('token');
    if (!token) {
        this.loading = false;
        return;
    }

    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');

    const offset = (this.page - 1) * this.itemsPerPage; // 🔹 Calculamos el offset
    const url = `${this.apiUrl}/all?limit=${this.itemsPerPage}&offset=${offset}&sort=desc`;

    console.log("📌 URL enviada a la API:", url);

    this.http.get<ApiResponse>(url, { headers }).subscribe({
        next: (data) => {

          console.log("📥 Respuesta de la API:", data);
          console.log("📥 Tickets recibidos en esta página:", data.tickets.map(t => t.id));

            if (!data?.tickets) {
                this.loading = false;
                return;
            }

            this.tickets = data.tickets.map(ticket => ({
                ...ticket,
                criticidad: ticket.criticidad || 1,
                estado: this.normalizarEstado(ticket.estado),
                departamento: this.departamentoService.obtenerNombrePorId(ticket.departamento_id),
                fecha_creacion: this.formatearFecha(ticket.fecha_creacion),
                fecha_finalizado: ticket.fecha_finalizado ? this.formatearFecha(ticket.fecha_finalizado) : null,
                historial_fechas: typeof ticket.historial_fechas === "string" ? JSON.parse(ticket.historial_fechas) : ticket.historial_fechas || []
            }));

            this.totalTickets = data.total_tickets; // 🔹 Guardamos el total de tickets
            this.filteredTickets = [...this.tickets];


            console.log("📌 Tickets guardados en `filteredTickets`:", this.filteredTickets.map(t => t.id));
            console.log("📌 Tickets cargados en la página:", this.page);
            console.log("📌 Total de tickets disponibles:", this.totalTickets);

            this.loading = false;
        },
        error: (error) => {
            console.error("❌ Error al cargar los tickets:", error);
            this.loading = false;
        }
    });
}

private ordenarTickets() {
  // 🔹 Asegurar que todos los tickets tengan una fecha válida
  const tieneFechasValidas = this.tickets.every(ticket => {
      return ticket.fecha_creacion && !isNaN(new Date(ticket.fecha_creacion).getTime());
  });

  if (tieneFechasValidas) {
      console.log("✅ Usando orden por fecha de creación");
      this.tickets.sort((a, b) => 
          new Date(b.fecha_creacion).getTime() - new Date(a.fecha_creacion).getTime()
      );
  } else {
      console.warn("⚠️ Algunas fechas son inválidas, ordenando por ID");
      this.tickets.sort((a, b) => b.id - a.id);
  }
}

  // ✅ Función para mostrar el modal de confirmación

  mostrarConfirmacion(mensaje: string, accion: () => void) {
    this.mensajeConfirmacion = mensaje;
    this.accionPendiente = accion;
    this.confirmacionVisible = true;
}

  // ✅ Función para ejecutar la acción confirmada
  confirmarAccion() {
      if (this.accionPendiente) {
          this.accionPendiente();  // 🔥 Ejecuta la acción almacenada
      }
      this.confirmacionVisible = false;  // Cierra el modal
  }

  // ✅ Función para cerrar el modal sin hacer cambios
  cancelarAccion() {
      this.confirmacionVisible = false;
      this.accionPendiente = null;
  }


  cambiarEstadoTicket(ticket: Ticket, nuevoEstado: "pendiente" | "en progreso" | "finalizado") {
    if (!this.usuarioEsAdmin) return;
  
    this.mostrarConfirmacion(
      `¿Estás seguro de cambiar el estado del ticket #${ticket.id} a ${nuevoEstado.toUpperCase()}?`,
      () => {
        const token = localStorage.getItem('token');
        if (!token) return;
  
        const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');
  
        this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, { estado: nuevoEstado }, { headers }).subscribe({
          next: () => {
            ticket.estado = nuevoEstado;
            this.changeDetectorRef.detectChanges(); // 🔹 Forzar actualización de la UI
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

            const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');

            const fechaFinalizado = new Date().toISOString().slice(0, 19).replace("T", " ");

            this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, { estado: "finalizado", fecha_finalizado: fechaFinalizado }, { headers }).subscribe({
                next: () => {
                    console.log("✅ Ticket finalizado en el backend.");

                    // 🔹 Recargar la lista de tickets desde el backend
                    this.cargarTickets();
                },
                error: (error) => console.error(`❌ Error al finalizar el ticket ${ticket.id}:`, error)
            });
        }
    );
}



  eliminarTicket(ticketId: number) {
    if (!this.usuarioEsAdmin) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
    
    this.http.delete<ApiResponse>(`${this.apiUrl}/delete/${ticketId}`, { headers }).subscribe({
      next: () => {
        this.tickets = this.tickets.filter(ticket => ticket.id !== ticketId);
        this.filteredTickets = this.filteredTickets.filter(ticket => ticket.id !== ticketId);
      },
      error: () => console.error("❌ Error al eliminar el ticket.")
    });
  }

  filtrarTickets() {
    this.filteredTickets = this.tickets.filter(ticket => 
      (this.filtroEstado ? ticket.estado === this.filtroEstado : true) &&
      (this.filtroDepartamento ? ticket.departamento === this.filtroDepartamento : true) &&
      (this.filtroFecha ? new Date(ticket.fecha_creacion).toISOString().split('T')[0] === this.filtroFecha : true) &&
      (this.filtroFechaFinalizacion ? ticket.fecha_finalizado && new Date(ticket.fecha_finalizado).toISOString().split('T')[0] === this.filtroFechaFinalizacion : true) &&
      (this.filtroCriticidad ? ticket.criticidad === parseInt(this.filtroCriticidad, 10) : true)
    );
  }

  formatearFecha(fechaString: string | null): string {
    if (!fechaString) return 'Sin finalizar';

    console.log(`🔍 Formateando fecha: ${fechaString}`);

    let fecha = new Date(fechaString);

    if (isNaN(fecha.getTime())) {
        console.error(`❌ Fecha inválida detectada: ${fechaString}`);
        return 'Fecha inválida';
    }

    // 🔹 Ajuste de zona horaria para evitar desfases
    fecha.setMinutes(fecha.getMinutes() + fecha.getTimezoneOffset());

    return fecha.toLocaleString('es-ES', {
        year: '2-digit',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    }).replace(',', '').replace(/\//g, '-'); // 🔹 Cambia "/" por "-"
}


  exportToExcel() {
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

    this.filteredTickets.forEach(ticket => {
      worksheet.addRow({
        ...ticket,
        fecha_finalizado: ticket.fecha_finalizado || 'N/A'
      });
    });

    workbook.xlsx.writeBuffer().then(buffer => saveAs(new Blob([buffer]), `tickets_${new Date().toISOString().slice(0, 10)}.xlsx`));
  }


  editarFechaSolucion(ticket: Ticket) {
    this.editandoFechaSolucion[ticket.id] = true;
    this.fechaSolucionSeleccionada[ticket.id] = ticket.fecha_solucion || "";
  }

  guardarFechaSolucion(ticket: Ticket) {
    if (!this.fechaSolucionSeleccionada[ticket.id]) return;
  
    const token = localStorage.getItem("token");
    if (!token) {
      console.error("❌ No hay token almacenado.");
      return;
    }

    console.log(`📤 Fecha enviada al backend para ticket ${ticket.id}: ${this.fechaSolucionSeleccionada[ticket.id]}`);

    const headers = new HttpHeaders()
      .set("Authorization", `Bearer ${token}`)
      .set("Content-Type", "application/json");

    console.log(`📤 Fecha antes de ajustes: ${this.fechaSolucionSeleccionada[ticket.id]}`);

    const fechaFormateada = `${this.fechaSolucionSeleccionada[ticket.id]} 00:01:00`;

    const datosEnviados = {
        estado: ticket.estado,
        fecha_solucion: fechaFormateada, // ✅ Ahora con hora fija 00:01:00
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

        if (!ticket.historial_fechas) ticket.historial_fechas = [];
        ticket.historial_fechas.push({
          fecha: fechaFormateada,
          cambiadoPor: this.user.username,
          fechaCambio: new Date().toISOString(),
        });

        console.log(`✅ Fecha de solución del ticket #${ticket.id} actualizada.`);
      },
      error: (error) => console.error(`❌ Error al actualizar la fecha de solución del ticket:`, error),
    });
}

  
  cancelarEdicion(ticket: Ticket) {
    this.editandoFechaSolucion[ticket.id] = false;
  }

  confirmarEdicionFecha(ticket: Ticket) {
    const passwordCorrecta = "admin123"; // Reemplazar con un sistema seguro de autenticación
  
    if (this.passwordEdicion !== passwordCorrecta) {
      alert("❌ Contraseña incorrecta. No tienes permisos para editar esta fecha.");
      return;
    }
  
    this.editandoFechaSolucion[ticket.id] = true;
  }
  
  toggleHistorial(ticketId: number) {
    const ticket = this.tickets.find(t => t.id === ticketId);
    
    if (!ticket) {
      console.error(`❌ No se encontró el ticket con ID: ${ticketId}`);
      return;
    }
  
    console.log(`📜 Historial del ticket #${ticketId}:`, ticket.historial_fechas);
  
    if (!this.historialVisible[ticketId]) {
      this.historialVisible[ticketId] = true;
    } else {
      this.historialVisible[ticketId] = !this.historialVisible[ticketId];
    }
  }
  
  
  
  formatearFechaCorta(fechaString: string | null): string {
    if (!fechaString) return 'dd/mm/aaaa';
    
    const fecha = new Date(fechaString);
    return fecha.toLocaleDateString('es-ES', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit'
    });
  }

  // 🔹 Cambiar de página manualmente
cambiarPagina(direccion: number) {
  const nuevaPagina = this.page + direccion;
  if (nuevaPagina > 0 && nuevaPagina <= this.totalPaginas()) {
      this.page = nuevaPagina;
      this.cargarTickets();
  }
}

// 🔹 Calcular el número total de páginas
totalPaginas(): number {
  return Math.ceil(this.totalTickets / this.itemsPerPage);
}
}