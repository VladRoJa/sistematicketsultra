  // C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.estado-ticket.ts

  import { PantallaVerTicketsComponent, Ticket, ApiResponse } from '../pantalla-ver-tickets.component';
  import { HttpHeaders } from '@angular/common/http';
  import { cargarTickets } from './pantalla-ver-tickets.init';
  import { formatearFechaFinalizado } from 'src/app/utils/ticket-utils';
  import { environment } from 'src/environments/environment';

  /**
   * Funciones para cambiar el estado de un ticket
   */

  const API_URL = `${environment.apiUrl}/tickets`;

  /** Cambiar el estado de un ticket */
  export function cambiarEstadoTicket(
    component: PantallaVerTicketsComponent,
    ticket: Ticket,
    nuevoEstado: "pendiente" | "en progreso" | "finalizado"
  ): void {
    if (!component.usuarioEsAdmin) return;

    component.mostrarConfirmacion(
      `¿Estás seguro de cambiar el estado del ticket #${ticket.id} a ${nuevoEstado.toUpperCase()}?`,
      () => actualizarEstadoEnServidor(component, ticket, nuevoEstado)
    );
  }

  /** Finalizar directamente un ticket */
  export function finalizarTicket(
    component: PantallaVerTicketsComponent,
    ticket: Ticket
  ): void {
    if (!component.usuarioEsAdmin) return;

    component.mostrarConfirmacion(
      `¿Estás seguro de marcar como FINALIZADO el ticket #${ticket.id}?`,
      () => actualizarEstadoEnServidor(component, ticket, "finalizado", true)
    );
  }

  /** Actualizar el estado del ticket en la base de datos */
  function actualizarEstadoEnServidor(
    component: PantallaVerTicketsComponent,
    ticket: Ticket,
    nuevoEstado: "pendiente" | "en progreso" | "finalizado",
    recargar: boolean = false
  ): void {
    const token = localStorage.getItem('token');
    if (!token) return;

    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');

    const updateData: any = { estado: nuevoEstado };

    if (nuevoEstado === "finalizado") {
      const fechaLocal = new Intl.DateTimeFormat('sv-SE', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'America/Tijuana'
      }).format(new Date()).replace(' ', 'T') + ':00';
      
      updateData.fecha_finalizado = fechaLocal.replace('T', ' ');  }

    component.http.put<ApiResponse>(`${API_URL}/update/${ticket.id}`, updateData, { headers }).subscribe({
      next: () => {
        if (recargar) {
          cargarTickets(component);
        } else {
          ticket.estado = nuevoEstado;
          if (nuevoEstado === "finalizado") {
            ticket.fecha_finalizado = formatearFechaFinalizado(updateData.fecha_finalizado);
          }
          component.changeDetectorRef.detectChanges();
        }
      },
      error: (error) => console.error(`❌ Error actualizando el ticket #${ticket.id}:`, error),
    });
  }
