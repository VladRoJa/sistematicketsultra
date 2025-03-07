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
  titulo: string;
  descripcion: string;
  username: string;
  estado: string;
  criticidad: number;
  fecha_creacion: string;
  fecha_finalizado: string | null;
  departamento: string;
  departamento_id: number;
  categoria: string;
}

interface ApiResponse {
  mensaje: string;
  tickets: Ticket[];
}

@Component({
  selector: 'app-pantalla-ver-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule, NgxPaginationModule],
  templateUrl: './pantalla-ver-tickets.component.html',
  styleUrls: ['./pantalla-ver-tickets.component.css']
})
export class PantallaVerTicketsComponent implements OnInit {

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
  
    this.http.get<ApiResponse>(`${this.apiUrl}/all`, { headers }).subscribe({
      next: (data) => {
        if (!data?.tickets) {
          this.loading = false;
          return;
        }
  
        this.tickets = data.tickets.map(ticket => {
          const estadoNormalizado = this.normalizarEstado(ticket.estado);
          console.log(`🎯 Ticket ID: ${ticket.id}, Estado Normalizado: ${estadoNormalizado}`);
  
          return {
            ...ticket,
            criticidad: ticket.criticidad || 1,
            estado: estadoNormalizado,
            departamento: this.departamentoService.obtenerNombrePorId(ticket.departamento_id),
            fecha_creacion: this.formatearFecha(ticket.fecha_creacion),
            fecha_finalizado: ticket.fecha_finalizado ? this.formatearFecha(ticket.fecha_finalizado) : null
          };
        });
  
        this.ordenarTickets();
        this.filteredTickets = [...this.tickets];
        this.loading = false;
      },
      error: (error) => {
        console.error("❌ Error al cargar los tickets:", error);
        this.loading = false;
      }
    });
  }
  
  private ordenarTickets() {
    this.tickets.sort((a, b) => new Date(b.fecha_creacion).getTime() - new Date(a.fecha_creacion).getTime());
  }

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
                    ticket.estado = "finalizado";
                    ticket.fecha_finalizado = fechaFinalizado;
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
    if (!fechaString) return 'Sin finalizar'; // ✅ Muestra "Sin finalizar" si la fecha es NULL
  
    const fecha = new Date(fechaString);
    if (isNaN(fecha.getTime())) return 'Fecha inválida'; // ✅ Evita errores con fechas incorrectas
  
    // 🔹 Ajuste de zona horaria (GMT-8)
    fecha.setHours(fecha.getHours() - 8);
  
    return fecha.toLocaleString('es-ES', { 
      year: 'numeric', 
      month: '2-digit', 
      day: '2-digit', 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit'
    }).replace(',', '');
  }
   
  

  exportToExcel() {
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Tickets');

    worksheet.columns = [
      { header: 'ID', key: 'id', width: 10 },
      { header: 'Título', key: 'titulo', width: 30 },
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


}
