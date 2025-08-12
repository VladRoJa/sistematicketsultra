// frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.acciones.ts

import { PantallaVerTicketsComponent, Ticket } from '../pantalla-ver-tickets.component';
import { exportarTickets as exportarTicketsExcel } from './pantalla-ver-tickets.exportacion';
import { cambiarEstadoTicket, finalizarTicket } from './pantalla-ver-tickets.estado-ticket';
import { toggleHistorial } from './pantalla-ver-tickets.historial';
import { isFilterActive as isFilterActiveHelper } from '../../utils/ticket-utils';
import { regenerarFiltrosFiltradosDesdeTickets } from '../../utils/ticket-utils';
import { aplicarFiltrosDesdeMemoria, hayFiltrosActivos, obtenerFiltrosActivos } from './pantalla-ver-tickets.filtros';
import { cargarTickets } from './pantalla-ver-tickets.init';
import { actualizarVisibleTickets } from './pantalla-ver-tickets.init';
import { ChangeDetectorRef } from '@angular/core';
import { DialogoConfirmacionComponent } from 'src/app/shared/dialogo-confirmacion/dialogo-confirmacion.component';

/** Exportar tickets a Excel */
export function exportarTickets(component: PantallaVerTicketsComponent): void {
  exportarTicketsExcel(component);
}

/** Cambiar el estado de un ticket */
export function cambiarEstado(component: PantallaVerTicketsComponent, ticket: Ticket, estado: "pendiente" | "en progreso" | "finalizado"): void {
  cambiarEstadoTicket(component, ticket, estado);
}

/** Finalizar un ticket */
export function finalizar(component: PantallaVerTicketsComponent, ticket: Ticket): void {
  finalizarTicket(component, ticket);
}

export function mostrarConfirmacionAccion(
  component: any,
  mensaje: string,
  accion: () => void
): void {
  const dialogRef = component.dialog.open(DialogoConfirmacionComponent, {
    data: {
      titulo: 'Confirmación requerida',
      mensaje,
      textoAceptar: 'Aceptar',
      textoCancelar: 'Cancelar'
    }
  });

  dialogRef.afterClosed().subscribe((result: boolean) => {
    if (result) {
      accion();
    }
  });
}

/** Alternar visibilidad del historial de fechas */
export function alternarHistorial(component: PantallaVerTicketsComponent, ticketId: number): void {
  toggleHistorial(component, ticketId);
}


/** Cambiar de página en la tabla */
export function cambiarPagina(component: PantallaVerTicketsComponent, direccion: number): void {
  const nuevaPagina = component.page + direccion;
  const totalPaginas = Math.ceil(component.filteredTickets.length / component.itemsPerPage);

  if (nuevaPagina > 0 && nuevaPagina <= totalPaginas) {
    component.page = nuevaPagina;
    actualizarVisibleTickets(component); // ✅ sincroniza la tabla
  }
}


/** Calcular el total de páginas */
export function totalPages(component: PantallaVerTicketsComponent): number {
  return Math.ceil(component.filteredTickets.length / component.itemsPerPage);
}



/** Limpiar todos los filtros aplicados */
// pantalla-ver-tickets.acciones.ts
export function limpiarTodosLosFiltros(component: PantallaVerTicketsComponent): void {
  // Limpiar selección de todos los filtros
  const limpiarSeleccion = (lista: any[]) => lista.forEach(i => i.seleccionado = false);

  limpiarSeleccion(component.categoriasDisponibles);
  limpiarSeleccion(component.descripcionesDisponibles);
  limpiarSeleccion(component.usuariosDisponibles);
  limpiarSeleccion(component.estadosDisponibles);
  limpiarSeleccion(component.criticidadesDisponibles);
  limpiarSeleccion(component.departamentosDisponibles);
  limpiarSeleccion(component.subcategoriasDisponibles);
  limpiarSeleccion(component.detallesDisponibles);
  limpiarSeleccion(component.sucursalesDisponibles);

  // Resetear filtros visibles
  component.categoriasFiltradas = [...component.categoriasDisponibles];
  component.descripcionesFiltradas = [...component.descripcionesDisponibles];
  component.usuariosFiltrados = [...component.usuariosDisponibles];
  component.estadosFiltrados = [...component.estadosDisponibles];
  component.criticidadesFiltradas = [...component.criticidadesDisponibles];
  component.departamentosFiltrados = [...component.departamentosDisponibles];
  component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
  component.detallesFiltrados = [...component.detallesDisponibles];
  component.sucursalesFiltradas = [...component.sucursalesDisponibles];

  // Limpia buscadores
  component.filtroCategoriaTexto = '';
  component.filtroDescripcionTexto = '';
  component.filtroUsuarioTexto = '';
  component.filtroEstadoTexto = '';
  component.filtroCriticidadTexto = '';
  component.filtroDeptoTexto = '';
  component.filtroSubcategoriaTexto = '';
  component.filtroDetalleTexto = '';
  component.filtroSucursalTexto = '';

  // Limpia rangos de fechas
  component.rangoFechaCreacionSeleccionado = { start: null, end: null };
  component.rangoFechaFinalSeleccionado = { start: null, end: null };

  // Restaurar tickets
  component.filteredTickets = [...component.ticketsCompletos];


  // ✅ RESET A PÁGINA 1
  component.page = 1;

  component.filtroProgresoActivo = false;
  component.filtroFinalizadoActivo = false;
  component.incluirSinFechaProgreso = false;
  component.incluirSinFechaFinalizado = false;

  actualizarVisibleTickets(component);
}




/** Verifica si un filtro está activo */
export function isFilterActive(component: PantallaVerTicketsComponent, columna: string): boolean {
  return isFilterActiveHelper(component, columna);
}

