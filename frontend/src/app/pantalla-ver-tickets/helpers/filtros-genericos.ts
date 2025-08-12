//frontend-angular\src\app\pantalla-ver-tickets\helpers\filtros-genericos.ts


export function inicializarTemporales(component: any, columna: string): void {
  const aliasPlural: Record<string, string> = {
    descripcion: 'descripciones', username: 'usuarios', estado: 'estados',
    criticidad: 'criticidades', categoria: 'categorias', departamento: 'departamentos',
    subcategoria: 'subcategorias', detalle: 'detalles', inventario: 'inventarios',
    sucursal: 'sucursales'  
  };

  // 👉 alias para la caja de texto
  const aliasFiltroTexto: Record<string, string> = {
    departamento: 'filtroDeptoTexto',
    detalle: 'filtroDetalleTexto',
    inventario: 'filtroInventarioTexto'
  };

  const key = aliasPlural[columna] ?? `${columna}s`;

  // ⬇️ ahora sí resetea la caja correcta
  const filtroProp = aliasFiltroTexto[columna] ?? `filtro${columna[0].toUpperCase() + columna.slice(1)}Texto`;
  component[filtroProp] = '';

const actuales = (component[`${key}Filtradas`] && component[`${key}Filtradas`].length)
  ? component[`${key}Filtradas`]
  : component[`${key}Disponibles`];

component[`${key}Filtradas`] = [...actuales];
component.temporalSeleccionados[columna] = actuales.map((item: any) => ({ ...item }));

}

export function confirmarFiltroColumna(component: any, columna: string): void {
  const pluralMap: Record<string, string> = {
    categoria: 'categorias', descripcion: 'descripciones', username: 'usuarios',
    estado: 'estados', criticidad: 'criticidades', departamento: 'departamentos',
    subcategoria: 'subcategorias', detalle: 'detalles', inventario: 'inventarios',
    sucursal: 'sucursales'
  };

  const plural = pluralMap[columna];
  if (!plural) { console.warn(`❌ columna desconocida '${columna}'`); return; }

  const disponibles = component[`${plural}Disponibles`];
  const temporales = component.temporalSeleccionados[columna];
  if (!disponibles || !temporales) { return; }

  // 1️⃣  sincroniza disponibles
  disponibles.forEach((item: any) => {
    const tmp = temporales.find((t: any) => t.valor === item.valor);
    item.seleccionado = tmp ? tmp.seleccionado : false;
  });

  // 2️⃣  lista completa → filtradas y temporales
  component[`${plural}Filtradas`] = disponibles.map((i: any) => ({ ...i }));
  component.temporalSeleccionados[columna] = disponibles.map((i: any) => ({ ...i }));

  // 3️⃣  aplica filtro global
  component.aplicarFiltroColumna(columna);
}

export function alternarSeleccionTemporal(component: any, columna: string, valor: boolean): void {
  component.temporalSeleccionados[columna]?.forEach((item: any) => item.seleccionado = valor);
}

export function actualizarSeleccionTemporal(component: any, columna: string, index: number, nuevoValor: boolean): void {
  if (component.temporalSeleccionados[columna]) {
    component.temporalSeleccionados[columna][index].seleccionado = nuevoValor;
  }
}

export function isTodoSeleccionado(component: any, columna: string): boolean {
  return component.temporalSeleccionados[columna]?.every((item: any) => item.seleccionado) ?? false;
}

export function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function filtrarPorTextoEnTemporales(component: any, columna: string): void {
  const texto = component[`filtro${capitalizar(columna)}Texto`]?.toLowerCase?.() || '';

  const alias: Record<string, string> = {
    descripcion: 'descripciones',
    username: 'usuarios',
    estado: 'estados',
    criticidad: 'criticidades',
    categoria: 'categorias',
    departamento: 'departamentos',
    subcategoria: 'subcategorias',
    detalle: 'detalles',
    inventario: 'inventarios',
    sucursal: 'sucursales'
  };

  const key = alias[columna] ?? `${columna}s`;

  const originales =
    (component[`${key}Filtradas`] && component[`${key}Filtradas`].length)
      ? component[`${key}Filtradas`]
      : component[`${key}Disponibles`];

  if (!Array.isArray(originales)) return;

  const filtrados = originales.filter((item: any) =>
    (item.etiqueta ?? item.valor ?? '').toString().toLowerCase().includes(texto)
  );

  // ⬅️ Escribe en la colección con alias correcto
  component[`${key}Filtradas`] = filtrados;
  component.temporalSeleccionados[columna] = filtrados.map((item: any) => ({ ...item }));
}

