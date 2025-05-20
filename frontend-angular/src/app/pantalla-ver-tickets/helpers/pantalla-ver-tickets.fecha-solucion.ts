import { ChangeDetectorRef } from '@angular/core';
import { PantallaVerTicketsComponent, Ticket } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

const API_URL = `${environment.apiUrl}/tickets`;

/** Activar el modo de edición para la fecha de solución */
export function editarFechaSolucion(
  component: PantallaVerTicketsComponent,
  ticket: Ticket,
  cdr: ChangeDetectorRef
): void {
  component.editandoFechaSolucion[ticket.id] = true;

  if (!component.fechaSolucionSeleccionada[ticket.id]) {
    component.fechaSolucionSeleccionada[ticket.id] = ticket.fecha_solucion
      ? formatearFechaParaInput(ticket.fecha_solucion)
      : null;
  }

  cdr.detectChanges();
}

/** Guardar la nueva fecha de solución con hora fija 07:00 AM */
export function guardarFechaSolucion(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  const fechaSeleccionada = component.fechaSolucionSeleccionada[ticket.id];
  if (!fechaSeleccionada) return;

  const token = localStorage.getItem("token");
  if (!token) return;

  const fechaConHoraFija = new Date(
    fechaSeleccionada.getFullYear(),
    fechaSeleccionada.getMonth(),
    fechaSeleccionada.getDate(),
    7, 0, 0
  );

  const fechaISO = fechaConHoraFija.toISOString();

  // ✅ Evitar guardar si no ha cambiado la fecha
  if (ticket.fecha_solucion === fechaISO) {
    component.editandoFechaSolucion[ticket.id] = false;
    return;
  }

  const nuevoHistorial = [
    ...(ticket.historial_fechas || []),
    {
      fecha: fechaISO,
      cambiadoPor: component.user.username,
      fechaCambio: new Date().toISOString(),
    }
  ];

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  component.http.put(`${API_URL}/update/${ticket.id}`, {
    estado: ticket.estado,
    fecha_solucion: fechaISO,
    historial_fechas: nuevoHistorial,
  }, { headers }).subscribe({
    next: () => {
      component.ticketService.getTickets().subscribe({
        next: (res) => {
          const actualizado = res.tickets.find((t: Ticket) => t.id === ticket.id);
          if (actualizado) {
            const actualizar = (lista: Ticket[]) =>
              lista.map(t => t.id === ticket.id ? actualizado : t);

            component.tickets = actualizar(component.tickets);
            component.filteredTickets = actualizar(component.filteredTickets);
            component.visibleTickets = actualizar(component.visibleTickets);
          }

          // ✅ Cerrar editor y limpiar selección
          component.editandoFechaSolucion[ticket.id] = false;
          delete component.fechaSolucionSeleccionada[ticket.id];
        },
        error: (error) => {
          console.error("❌ Error al refrescar ticket actualizado:", error);
          component.refrescoService.emitirRefresco();
        }
      });
    },
    error: (error) => {
      console.error(`❌ Error al actualizar la fecha de solución del ticket #${ticket.id}:`, error);
    }
  });
}


/** Cancelar edición */
export function cancelarEdicionFechaSolucion(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  component.editandoFechaSolucion[ticket.id] = false;
}

/** Convertir string ISO a Date con hora fija 07:00 AM para el input */
function formatearFechaParaInput(fechaDB: string): Date {
  const fecha = new Date(fechaDB);
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), 7, 0, 0);
}
