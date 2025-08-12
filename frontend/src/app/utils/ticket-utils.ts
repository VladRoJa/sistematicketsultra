// src/app/utils/ticket-utils.ts

import { Ticket } from '../pantalla-ver-tickets/pantalla-ver-tickets.component';

// ----------- TIPOS -----------
export type FiltroString = { valor: string; seleccionado: boolean };
export type FiltroNumero = { valor: number; etiqueta: string; seleccionado: boolean };
export type Filtro = FiltroString | FiltroNumero;

// ----------- GENERADORES DE OPCIONES -----------
// Departamentos (por ID y nombre)
export function generarOpcionesDepartamentosDesdeTickets(
  tickets: Ticket[],
  listaDepartamentos: { id: number, nombre: string }[]
): FiltroNumero[] {
  const idsUnicos = Array.from(new Set(tickets.map(ticket => ticket.departamento_id)));
  return idsUnicos
    .filter((id): id is number => id !== null && id !== undefined)
    .map(id => ({
      valor: id,
      etiqueta: listaDepartamentos.find(dep => dep.id === id)?.nombre || '—',
      seleccionado: true
    }));
}

// Generales (string)
export function generarOpcionesDisponiblesDesdeTickets(
  tickets: Ticket[],
  campo: keyof Ticket
): FiltroString[] {
  let valoresUnicos: string[] = [];
  if (campo === 'inventario') {
    valoresUnicos = Array.from(new Set(tickets.map(ticket => ticket.inventario?.nombre || '—')));
  } else {
    valoresUnicos = Array.from(new Set(tickets.map(ticket => (ticket[campo] ?? '—').toString())));
  }
  return valoresUnicos.map(valor => ({
    valor,
    seleccionado: true
  }));
}

// ----------- GET FILTROS ACTIVOS (para enviar al backend) -----------
export function getFiltrosActivosFrom(
  usuarios: FiltroString[],
  estados: FiltroString[],
  categorias: FiltroString[],
  inventarios: FiltroString[],
  descripciones: FiltroString[],
  criticidades: FiltroString[],
  departamentos: FiltroNumero[],
  subcategorias: FiltroString[],
  detalles: FiltroString[]
): { [clave: string]: (string | number)[] } {
  return {
    username: usuarios.filter(i => i.seleccionado).map(i => i.valor),
    estado: estados.filter(i => i.seleccionado).map(i => i.valor),
    categoria: categorias.filter(i => i.seleccionado).map(i => i.valor),
    inventario: inventarios.filter(i => i.seleccionado).map(i => i.valor),
    descripcion: descripciones.filter(i => i.seleccionado).map(i => i.valor),
    criticidad: criticidades.filter(i => i.seleccionado).map(i => i.valor),
    departamento: departamentos.filter(i => i.seleccionado).map(i => i.valor),
    subcategoria: subcategorias.filter(i => i.seleccionado).map(i => i.valor),
    detalle: detalles.filter(i => i.seleccionado).map(i => i.valor),
  };
}

