// src/app/utils/filtro-unificado.ts

import { confirmarFiltroColumna } from "../pantalla-ver-tickets/helpers/filtros-genericos";
import { obtenerFiltrosActivos } from "../pantalla-ver-tickets/helpers/pantalla-ver-tickets.filtros";
import { filtrarTicketsConFiltros, regenerarFiltrosFiltradosDesdeTickets } from "./ticket-utils";



// ---- Campos soportados del filtro unificado ----

export type CampoFiltro =
  | 'categoria'
  | 'descripcion'
  | 'username'
  | 'estado'
  | 'criticidad'
  | 'departamento'
  | 'subcategoria'
  | 'detalle'
  | 'inventario'   // usaría ticket.inventario?.nombre
  | 'sucursal'     // tu componente ya hidrata ticket.sucursal
;


export interface TicketVistaMin {
  // En tu procesamiento final, 'categoria' es id (nivel 2) o null
  categoria?: number | null;
  descripcion?: string | null;
  username?: string | null;
  estado?: string | null;
  criticidad?: number | null;
  departamento?: string | null; // tu comp lo resuelve por nombre
  subcategoria?: number | null;
  detalle?: number | null;
  inventario?: { nombre?: string | null } | null;
  sucursal?: string | null; // la hidratas en el componente
  departamento_id?: number | null; 
}

// ---- Estado del filtro unificado ----
export interface EstadoFiltroUnificado {
  campoSeleccionado: CampoFiltro | null;
  opcionesDisponibles: Array<{ valor: string; etiqueta: string }>;
  textoBusqueda: string;
  seleccionTemporal: Set<string>;
  filtrosAplicados: Map<CampoFiltro, Set<string>>;
}

// ---- Inicializador ----
export function crearEstadoInicial(): EstadoFiltroUnificado {
  return {
    campoSeleccionado: null,
    opcionesDisponibles: [],
    textoBusqueda: '',
    seleccionTemporal: new Set<string>(),
    filtrosAplicados: new Map<CampoFiltro, Set<string>>(),
  };
}

// ---- Extractor de valor crudo por campo (lo que realmente filtra) ----
function extractorPorCampo(campo: CampoFiltro): (t: TicketVistaMin) => string | null {
  switch (campo) {
    case 'categoria':
      return (t) => (t.categoria != null ? String(t.categoria) : null);
    case 'descripcion': return (t) => t.descripcion ?? null;
    case 'username':    return (t) => t.username ?? null;
    case 'estado':      return (t) => t.estado ?? null;
    case 'criticidad':  return (t) => (t.criticidad != null ? String(t.criticidad) : null);
    case 'departamento': return (t) => t.departamento ?? null;
    case 'subcategoria': return (t) => (t.subcategoria != null ? String(t.subcategoria) : null);
    case 'detalle':      return (t) => (t.detalle != null ? String(t.detalle) : null);
    case 'inventario':   return (t) => t.inventario?.nombre ?? null;
    case 'sucursal':     return (t) => t.sucursal ?? null;
  }
}


// ---- Formateadores opcionales de ETIQUETA (para mostrar bonito al usuario) ----
// clave: campo, valor: función que recibe el valor crudo y devuelve etiqueta visible
export type EtiquetaFormatters = Partial<Record<CampoFiltro, (valor: string) => string>>;

// ---- Construye opciones únicas para el campo, con etiqueta opcional ----
export function construirOpciones(
  tickets: TicketVistaMin[],
  campo: CampoFiltro,
  formatters?: EtiquetaFormatters
): Array<{ valor: string; etiqueta: string }> {
  const extraer = extractorPorCampo(campo);
  const set = new Set<string>();

  for (const t of tickets) {
    const v = extraer(t);
    if (v && v.trim()) set.add(v.trim());
  }

  const toEtiqueta = (v: string) =>
    (formatters && formatters[campo] ? formatters[campo]!(v) : v);

  return Array.from(set)
    .sort((a, b) => toEtiqueta(a).localeCompare(toEtiqueta(b)))
    .map(v => ({ valor: v, etiqueta: toEtiqueta(v) }));
}

// ---- Filtra opciones por texto (sobre etiqueta/valor) ----
export function filtrarOpcionesPorTexto(
  opciones: Array<{ valor: string; etiqueta: string }>,
  texto: string
) {
  const q = (texto ?? '').trim().toLowerCase();
  if (!q) return opciones;
  return opciones.filter(o =>
    (o.etiqueta ?? o.valor).toLowerCase().includes(q)
  );
}

// ---- Alternar en el checklist temporal ----
export function alternarSeleccionTemporal(
  estado: EstadoFiltroUnificado,
  valor: string
) {
  if (estado.seleccionTemporal.has(valor)) estado.seleccionTemporal.delete(valor);
  else estado.seleccionTemporal.add(valor);
}

// ---- Aplicar checklist temporal al mapa de filtros persistidos ----
export function aplicarFiltroActual(estado: EstadoFiltroUnificado) {
  const campo = estado.campoSeleccionado;
  if (!campo) return;
  estado.filtrosAplicados.set(campo, new Set(estado.seleccionTemporal));
}

