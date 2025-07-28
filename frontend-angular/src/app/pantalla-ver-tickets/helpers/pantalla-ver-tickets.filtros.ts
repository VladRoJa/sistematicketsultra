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
export function toggleSeleccionarTodo(
  component: PantallaVerTicketsComponent,
  campo: string,
  todos: boolean
): void {
  // 🔒 1) Verificamos que la propiedad exista antes de tocarla
  const campoFiltrado = (campo + 'Filtrados') as keyof PantallaVerTicketsComponent;
  const campoDisponibles = (campo + 'Disponibles') as keyof PantallaVerTicketsComponent;
  if (!(campoFiltrado in component) || !(campoDisponibles in component)) {
    console.warn(`toggleSeleccionarTodo: columna desconocida '${campo}'`);
    return;                        // ⇦ Salimos silenciosamente
  }

  // 🔄 2) Array de opciones visibles (filtradas)
  const filtrados = component[campoFiltrado] as { valor: string; seleccionado: boolean }[];
  if (!Array.isArray(filtrados)) { return; }

  // ✅ 3) Marcamos / desmarcamos lo visible
  filtrados.forEach(item => (item.seleccionado = todos));

  // 🔄 4) Sincronizamos los disponibles con lo recién marcado
  const disponibles = component[campoDisponibles] as { valor: string; seleccionado: boolean }[];
  disponibles.forEach(item => {
    const match = filtrados.find(f => f.valor === item.valor);
    if (match) { item.seleccionado = match.seleccionado; }
  });
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
/** Devuelve un objeto { campoTabla: [valoresSeleccionados] } */
export function obtenerFiltrosActivos(
  component: any
): { [clave: string]: string[] } {

  const filtros: { [clave: string]: string[] } = {};

  // Los nueve campos que soportan filtrado por check-box
  const campos = [
    'categoria',
    'descripcion',
    'username',
    'estado',
    'criticidad',
    'departamento',
    'subcategoria',
    'detalle',
    'inventario'
  ] as const;

  campos.forEach(campo => {
    const seleccion = component.temporalSeleccionados[campo]
      ?.filter(i => i.seleccionado)
      .map(i => i.valor) ?? [];

    const totalOpciones = component.temporalSeleccionados[campo]?.length ?? 0;
    if (seleccion.length > 0 && seleccion.length !== totalOpciones) {
      filtros[campo] = seleccion;
    }
  });

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
    component.inventariosDisponibles,
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
  if (columna === 'detalle') component.filtroDetalleTexto = '';
  if (columna === 'inventario') component.filtroInventarioTexto = '';

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
    component.inventariosDisponibles,
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
    component.inventariosDisponibles,
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
    component.inventariosDisponibles,
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
  if (columna === 'detalle') component.filtroDetalleTexto = '';
  if (columna === 'inventario') component.filtroInventarioTexto = '';

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
  const detalle = getSeleccionados(component.detallesFiltrados);
  const descripcion = getSeleccionados(component.descripcionesFiltradas);
  const inventario = getSeleccionados(component.inventariosFiltrados);

  if (estado.length) filtros.estado = estado;
  if (departamento_id.length) filtros.departamento_id = departamento_id;
  if (criticidad.length) filtros.criticidad = criticidad;
  if (username.length) filtros.username = username;
  if (categoria.length) filtros.categoria = categoria;
  if (subcategoria.length) filtros.subcategoria = subcategoria;
  if (detalle.length) filtros.detalle = detalle;
  if (descripcion.length) filtros.descripcion = descripcion;
  if (inventario.length) filtros.inventario = getSeleccionados(component.inventariosFiltrados);

  // ✅ Función segura para convertir a YYYY-MM-DD
  const formatearFecha = (fecha: Date | null): string | null => {
    if (fecha instanceof Date && !isNaN(fecha.getTime())) {
      return fecha.toISOString().split("T")[0];
    }
    return null;
  };

  // Fechas como strings en formato YYYY-MM-DD (solo si son válidas)
  const fechaCreacionStart = formatearFecha(component.rangoFechaCreacionSeleccionado.start);
  const fechaCreacionEnd = formatearFecha(component.rangoFechaCreacionSeleccionado.end);
  const fechaFinalStart = formatearFecha(component.rangoFechaFinalSeleccionado.start);
  const fechaFinalEnd = formatearFecha(component.rangoFechaFinalSeleccionado.end);
  const fechaProgresoStart = formatearFecha(component.rangoFechaProgresoSeleccionado.start);
  const fechaProgresoEnd = formatearFecha(component.rangoFechaProgresoSeleccionado.end);

  if (fechaCreacionStart) filtros.fecha_desde = fechaCreacionStart;
  if (fechaCreacionEnd) filtros.fecha_hasta = fechaCreacionEnd;
  if (fechaFinalStart) filtros.fecha_fin_desde = fechaFinalStart;
  if (fechaFinalEnd) filtros.fecha_fin_hasta = fechaFinalEnd;
  if (fechaProgresoStart) filtros.fecha_prog_desde = fechaProgresoStart;
  if (fechaProgresoEnd) filtros.fecha_prog_hasta = fechaProgresoEnd;

  // Log opcional para depuración
  console.log("📤 Filtros para exportar:", filtros);

  return filtros;
}


