// src/app/utils/ticket-utils.ts

import { Ticket } from '../pantalla-ver-tickets/pantalla-ver-tickets.component';

type Filtro = { valor: string; seleccionado: boolean };

export function getFiltrosActivosFrom(
  usuarios: Filtro[],
  estados: Filtro[],
  categorias: Filtro[],
  descripciones: Filtro[],
  criticidades: Filtro[],
  departamentos: Filtro[],
  subcategorias: Filtro[],
  detalles: Filtro[]
): { [clave: string]: string[] } {
  return {
    username: usuarios.filter(i => i.seleccionado).map(i => i.valor),
    estado: estados.filter(i => i.seleccionado).map(i => i.valor),
    categoria: categorias.filter(i => i.seleccionado).map(i => i.valor),
    descripcion: descripciones.filter(i => i.seleccionado).map(i => i.valor),
    criticidad: criticidades.filter(i => i.seleccionado).map(i => i.valor),
    departamento: departamentos.filter(i => i.seleccionado).map(i => i.valor),
    subcategoria: subcategorias.filter(i => i.seleccionado).map(i => i.valor),
    subsubcategoria: detalles.filter(i => i.seleccionado).map(i => i.valor),
  };
}

export function filtrarTicketsConFiltros(tickets: Ticket[], filtros: { [clave: string]: string[] }): Ticket[] {
  return tickets.filter(ticket => {
    for (const [clave, valores] of Object.entries(filtros)) {
      if (valores.length === 0) continue;
      const valorTicket = (ticket as any)[clave] ?? '—';
      if (!valores.includes(valorTicket.toString())) {
        return false;
      }
    }
    return true;
  });
}

export function actualizarFiltrosCruzados(
  filteredTickets: Ticket[],
  usuarios: Filtro[],
  estados: Filtro[],
  categorias: Filtro[],
  descripciones: Filtro[],
  criticidades: Filtro[],
  departamentos: Filtro[],
  subcategorias: Filtro[],
  detalles: Filtro[],
  context: any
): void {
  const actualizar = (
    campo: string,
    disponibles: Filtro[]
  ) => {
    const valoresUnicos = new Set(
      filteredTickets.map(t => ((t as any)[campo] ?? '—').toString())
    );

    const nuevosValores: Filtro[] = Array.from(valoresUnicos).map(valor => {
      const original = disponibles.find(i => i.valor === valor);
      return {
        valor,
        seleccionado: original?.seleccionado || false
      };
    });

    context[`${campo}Filtrados`] = nuevosValores;
  };

  actualizar('username', usuarios);
  actualizar('estado', estados);
  actualizar('categoria', categorias);
  actualizar('descripcion', descripciones);
  actualizar('criticidad', criticidades);
  actualizar('departamento', departamentos);
  actualizar('subcategoria', subcategorias);
  actualizar('subsubcategoria', detalles);
}

export function isFilterActive(ctx: any, columna: string): boolean {
  const disponibles = ctx[`${columna}Disponibles`];
  return Array.isArray(disponibles) && disponibles.some((item: Filtro) => item.seleccionado);
}

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
      subsubcategoria: {
        disponibles: 'detallesDisponibles',
        filtradas: 'detallesFiltrados',
        filtroTexto: 'filtroDetalleTexto',
        seleccionarTodo: 'seleccionarTodoDetalle',
      }
    };
  
    const config = mapa[columna];
    if (!config) return;
  
    component[config.disponibles].forEach((item: any) => item.seleccionado = false);
    component[config.filtradas] = [...component[config.disponibles]];
    component[config.filtroTexto] = '';
    component[config.seleccionarTodo] = false;
  }

  
  export function removeDiacritics(texto: string): string {
    return texto.normalize("NFD").replace(/\p{Diacritic}/gu, "");
  }

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
      subsubcategoria: {
        disponibles: 'detallesDisponibles',
        filtradas: 'detallesFiltrados',
        seleccionarTodo: 'seleccionarTodoDetalle',
      },
    };
  
    const entry = mapa[columna as keyof typeof mapa];
    if (!entry) return;
  
    const seleccionarTodo = !component[entry.seleccionarTodo];
    component[entry.seleccionarTodo] = seleccionarTodo;
  
    // Aplicar selección a elementos visibles (filtrados)
    component[entry.filtradas].forEach((item: any) => item.seleccionado = seleccionarTodo);
  
    // Sincronizar con los disponibles
    component[entry.disponibles].forEach((item: any) => {
      const filtrado = component[entry.filtradas].find((f: any) => f.valor === item.valor);
      if (filtrado) {
        item.seleccionado = filtrado.seleccionado;
      }
    });
  }
  