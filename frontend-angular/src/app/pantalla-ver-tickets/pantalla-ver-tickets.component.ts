//pantalla-ver-tickets.componets.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TicketService } from '../services/ticket.service';

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
  private apiUrl = 'http://localhost:5000/api/tickets';  // ✅ URL de la API

  constructor(private ticketService: TicketService, private http: HttpClient) {}

  ngOnInit() {
    this.cargarTickets();
  }

  cargarTickets() {
    this.ticketService.getTickets().subscribe({
      next: (data) => {
        console.log("📌 Respuesta del backend:", data);
  
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
                estadoNormalizado = "pendiente"; // Valor por defecto si viene un estado desconocido
            }
  
            return { ...ticket, estado: estadoNormalizado };
          });
  
          this.filteredTickets = [...this.tickets];
  
          console.log("📌 Tickets después de la transformación:", this.tickets);
        } else {
          console.error("❌ La respuesta no contiene 'tickets'", data);
        }
      },
      error: (error) => {
        console.error("❌ Error al cargar los tickets:", error);
      }
    });
  }
                  
  cambiarEstadoTicket(ticket: Ticket, nuevoEstado:  "pendiente" | "en progreso" | "finalizado") {
    const token = localStorage.getItem('token');
    if (!token) {
      console.error("❌ No hay token en localStorage. No se puede actualizar el ticket.");
      return;
    }
  
    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');
  
    this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, { estado: nuevoEstado }, { headers, withCredentials: true }).subscribe({
      next: (data: ApiResponse) => {
        console.log(`✅ Ticket ${ticket.id} cambiado a '${nuevoEstado}':`, data.mensaje);
  
        // Actualizar el estado localmente para que Angular refleje el cambio
        ticket.estado = nuevoEstado as "pendiente" | "en progreso" | "finalizado";

      },
      error: (error: any) => {
        console.error(`❌ Error al cambiar el estado del ticket ${ticket.id}:`, error);
      }
    });
  }
  
  finalizarTicket(ticket: Ticket) {
    const token = localStorage.getItem('token');
    if (!token) {
      console.error("❌ No hay token en localStorage. No se puede finalizar el ticket.");
      return;
    }
  
    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');
  
    // 🔹 Convertir la fecha actual al formato compatible con MySQL (YYYY-MM-DD HH:MM:SS)
    const fechaActual = new Date();
    const fechaFinalizado = `${fechaActual.getFullYear()}-${('0' + (fechaActual.getMonth() + 1)).slice(-2)}-${('0' + fechaActual.getDate()).slice(-2)} ${('0' + fechaActual.getHours()).slice(-2)}:${('0' + fechaActual.getMinutes()).slice(-2)}:${('0' + fechaActual.getSeconds()).slice(-2)}`;
  
    console.log(`📌 Enviando PUT: Ticket ID ${ticket.id}, Estado: 'finalizado', Fecha Finalizado: '${fechaFinalizado}'`);
  
    this.http.put<ApiResponse>(`${this.apiUrl}/update/${ticket.id}`, 
      { estado: "finalizado", fecha_finalizado: fechaFinalizado }, 
      { headers, withCredentials: true }
    ).subscribe({
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

  getEstadoLimpio(estado: string): string {
    return estado ? estado.trim().toLowerCase() : '';
  }
  

}