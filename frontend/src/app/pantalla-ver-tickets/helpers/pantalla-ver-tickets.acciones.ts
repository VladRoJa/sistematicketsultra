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

export function limpiarTodosLosFiltros(component: PantallaVerTicketsComponent): void {
  const marcarTodoSeleccionado = (lista: any[] | undefined) => {
    if (!Array.isArray(lista)) {
      return;
    }

    lista.forEach(item => {
      item.seleccionado = true;
    });
  };

  const columnas = [
    'categoria',
    'descripcion',
    'username',
    'estado',
    'criticidad',
    'departamento',
    'subcategoria',
    'detalle',
    'inventario',
    'sucursal',
  ];

  // 1) Limpiar selección de todos los filtros.
  // Todo seleccionado = sin filtro activo.
  marcarTodoSeleccionado(component.categoriasDisponibles);
  marcarTodoSeleccionado(component.descripcionesDisponibles);
  marcarTodoSeleccionado(component.usuariosDisponibles);
  marcarTodoSeleccionado(component.estadosDisponibles);
  marcarTodoSeleccionado(component.criticidadesDisponibles);
  marcarTodoSeleccionado(component.departamentosDisponibles);
  marcarTodoSeleccionado(component.subcategoriasDisponibles);
  marcarTodoSeleccionado(component.detallesDisponibles);
  marcarTodoSeleccionado(component.inventariosDisponibles);
  marcarTodoSeleccionado(component.sucursalesDisponibles);

  // 2) Resetear filtros visibles.
  component.categoriasFiltradas = [...component.categoriasDisponibles];
  component.descripcionesFiltradas = [...component.descripcionesDisponibles];
  component.usuariosFiltrados = [...component.usuariosDisponibles];
  component.estadosFiltrados = [...component.estadosDisponibles];
  component.criticidadesFiltradas = [...component.criticidadesDisponibles];
  component.departamentosFiltrados = [...component.departamentosDisponibles];
  component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
  component.detallesFiltrados = [...component.detallesDisponibles];
  component.inventariosFiltrados = [...component.inventariosDisponibles];
  component.sucursalesFiltradas = [...component.sucursalesDisponibles];

  // 3) Resetear temporales.
  columnas.forEach(columna => {
    const pluralMap: Record<string, string> = {
      categoria: 'categorias',
      descripcion: 'descripciones',
      username: 'usuarios',
      estado: 'estados',
      criticidad: 'criticidades',
      departamento: 'departamentos',
      subcategoria: 'subcategorias',
      detalle: 'detalles',
      inventario: 'inventarios',
      sucursal: 'sucursales',
    };

    const plural = pluralMap[columna];
    const disponibles = (component as any)[`${plural}Disponibles`] || [];

    component.temporalSeleccionados[columna] = disponibles.map((opcion: any) => ({
      ...opcion,
      seleccionado: true,
    }));
  });

  // 4) Limpia buscadores.
  component.filtroCategoriaTexto = '';
  component.filtroDescripcionTexto = '';
  component.filtroUsuarioTexto = '';
  component.filtroEstadoTexto = '';
  component.filtroCriticidadTexto = '';
  component.filtroDeptoTexto = '';
  component.filtroSubcategoriaTexto = '';
  component.filtroDetalleTexto = '';
  component.filtroInventarioTexto = '';
  component.filtroSucursalTexto = '';

  // 5) Limpia rangos de fechas.
  component.rangoFechaCreacionSeleccionado = { start: null, end: null };
  component.rangoFechaFinalSeleccionado = { start: null, end: null };
  component.rangoFechaProgresoSeleccionado = { start: null, end: null };

  component.fechaCreacionTemp = { start: null, end: null };
  component.fechaFinalTemp = { start: null, end: null };
  component.fechaProgresoTemp = { start: null, end: null };

  component.filtroProgresoActivo = false;
  component.filtroFinalizadoActivo = false;
  component.filtroCreacionActivo = false;
  component.incluirSinFechaProgreso = false;
  component.incluirSinFechaFinalizado = false;
  component.filtroRapidoPorValidarActivo = false;

  // 6) Restaurar vista base respetando ocultarFinalizados.
  const base = [...component.ticketsCompletos];

  component.filteredTickets = component.ocultarFinalizados
    ? base.filter((ticket: any) => {
        const estado = (ticket.estado || '').toString().trim().toLowerCase();
        return estado !== 'finalizado';
      })
    : base;

  // 7) Reset paginación.
  component.page = 1;
  component.totalTickets = component.filteredTickets.length;
  component.totalPagesCount = Math.ceil(component.totalTickets / component.itemsPerPage);
  component.visibleTickets = component.filteredTickets.slice(0, component.itemsPerPage);

  component.changeDetectorRef.detectChanges();
}



/** Verifica si un filtro está activo */
export function isFilterActive(component: PantallaVerTicketsComponent, columna: string): boolean {
  return isFilterActiveHelper(component, columna);
}

