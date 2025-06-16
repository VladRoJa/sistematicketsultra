// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.estado-ticket.ts

import { PantallaVerTicketsComponent, Ticket, ApiResponse } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { cargarTickets } from './pantalla-ver-tickets.init';
import { environment } from 'src/environments/environment';
import { mostrarAlertaErrorDesdeStatus, mostrarAlertaToast } from 'src/app/utils/alertas';
import { AsignarFechaModalComponent } from '../modals/asignar-fecha-modal.component';


/**
 * Funciones para cambiar el estado de un ticket
 */

const API_URL = `${environment.apiUrl}/tickets`;

/** Cambiar el estado de un ticket */
export function cambiarEstadoTicket(
  component: PantallaVerTicketsComponent,
  ticket: Ticket,
  nuevoEstado: 'pendiente' | 'en progreso' | 'finalizado',
  onSuccess?: () => void
): void {
  const token = localStorage.getItem("token");
  if (!token) { console.error("❌ No hay token disponible."); return; }

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  // Si es "en progreso" y no tiene fecha_solucion, abrir modal obligatorio
  if (nuevoEstado === 'en progreso' && !ticket.fecha_solucion) {
    const dialogRef = component.dialog.open(AsignarFechaModalComponent, {
      width: '400px',
      disableClose: true,
      data: {}
    });

    dialogRef.componentInstance.onGuardar.subscribe(({ fecha }) => {
      const fechaSolucion = new Date(
        fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), 7, 0, 0
      ).toISOString();

      const body = {
        estado: nuevoEstado,
        fecha_solucion: fechaSolucion,
        fecha_en_progreso: new Date().toISOString()
      };

      component.http.put(`${API_URL}/update/${ticket.id}`, body, { headers }).subscribe({
        next: () => {
          ticket.estado = nuevoEstado;
          ticket.fecha_en_progreso = body.fecha_en_progreso;
          ticket.fecha_solucion = fechaSolucion;
          mostrarAlertaToast(`✅ Ticket #${ticket.id} actualizado a '${nuevoEstado}'`);
          dialogRef.close();
          if (onSuccess) onSuccess();
        },
        error: (error) => {
          mostrarAlertaErrorDesdeStatus(error.status);
        }
      });
    });

    dialogRef.componentInstance.onCancelar.subscribe(() => {
      dialogRef.close();
    });

    return;
  }

  // ✅ Flujo normal para otros estados o si ya tiene fecha_solucion
  const body = { estado: nuevoEstado };

  component.http.put(`${API_URL}/update/${ticket.id}`, body, { headers }).subscribe({
    next: () => {
      ticket.estado = nuevoEstado;
      mostrarAlertaToast(`✅ Ticket #${ticket.id} actualizado a '${nuevoEstado}'`);
      if (onSuccess) onSuccess();
    },
    error: (error) => {
      mostrarAlertaErrorDesdeStatus(error.status);
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
