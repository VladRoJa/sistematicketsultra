// src/app/utils/tabla-filtros.helper.ts

export interface FiltroColumna {
  nombre: string;
  texto: string;
  opciones: { valor: string, seleccionado: boolean }[];
  temporales: { valor: string, seleccionado: boolean }[];
}

// Inicializa filtros para cada columna
export function inicializarFiltros(tabla: any[], columnas: string[]): Record<string, FiltroColumna> {
  const filtros: Record<string, FiltroColumna> = {};

  columnas.forEach(col => {
    const valoresUnicos = Array.from(new Set(tabla.map(row => String(row[col] ?? '')).filter(x => x !== '')));
    const opciones = valoresUnicos.map(v => ({ valor: v, seleccionado: true }));
    filtros[col] = {
      nombre: col,
      texto: '',
      opciones,
      temporales: [...opciones]
    };
  });

  return filtros;
}

// Opciones temporales filtradas por texto de búsqueda
export function obtenerOpcionesVisibles(filtro: FiltroColumna) {
  const texto = (filtro.texto || '').toLowerCase();
  return filtro.temporales.filter(o => o.valor.toLowerCase().includes(texto));
}

// Seleccionar/deseleccionar todos los checkboxes visibles
export function alternarSeleccionTemporal(filtro: FiltroColumna, valor: boolean): void {
  filtro.temporales.forEach(op => op.seleccionado = valor);
}

// Confirmar selección: aplica lo temporal al global
export function confirmarSeleccion(filtro: FiltroColumna): void {
  filtro.opciones.forEach(o => {
    const temp = filtro.temporales.find(t => t.valor === o.valor);
    o.seleccionado = temp ? temp.seleccionado : false;
  });
  filtro.temporales = filtro.opciones.map(o => ({ ...o }));
}

// Filtrar la tabla completa usando los filtros activos
export function filtrarTabla(tabla: any[], filtros: Record<string, FiltroColumna>): any[] {
  return tabla.filter(row => {
    return Object.values(filtros).every(f => {
      const seleccionadas = f.opciones.filter(o => o.seleccionado).map(o => o.valor);
      if (seleccionadas.length === f.opciones.length) return true; // no hay filtro activo
      return seleccionadas.includes(row[f.nombre]);
    });
  });
}