// ----------- FILTRADO CRUZADO PRINCIPAL -----------
// ----------- FILTRADO PRINCIPAL (sin cross UI, solo tabla) -----------
export function filtrarTicketsConFiltros(
  tickets: any[],
  filtros: FiltrosEntrada | Record<string, any>
) {
  const filtrosSet = normalizaFiltros(filtros);
console.log('🧪 filtrosSet:', Object.fromEntries(
  Object.entries(filtrosSet).map(([k, v]) => [k, Array.from(v)])
));

  const getValue = (t: any, col: string): string => {
    switch (col) {
      case 'categoria':    return t.categoria != null ? String(t.categoria) : '';
      case 'descripcion':  return t.descripcion ?? '';
      case 'username':     return t.username ?? '';
      case 'estado':       return t.estado ?? '';
      case 'criticidad':   return t.criticidad != null ? String(t.criticidad) : '';
      case 'departamento': return t.departamento ?? '';      // ← por nombre
      case 'subcategoria': return t.subcategoria != null ? String(t.subcategoria) : '';
      case 'detalle':      return t.detalle != null ? String(t.detalle) : '';
      case 'inventario':   return t.inventario?.nombre ?? '';
      case 'sucursal':     return t.sucursal ?? '';
      default:             return '';
    }
  };

return tickets.filter(t => {
  for (const [col, valores] of Object.entries(filtrosSet)) {
    if (!valores || valores.size === 0) continue;

    let valorTicket = '';

    if (col === 'departamento') {
      // si todos los valores del filtro son dígitos → comparamos contra departamento_id
      const usandoIds = Array.from(valores).every(v => /^\d+$/.test(v));
      valorTicket = usandoIds
        ? (t.departamento_id != null ? String(t.departamento_id) : '')
        : (t.departamento ?? '');

      // 🔎 log de comparación departamento
      console.log('🔎 dept comparando', {
        usandoIds,
        valorTicket,
        valores: Array.from(valores),
        ticket_dep_id: t.departamento_id,
        ticket_dep_nombre: t.departamento
      });
    } else {
      // tu getValue normal
      valorTicket = (() => {
        switch (col) {
          case 'categoria':    return t.categoria != null ? String(t.categoria) : '';
          case 'descripcion':  return t.descripcion ?? '';
          case 'username':     return t.username ?? '';
          case 'estado':       return t.estado ?? '';
          case 'criticidad':   return t.criticidad != null ? String(t.criticidad) : '';
          case 'subcategoria': return t.subcategoria != null ? String(t.subcategoria) : '';
          case 'detalle':      return t.detalle != null ? String(t.detalle) : '';
          case 'inventario':   return t.inventario?.nombre ?? '';
          case 'sucursal':     return t.sucursal ?? '';
          default:             return '';
        }
      })();
    }

    if (!valores.has(valorTicket)) return false;
  }
  return true;
});
}



// ----------- REGENERAR OPCIONES FILTRADAS (para checkboxes dinámicos) -----------
export function regenerarFiltrosFiltradosDesdeTickets(
  filteredTickets: Ticket[],
  usuariosDisponibles: FiltroString[],
  estadosDisponibles: FiltroString[],
  categoriasDisponibles: FiltroString[] | FiltroNumero[],   // <-- podrían ser numéricas
  descripcionesDisponibles: FiltroString[],
  criticidadesDisponibles: FiltroString[] | FiltroNumero[], // <-- podrían ser numéricas
  departamentosDisponibles: FiltroNumero[],
  subcategoriasDisponibles: FiltroString[] | FiltroNumero[],// <-- podrían ser numéricas
  detallesDisponibles: FiltroString[] | FiltroNumero[],     // <-- podrían ser numéricas
  inventariosDisponibles: FiltroString[],
  sucursalesDisponibles: any[],
  context: any
): void {
  const numericFields = new Set<keyof Ticket | 'departamento' | 'categoria' | 'subcategoria' | 'detalle' | 'criticidad'>([
    'departamento', 'categoria', 'subcategoria', 'detalle', 'criticidad'
  ]);

  const actualizarCampo = (
    campo: keyof Ticket | 'inventario' | 'departamento' | 'sucursal' | 'categoria' | 'subcategoria' | 'detalle' | 'criticidad',
    disponibles: any[],
    filtradasKey: string
  ) => {
    let valoresExistentes: Set<string | number>;

    if (campo === 'inventario') {
      valoresExistentes = new Set(filteredTickets.map(t => t.inventario?.nombre ?? '—'));
    } else if (campo === 'departamento') {
      valoresExistentes = new Set(filteredTickets.map(t => t.departamento_id ?? '—'));
    } else if (campo === 'sucursal') {
      valoresExistentes = new Set(filteredTickets.map(t => (t as any).sucursal ?? '—'));
    } else {
      // Para campos numéricos conservamos el tipo (número), para el resto usamos string
      valoresExistentes = new Set(
        filteredTickets.map(t => {
          const raw = (t as any)[campo];
          if (numericFields.has(campo)) return raw ?? '—';
          return (raw ?? '—').toString();
        })
      );
    }

    context[filtradasKey] = (disponibles || [])
      .filter(opcion => valoresExistentes.has(opcion.valor))
      .map((opcion: any) => ({ ...opcion }));
  };

  actualizarCampo('username', usuariosDisponibles, 'usuariosFiltrados');
  actualizarCampo('estado', estadosDisponibles, 'estadosFiltrados');
  actualizarCampo('categoria', categoriasDisponibles as any[], 'categoriasFiltradas');
  actualizarCampo('descripcion', descripcionesDisponibles, 'descripcionesFiltradas');
  actualizarCampo('criticidad', criticidadesDisponibles as any[], 'criticidadesFiltradas');
  actualizarCampo('departamento', departamentosDisponibles, 'departamentosFiltrados');
  actualizarCampo('subcategoria', subcategoriasDisponibles as any[], 'subcategoriasFiltradas');
  actualizarCampo('detalle', detallesDisponibles as any[], 'detallesFiltrados');
  actualizarCampo('inventario', inventariosDisponibles, 'inventariosFiltrados');
  actualizarCampo('sucursal', sucursalesDisponibles, 'sucursalesFiltradas');
}

