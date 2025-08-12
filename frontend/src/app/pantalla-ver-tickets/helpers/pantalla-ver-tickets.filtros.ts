// frontend-angular/src/app/pantalla-ver-tickets/helpers/pantalla-ver-tickets.filtros.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';
import {
  filtrarTicketsConFiltros,
  regenerarFiltrosFiltradosDesdeTickets,
  limpiarFiltroColumnaConMapa,
  removeDiacritics,
} from '../../utils/ticket-utils';
import {
  actualizarDiasConTicketsCreacion,
  actualizarDiasConTicketsFinalizado,
  actualizarVisibleTickets,
} from './pantalla-ver-tickets.init';

/**
 * Filtros dinámicos (versión DRY)
 * - Un único motor para filtrar opciones por texto (checkboxes)
 * - Mantiene compatibilidad exportando los nombres anteriores
 */

/* =======================
   Utilidades internas DRY
   ======================= */

const PLURAL: Record<string, string> = {
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

const TEXTO_PROP: Record<string, string> = {
  departamento: 'filtroDeptoTexto',
  detalle: 'filtroDetalleTexto',
  inventario: 'filtroInventarioTexto',
  sucursal: 'filtroSucursalTexto',
  // los demás siguen la convención filtro{Columna}Texto
};

function getPlural(col: string) {
  return PLURAL[col] ?? `${col}s`;
}

function getSearchProp(col: string) {
  if (TEXTO_PROP[col]) return TEXTO_PROP[col];
  return `filtro${col.charAt(0).toUpperCase() + col.slice(1)}Texto`;
}

/**
 * Motor genérico: filtra las opciones visibles (…Filtradas) de una columna
 * en base al texto escrito, usando (etiqueta ?? valor).
 */
function filtrarOpcionesTextoGenerico(
  component: PantallaVerTicketsComponent,
  columna: string
): void {
  const plural = getPlural(columna);
  const propTexto = getSearchProp(columna);

  const texto = (component as any)[propTexto]?.trim?.().toLowerCase?.() || '';

  // Base: si ya hay …Filtradas úsala; si no, parte de …Disponibles
  const base =
    (component as any)[`${plural}Filtradas`]?.length
      ? (component as any)[`${plural}Filtradas`]
      : (component as any)[`${plural}Disponibles`] || [];

  if (!Array.isArray(base)) return;

  const match = (it: any) =>
    removeDiacritics(String(it?.etiqueta ?? it?.valor ?? ''))
      .toLowerCase()
      .includes(removeDiacritics(texto));

  const filtradas = texto ? base.filter(match) : [...base];

  (component as any)[`${plural}Filtradas`] = filtradas;
  component.temporalSeleccionados[columna] = filtradas.map((i: any) => ({ ...i }));
}

/* ============================================
   Wrappers de compatibilidad (mismos nombres)
   ============================================ */

export function filtrarOpcionesCategoria(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'categoria');
}
export function filtrarOpcionesDescripcion(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'descripcion');
}
export function filtrarOpcionesUsuario(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'username');
}
export function filtrarOpcionesEstado(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'estado');
}
export function filtrarOpcionesCriticidad(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'criticidad');
}
export function filtrarOpcionesDepto(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'departamento');
}
export function filtrarOpcionesSubcategoria(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'subcategoria');
}
export function filtrarOpcionesDetalle(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'detalle');
}
// Si activas buscador para inventario/sucursal:
export function filtrarOpcionesInventario(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'inventario');
}
export function filtrarOpcionesSucursal(c: PantallaVerTicketsComponent) {
  filtrarOpcionesTextoGenerico(c, 'sucursal');
}

/* ==========================
   Fechas (se quedan iguales)
   ========================== */

export function filtrarOpcionesFechaC(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroFechaTexto.trim().toLowerCase();
  component.fechasCreacionFiltradas = texto
    ? component.fechasCreacionDisponibles.filter((fc) =>
        fc.valor.toLowerCase().includes(texto)
      )
    : [...component.fechasCreacionDisponibles];
}

export function filtrarOpcionesFechaF(component: PantallaVerTicketsComponent): void {
  const texto = component.filtroFechaFinalTexto.trim().toLowerCase();
  component.fechasFinalFiltradas = texto
    ? component.fechasFinalDisponibles.filter((ff) =>
        ff.valor.toLowerCase().includes(texto)
      )
    : [...component.fechasFinalDisponibles];
}

/* ==========================================
   Checkboxes y sincronización (sin cambios)
   ========================================== */

export function toggleSeleccionarTodo(
  component: PantallaVerTicketsComponent,
  campo: string,
  todos: boolean
): void {
  const campoFiltrado = (campo + 'Filtrados') as keyof PantallaVerTicketsComponent;
  const campoDisponibles = (campo + 'Disponibles') as keyof PantallaVerTicketsComponent;
  if (!(campoFiltrado in component) || !(campoDisponibles in component)) return;

  const filtrados = component[campoFiltrado] as { valor: string; seleccionado: boolean }[];
  if (!Array.isArray(filtrados)) return;

  filtrados.forEach((item) => (item.seleccionado = todos));

  const disponibles = component[campoDisponibles] as {
    valor: string;
    seleccionado: boolean;
  }[];
  disponibles.forEach((item) => {
    const match = filtrados.find((f) => f.valor === item.valor);
    if (match) item.seleccionado = match.seleccionado;
  });
}

