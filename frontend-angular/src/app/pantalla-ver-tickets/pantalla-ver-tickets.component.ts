//pantalla-ver-tickets.componets.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TicketService } from '../services/ticket.service';
import * as ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';

// Definición del tipo esperado de la respuesta de la API
interface Ticket {
  id: number;
  titulo: string;
  descripcion: string;
  username: string;
  estado: string;
  fecha_creacion: string;
  fecha_finalizado: string | null;
}

interface ApiResponse {
  mensaje: string;
  tickets: Ticket[];
}

@Component({
  selector: 'app-pantalla-ver-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pantalla-ver-tickets.component.html',
  styleUrls: ['./pantalla-ver-tickets.component.css']
})
export class PantallaVerTicketsComponent implements OnInit {

  tickets: Ticket[] = [];
  filteredTickets: Ticket[] = [];
  usuariosDisponibles: string[] = [];

  filtroEstado: string = "";
  filtroUsuario: string = "";
  filtroFecha: string = "";

  user: any = null; // 🔥 Aquí guardaremos el usuario autenticado

  private apiUrl = 'http://localhost:5000/api/tickets'; // ✅ URL de la API
  private authUrl = 'http://localhost:5000/api/auth/session-info'; // ✅ URL para obtener info del usuario

  constructor(private ticketService: TicketService, private http: HttpClient) {}

  ngOnInit() {
    this.obtenerUsuarioAutenticado().then(() => {
      this.cargarTickets();
    });
  }
  

// ✅ Obtener información del usuario autenticado
async obtenerUsuarioAutenticado() {
  const token = localStorage.getItem('token');
  if (!token) {
    console.warn("⚠️ No hay token, el usuario no está autenticado.");
    return;
  }

  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

  try {
    const response = await this.http.get<{ user: any }>('http://localhost:5000/api/auth/session-info', { headers }).toPromise();
    this.user = response?.user;
    console.log("✅ Usuario autenticado:", this.user);
  } catch (error) {
    console.error("❌ Error obteniendo usuario autenticado:", error);
  }
}
  // ✅ Cargar los tickets desde el backend
cargarTickets() {
  this.ticketService.getTickets().subscribe({
    next: (data) => {
      if (data && data.tickets) {
        this.tickets = data.tickets.map((ticket: any) => {
          let estadoNormalizado: "pendiente" | "en progreso" | "finalizado";

          switch (ticket.estado?.trim().toLowerCase()) {
            case "abierto":
            case "pendiente":
              estadoNormalizado = "pendiente";
              break;
            case "en progreso":
              estadoNormalizado = "en progreso";
              break;
            case "finalizado":
              estadoNormalizado = "finalizado";
              break;
            default:
              estadoNormalizado = "pendiente";
          }
          const fechaCreacion = new Date(ticket.fecha_creacion);
          const offset = fechaCreacion.getTimezoneOffset();
          const fechaLocal = new Date(fechaCreacion.getTime() - offset);

          if (isNaN(fechaCreacion.getTime())) {
            console.warn(`⚠️ Fecha inválida en ticket ID ${ticket.id}: ${ticket.fecha_creacion}`);
            ticket.fecha_creacion = null;  // Evitar errores con fechas inválidas
          }
          else {
            ticket.fecha_creacion = fechaLocal.toISOString().slice(0, 19).replace("T", " ");
          }
          return { ...ticket, estado: estadoNormalizado };
        });

        // 🔹 Ordenar los tickets por fecha de creación (más reciente primero)
        this.tickets.sort((a, b) => new Date(b.fecha_creacion).getTime() - new Date(a.fecha_creacion).getTime());

        // Extraer usuarios únicos para el filtro
        this.usuariosDisponibles = [...new Set(this.tickets.map(ticket => ticket.username))];

        this.filteredTickets = [...this.tickets];
      }
    },
    error: (error) => {
      console.error("❌ Error al cargar los tickets:", error);
    }
  });
}

