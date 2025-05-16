// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.estado-ticket.ts

import { PantallaVerTicketsComponent, Ticket, ApiResponse } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { cargarTickets } from './pantalla-ver-tickets.init';
import { environment } from 'src/environments/environment';
import { DialogoConfirmacionComponent } from 'src/app/shared/dialogo-confirmacion/dialogo-confirmacion.component';


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
  if (!component.usuarioEsAdmin && !component.usuarioEsEditorCorporativo) return;

  const dialogRef = (component as any).dialog.open(DialogoConfirmacionComponent, {
    data: {
      titulo: 'Cambiar Estado',
      mensaje: `¿Estás seguro de cambiar el estado del ticket #${ticket.id} a ${nuevoEstado.toUpperCase()}?`,
      textoConfirmar: 'Confirmar',
      color: 'primary'
    }
  });

  dialogRef.afterClosed().subscribe((resultado: boolean) => {
    if (resultado) {
      actualizarEstadoEnServidor(component, ticket, nuevoEstado);
    }
  });
}

/** Finalizar directamente un ticket */
export function finalizarTicket(
  component: PantallaVerTicketsComponent,
  ticket: Ticket
): void {
  if (!component.usuarioEsAdmin && !component.usuarioEsEditorCorporativo) return;

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
  const fechaActual = new Date();
  const fechaISO = fechaActual.toISOString();

  if (nuevoEstado === "finalizado") {
    updateData.fecha_finalizado = fechaISO;
  }

  if (nuevoEstado === "en progreso") {
    updateData.fecha_en_progreso = fechaISO;
  }

  component.http.put<ApiResponse>(`${API_URL}/update/${ticket.id}`, updateData, { headers }).subscribe({
    next: () => {
      // 🧼 Que el backend nos regrese datos limpios
      cargarTickets(component);
    },
    error: (error) => console.error(`❌ Error actualizando el ticket #${ticket.id}:`, error),
  });
}