// ----------- FUNCIONES VISUALES Y DE SELECCIÓN MULTIPLE -----------

// ¿El filtro de una columna está activo?
export function isFilterActive(ctx: any, columna: string): boolean {
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
    sucursal: 'sucursales'
  };
  const plural = pluralMap[columna] || `${columna}s`;
  const disponibles = ctx[`${plural}Disponibles`];
  if (!Array.isArray(disponibles) || disponibles.length === 0) return false;
  const algunoMarcado = disponibles.some((i: any) => i.seleccionado);
  const algunoDesmarcado = disponibles.some((i: any) => !i.seleccionado);
  if (algunoMarcado && algunoDesmarcado) return true;
  if (columna === 'fecha_creacion') {
    return !!(ctx.rangoFechaCreacionSeleccionado?.start || ctx.rangoFechaCreacionSeleccionado?.end);
  }
  if (columna === 'fecha_en_progreso') return ctx.filtroProgresoActivo;
  if (columna === 'fecha_finalizado') return ctx.filtroFinalizadoActivo;
  return false;
}

// Limpiar filtro de una columna (checkboxes, texto, seleccionar todo)
export function limpiarFiltroColumnaConMapa(component: any, columna: string): void {
  const mapa: {
    [clave: string]: {
      disponibles: string;
      filtradas: string;
      filtroTexto: string;
      seleccionarTodo: string;
    };
  } = {
    username: {
      disponibles: 'usuariosDisponibles',
      filtradas: 'usuariosFiltrados',
      filtroTexto: 'filtroUsuarioTexto',
      seleccionarTodo: 'seleccionarTodoUsuario',
    },
    estado: {
      disponibles: 'estadosDisponibles',
      filtradas: 'estadosFiltrados',
      filtroTexto: 'filtroEstadoTexto',
      seleccionarTodo: 'seleccionarTodoEstado',
    },
    categoria: {
      disponibles: 'categoriasDisponibles',
      filtradas: 'categoriasFiltradas',
      filtroTexto: 'filtroCategoriaTexto',
      seleccionarTodo: 'seleccionarTodoCategoria',
    },
    descripcion: {
      disponibles: 'descripcionesDisponibles',
      filtradas: 'descripcionesFiltradas',
      filtroTexto: 'filtroDescripcionTexto',
      seleccionarTodo: 'seleccionarTodoDescripcion',
    },
    criticidad: {
      disponibles: 'criticidadesDisponibles',
      filtradas: 'criticidadesFiltradas',
      filtroTexto: 'filtroCriticidadTexto',
      seleccionarTodo: 'seleccionarTodoCriticidad',
    },
    departamento: {
      disponibles: 'departamentosDisponibles',
      filtradas: 'departamentosFiltrados',
      filtroTexto: 'filtroDeptoTexto',
      seleccionarTodo: 'seleccionarTodoDepto',
    },
    subcategoria: {
      disponibles: 'subcategoriasDisponibles',
      filtradas: 'subcategoriasFiltradas',
      filtroTexto: 'filtroSubcategoriaTexto',
      seleccionarTodo: 'seleccionarTodoSubcategoria',
    },
    detalle: {
      disponibles: 'detallesDisponibles',
      filtradas: 'detallesFiltrados',
      filtroTexto: 'filtroDetalleTexto',
      seleccionarTodo: 'seleccionarTodoDetalle',
    },
    inventario: {
      disponibles: 'inventariosDisponibles',
      filtradas: 'inventariosFiltrados',
      filtroTexto: 'filtroInventarioTexto',
      seleccionarTodo: 'seleccionarTodoInventario',
    },
    sucursal: {
      disponibles: 'sucursalesDisponibles',
      filtradas: 'sucursalesFiltradas',
      filtroTexto: 'filtroSucursalTexto',
      seleccionarTodo: 'seleccionarTodoSucursal',
},
  };

  const config = mapa[columna];
  if (!config) return;
  component[config.disponibles].forEach((item: any) => item.seleccionado = true);
  component[config.filtradas] = [...component[config.disponibles]];
  component[config.filtroTexto] = '';
  component[config.seleccionarTodo] = false;
}