// ---- Limpiar filtro del campo actual ----
export function limpiarFiltroActual(estado: EstadoFiltroUnificado) {
  const campo = estado.campoSeleccionado;
  if (!campo) return;
  estado.filtrosAplicados.delete(campo);
  estado.seleccionTemporal.clear();
  estado.textoBusqueda = '';
}

// ---- Seleccionar campo (reconstruye opciones y precarga lo aplicado) ----
export function seleccionarCampo(
  estado: EstadoFiltroUnificado,
  tickets: TicketVistaMin[],
  campo: CampoFiltro,
  formatters?: EtiquetaFormatters
) {
  estado.campoSeleccionado = campo;
  estado.opcionesDisponibles = construirOpciones(tickets, campo, formatters);
  estado.textoBusqueda = '';
  estado.seleccionTemporal = new Set(estado.filtrosAplicados.get(campo) ?? []);
}

// ---- Aplica TODOS los filtros persistidos al arreglo ----
export function filtrarTickets(
  tickets: TicketVistaMin[],
  filtros: Map<CampoFiltro, Set<string>>
): TicketVistaMin[] {
  if (filtros.size === 0) return tickets;

  return tickets.filter(t => {
    for (const [campo, valores] of filtros.entries()) {
      if (valores.size === 0) continue;
      const valorTicket = extractorPorCampo(campo)(t) ?? '';
      if (!valores.has(valorTicket)) return false;
    }
    return true;
  });
}


// Clona ...Filtradas -> temporalSeleccionados para todas las columnas
function resyncTemporalesDesdeFiltradas(component: any): void {
  const columnas = [
    'categoria','descripcion','username','estado','criticidad',
    'departamento','subcategoria','detalle','inventario','sucursal'
  ] as const;

  const pluralMap: Record<string, string> = {
    categoria:'categorias', descripcion:'descripciones', username:'usuarios',
    estado:'estados', criticidad:'criticidades', departamento:'departamentos',
    subcategoria:'subcategorias', detalle:'detalles', inventario:'inventarios',
    sucursal:'sucursales'
  };

  if (!component.temporalSeleccionados) {
    component.temporalSeleccionados = {};
  }

  columnas.forEach(col => {
    const plural = pluralMap[col] ?? `${col}s`;
    const filtradas = (component[`${plural}Filtradas`] as Array<{ valor:any; etiqueta?:string; seleccionado:boolean }>) ?? [];
    // Clon superficial para no compartir referencias
    component.temporalSeleccionados[col] = filtradas.map(op => ({ ...op }));
  });
}




/**
 * Versión unificada/estable del flujo de "Aplicar" para cualquier columna.
 * No colisiona con tu versión existente.
 */
export function aplicarFiltroColumnaConResetUnificado(component: any, columna: string): void {
  // 1) Persistir selección del modal en ...Disponibles
  confirmarFiltroColumna(component, columna);

  // 2) Construir filtros activos y convertir a Set<string>
  const filtros = obtenerFiltrosActivos(component);
  const filtrosSet: Record<string, Set<string>> = {};
  for (const key in filtros) if (Array.isArray(filtros[key])) filtrosSet[key] = new Set(filtros[key].map(String));

  // 3) Filtrar SOLO la tabla
  component.filteredTickets = filtrarTicketsConFiltros(component.ticketsCompletos, filtrosSet);

  // 4) Limpiar buscador de ESA columna (opcional)
  const propTexto = `filtro${columna.charAt(0).toUpperCase()}${columna.slice(1)}Texto`;
  if (propTexto in component) component[propTexto] = '';

  // 5) Paginación / render
  component.page = 1;
  component.totalTickets = component.filteredTickets.length;
  component.totalPagesCount = Math.ceil(component.totalTickets / component.itemsPerPage);
  component.visibleTickets = component.filteredTickets.slice(0, component.itemsPerPage);
  component.changeDetectorRef?.detectChanges?.();
}

export function limpiarFiltroColumnaUnificado(component: any, columna: string): void {
  const pluralMap: Record<string, string> = {
    categoria:'categorias', descripcion:'descripciones', username:'usuarios',
    estado:'estados', criticidad:'criticidades', departamento:'departamentos',
    subcategoria:'subcategorias', detalle:'detalles', inventario:'inventarios', sucursal:'sucursales'
  };

  const plural = pluralMap[columna] ?? `${columna}s`;
  const disponibles = (component[`${plural}Disponibles`] as Array<{ seleccionado:boolean }> | undefined) ?? [];

  disponibles.forEach(op => op.seleccionado = true);
  component[`${plural}Filtradas`] = disponibles.map(op => ({ ...op }));
  if (!component.temporalSeleccionados) component.temporalSeleccionados = {};
  component.temporalSeleccionados[columna] = disponibles.map(op => ({ ...op }));

  const filtros = obtenerFiltrosActivos(component);
  const filtrosSet: Record<string, Set<string>> = {};
  for (const key in filtros) if (Array.isArray(filtros[key])) filtrosSet[key] = new Set(filtros[key].map(String));

  component.filteredTickets = filtrarTicketsConFiltros(component.ticketsCompletos, filtrosSet);

  component.page = 1;
  component.totalTickets = component.filteredTickets.length;
  component.totalPagesCount = Math.ceil(component.totalTickets / component.itemsPerPage);
  component.visibleTickets = component.filteredTickets.slice(0, component.itemsPerPage);
  component.changeDetectorRef?.detectChanges?.();
}


