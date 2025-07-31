// frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.fecha-solucion.ts

import { ChangeDetectorRef } from '@angular/core';
import { PantallaVerTicketsComponent, Ticket } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from 'src/app/utils/alertas';
import { cargarTickets } from './pantalla-ver-tickets.init';

const API_URL = `${environment.apiUrl}/tickets`;

/** Alternar visibilidad del historial */
export function alternarHistorial(component: PantallaVerTicketsComponent, ticketId: number): void {
  component.historialVisible[ticketId] = !component.historialVisible[ticketId];
  component.changeDetectorRef.detectChanges();
}

/** Si necesitas convertir un string ISO a Date para algún modal */
export function formatearFechaParaInput(fechaDB: string): Date {
  const fecha = new Date(fechaDB);
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), 7, 0, 0);
}


export function asignarFechaSolucionYEnProgreso(
  component: PantallaVerTicketsComponent,
  ticket: Ticket,
  nuevaFecha: Date,
  motivo: string,
  onSuccess?: () => void
): void {
  const token = localStorage.getItem("token");
  if (!token) {
    mostrarAlertaErrorDesdeStatus(401);
    return;
  }

  // Fecha de solución a las 07:00 AM UTC
  const fechaSolucion = new Date(
    nuevaFecha.getFullYear(),
    nuevaFecha.getMonth(),
    nuevaFecha.getDate(),
    7, 0, 0
  );
  const fechaSolucionISO = fechaSolucion.toISOString();
  const fechaEnProgresoISO = new Date().toISOString();

  // Arma la nueva entrada de historial
  const historialActual = Array.isArray(ticket.historial_fechas) ? [...ticket.historial_fechas] : [];
  const nuevaEntrada = {
    fecha: fechaSolucionISO,
    cambiadoPor: component.user?.username || '',
    fechaCambio: new Date().toISOString(),
    motivo
  };

  // No agregues duplicado
  const yaExiste = historialActual.some(item => item.fecha === fechaSolucionISO);
  if (!yaExiste) historialActual.push(nuevaEntrada);

  // Ordena el historial
  historialActual.sort((a, b) => new Date(b.fecha).getTime() - new Date(a.fecha).getTime());

  // Prepara el body completo
  const body = {
    estado: "en progreso",
    fecha_solucion: fechaSolucionISO,
    fecha_en_progreso: fechaEnProgresoISO,
    historial_fechas: historialActual,
    motivo_cambio: motivo
  };

  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  // Una sola llamada PUT
  component.http.put(`${API_URL}/update/${ticket.id}`, body, { headers }).subscribe({
    next: () => {
      cargarTickets(component); // refresca toda la tabla para evitar N/A y desfaces
      mostrarAlertaToast('✅ Fecha de solución y estado "en progreso" guardados exitosamente.');
      if (onSuccess) onSuccess();
    },
    error: (error) => {
      mostrarAlertaErrorDesdeStatus(error.status);
    }
  });
}