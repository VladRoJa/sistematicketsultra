//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.fecha-solucion.ts

import { ChangeDetectorRef } from '@angular/core';
import { PantallaVerTicketsComponent, Ticket } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from 'src/app/utils/alertas';


const API_URL = `${environment.apiUrl}/tickets`;

/** Activar el modo de edición para la fecha de solución */
export function editarFechaSolucion(
  component: PantallaVerTicketsComponent,
  ticket: Ticket,
  cdr: ChangeDetectorRef
): void {
  // Solo permitir edición a administradores
  if (!component.usuarioEsAdmin && !component.usuarioEsEditorCorporativo) {
    console.warn('Solo administradores o editores corporativos pueden editar la fecha de solución');
    return;
  }

  component.editandoFechaSolucion[ticket.id] = true;

  // Inicializar con la fecha actual si existe
  if (!component.fechaSolucionSeleccionada[ticket.id]) {
    component.fechaSolucionSeleccionada[ticket.id] = ticket.fecha_solucion
      ? formatearFechaParaInput(ticket.fecha_solucion)
      : null;
  }

  cdr.detectChanges();
}

/** Guardar la nueva fecha de solución con hora fija 07:00 AM */
export function guardarFechaSolucion(
  component: PantallaVerTicketsComponent,
  ticket: Ticket,
  nuevaFecha: Date
): void {
  if (!component.usuarioEsAdmin && !component.usuarioEsEditorCorporativo) {
    console.warn('Solo administradores o editores corporativos pueden guardar la fecha de solución');
    return;
  }

  const token = localStorage.getItem("token");
  if (!token) {
    console.error('No hay token de autenticación');
    return;
  }

  // Aplicar hora fija 07:00 AM
  const fechaConHoraFija = new Date(
    nuevaFecha.getFullYear(),
    nuevaFecha.getMonth(),
    nuevaFecha.getDate(),
    7, 0, 0
  );
  const fechaISO = fechaConHoraFija.toISOString();

  // Obtener historial actual o crear uno nuevo
  const historialActual = Array.isArray(ticket.historial_fechas)
    ? [...ticket.historial_fechas]
    : [];

  // Verificar si ya existe una entrada con la misma fecha
  const yaExiste = historialActual.some(item => item.fecha === fechaISO);

  if (yaExiste) {
    console.log('⚠️ Esta fecha ya está registrada en el historial. No se agregará nuevamente.');
  } else {
    const nuevoRegistro = {
      fecha: fechaISO,
      cambiadoPor: component.user.username,
      fechaCambio: new Date().toISOString(),
    };

    historialActual.push(nuevoRegistro);
  }

  const historialActualizado = historialActual.sort(
    (a, b) => new Date(b.fecha).getTime() - new Date(a.fecha).getTime()
  );

  const datosActualizacion = {
    estado: ticket.estado,
    fecha_solucion: fechaISO,
    historial_fechas: historialActualizado,
  };

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  component.http.put(`${API_URL}/update/${ticket.id}`, datosActualizacion, { headers }).subscribe({
    next: () => {
      component.ticketService.getTickets().subscribe({
        next: (res) => {
          const actualizado = res.tickets.find((t: Ticket) => t.id === ticket.id);
          if (actualizado) {
            ticket.fecha_solucion = actualizado.fecha_solucion;
            ticket.historial_fechas = actualizado.historial_fechas;

            const actualizar = (lista: Ticket[]) =>
              lista.map(t => t.id === ticket.id ? actualizado : t);

            component.tickets = actualizar(component.tickets);
            component.filteredTickets = actualizar(component.filteredTickets);
            component.visibleTickets = actualizar(component.visibleTickets);
          }

          component.editandoFechaSolucion[ticket.id] = false;
          mostrarAlertaToast('✅ Fecha solución guardada exitosamente.');
          delete component.fechaSolucionSeleccionada[ticket.id];
        },
        error: (error) => {
          console.error("Error al refrescar ticket actualizado:", error);
          component.refrescoService.emitirRefresco();
        }
      });
    },
    error: (error) => {
      console.error(`Error al actualizar la fecha de solución del ticket #${ticket.id}:`, error);
      mostrarAlertaErrorDesdeStatus(error.status);
    }
  });
}




/** Cancelar edición */
export function cancelarEdicionFechaSolucion(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  component.editandoFechaSolucion[ticket.id] = false;
  delete component.fechaSolucionSeleccionada[ticket.id];
}

/** Convertir string ISO a Date con hora fija 07:00 AM para el input */
function formatearFechaParaInput(fechaDB: string): Date {
  const fecha = new Date(fechaDB);
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), 7, 0, 0);
}

/** Alternar visibilidad del historial */
export function alternarHistorial(component: PantallaVerTicketsComponent, ticketId: number): void {
  component.historialVisible[ticketId] = !component.historialVisible[ticketId];
  component.changeDetectorRef.detectChanges();
}
