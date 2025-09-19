// frontend-angular\src\app\pantalla-ver-tickets\helpers\fechas.helper.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';

/**
 * Funciones relacionadas a manejo de fechas y filtros cruzados en PantallaVerTicketsComponent.
 */

function parsearFecha(fechaTexto: any): Date | null {
  if (!fechaTexto) return null;

  // 1) Si ya es Date válido
  if (fechaTexto instanceof Date && !isNaN(fechaTexto.getTime())) {
    return fechaTexto;
  }

  const s = String(fechaTexto).trim();
  if (!s || s === '—') return null;

  // 2) ISO 8601 (con T o con espacio) -> Date.parse lo entiende
  //    Ej: 2025-09-19T17:03:11Z  |  2025-09-19 17:03:11
  //    Lo detectamos si hay patrón de hora tipo HH:MM en la cadena.
  if (/T\d{2}:\d{2}| \d{2}:\d{2}/.test(s)) {
    const t = Date.parse(s);
    if (!isNaN(t)) return new Date(t);
  }

  // 3) dd/mm/yy(yy) opcionalmente con hora HH:MM y opcional AM/PM
  //    Coincide: 1/9/25, 01/09/2025, 01/09/2025 6:13, 01/09/2025 06:13 PM
  const m = s.match(
    /^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})(?:\s+(\d{1,2}):(\d{2})(?:\s*(AM|PM|am|pm))?)?$/
  );
  if (m) {
    let [, dd, mm, yy, hh, min, ampm] = m;
    const day = parseInt(dd, 10);
    const mon = parseInt(mm, 10) - 1;

    let year = parseInt(yy, 10);
    if (yy.length === 2) year += 2000; // 25 -> 2025

    let hour = hh ? parseInt(hh, 10) : 0;
    const minute = min ? parseInt(min, 10) : 0;

    // Normalizar AM/PM si existe
    if (ampm) {
      const p = ampm.toLowerCase();
      if (p === 'pm' && hour < 12) hour += 12;
      if (p === 'am' && hour === 12) hour = 0;
    }

    const d = new Date(year, mon, day, hour, minute, 0, 0);
    return isNaN(d.getTime()) ? null : d;
  }

  // 4) Fallback: intenta Date.parse por si llega algo raro pero parseable
  const t = Date.parse(s);
  return isNaN(t) ? null : new Date(t);
}


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
  actualizar(detallesDisponibles, contarValores(ticketsFiltrados, 'detalle'));
}

export function aplicarFiltroPorRangoFechaCreacion(
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
    if (!ticket.fecha_creacion_original) return false;
    const fecha = parsearFecha(ticket.fecha_creacion_original);
    return fecha && fecha >= fechaInicio && fecha <= fechaFin;
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

  component.filtroCreacionActivo = true;
}

export function aplicarFiltroPorRangoFechaFinalizado(
  component: PantallaVerTicketsComponent,
  rango: { start: Date | null; end: Date | null }
): void {
  const fechaInicio = new Date(rango.start!);
  const fechaFin = new Date(rango.end!);
  fechaFin.setHours(23, 59, 59, 999);

  component.filteredTickets = component.tickets.filter(ticket => {
    const fecha = ticket.fecha_finalizado_original ? parsearFecha(ticket.fecha_finalizado_original) : null;

    if (component.incluirSinFechaFinalizado && !fecha) return true;
    if (!component.incluirSinFechaFinalizado && !fecha) return false;

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

  component.filtroFinalizadoActivo = true;
}

export function aplicarFiltroPorRangoFechaEnProgreso(
  component: PantallaVerTicketsComponent,
  rango: { start: Date | null; end: Date | null }
): void {
  const fechaInicio = new Date(rango.start!);
  const fechaFin = new Date(rango.end!);
  fechaFin.setHours(23, 59, 59, 999);

  component.filteredTickets = component.tickets.filter(ticket => {
    const fecha = ticket.fecha_en_progreso ? parsearFecha(ticket.fecha_en_progreso) : null;

    if (component.incluirSinFechaProgreso && !fecha) return true;
    if (!component.incluirSinFechaProgreso && !fecha) return false;

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

  component.filtroProgresoActivo = true;
}

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
  sincronizar(component.idsDisponibles, component.idsDisponibles);
}