// Seleccionar/deseleccionar todos los checkboxes visibles (con sincronización)
export function toggleSeleccionarTodoConMapa(component: any, columna: string): void {
  const mapa = {
    categoria: {
      disponibles: 'categoriasDisponibles',
      filtradas: 'categoriasFiltradas',
      seleccionarTodo: 'seleccionarTodoCategoria',
    },
    descripcion: {
      disponibles: 'descripcionesDisponibles',
      filtradas: 'descripcionesFiltradas',
      seleccionarTodo: 'seleccionarTodoDescripcion',
    },
    username: {
      disponibles: 'usuariosDisponibles',
      filtradas: 'usuariosFiltrados',
      seleccionarTodo: 'seleccionarTodoUsuario',
    },
    estado: {
      disponibles: 'estadosDisponibles',
      filtradas: 'estadosFiltrados',
      seleccionarTodo: 'seleccionarTodoEstado',
    },
    criticidad: {
      disponibles: 'criticidadesDisponibles',
      filtradas: 'criticidadesFiltradas',
      seleccionarTodo: 'seleccionarTodoCriticidad',
    },
    departamento: {
      disponibles: 'departamentosDisponibles',
      filtradas: 'departamentosFiltrados',
      seleccionarTodo: 'seleccionarTodoDepto',
    },
    subcategoria: {
      disponibles: 'subcategoriasDisponibles',
      filtradas: 'subcategoriasFiltradas',
      seleccionarTodo: 'seleccionarTodoSubcategoria',
    },
    detalle: {
      disponibles: 'detallesDisponibles',
      filtradas: 'detallesFiltrados',
      seleccionarTodo: 'seleccionarTodoDetalle',
    },
    inventario: {
      disponibles: 'inventariosDisponibles',
      filtradas: 'inventariosFiltrados',
      seleccionarTodo: 'seleccionarTodoInventario',
    },
    sucursal: {
      disponibles: 'sucursalesDisponibles',
      filtradas: 'sucursalesFiltradas',
      seleccionarTodo: 'seleccionarTodoSucursal',
    },
  };

  const entry = mapa[columna as keyof typeof mapa];
  if (!entry) return;
  const visibles = component[entry.filtradas];
  const todosSeleccionados = visibles.every((item: any) => item.seleccionado);
  visibles.forEach((item: any) => item.seleccionado = !todosSeleccionados);
  component[entry.seleccionarTodo] = !todosSeleccionados;
  component[entry.disponibles].forEach((item: any) => {
    const coincide = visibles.find((v: any) => v.valor === item.valor);
    if (coincide) item.seleccionado = coincide.seleccionado;
  });
}

