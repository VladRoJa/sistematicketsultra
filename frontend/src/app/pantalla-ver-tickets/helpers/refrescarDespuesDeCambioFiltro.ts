//frontend-angular\src\app\pantalla-ver-tickets\helpers\refrescarDespuesDeCambioFiltro.ts

import { filtrarTicketsConFiltros } from "src/app/utils/ticket-utils";
import { obtenerFiltrosActivos } from "./pantalla-ver-tickets.filtros";

export function refrescarDespuesDeCambioFiltro(component: any) {
  const filtros = obtenerFiltrosActivos(component);
  const filtrados = filtrarTicketsConFiltros(component.tickets, filtros);
  component.filteredTickets = filtrados;
  component.totalTickets = filtrados.length;
  component.page = 1;
  component.totalPagesCount = Math.ceil(component.totalTickets / component.itemsPerPage);
  component.visibleTickets = component.filteredTickets.slice(0, component.itemsPerPage);
  component.changeDetectorRef.detectChanges();
}
