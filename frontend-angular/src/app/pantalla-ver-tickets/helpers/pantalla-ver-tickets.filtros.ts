// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.filtros.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';
import { filtrarTicketsConFiltros, regenerarFiltrosFiltradosDesdeTickets, limpiarFiltroColumnaConMapa, todasOpcionesDesmarcadas, removeDiacritics } from '../../utils/ticket-utils';
import { actualizarDiasConTicketsCreacion, actualizarDiasConTicketsFinalizado, actualizarVisibleTickets } from './pantalla-ver-tickets.init'

/**
 * Funciones para manejar todos los filtros dinámicos en PantallaVerTicketsComponent
 */

/** ------ Filtros individuales ------ */

/** Filtrar categorías */
export function filtrarOpcionesCategoria(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroCategoriaTexto.trim().toLowerCase();
  component.categoriasFiltradas = texto
    ? component.categoriasDisponibles.filter(cat => removeDiacritics(cat.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.categoriasDisponibles];
}

/** Filtrar descripciones */
export function filtrarOpcionesDescripcion(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroDescripcionTexto.trim().toLowerCase();
  component.descripcionesFiltradas = texto
    ? component.descripcionesDisponibles.filter(desc => removeDiacritics(desc.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.descripcionesDisponibles];
}

/** Filtrar usuarios */
export function filtrarOpcionesUsuario(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroUsuarioTexto.trim().toLowerCase();
  component.usuariosFiltrados = texto
    ? component.usuariosDisponibles.filter(usr => removeDiacritics(usr.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.usuariosDisponibles];
}

/** Filtrar estados */
export function filtrarOpcionesEstado(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroEstadoTexto.trim().toLowerCase();
  component.estadosFiltrados = texto
    ? component.estadosDisponibles.filter(est => removeDiacritics(est.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.estadosDisponibles];
}

/** Filtrar criticidades */
export function filtrarOpcionesCriticidad(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroCriticidadTexto.trim().toLowerCase();
  component.criticidadesFiltradas = texto
    ? component.criticidadesDisponibles.filter(crit => removeDiacritics(crit.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.criticidadesDisponibles];
}

/** Filtrar departamentos */
export function filtrarOpcionesDepto(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroDeptoTexto.trim().toLowerCase();
  component.departamentosFiltrados = texto
    ? component.departamentosDisponibles.filter(dep => removeDiacritics(dep.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.departamentosDisponibles];
}

/** Filtrar subcategorías */
export function filtrarOpcionesSubcategoria(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroSubcategoriaTexto.trim().toLowerCase();
  component.subcategoriasFiltradas = texto
    ? component.subcategoriasDisponibles.filter(sub => removeDiacritics(sub.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.subcategoriasDisponibles];
}

/** Filtrar detalles (subsubcategorías) */
export function filtrarOpcionesDetalle(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroDetalleTexto.trim().toLowerCase();
  component.detallesFiltrados = texto
    ? component.detallesDisponibles.filter(det => removeDiacritics(det.valor.toLowerCase()).includes(removeDiacritics(texto)))
    : [...component.detallesDisponibles];
}

/** Filtrar fechas de creación */
export function filtrarOpcionesFechaC(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroFechaTexto.trim().toLowerCase();
  component.fechasCreacionFiltradas = texto
    ? component.fechasCreacionDisponibles.filter(fc => fc.valor.toLowerCase().includes(texto))
    : [...component.fechasCreacionDisponibles];
}

/** Filtrar fechas de finalización */
export function filtrarOpcionesFechaF(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroFechaFinalTexto.trim().toLowerCase();
  component.fechasFinalFiltradas = texto
    ? component.fechasFinalDisponibles.filter(ff => ff.valor.toLowerCase().includes(texto))
    : [...component.fechasFinalDisponibles];
}

/** ------ Checkboxes y sincronización ------ */

/** Alternar selección de todos los checkboxes de una columna */
export function toggleSeleccionarTodo(component: PantallaVerTicketsComponent, campo: string, todos: boolean): void {
  const campoFiltrado = campo + 'Filtrados';
  if (component[campoFiltrado]) {
    component[campoFiltrado].forEach((item: any) => {
      item.seleccionado = todos;
    });
  }
}

/** Sincronizar selección de disponibles basado en filtrados */
export function sincronizarCheckboxesConDisponibles(component: PantallaVerTicketsComponent): void {
  const sincronizar = (disponibles: { valor: string; seleccionado: boolean }[], filtradas: { valor: string; seleccionado: boolean }[]) => {
    disponibles.forEach(item => {
      const match = filtradas.find(f => f.valor === item.valor);
      if (match) {
        item.seleccionado = match.seleccionado;
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
}

/** ------ Funciones generales de filtros ------ */

/** Obtener todos los filtros activos de la tabla */
export function obtenerFiltrosActivos(component: PantallaVerTicketsComponent): { [clave: string]: string[] } {
  const filtros: { [clave: string]: string[] } = {};

  const agregarFiltro = (nombreCampoTabla: string, disponibles: { valor: string, seleccionado: boolean }[]) => {
    const seleccionados = disponibles.filter(item => item.seleccionado).map(item => item.valor);
    if (seleccionados.length > 0) {
      filtros[nombreCampoTabla] = seleccionados;
    }
  };

  agregarFiltro('categoria', component.categoriasDisponibles);
  agregarFiltro('descripcion', component.descripcionesDisponibles);
  agregarFiltro('username', component.usuariosDisponibles);
  agregarFiltro('estado', component.estadosDisponibles);
  agregarFiltro('criticidad', component.criticidadesDisponibles);
  agregarFiltro('departamento', component.departamentosDisponibles);
  agregarFiltro('subcategoria', component.subcategoriasDisponibles);
  agregarFiltro('subsubcategoria', component.detallesDisponibles);

  return filtros;
}




/** Borrar filtro de rango de fecha de creación */
export function borrarFiltroRangoFechaCreacion(component: PantallaVerTicketsComponent): void {
  component.rangoFechaCreacionSeleccionado = { start: null, end: null };
  component.filteredTickets = [...component.tickets];
}

/** Borrar filtro de rango de fecha de finalización */
export function borrarFiltroRangoFechaFinalizado(component: PantallaVerTicketsComponent): void {
  component.rangoFechaFinalSeleccionado = { start: null, end: null };
  component.filteredTickets = [...component.tickets];
}

/** Borrar filtro de rango de fecha en progreso */
export function borrarFiltroRangoFechaEnProgreso(component: PantallaVerTicketsComponent): void {
  component.rangoFechaProgresoSeleccionado = { start: null, end: null };
  component.filteredTickets = [...component.tickets];
}

/** Aplicar todos los filtros activos en todas las columnas */
export function aplicarFiltroColumna(component: PantallaVerTicketsComponent, columna: string): void {
  sincronizarCheckboxesConDisponibles(component);

  // 1. Obtener los filtros activos (todos los checkboxes seleccionados)
  const filtros = obtenerFiltrosActivos(component);

  if (Object.keys(filtros).length === 0) {
    // No hay filtros activos, restauramos todo
    component.filteredTickets = [...component.tickets];
  } else {
    // Filtramos los tickets basándonos en los filtros activos
    const filtrados = filtrarTicketsConFiltros(component.tickets, filtros);
    component.filteredTickets = filtrados;
  }

  // 2. Regeneramos todos los checkboxes de todos los filtros
  regenerarFiltrosFiltradosDesdeTickets(
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

  // 3. Limpiamos filtro de texto (opcional)
  if (columna === 'categoria') component.filtroCategoriaTexto = '';
  if (columna === 'descripcion') component.filtroDescripcionTexto = '';
  if (columna === 'username') component.filtroUsuarioTexto = '';
  if (columna === 'estado') component.filtroEstadoTexto = '';
  if (columna === 'criticidad') component.filtroCriticidadTexto = '';
  if (columna === 'departamento') component.filtroDeptoTexto = '';
  if (columna === 'subcategoria') component.filtroSubcategoriaTexto = '';
  if (columna === 'subsubcategoria') component.filtroDetalleTexto = '';

  actualizarDiasConTicketsCreacion(component);
  actualizarDiasConTicketsFinalizado(component);

}

  

/** Limpiar filtro individual de una columna */
export function limpiarFiltroColumna(component: PantallaVerTicketsComponent, columna: string): void {
  limpiarFiltroColumnaConMapa(component, columna);

  const filtros = obtenerFiltrosActivos(component);
  const filtrados = filtrarTicketsConFiltros(component.tickets, filtros);
  component.filteredTickets = filtrados;

  regenerarFiltrosFiltradosDesdeTickets(
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

/** Detecta si el usuario tiene algún filtro activo */
export function hayFiltrosActivos(component: PantallaVerTicketsComponent): boolean {
  const filtros = obtenerFiltrosActivos(component);
  return Object.keys(filtros).length > 0;
}

/** Aplica filtros directamente sobre los tickets en memoria */
export function aplicarFiltrosDesdeMemoria(component: PantallaVerTicketsComponent): void {
  const filtros = obtenerFiltrosActivos(component);

  if (Object.keys(filtros).length === 0) {
    component.filteredTickets = [...component.tickets];
  } else {
    const filtrados = filtrarTicketsConFiltros(component.tickets, filtros);
    component.filteredTickets = filtrados;
  }

  regenerarFiltrosFiltradosDesdeTickets(
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

  actualizarDiasConTicketsCreacion(component);
  actualizarDiasConTicketsFinalizado(component);

}

/** Aplicar filtro y resetear a página 1 */
export function aplicarFiltroColumnaConReset(component: PantallaVerTicketsComponent, columna: string): void {
  component.page = 1;

  // 🟢 NECESARIO para aplicar correctamente filtros cruzados
  sincronizarCheckboxesConDisponibles(component);

  const filtros = obtenerFiltrosActivos(component);
  if (Object.keys(filtros).length === 0) {
    component.filteredTickets = [...component.ticketsCompletos];
  } else {
    component.filteredTickets = filtrarTicketsConFiltros(component.ticketsCompletos, filtros);
  }

  regenerarFiltrosFiltradosDesdeTickets(
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

  // Limpiar buscadores de texto
  if (columna === 'categoria') component.filtroCategoriaTexto = '';
  if (columna === 'descripcion') component.filtroDescripcionTexto = '';
  if (columna === 'username') component.filtroUsuarioTexto = '';
  if (columna === 'estado') component.filtroEstadoTexto = '';
  if (columna === 'criticidad') component.filtroCriticidadTexto = '';
  if (columna === 'departamento') component.filtroDeptoTexto = '';
  if (columna === 'subcategoria') component.filtroSubcategoriaTexto = '';
  if (columna === 'subsubcategoria') component.filtroDetalleTexto = '';

  // 🔄 Actualizar visibilidad
  actualizarVisibleTickets(component);
}


/** Obtener filtros activos en formato para backend (solo uno por filtro) *//** Obtener filtros activos en formato para backend (acepta múltiples valores por filtro) */
export function obtenerFiltrosActivosParaBackend(component: PantallaVerTicketsComponent): any {
  const filtros: any = {};

  const getSeleccionados = (lista: { valor: string, seleccionado: boolean }[]) =>
    lista.filter(item => item.seleccionado).map(item => item.valor);

  // Filtros múltiples (mismo nombre que espera el backend)
  const estado = getSeleccionados(component.estadosFiltrados);
  const departamento_id = getSeleccionados(component.departamentosFiltrados);
  const criticidad = getSeleccionados(component.criticidadesFiltradas);
  const username = getSeleccionados(component.usuariosFiltrados);
  const categoria = getSeleccionados(component.categoriasFiltradas);
  const subcategoria = getSeleccionados(component.subcategoriasFiltradas);
  const subsubcategoria = getSeleccionados(component.detallesFiltrados);
  const descripcion = getSeleccionados(component.descripcionesFiltradas);

  if (estado.length) filtros.estado = estado;
  if (departamento_id.length) filtros.departamento_id = departamento_id;
  if (criticidad.length) filtros.criticidad = criticidad;
  if (username.length) filtros.username = username;
  if (categoria.length) filtros.categoria = categoria;
  if (subcategoria.length) filtros.subcategoria = subcategoria;
  if (subsubcategoria.length) filtros.subsubcategoria = subsubcategoria;
  if (descripcion.length) filtros.descripcion = descripcion;

  // Fechas como strings en formato YYYY-MM-DD
  if (component.rangoFechaCreacionSeleccionado.start)
    filtros.fecha_desde = component.rangoFechaCreacionSeleccionado.start.toISOString().split("T")[0];
  if (component.rangoFechaCreacionSeleccionado.end)
    filtros.fecha_hasta = component.rangoFechaCreacionSeleccionado.end.toISOString().split("T")[0];
  if (component.rangoFechaFinalSeleccionado.start)
    filtros.fecha_fin_desde = component.rangoFechaFinalSeleccionado.start.toISOString().split("T")[0];
  if (component.rangoFechaFinalSeleccionado.end)
    filtros.fecha_fin_hasta = component.rangoFechaFinalSeleccionado.end.toISOString().split("T")[0];
  if (component.rangoFechaProgresoSeleccionado.start)
    filtros.fecha_prog_desde = component.rangoFechaProgresoSeleccionado.start.toISOString().split("T")[0];
  if (component.rangoFechaProgresoSeleccionado.end)
    filtros.fecha_prog_hasta = component.rangoFechaProgresoSeleccionado.end.toISOString().split("T")[0];

  return filtros;
}



