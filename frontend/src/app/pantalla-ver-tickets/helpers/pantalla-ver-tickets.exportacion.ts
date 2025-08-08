// frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.exportacion.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';
import { HttpParams } from '@angular/common/http';
import { obtenerFiltrosActivosParaBackend } from './pantalla-ver-tickets.filtros';

/**
 * Funciones relacionadas con la exportación de tickets.
 */

/** Exportar tickets filtrados a Excel */
export function exportarTickets(component: PantallaVerTicketsComponent) {
  component.exportandoExcel = true;
  console.log("🔍 temporalSeleccionados justo antes de exportar:", JSON.stringify(component.temporalSeleccionados, null, 2));
  const filtros = obtenerFiltrosActivosParaBackend(component);

  component.ticketService.exportarTickets(filtros).subscribe({
    next: (blob: Blob) => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tickets_exportados_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);
      component.exportandoExcel = false;
    },
    error: (error) => {
      console.error("❌ Error al exportar tickets a Excel:", error);
      component.exportandoExcel = false;
    }
  });
}


