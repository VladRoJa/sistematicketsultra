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
      if (valores.length === 0) continue;
      const valorTicket = (ticket as any)[clave] ?? '—';
      const valorTicketStr = valorTicket.toString();
      const valoresStr = valores.map(v => v.toString());

      if (!valoresStr.includes(valorTicketStr)) {
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
  const tieneSeleccionados = (lista: any[]) =>
    lista?.some((item: any) => item.seleccionado);

  if (columna === 'username') return tieneSeleccionados(ctx.usuariosDisponibles);
  if (columna === 'estado') return tieneSeleccionados(ctx.estadosDisponibles);
  if (columna === 'categoria') return tieneSeleccionados(ctx.categoriasDisponibles);
  if (columna === 'descripcion') return tieneSeleccionados(ctx.descripcionesDisponibles);
  if (columna === 'criticidad') return tieneSeleccionados(ctx.criticidadesDisponibles);
  if (columna === 'departamento') return tieneSeleccionados(ctx.departamentosDisponibles);
  if (columna === 'subcategoria') return tieneSeleccionados(ctx.subcategoriasDisponibles);
  if (columna === 'subsubcategoria') return tieneSeleccionados(ctx.detallesDisponibles);

  
  if (columna === 'fecha_creacion') {
    return !!(ctx.rangoFechaCreacionSeleccionado?.start && ctx.rangoFechaCreacionSeleccionado?.end);
  }

  if (columna === 'fecha_finalizado') {
    return !!(ctx.rangoFechaFinalSeleccionado?.start && ctx.rangoFechaFinalSeleccionado?.end);
  }

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
  
  export function formatearFechaCorta(fechaString: string | null | undefined): string {
    if (!fechaString || fechaString === 'N/A' || fechaString.trim() === '') {
      return '—'; // O puedes poner "No disponible" si prefieres
    }
    const fecha = new Date(fechaString);
    if (isNaN(fecha.getTime())) {
      console.error("❌ Fecha inválida detectada en formatearFecha:", fechaString);
      return '—'; // Antes ponías "Fecha inválida", mejor regresamos limpio
    }
    return fecha.toLocaleDateString('es-ES', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit'
    });
  }
  
  
  export function parsearFechaDesdeTabla(valor: string): Date | null {
    if (!valor) return null;
  
    try {
      const partes = valor.split(" ");
      const [dia, mes, año] = partes[0].split("-");
      const horaMinuto = partes[1] || "00:00";
      const [hora, minuto] = horaMinuto.split(":");
  
      const fechaISO = `20${año}-${mes}-${dia}T${hora}:${minuto}:00`;
      const fechaFinal = new Date(fechaISO);
  
      return isNaN(fechaFinal.getTime()) ? null : fechaFinal;
    } catch (error) {
      console.error("❌ Error parseando fecha:", valor, error);
      return null;
    }
  }
  

/**
 * Formatea una fecha larga tipo "dd-mm-aa hh:mm" (ajustada a zona horaria local)
 */
export function formatearFecha(fechaString: string | null): string {
  if (!fechaString) return 'Sin finalizar';

  const fecha = new Date(fechaString);

  if (isNaN(fecha.getTime())) {
    console.error("❌ Fecha inválida detectada en formatearFecha:", fechaString);
    return 'Fecha inválida';
  }



  return fecha.toLocaleString('es-ES', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).replace(',', '').replace(/\//g, '-');
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


export function formatearFechaFinalizado(fecha: string): string {
  const tzFecha = new Date(fecha).toLocaleString('en-US', {
    timeZone: 'America/Tijuana'
  });

  const date = new Date(tzFecha);
  const dia = String(date.getDate()).padStart(2, '0');
  const mes = String(date.getMonth() + 1).padStart(2, '0');
  const año = String(date.getFullYear()).slice(-2);
  const hora = String(date.getHours()).padStart(2, '0');
  const minuto = String(date.getMinutes()).padStart(2, '0');

  return `${dia}-${mes}-${año} ${hora}:${minuto}`;
}