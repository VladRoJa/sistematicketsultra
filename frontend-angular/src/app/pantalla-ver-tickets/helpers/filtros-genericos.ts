// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\filtros-genericos.ts

/**
 * Inicializa las opciones temporales copiando el estado actual de selección de las disponibles.
 */


export function inicializarTemporales(component: any, columna: string): void {
  const aliasPlural: Record<string,string> = {
    descripcion:'descripciones', username:'usuarios', estado:'estados',
    criticidad:'criticidades', categoria:'categorias', departamento:'departamentos',
    subcategoria:'subcategorias', subsubcategoria:'detalles'
  };

  // 👉 alias para la caja de texto
  const aliasFiltroTexto: Record<string,string> = {
    departamento:'filtroDeptoTexto',
    subsubcategoria:'filtroDetalleTexto'
  };

  const key = aliasPlural[columna] ?? `${columna}s`;

  // ⬇️ ahora sí resetea la caja correcta
  const filtroProp = aliasFiltroTexto[columna] ?? `filtro${columna[0].toUpperCase()+columna.slice(1)}Texto`;
  component[filtroProp] = '';

  component[`${key}Filtradas`] = component[`${key}Disponibles`];

  component.temporalSeleccionados[columna] =
    component[`${key}Filtradas`].map((item: any) => ({ ...item }));
}






/** Confirma la selección temporal, sincroniza disponibles/filtradas y aplica el filtro */
export function confirmarFiltroColumna(component: any, columna: string): void {
  const pluralMap: Record<string,string> = {
    categoria:'categorias', descripcion:'descripciones', username:'usuarios',
    estado:'estados', criticidad:'criticidades', departamento:'departamentos',
    subcategoria:'subcategorias', subsubcategoria:'detalles'
  };

  const plural = pluralMap[columna];
  if (!plural) { console.warn(`❌ columna desconocida '${columna}'`); return; }

  const disponibles = component[`${plural}Disponibles`];
  const temporales  = component.temporalSeleccionados[columna];
  if (!disponibles || !temporales) { return; }

  // 1️⃣  sincroniza disponibles
  disponibles.forEach((item: any) => {
    const tmp = temporales.find((t: any) => t.valor === item.valor);
    item.seleccionado = tmp ? tmp.seleccionado : false;
  });

  // 2️⃣  lista completa → filtradas y temporales
  component[`${plural}Filtradas`]          = disponibles.map((i:any)=>({...i}));
  component.temporalSeleccionados[columna] = disponibles.map((i:any)=>({...i}));

  // 3️⃣  aplica filtro global
  component.aplicarFiltroColumna(columna);
}




/**
 * Marca o desmarca todos los temporales de una columna.
 */
export function alternarSeleccionTemporal(component: any, columna: string, valor: boolean): void {
  component.temporalSeleccionados[columna]?.forEach((item: any) => item.seleccionado = valor);
}

/**
 * Marca un solo ítem temporal por índice.
 */
export function actualizarSeleccionTemporal(component: any, columna: string, index: number, nuevoValor: boolean): void {
  if (component.temporalSeleccionados[columna]) {
    component.temporalSeleccionados[columna][index].seleccionado = nuevoValor;
  }
}

/**
 * Evalúa si todos los ítems temporales están seleccionados.
 */
export function isTodoSeleccionado(component: any, columna: string): boolean {
  return component.temporalSeleccionados[columna]?.every((item: any) => item.seleccionado) ?? false;
}

/**
 * Capitaliza una cadena para acceder dinámicamente a nombres de variables.
 */
export function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}



/**
 * Filtra las opciones temporales de una columna basado en el texto del input asociado.
 */
export function filtrarPorTextoEnTemporales(component: any, columna: string): void {
  const textoFiltro = component[`filtro${capitalizar(columna)}Texto`]?.toLowerCase?.() || '';
  const originales = component[`${columna}sDisponibles`];
  

  if (!Array.isArray(originales)) return;

  // Filtrar en base al texto
  const filtrados = originales.filter((item: any) =>
    item.valor?.toLowerCase().includes(textoFiltro)
  );
  component[`${columna}sFiltradas`] = filtrados; 
  component.temporalSeleccionados[columna] = filtrados.map((item: any) => ({
    ...item
  }));
}