export function sincronizarCheckboxesConDisponibles(c: PantallaVerTicketsComponent) {
  const sync = (d: any[], f: any[]) =>
    d.forEach((it) => {
      const m = f.find((x) => x.valor === it.valor);
      if (m) it.seleccionado = m.seleccionado;
    });

  sync(c.categoriasDisponibles, c.categoriasFiltradas);
  sync(c.descripcionesDisponibles, c.descripcionesFiltradas);
  sync(c.usuariosDisponibles, c.usuariosFiltrados);
  sync(c.estadosDisponibles, c.estadosFiltrados);
  sync(c.criticidadesDisponibles, c.criticidadesFiltradas);
  sync(c.departamentosDisponibles, c.departamentosFiltrados);
  sync(c.subcategoriasDisponibles, c.subcategoriasFiltradas);
  sync(c.detallesDisponibles, c.detallesFiltrados);
  sync(c.sucursalesDisponibles, c.sucursalesFiltradas);
  sync(c.inventariosDisponibles, c.inventariosFiltrados);
}

/* =========================
   Núcleo de aplicación DRY
   ========================= */

// Devuelve un objeto { campoTabla: [valoresSeleccionados] }
export function obtenerFiltrosActivos(
  component: any
): { [clave: string]: (string | number)[] } {

  const filtros: { [clave: string]: (string | number)[] } = {};

  const campos = [
    'categoria','descripcion','username','estado','criticidad',
    'departamento','subcategoria','detalle','inventario','sucursal'
  ] as const;

  const pluralMap: Record<string, string> = {
    categoria:'categorias', descripcion:'descripciones', username:'usuarios',
    estado:'estados', criticidad:'criticidades', departamento:'departamentos',
    subcategoria:'subcategorias', detalle:'detalles', inventario:'inventarios',
    sucursal:'sucursales'
  };

  campos.forEach(campo => {
    // selección tomada de los TEMPORALES (lo que quedó tras el buscador)
    const seleccion = component.temporalSeleccionados[campo]
      ?.filter((i: any) => i.seleccionado)
      .map((i: any) => i.valor) ?? [];

    // 👈 comparar SIEMPRE contra el total de DISPONIBLES (no temporales)
    const plural = pluralMap[campo] ?? `${campo}s`;
    const totalDisponibles = component[`${plural}Disponibles`]?.length ?? 0;

    if (seleccion.length > 0 && seleccion.length !== totalDisponibles) {
      filtros[campo] = seleccion;
    }
  });

  return filtros;
}


export function borrarFiltroRangoFechaCreacion(component: PantallaVerTicketsComponent): void {
  component.rangoFechaCreacionSeleccionado = { start: null, end: null };
  component.filteredTickets = [...component.tickets];
}

export function borrarFiltroRangoFechaFinalizado(component: PantallaVerTicketsComponent): void {
  component.rangoFechaFinalSeleccionado = { start: null, end: null };
  component.filteredTickets = [...component.tickets];
}

export function borrarFiltroRangoFechaEnProgreso(component: PantallaVerTicketsComponent): void {
  component.rangoFechaProgresoSeleccionado = { start: null, end: null };
  component.filteredTickets = [...component.tickets];
}

export function aplicarFiltroColumna(
  component: PantallaVerTicketsComponent,
  columna: string
): void {
  sincronizarCheckboxesConDisponibles(component);

  const filtros = obtenerFiltrosActivos(component);
  component.filteredTickets =
    Object.keys(filtros).length === 0
      ? [...component.tickets]
      : filtrarTicketsConFiltros(component.tickets, filtros);

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
    component.sucursalesDisponibles,
    component
  );

  limpiarTextoColumna(component, columna);

  actualizarDiasConTicketsCreacion(component);
  actualizarDiasConTicketsFinalizado(component);
}

export function limpiarFiltroColumna(
  component: PantallaVerTicketsComponent,
  columna: string
): void {
  limpiarFiltroColumnaConMapa(component, columna);

  const filtros = obtenerFiltrosActivos(component);
  component.filteredTickets = filtrarTicketsConFiltros(component.tickets, filtros);

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
    component.sucursalesDisponibles,
    component
  );
}

export function hayFiltrosActivos(component: PantallaVerTicketsComponent): boolean {
  const filtros = obtenerFiltrosActivos(component);
  return Object.keys(filtros).length > 0;
}

export function aplicarFiltrosDesdeMemoria(component: PantallaVerTicketsComponent): void {
  const filtros = obtenerFiltrosActivos(component);

  component.filteredTickets =
    Object.keys(filtros).length === 0
      ? [...component.tickets]
      : filtrarTicketsConFiltros(component.tickets, filtros);

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
    component.sucursalesDisponibles,
    component
  );

  actualizarDiasConTicketsCreacion(component);
  actualizarDiasConTicketsFinalizado(component);
}

