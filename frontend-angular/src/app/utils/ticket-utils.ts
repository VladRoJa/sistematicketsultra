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
export function filtrarTicketsConFiltros(
  tickets: Ticket[],
  filtros: { [clave: string]: (string | number)[] }
): Ticket[] {
  return tickets.filter(ticket => {
    for (const [clave, valores] of Object.entries(filtros)) {
      if (!valores.length) continue;

      let valorTicket: string | number = '—';
      if (clave === 'inventario') {
        valorTicket = ticket.inventario?.nombre || '—';
      } else if (clave === 'departamento') {
        valorTicket = ticket.departamento_id ?? '—';
      } else {
        valorTicket = (ticket as any)[clave] ?? '—';
      }
      if (!valores.some(v => v == valorTicket)) {
        return false;
      }
    }
    return true;
  });
}

// ----------- REGENERAR OPCIONES FILTRADAS (para checkboxes dinámicos) -----------
export function regenerarFiltrosFiltradosDesdeTickets(
  filteredTickets: Ticket[],
  usuariosDisponibles: FiltroString[],
  estadosDisponibles: FiltroString[],
  categoriasDisponibles: FiltroString[],
  descripcionesDisponibles: FiltroString[],
  criticidadesDisponibles: FiltroString[],
  departamentosDisponibles: FiltroNumero[],
  subcategoriasDisponibles: FiltroString[],
  detallesDisponibles: FiltroString[],
  inventariosDisponibles: FiltroString[],
  context: any
): void {
  const actualizarCampo = (
    campo: keyof Ticket | 'inventario' | 'departamento',
    disponibles: any[],
    filtradasKey: string
  ) => {
    let valoresExistentes: Set<string | number>;
    if (campo === 'inventario') {
      valoresExistentes = new Set(filteredTickets.map(ticket => ticket.inventario?.nombre || '—'));
    } else if (campo === 'departamento') {
      valoresExistentes = new Set(filteredTickets.map(ticket => ticket.departamento_id ?? '—'));
    } else {
      valoresExistentes = new Set(filteredTickets.map(ticket => (ticket[campo] ?? '—').toString()));
    }

    context[filtradasKey] = disponibles
      .filter(opcion => valoresExistentes.has(opcion.valor))
      .map(opcion => ({ ...opcion }));
  };

  actualizarCampo('username', usuariosDisponibles, 'usuariosFiltrados');
  actualizarCampo('estado', estadosDisponibles, 'estadosFiltrados');
  actualizarCampo('categoria', categoriasDisponibles, 'categoriasFiltradas');
  actualizarCampo('descripcion', descripcionesDisponibles, 'descripcionesFiltradas');
  actualizarCampo('criticidad', criticidadesDisponibles, 'criticidadesFiltradas');
  actualizarCampo('departamento', departamentosDisponibles, 'departamentosFiltrados');
  actualizarCampo('subcategoria', subcategoriasDisponibles, 'subcategoriasFiltradas');
  actualizarCampo('detalle', detallesDisponibles, 'detallesFiltrados');
  actualizarCampo('inventario', inventariosDisponibles, 'inventariosFiltrados');
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
    inventario: 'inventarios'
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
    }
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
    }
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

