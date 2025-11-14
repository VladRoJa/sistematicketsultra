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

  // ⛔ IMPORTANTE:
  // Este helper ya NO debe hacer PUT cuando el estado sea "finalizado".
  // El cierre completo se hace con /cierre/aprobar-jefe en el componente.
  if (nuevoEstado === 'finalizado') {
    console.warn(
      'cambiarEstadoTicket no debe usarse para "finalizado". ' +
      'Usa TicketAcciones.finalizar (que a su vez llama al endpoint de cierre).'
    );
    return;
  }

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

      component.http.put<{ mensaje: string; notificados?: string[] }>(
        `${API_URL}/update/${ticket.id}`,
        body,
        { headers }
      ).subscribe({
        next: (res) => {
          const lista = (res.notificados && res.notificados.length)
            ? res.notificados.join(', ')
            : '—';
          mostrarAlertaToast(`✅ Ticket #${ticket.id} actualizado a '${nuevoEstado}'. Notificados: ${lista}`);
          cargarTickets(component); // <<--- SIEMPRE RECARGA TABLA
          dialogRef.close();
          if (onSuccess) onSuccess();
        },
        error: (error) => {
          mostrarAlertaErrorDesdeStatus(error.status);
        }
      });
    }); // 👈 cierre que faltaba del subscribe(onGuardar)

    dialogRef.componentInstance.onCancelar.subscribe(() => {
      dialogRef.close();
    });

    return;
  }

  // ✅ Flujo normal para otros estados o si ya tiene fecha_solucion
  const body = { estado: nuevoEstado };

  component.http.put<{ mensaje: string; notificados?: string[] }>(
    `${API_URL}/update/${ticket.id}`,
    body,
    { headers }
  ).subscribe({
    next: (res) => {
      const lista = (res.notificados && res.notificados.length)
        ? res.notificados.join(', ')
        : '—';
      mostrarAlertaToast(`✅ Ticket #${ticket.id} actualizado a '${nuevoEstado}'. Notificados: ${lista}`);
      cargarTickets(component); // <<--- SIEMPRE RECARGA TABLA
      if (onSuccess) onSuccess();
    },
    error: (error) => {
      mostrarAlertaErrorDesdeStatus(error.status);
    }
  });
}

/** Finalizar directamente un ticket */
/** Finalizar directamente un ticket (solo parcheo en front).
 *  El cambio real (estado, fecha_finalizado, costo, notas)
 *  lo hace el endpoint /tickets/cierre/aprobar-jefe/:id
 *  que llamas desde el componente (onFinalizar / onCierreAprobarJefe).
 */
export function finalizarTicket(
  component: PantallaVerTicketsComponent,
  ticket: Ticket
): void {
  // Si quieres, puedes limitar por rol (opcional)
  if (!component.usuarioEsAdmin && !component.usuarioEsEditorCorporativo) {
    return;
  }

  // Parche visual mínimo: asumimos que el backend ya marcó finalizado.
  ticket.estado = 'finalizado';
  if (!ticket.fecha_finalizado) {
    ticket.fecha_finalizado = new Date().toISOString();
  }

  // No hacemos PUT aquí. El componente ya está llamando a
  // ticketService.cierreAprobarJefe(...) y luego a postAccionRefrescar().
}



