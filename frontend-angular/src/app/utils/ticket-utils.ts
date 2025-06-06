// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\utils\ticket-utils.ts

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
      if (!valores.length) continue;

      const valorTicket = (ticket as any)[clave] ?? '—';
      const valorTicketNormalizado = removeDiacritics(valorTicket.toString().trim().toLowerCase());

      const valoresNormalizados = valores.map(v => removeDiacritics(v.toString().trim().toLowerCase()));

      if (!valoresNormalizados.includes(valorTicketNormalizado)) {
        return false;
      }
    }
    return true;
  });
}


// utils/ticket-utils.ts
export function regenerarFiltrosFiltradosDesdeTickets(


  filteredTickets: Ticket[],
  usuariosDisponibles: { valor: string, seleccionado: boolean }[],
  estadosDisponibles: { valor: string, seleccionado: boolean }[],
  categoriasDisponibles: { valor: string, seleccionado: boolean }[],
  descripcionesDisponibles: { valor: string, seleccionado: boolean }[],
  criticidadesDisponibles: { valor: string, seleccionado: boolean }[],
  departamentosDisponibles: { valor: string, seleccionado: boolean }[],
  subcategoriasDisponibles: { valor: string, seleccionado: boolean }[],
  detallesDisponibles: { valor: string, seleccionado: boolean }[],
  context: any
): void {
  const actualizarCampo = (
    campo: keyof Ticket,
    disponibles: { valor: string, seleccionado: boolean }[],
    filtradasKey: string
  ) => {
    const valoresExistentes = new Set(  
      filteredTickets.map(ticket => (ticket[campo] ?? '—').toString())
    );

    const nuevasOpciones = disponibles
      .filter(opcion => valoresExistentes.has(opcion.valor))
      .map(opcion => ({
        valor: opcion.valor,
        seleccionado: opcion.seleccionado
      }));

    context[filtradasKey] = nuevasOpciones;
  };

  actualizarCampo('username', usuariosDisponibles, 'usuariosFiltrados');
  actualizarCampo('estado', estadosDisponibles, 'estadosFiltrados');
  actualizarCampo('categoria', categoriasDisponibles, 'categoriasFiltradas');
  actualizarCampo('descripcion', descripcionesDisponibles, 'descripcionesFiltradas');
  actualizarCampo('criticidad', criticidadesDisponibles, 'criticidadesFiltradas');
  actualizarCampo('departamento', departamentosDisponibles, 'departamentosFiltrados');
  actualizarCampo('subcategoria', subcategoriasDisponibles, 'subcategoriasFiltradas');
  actualizarCampo('subsubcategoria', detallesDisponibles, 'detallesFiltrados');
}



export function isFilterActive(ctx: any, columna: string): boolean {
  const pluralMap: Record<string, string> = {
    categoria: 'categorias',
    descripcion: 'descripciones',
    username: 'usuarios',
    estado: 'estados',
    criticidad: 'criticidades',
    departamento: 'departamentos',
    subcategoria: 'subcategorias',
    subsubcategoria: 'detalles'
  };

  const plural = pluralMap[columna] || `${columna}s`;
  const disponibles = ctx[`${plural}Disponibles`];

  // Si no hay disponibles aún, no hay filtro activo
  if (!Array.isArray(disponibles) || disponibles.length === 0) return false;

  // Si hay al menos un ítem desmarcado y otro marcado, el filtro está activo
  const algunoMarcado = disponibles.some((i: any) => i.seleccionado);
  const algunoDesmarcado = disponibles.some((i: any) => !i.seleccionado);

  if (algunoMarcado && algunoDesmarcado) return true;

  // Casos especiales para fechas
  if (columna === 'fecha_creacion') {
    return !!(ctx.rangoFechaCreacionSeleccionado?.start || ctx.rangoFechaCreacionSeleccionado?.end);
  }
  if (columna === 'fecha_en_progreso') return ctx.filtroProgresoActivo;
  if (columna === 'fecha_finalizado') return ctx.filtroFinalizadoActivo;

  return false;
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
  
    component[config.disponibles].forEach((item: any) => item.seleccionado = true);
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

  const visibles = component[entry.filtradas];
  const todosSeleccionados = visibles.every((item: any) => item.seleccionado);

  visibles.forEach((item: any) => item.seleccionado = !todosSeleccionados);
  component[entry.seleccionarTodo] = !todosSeleccionados;

  // También sincronizamos los "disponibles" en base a los "filtrados"
  component[entry.disponibles].forEach((item: any) => {
    const coincide = visibles.find((v: any) => v.valor === item.valor);
    if (coincide) {
      item.seleccionado = coincide.seleccionado;
    }
  });
}


export function todasOpcionesDesmarcadas(opciones: { valor: string, seleccionado: boolean }[]): boolean {
  return opciones.every(opcion => !opcion.seleccionado);
}


export function generarOpcionesDisponiblesDesdeTickets(tickets: Ticket[], campo: keyof Ticket): { valor: string, seleccionado: boolean }[] {
  const valoresUnicos = Array.from(new Set(tickets.map(ticket => (ticket[campo] ?? '—').toString())));
  return valoresUnicos.map(valor => ({
    valor,
    seleccionado: false
  }));
}



