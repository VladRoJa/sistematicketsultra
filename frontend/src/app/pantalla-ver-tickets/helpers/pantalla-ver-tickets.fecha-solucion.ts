// frontend-angular/src/app/pantalla-ver-tickets/helpers/pantalla-ver-tickets.fecha-solucion.ts

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
  const token = localStorage.getItem('token');
  if (!token) {
    mostrarAlertaErrorDesdeStatus(401);
    return;
  }

  // Fecha compromiso a las 07:00 (horario local del navegador)
  const fechaSolucion = new Date(
    nuevaFecha.getFullYear(),
    nuevaFecha.getMonth(),
    nuevaFecha.getDate(),
    7, 0, 0
  );
  const fechaSolucionISO = fechaSolucion.toISOString();
  const fechaEnProgresoISO = new Date().toISOString();

  // Historial local (evitar duplicado)
  const historialActual = Array.isArray(ticket.historial_fechas) ? [...ticket.historial_fechas] : [];
  const nuevaEntrada = {
    fecha: fechaSolucionISO,
    cambiadoPor: component.user?.username || '',
    fechaCambio: new Date().toISOString(),
    motivo
  };
  const yaExiste = historialActual.some(item => item.fecha === fechaSolucionISO);
  if (!yaExiste) historialActual.push(nuevaEntrada);
  historialActual.sort((a, b) => new Date(b.fecha).getTime() - new Date(a.fecha).getTime());

  // Headers
  const headers = new HttpHeaders()
    .set('Authorization', `Bearer ${token}`)
    .set('Content-Type', 'application/json');

  // Helper: PUT /tickets/update/:id → estado + fechas + historial
  const finalizarUpdate = () => {
    const bodyUpdate = {
      estado: 'en progreso',
      fecha_solucion: fechaSolucionISO,      // mantener compromiso en el mismo update
      fecha_en_progreso: fechaEnProgresoISO,
      historial_fechas: historialActual,
      motivo_cambio: motivo
    };

    component.http.put(`${API_URL}/update/${ticket.id}`, bodyUpdate, { headers }).subscribe({
      next: () => {
        cargarTickets(component);
        mostrarAlertaToast('✅ Fecha de solución y estado "en progreso" guardados exitosamente.');
        if (onSuccess) onSuccess();
      },
      error: (error) => {
        mostrarAlertaErrorDesdeStatus(error.status);
      }
    });
  };

  // ¿Trae refacción definida por el Jefe? → primero /compromiso, luego /update
  if (component?.extrasCompromisoRefaccion?.refaccion_definida_por_jefe) {
    const ex = component.extrasCompromisoRefaccion;
    const necesita = !!ex.necesita_refaccion;
    const descr = necesita ? (ex.descripcion_refaccion || '') : '';

    // Parche optimista en UI
    (ticket as any).necesita_refaccion = necesita;
    (ticket as any).descripcion_refaccion = descr;
    (ticket as any).refaccion_definida_por_jefe = true;

    const patchLocal = (arr?: any[]) => {
      if (!Array.isArray(arr)) return;
      const t = arr.find(x => x?.id === ticket.id);
      if (t) {
        t.necesita_refaccion = necesita;
        t.descripcion_refaccion = descr;
        t.refaccion_definida_por_jefe = true;
      }
    };
    patchLocal(component.visibleTickets);
    patchLocal(component.filteredTickets);
    patchLocal(component.tickets);
    component.changeDetectorRef.detectChanges();

    // 1) Compromiso con refacción (endpoint que sí acepta estos campos)
    const bodyCompromiso: any = {
      fecha_solucion: fechaSolucionISO,
      necesita_refaccion: necesita,
      descripcion_refaccion: descr
    };

    component.http.put(`${API_URL}/compromiso/${ticket.id}`, bodyCompromiso, { headers }).subscribe({
      next: () => {
        // 2) Estado + historial
        finalizarUpdate();
      },
      error: (error) => {
        // Si falla (403/400), re-sincroniza la tabla para deshacer parche optimista
        cargarTickets(component);
        mostrarAlertaErrorDesdeStatus(error.status);
      }
    });

    return; // corta aquí; el resto lo hace en los callbacks
  }

  // Sin refacción del Jefe → un solo update
  finalizarUpdate();
}
