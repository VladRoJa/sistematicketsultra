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
  // Solo permitir edición a administradores
  if (!component.usuarioEsAdmin) {
    console.warn('Solo los administradores pueden editar la fecha de solución');
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
export function guardarFechaSolucion(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  // Verificar permisos de administrador
  if (!component.usuarioEsAdmin) {
    console.warn('Solo los administradores pueden guardar la fecha de solución');
    return;
  }

  const fechaSeleccionada = component.fechaSolucionSeleccionada[ticket.id];
  if (!fechaSeleccionada) {
    console.warn('No hay fecha seleccionada para guardar');
    return;
  }

  const token = localStorage.getItem("token");
  if (!token) {
    console.error('No hay token de autenticación');
    return;
  }

  const fechaConHoraFija = new Date(
    fechaSeleccionada.getFullYear(),
    fechaSeleccionada.getMonth(),
    fechaSeleccionada.getDate(),
    7, 0, 0
  );

  const fechaISO = fechaConHoraFija.toISOString();

  // Evitar guardar si no ha cambiado la fecha
  if (ticket.fecha_solucion === fechaISO) {
    console.log('La fecha no ha cambiado, no es necesario guardar');
    component.editandoFechaSolucion[ticket.id] = false;
    return;
  }

  // Asegurarse que el historial existente sea un array
  const historialActual = Array.isArray(ticket.historial_fechas) 
    ? ticket.historial_fechas 
    : [];

  console.log('Historial actual:', historialActual);

  // Preparar el nuevo registro en el historial
  const nuevoRegistro = {
    fecha: fechaISO,
    cambiadoPor: component.user.username,
    fechaCambio: new Date().toISOString(),
  };

  console.log('Nuevo registro a agregar:', nuevoRegistro);

  const nuevoHistorial = [...historialActual, nuevoRegistro];

  console.log('Historial completo a guardar:', nuevoHistorial);

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  const datosActualizacion = {
    estado: ticket.estado,
    fecha_solucion: fechaISO,
    historial_fechas: nuevoHistorial,
  };

  console.log('Datos completos a enviar:', datosActualizacion);

  // Actualizar el ticket
  component.http.put(`${API_URL}/update/${ticket.id}`, datosActualizacion, { headers }).subscribe({
    next: (response) => {
      console.log('Respuesta del servidor:', response);
      
      // Recargar los tickets para obtener la información actualizada
      component.ticketService.getTickets().subscribe({
        next: (res) => {
          const actualizado = res.tickets.find((t: Ticket) => t.id === ticket.id);
          if (actualizado) {
            console.log('Ticket actualizado recibido:', actualizado);
            
            const actualizar = (lista: Ticket[]) =>
              lista.map(t => t.id === ticket.id ? actualizado : t);

            component.tickets = actualizar(component.tickets);
            component.filteredTickets = actualizar(component.filteredTickets);
            component.visibleTickets = actualizar(component.visibleTickets);
          } else {
            console.warn('No se encontró el ticket actualizado en la respuesta');
          }

          // Cerrar editor y limpiar selección
          component.editandoFechaSolucion[ticket.id] = false;
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
