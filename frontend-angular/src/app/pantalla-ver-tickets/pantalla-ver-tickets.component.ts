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



// Definición del tipo esperado de la respuesta de la API
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
  itemsPerPage: number =15;
  loading: boolean = false;

  user: any = null; // 🔥 Aquí guardaremos el usuario autenticado

  private apiUrl = 'http://localhost:5000/api/tickets'; // ✅ URL de la API
  private authUrl = 'http://localhost:5000/auth/session-info'; // ✅ URL para obtener info del usuario

  constructor(
    private ticketService: TicketService,
    private http: HttpClient,
    private departamentoService: DepartamentoService
  
  ) { }

  ngOnInit() {
    this.obtenerUsuarioAutenticado().then(() => {
      this.cargarTickets();
    });
    this.departamentos = this.departamentoService.obtenerDepartamentos();
  }
  

// ✅ Obtener información del usuario autenticado
async obtenerUsuarioAutenticado() {
  const token = localStorage.getItem('token');
  console.log("📡 Token obtenido del localStorage:", token);

  if (!token) {
    console.warn("⚠️ No hay token, el usuario no está autenticado.");
    return;
  }

  console.log("📡 Enviando petición a session-info con token:", token);

  const headers = new HttpHeaders()
    .set('Authorization', `Bearer ${token}`)
    .set('Content-Type', 'application/json');

  try {
    console.log("📡 Enviando petición a session-info con headers:", headers);
    const response = await this.http.get<{ user: any }>('http://localhost:5000/api/auth/session-info', { headers }).toPromise();
    
    if (!response || !response.user) {
      console.error("❌ No se recibió un usuario válido desde session-info");
      return;
    }

    this.user = response.user;
    console.log("✅ Usuario autenticado:", this.user);
  } catch (error) {
    console.error("❌ Error obteniendo usuario autenticado:", error);
  }
}
  // ✅ Cargar los tickets desde el backend
  cargarTickets() {
    this.loading = true;  // ⏳ Activar el loader mientras se cargan los tickets
    console.log("⏳ Loader activado, estado de loading:", this.loading);


    const token = localStorage.getItem('token');
    if (!token) {
      console.error("❌ No hay token, no se pueden cargar los tickets.");
      this.loading = false; // ⏹️ Desactivar el loader si no hay token
      return;
    }
  
    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');
  
    console.log("📡 Enviando petición a /tickets con headers:", headers);

    const inicioTiempo = Date.now();
    
  
    this.http.get<ApiResponse>('http://localhost:5000/api/tickets/all', { headers }).subscribe({
      next: (data) => {
        if (!data || !data.tickets) {
          console.error("❌ La respuesta de la API no contiene tickets válidos.", data);
          this.loading = false; // ⏹️ Desactivar el loader si no hay tickets
          return;
        }
  
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
          if (isNaN(fechaCreacion.getTime())) {
            console.warn(`⚠️ Fecha inválida en ticket ID ${ticket.id}: ${ticket.fecha_creacion}`);
            ticket.fecha_creacion = null;  
          } else {
            ticket.fecha_creacion = fechaCreacion.toISOString().slice(0, 19).replace("T", " ");
          }
  
          return { ...ticket, criticidad: ticket.criticidad || 1, estado: estadoNormalizado, departamento: this.departamentoService.obtenerNombrePorId(ticket.departamento_id)
        };
      });

        this.filteredTickets = [...this.tickets];
  
        console.log("✅ Tickets cargados:", this.tickets);
      },
      error: (error) => {
        console.error("❌ Error al cargar los tickets:", error);
      },
      complete: () => {
        const tiempoTranscurrido = Date.now() - inicioTiempo;
        const tiempoRestante = Math.max(2000 - tiempoTranscurrido, 0); // ⏳ Asegurar al menos 2.5 segundos
  
        console.log(`⏳ Asegurando un tiempo mínimo de carga: ${tiempoRestante} ms`);
        setTimeout(() => {
          this.loading = false;
          console.log("✅ Loader desactivado");
        }, tiempoRestante);
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



formatearFechaCreacion(fechaString: string | null): string {
  if (!fechaString || fechaString === 'N/A' || fechaString === 'null') return 'N/A';

  const fechaUTC = new Date(fechaString);
  if (isNaN(fechaUTC.getTime())) return 'Fecha inválida'; // Evita errores si el formato es incorrecto

  // 🔥 Ajusta la zona horaria manualmente restando 8 horas
  fechaUTC.setHours(fechaUTC.getHours());

  return fechaUTC.toLocaleString('es-ES', { 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit'
  }).replace(',', '');
}

formatearFechaFinalizacion(fechaString: string | null): string {
  if (!fechaString || fechaString === 'N/A' || fechaString === 'null') return 'N/A';

  const fechaUTC = new Date(fechaString);
  if (isNaN(fechaUTC.getTime())) return 'Fecha inválida'; // Evita errores si el formato es incorrecto

  // 🔥 Ajusta la zona horaria manualmente restando 8 horas
  fechaUTC.setHours(fechaUTC.getHours() +8);

  return fechaUTC.toLocaleString('es-ES', { 
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
  console.log("🔍 Aplicando filtros...");
  console.log("🎯 Estado:", this.filtroEstado);
  console.log("🏢 Departamento:", this.filtroDepartamento);
  console.log("📅 Fecha de creación:", this.filtroFecha);
  console.log("📅 Fecha de finalización:", this.filtroFechaFinalizacion);
  console.log("⚡ Criticidad:", this.filtroCriticidad);

  this.filteredTickets = this.tickets.filter(ticket => {
    const coincideEstado = this.filtroEstado ? ticket.estado === this.filtroEstado : true;
    const coincideDepartamento = this.filtroDepartamento ? ticket.departamento === this.filtroDepartamento : true;
    const coincideFecha = this.filtroFecha
      ? new Date(ticket.fecha_creacion).toISOString().split('T')[0] === this.filtroFecha
      : true;
    const coincideFechaFinalizacion = this.filtroFechaFinalizacion
      ? ticket.fecha_finalizado && new Date(ticket.fecha_finalizado).toISOString().split('T')[0] === this.filtroFechaFinalizacion
      : true;
    const coincideCriticidad = this.filtroCriticidad
      ? ticket.criticidad === parseInt(this.filtroCriticidad, 10)
      : true;

    return coincideEstado && coincideDepartamento && coincideFecha && coincideFechaFinalizacion && coincideCriticidad;
  });

  console.log("🎯 Tickets después de filtrar:", this.filteredTickets);
}


exportToExcel() {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Tickets');

  // ✅ Definir las columnas a exportar
  worksheet.columns = [
    { header: 'ID', key: 'id', width: 10 },
    { header: 'Título', key: 'titulo', width: 30 },
    { header: 'Descripción', key: 'descripcion', width: 50 },
    { header: 'Usuario', key: 'username', width: 20 },
    { header: 'Estado', key: 'estado', width: 15 },
    { header: 'Criticidad', key: 'criticidad', width: 10 },
    { header: 'Fecha de Creación', key: 'fecha_creacion', width: 20 },
    { header: 'Fecha Finalizado', key: 'fecha_finalizado', width: 20 },
    { header: 'Departamento', key: 'departamento', width: 25 },
    { header: 'Categoría', key: 'categoria', width: 25 }
  ];

  // ✅ Recorrer los tickets filtrados y agregarlos al Excel
  this.filteredTickets.forEach(ticket => {
    worksheet.addRow({
      id: ticket.id,
      titulo: ticket.titulo,
      descripcion: ticket.descripcion,
      username: ticket.username,
      estado: ticket.estado,
      criticidad: ticket.criticidad,
      fecha_creacion: this.formatearFecha(ticket.fecha_creacion),
      fecha_finalizado: ticket.fecha_finalizado ? this.formatearFecha(ticket.fecha_finalizado) : 'N/A',
      departamento: ticket.departamento ? ticket.departamento : 'No asignado',
      categoria: ticket.categoria ? ticket.categoria : 'No especificada'
    });
  });

  // ✅ Aplicar estilos a la primera fila (encabezados)
  worksheet.getRow(1).font = { bold: true };

  // ✅ Generar y descargar el archivo Excel
  workbook.xlsx.writeBuffer().then((buffer) => {
    const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    saveAs(blob, `tickets_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }).catch(err => console.error("❌ Error al generar el Excel:", err));
}

// ✅ Función para formatear fechas correctamente
formatearFecha(fechaString: string | null): string {
  if (!fechaString || fechaString === 'N/A' || fechaString === 'null') return 'N/A';

  const fecha = new Date(fechaString);
  if (isNaN(fecha.getTime())) return 'Fecha inválida'; // Evita errores si el formato es incorrecto

  return fecha.toISOString().slice(0, 19).replace("T", " ");
}
  
// ✅ Eliminar un ticket (Solo Administrador)
eliminarTicket(ticketId: number) {
  if (!this.usuarioEsAdmin) {
    alert("❌ No tienes permisos para eliminar tickets.");
    return;
  }

  if (!confirm("⚠️ ¿Estás seguro de que quieres eliminar este ticket?")) return;

  const token = localStorage.getItem('token');
  if (!token) return;

  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

  this.http.delete<{ mensaje: string }>(`${this.apiUrl}/delete/${ticketId}`, { headers }).subscribe({
    next: () => {
      this.tickets = this.tickets.filter(ticket => ticket.id !== ticketId);
      this.filteredTickets = this.filteredTickets.filter(ticket => ticket.id !== ticketId);
      alert("✅ Ticket eliminado correctamente.");
    },
    error: () => alert("❌ Error al eliminar el ticket.")
  });
}

}