  // ✅ Cambiar el estado del ticket
cambiarEstadoTicket(ticket: Ticket, nuevoEstado: "pendiente" | "en progreso" | "finalizado") {
  if (!this.user || this.user.id_sucursal !== 1000) {
      console.warn("⚠️ No tienes permisos para cambiar el estado del ticket.");
      return;
  }

  console.log(`📌 Cambiando estado del ticket ID: ${ticket.id} a '${nuevoEstado}'`); // 🔥 Agregar esta línea para depurar

  if (!ticket.id) {
      console.error("❌ Error: Ticket ID es undefined.");
      return;
  }
  const token = localStorage.getItem('token');
  if (!token) {
    console.error("❌ No hay token en localStorage. No se puede actualizar el ticket.");
    return;
  }

  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');

  this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, { estado: nuevoEstado }, { headers, withCredentials: true }).subscribe({
    next: (data: ApiResponse) => {
      console.log(`✅ Ticket ${ticket.id} cambiado a '${nuevoEstado}':`, data.mensaje);
      ticket.estado = nuevoEstado;
    },
    error: (error: any) => {
      console.error(`❌ Error al cambiar el estado del ticket ${ticket.id}:`, error);
    }
  });
}

  // ✅ Finalizar un ticket
finalizarTicket(ticket: Ticket) {
  if (!this.user || this.user.id_sucursal !== 1000) return;

  const token = localStorage.getItem('token');
  if (!token) {
    console.error("❌ No hay token en localStorage. No se puede finalizar el ticket.");
    return;
  }

  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');

  const fechaActual = new Date();
  const offset = fechaActual.getTimezoneOffset() * 60000; // Obtiene la diferencia de zona horaria en milisegundos
  const fechaLocal = new Date(fechaActual.getTime() - offset);
  const fechaFinalizado = fechaLocal.toISOString().slice(0, 19).replace("T", " ");
  
  this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, { estado: "finalizado", fecha_finalizado: fechaFinalizado }, { headers, withCredentials: true }).subscribe({
    next: (data: ApiResponse) => {
      console.log(`✅ Ticket ${ticket.id} finalizado:`, data.mensaje);
      ticket.estado = "finalizado";
      ticket.fecha_finalizado = fechaFinalizado;
    },
    error: (error: any) => {
      console.error(`❌ Error al finalizar el ticket ${ticket.id}:`, error);
    }
  });
}

  // ✅ Exportar a Excel
exportToExcel() {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Tickets');

  worksheet.columns = [
    { header: 'ID', key: 'id', width: 10 },
    { header: 'Título', key: 'titulo', width: 30 },
    { header: 'Descripción', key: 'descripcion', width: 50 },
    { header: 'Usuario', key: 'username', width: 20 },
    { header: 'Estado', key: 'estado', width: 15 },
    { header: 'Fecha de Creación', key: 'fecha_creacion', width: 20 },
    { header: 'Fecha Finalizado', key: 'fecha_finalizado', width: 20 }
  ];

    this.filteredTickets.forEach(ticket => worksheet.addRow(ticket));

    worksheet.getRow(1).font = { bold: true };

    workbook.xlsx.writeBuffer().then((buffer) => {
      const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      saveAs(blob, 'tickets.xlsx');
    }).catch(err => console.error("❌ Error al generar el Excel:", err));
  }

  logTicket(ticket: Ticket) {
    console.log("🟡 Ticket recibido al hacer click:", ticket);
}


formatearFecha(fechaString: string | null): string {
  if (!fechaString || fechaString === 'N/A' || fechaString === 'null') return 'N/A';

  const fecha = new Date(fechaString);
  if (isNaN(fecha.getTime())) return 'Fecha inválida'; // Evita errores si el formato es incorrecto

  return fecha.toLocaleString('es-ES', { 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit'
  }).replace(',', '');
}



// ✅ Filtrar tickets
filtrarTickets() {
  this.filteredTickets = this.tickets.filter(ticket => {
    const coincideEstado = this.filtroEstado ? ticket.estado === this.filtroEstado : true;
    const coincideUsuario = this.filtroUsuario ? ticket.username.toLowerCase().includes(this.filtroUsuario.toLowerCase()) : true;
    const coincideFecha = this.filtroFecha ? new Date(ticket.fecha_creacion).toISOString().split('T')[0] === this.filtroFecha : true;
    return coincideEstado && coincideUsuario && coincideFecha;
    });
  }
}
