// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\fecha-solucion.helper.ts

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

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  const fechaConHoraFija = new Date(
    fechaSeleccionada.getFullYear(),
    fechaSeleccionada.getMonth(),
    fechaSeleccionada.getDate(),
    7, 0, 0
  );

  const fechaISO = fechaConHoraFija.toISOString();

  const nuevoHistorial = [
    ...(ticket.historial_fechas || []),
    {
      fecha: fechaISO,
      cambiadoPor: component.user.username,
      fechaCambio: new Date().toISOString(),
    },
  ];

  console.log("📋 Historial a guardar:", nuevoHistorial);

  component.http.put(`${API_URL}/update/${ticket.id}`, {
    estado: ticket.estado,
    fecha_solucion: fechaISO,
    historial_fechas: nuevoHistorial,
  }, { headers }).subscribe({
    next: () => {
      // 🔁 Refrescar para forzar obtención del ticket actualizado
      component.editandoFechaSolucion[ticket.id] = false;
      component.refrescoService.emitirRefresco();
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
