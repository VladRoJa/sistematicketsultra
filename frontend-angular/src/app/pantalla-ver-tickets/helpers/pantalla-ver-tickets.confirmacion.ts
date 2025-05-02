// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.confirmacion.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';

/**
 * Funciones de confirmación de acciones en PantallaVerTicketsComponent
 */

/** Mostrar un cuadro de confirmación */
export function mostrarConfirmacion(component: PantallaVerTicketsComponent, mensaje: string, accion: () => void): void {
  console.log("🛑 Solicitud de confirmación:", mensaje);

  component.mensajeConfirmacion = mensaje;
  component.accionPendiente = accion;
  component.confirmacionVisible = true;
}

/** Confirmar la acción pendiente */
export function confirmarAccion(component: PantallaVerTicketsComponent): void {
  console.log("✅ Acción confirmada.");

  if (component.accionPendiente) {
    component.accionPendiente();
    component.accionPendiente = null;
  }
  component.confirmacionVisible = false;
}

/** Cancelar la acción pendiente */
export function cancelarAccion(component: PantallaVerTicketsComponent): void {
  console.log("❌ Acción cancelada.");

  component.accionPendiente = null;
  component.confirmacionVisible = false;
}
