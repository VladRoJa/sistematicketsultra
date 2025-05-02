// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.historial.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';

/**
 * Funciones relacionadas al historial de cambios de los tickets en PantallaVerTicketsComponent
 */

/** Alternar la visibilidad del historial de un ticket */
export function toggleHistorial(component: PantallaVerTicketsComponent, ticketId: number): void {
  component.historialVisible[ticketId] = !component.historialVisible[ticketId];
}
