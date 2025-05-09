// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.fecha-solucion.tssrc/app/pantalla-ver-tickets/helpers/fecha-solucion.helper.ts

import { ChangeDetectorRef } from '@angular/core';
import { PantallaVerTicketsComponent, Ticket } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

/**
 * Funciones relacionadas con la edición y guardado de la fecha de solución en tickets.
 */

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
  cdr.detectChanges(); // 👈 fuerza actualización del DOM
}

/** Guardar la nueva fecha de solución en el ticket */
export function guardarFechaSolucion(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  const fechaInput = component.fechaSolucionSeleccionada[ticket.id];
  if (!fechaInput) return;

  const token = localStorage.getItem("token");
  if (!token) return;

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  const fechaDate = new Date(fechaInput);

  const fechaFormateada = new Intl.DateTimeFormat('sv-SE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'America/Tijuana'
  }).format(fechaDate).replace('T', ' ');  // resultado: '2025-05-09 00:00:00'

  const nuevoHistorial = [
    ...(ticket.historial_fechas || []),
    {
      fecha: fechaFormateada,
      cambiadoPor: component.user.username,
      fechaCambio: new Date().toISOString(),
    },
  ];

  component.http.put(`${API_URL}/update/${ticket.id}`, {
    estado: ticket.estado,
    fecha_solucion: fechaFormateada,
    historial_fechas: nuevoHistorial,
  }, { headers }).subscribe({
    next: () => {
      ticket.fecha_solucion = fechaFormateada;
      ticket.historial_fechas = nuevoHistorial;
      component.editandoFechaSolucion[ticket.id] = false;
      console.log(`✅ Fecha de solución del ticket #${ticket.id} actualizada.`);
    },
    error: (error) => {
      console.error(`❌ Error al actualizar la fecha de solución del ticket #${ticket.id}:`, error);
    }
  });
}


/** Cancelar el modo de edición de fecha de solución */
export function cancelarEdicionFechaSolucion(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  component.editandoFechaSolucion[ticket.id] = false;
}

/** Utilidad: Formatear fecha de base de datos para input tipo date */
function formatearFechaParaInput(fechaDB: string): Date {
  const [fecha] = fechaDB.split(' ');
  const [year, month, day] = fecha.split('-').map(Number);
  return new Date(year, month - 1, day, 12, 0, 0); // 🔁 Forzar hora 12:00 PM
}