export function todasOpcionesDesmarcadas(opciones: { valor: string, seleccionado: boolean }[]): boolean {
  return opciones.every(opcion => !opcion.seleccionado);
}

export function removeDiacritics(texto: string): string {
  return texto.normalize("NFD").replace(/\p{Diacritic}/gu, "");
}


export function generarOpcionesPorCatalogo(
  tickets: Ticket[],
  campo: keyof Ticket,
  catalogo: { id: number, nombre: string }[]
): FiltroNumero[] {
  // 1. Extrae los IDs únicos usados en los tickets para ese campo
  const idsUnicos = Array.from(new Set(
    tickets
      .map(ticket => ticket[campo])
      .filter(id => id !== null && id !== undefined)
  ));

  // 2. Sólo regresa los elementos del catálogo que SÍ aparecen en los tickets
  return idsUnicos.map(id => {
    const item = catalogo.find(c => c.id === id);
    return {
      valor: id,
      etiqueta: item ? item.nombre : '—',
      seleccionado: true
    };
  });
}

export function generarOpcionesClasificacionDesdeTickets(
  tickets: Ticket[],
  catalogo: { id: number, nombre: string }[]
) {
  // Saca todos los ids de clasificacion que están en tickets
  const idsUnicos = Array.from(new Set(tickets.map(ticket => ticket.clasificacion_id)));
  return idsUnicos.map(id => {
    const item = catalogo.find(c => c.id == id);
    return {
      valor: id,
      etiqueta: item ? item.nombre : '—',
      seleccionado: true
    };
  });
}

export function buscarAncestroNivel(
  clasificacionId: number,
  nivelObjetivo: number,
  catalogo: { id: number, nombre: string, parent_id: number | null, nivel: number }[]
): { id: number, nombre: string } | null {
  let actual = catalogo.find(c => c.id === clasificacionId);
  while (actual && actual.nivel > nivelObjetivo) {
    actual = catalogo.find(c => c.id === actual.parent_id);
  }
  return actual && actual.nivel === nivelObjetivo
    ? { id: actual.id, nombre: actual.nombre }
    : null;
}

// ticket-utils.ts
export function generarOpcionesCategoriasDesdeTickets(
  tickets: Ticket[],
  catalogo: { id: number, nombre: string, nivel: number }[],
  nivel: number
) {
  const idsUnicos = Array.from(new Set(
    tickets.map(ticket => {
      if (nivel === 2) return ticket.categoria_nivel2?.id ?? null;
      if (nivel === 3) return ticket.subcategoria_nivel3?.id ?? null;
      if (nivel === 4) return ticket.detalle_nivel4?.id ?? null;
      return null;
    }).filter(Boolean)
  ));

  return idsUnicos.map(id => {
    const item = catalogo.find(c => c.id === id && c.nivel === nivel);
    return {
      valor: id as number,
      etiqueta: item ? item.nombre : '—',
      seleccionado: true
    };
  });
}


// ----------- NUEVO: tipos de entrada flexibles -----------
export type FiltroValorEntrada = Set<string> | Array<string | number>;
export type FiltrosEntrada = Record<string, FiltroValorEntrada>;

// ----------- NUEVO: normalizador -----------
function normalizaFiltros(filtros: FiltrosEntrada | Record<string, any>): Record<string, Set<string>> {
  const out: Record<string, Set<string>> = {};
  for (const key of Object.keys(filtros || {})) {
    const v = filtros[key];
    if (!v) continue;

    if (v instanceof Set) {
      // ya es Set<string> o Set<algo>
      out[key] = new Set(Array.from(v as Set<any>, (x) => String(x)));
    } else if (Array.isArray(v)) {
      // array de string|number
      out[key] = new Set((v as Array<string | number>).map(String));
    } else {
      // por si acaso: ignora tipos raros
      continue;
    }
  }
  return out;
}
