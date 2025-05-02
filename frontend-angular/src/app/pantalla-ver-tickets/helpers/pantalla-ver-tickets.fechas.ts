// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.fechas.tssrc/app/pantalla-ver-tickets/helpers/fechas.helper.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';

/**
 * Funciones relacionadas a manejo de fechas y filtros cruzados en PantallaVerTicketsComponent.
 */

/** Actualizar visibilidad de opciones basándose en los tickets filtrados */
export function actualizarFiltrosCruzados(
  ticketsFiltrados: any[],
  usuariosDisponibles: any[],
  estadosDisponibles: any[],
  categoriasDisponibles: any[],
  descripcionesDisponibles: any[],
  criticidadesDisponibles: any[],
  departamentosDisponibles: any[],
  subcategoriasDisponibles: any[],
  detallesDisponibles: any[],
  context: PantallaVerTicketsComponent
): void {
  const contarValores = (lista: any[], propiedad: string) => {
    const conteo: { [key: string]: number } = {};
    lista.forEach(item => {
      const valor = item[propiedad] || '—';
      conteo[valor] = (conteo[valor] || 0) + 1;
    });
    return conteo;
  };

  const actualizar = (disponibles: any[], conteo: { [key: string]: number }) => {
    disponibles.forEach(opcion => {
      opcion.visible = conteo[opcion.valor] > 0;
    });
  };

  actualizar(usuariosDisponibles, contarValores(ticketsFiltrados, 'username'));
  actualizar(estadosDisponibles, contarValores(ticketsFiltrados, 'estado'));
  actualizar(categoriasDisponibles, contarValores(ticketsFiltrados, 'categoria'));
  actualizar(descripcionesDisponibles, contarValores(ticketsFiltrados, 'descripcion'));
  actualizar(criticidadesDisponibles, contarValores(ticketsFiltrados, 'criticidad'));
  actualizar(departamentosDisponibles, contarValores(ticketsFiltrados, 'departamento'));
  actualizar(subcategoriasDisponibles, contarValores(ticketsFiltrados, 'subcategoria'));
  actualizar(detallesDisponibles, contarValores(ticketsFiltrados, 'subsubcategoria'));
}


/** Formatear fecha corta (sin hora) */
export function formatearFechaCorta(fechaString: string | null): string {
  if (!fechaString) return 'dd/mm/aa';
  const fecha = new Date(fechaString);
  if (isNaN(fecha.getTime())) {
    console.error("❌ Fecha inválida detectada:", fechaString);
    return 'Fecha inválida';
  }
  return fecha.toLocaleDateString('es-ES', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit'
  });
}

/** Parsear fecha desde tabla en formato "dd-mm-aa hh:mm" */
export function parsearFechaDesdeTabla(valor: string): Date | null {
  if (!valor) return null;

  try {
    const partes = valor.split(" ");
    const [dia, mes, año] = partes[0].split("-");
    const horaMinuto = partes[1] || "00:00";
    const [hora, minuto] = horaMinuto.split(":");

    const fechaISO = `20${año}-${mes}-${dia}T${hora}:${minuto}:00`;
    const fechaFinal = new Date(fechaISO);

    // Si no es válido, intenta parsearlo manualmente
    if (isNaN(fechaFinal.getTime())) {
      const fallback = new Date(`20${año}-${mes}-${dia}T${hora}:${minuto}:00`);
      return isNaN(fallback.getTime()) ? null : fallback;
    }

    return fechaFinal;
  } catch (error) {
    console.error("❌ Error parseando fecha:", valor, error);
    return null;
  }
}


/** Aplicar filtro de rango de fechas de creación */
export function aplicarFiltroPorRangoFechaCreacion(
  component: PantallaVerTicketsComponent,
  rango: { start: Date | null; end: Date | null }
): void {
  if (!rango.start || !rango.end) {
    component.filteredTickets = [...component.tickets];
    return;
  }

  component.filteredTickets = component.tickets.filter(ticket => {
    if (!ticket.fecha_creacion_original) return false;
    const fecha = new Date(ticket.fecha_creacion_original);
    return fecha >= rango.start && fecha <= rango.end;
  });

  actualizarFiltrosCruzados(
    component.filteredTickets,
    component.usuariosDisponibles,
    component.estadosDisponibles,
    component.categoriasDisponibles,
    component.descripcionesDisponibles,
    component.criticidadesDisponibles,
    component.departamentosDisponibles,
    component.subcategoriasDisponibles,
    component.detallesDisponibles,
    component
  );
}

/** Aplicar filtro de rango de fechas de finalización */
export function aplicarFiltroPorRangoFechaFinalizado(
  component: PantallaVerTicketsComponent,
  rango: { start: Date | null; end: Date | null }
): void {
  if (!rango.start || !rango.end) {
    component.filteredTickets = [...component.tickets];
    return;
  }

  const fechaInicio = new Date(rango.start);
  const fechaFin = new Date(rango.end);
  fechaFin.setHours(23, 59, 59, 999);
  
  component.filteredTickets = component.tickets.filter(ticket => {
    if (!ticket.fecha_finalizado_original) return false;
    const fecha = new Date(ticket.fecha_finalizado_original);
    return fecha >= fechaInicio && fecha <= fechaFin;
  });
  

  actualizarFiltrosCruzados(
    component.filteredTickets,
    component.usuariosDisponibles,
    component.estadosDisponibles,
    component.categoriasDisponibles,
    component.descripcionesDisponibles,
    component.criticidadesDisponibles,
    component.departamentosDisponibles,
    component.subcategoriasDisponibles,
    component.detallesDisponibles,
    component
  );
}

/** Sincronizar checkboxes disponibles después de filtrado cruzado */
export function sincronizarCheckboxesConFiltrado(component: PantallaVerTicketsComponent): void {
  const sincronizar = (
    disponibles: { valor: string; seleccionado: boolean }[],
    filtradas: { valor: string; seleccionado: boolean }[]
  ) => {
    disponibles.forEach(item => {
      const filtrado = filtradas.find(f => f.valor === item.valor);
      if (filtrado) {
        item.seleccionado = filtrado.seleccionado;
      }
    });
  };

  sincronizar(component.categoriasDisponibles, component.categoriasFiltradas);
  sincronizar(component.descripcionesDisponibles, component.descripcionesFiltradas);
  sincronizar(component.usuariosDisponibles, component.usuariosFiltrados);
  sincronizar(component.estadosDisponibles, component.estadosFiltrados);
  sincronizar(component.criticidadesDisponibles, component.criticidadesFiltradas);
  sincronizar(component.departamentosDisponibles, component.departamentosFiltrados);
  sincronizar(component.subcategoriasDisponibles, component.subcategoriasFiltradas);
  sincronizar(component.detallesDisponibles, component.detallesFiltrados);
  sincronizar(component.idsDisponibles, component.idsDisponibles); // IDs no tienen búsqueda
}