/** Aplicar filtro y resetear a página 1 */
export function aplicarFiltroColumnaConReset(
  component: PantallaVerTicketsComponent,
  columna: string
): void {
  component.page = 1;

  sincronizarCheckboxesConDisponibles(component);

  const filtros = obtenerFiltrosActivos(component);
  component.filteredTickets =
    Object.keys(filtros).length === 0
      ? [...component.ticketsCompletos]
      : filtrarTicketsConFiltros(component.ticketsCompletos, filtros);

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
    component.sucursalesDisponibles,
    component
  );

  // Re-sincroniza los temporales con las listas filtradas calculadas
  resyncTemporalesDesdeFiltradas(component);

  limpiarTextoColumna(component, columna);

  actualizarDiasConTicketsCreacion(component);
  actualizarDiasConTicketsFinalizado(component);
  actualizarVisibleTickets(component);
}

function resyncTemporalesDesdeFiltradas(c: PantallaVerTicketsComponent): void {
  const map: Record<string, string> = {
    categoria: 'categoriasFiltradas',
    descripcion: 'descripcionesFiltradas',
    username: 'usuariosFiltrados',
    estado: 'estadosFiltrados',
    criticidad: 'criticidadesFiltradas',
    departamento: 'departamentosFiltrados',
    subcategoria: 'subcategoriasFiltradas',
    detalle: 'detallesFiltrados',
    inventario: 'inventariosFiltrados',
    sucursal: 'sucursalesFiltradas',
  };

  Object.entries(map).forEach(([col, key]) => {
    const lista = (c as any)[key] as Array<{ valor: any; etiqueta?: string; seleccionado: boolean }>;
    if (Array.isArray(lista)) {
      (c.temporalSeleccionados as any)[col] = lista.map((i) => ({ ...i }));
    }
  });
}

function limpiarTextoColumna(c: PantallaVerTicketsComponent, columna: string) {
  const prop = getSearchProp(columna);
  if ((c as any)[prop] !== undefined) (c as any)[prop] = '';
}

/* ==============================
   Export: filtros para backend
   ============================== */

export function obtenerFiltrosActivosParaBackend(
  component: PantallaVerTicketsComponent
): any {
  const filtros: any = {};

  const campos = [
    { nombre: 'estado', temp: component.temporalSeleccionados.estado },
    { nombre: 'departamento_id', temp: component.temporalSeleccionados.departamento },
    { nombre: 'criticidad', temp: component.temporalSeleccionados.criticidad },
    { nombre: 'username', temp: component.temporalSeleccionados.username },
    { nombre: 'categoria', temp: component.temporalSeleccionados.categoria },
    { nombre: 'subcategoria', temp: component.temporalSeleccionados.subcategoria },
    { nombre: 'detalle', temp: component.temporalSeleccionados.detalle },
    { nombre: 'descripcion', temp: component.temporalSeleccionados.descripcion },
    { nombre: 'inventario', temp: component.temporalSeleccionados.inventario },
    { nombre: 'sucursal', temp: component.temporalSeleccionados.sucursal },
  ];

  campos.forEach(({ nombre, temp }) => {
    if (!Array.isArray(temp)) return;
    const seleccionados = temp.filter((i) => i.seleccionado);

    if (seleccionados.length > 0 && seleccionados.length !== temp.length) {
      if (seleccionados.length === 1 && seleccionados[0].valor === '—') {
        filtros[nombre] = ['—'];
      } else if (nombre === 'departamento_id') {
        filtros[nombre] = seleccionados
          .filter((i) => i.valor !== '—')
          .map((i) => Number(i.valor));
      } else {
        filtros[nombre] = seleccionados.map((i) => i.valor).filter((v) => v !== '—');
      }
    }
  });

  const formatearFecha = (fecha: Date | null): string | null =>
    fecha instanceof Date && !isNaN(fecha.getTime())
      ? fecha.toISOString().split('T')[0]
      : null;

  const cIni = formatearFecha(component.rangoFechaCreacionSeleccionado.start);
  const cFin = formatearFecha(component.rangoFechaCreacionSeleccionado.end);
  const fIni = formatearFecha(component.rangoFechaFinalSeleccionado.start);
  const fFin = formatearFecha(component.rangoFechaFinalSeleccionado.end);
  const pIni = formatearFecha(component.rangoFechaProgresoSeleccionado.start);
  const pFin = formatearFecha(component.rangoFechaProgresoSeleccionado.end);

  if (cIni) filtros.fecha_desde = cIni;
  if (cFin) filtros.fecha_hasta = cFin;
  if (fIni) filtros.fecha_fin_desde = fIni;
  if (fFin) filtros.fecha_fin_hasta = fFin;
  if (pIni) filtros.fecha_prog_desde = pIni;
  if (pFin) filtros.fecha_prog_hasta = pFin;

  return filtros;
}
