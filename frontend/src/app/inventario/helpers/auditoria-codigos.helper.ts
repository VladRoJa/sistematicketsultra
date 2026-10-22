import type { Inventario } from '../../models/inventario.model';

export interface GrupoCodigoDuplicado {
  codigo: string;
  registros: Inventario[];
}

/**
 * Auditoría de solo lectura del catálogo maestro ya autorizado por el backend.
 * Equivale a GROUP BY UPPER(TRIM(codigo_interno)) con HAVING COUNT(*) > 1.
 * No depende del filtro visual y no escribe en la base.
 */
export function detectarCodigosDuplicados(
  inventarios: readonly Inventario[],
): GrupoCodigoDuplicado[] {
  const grupos = new Map<string, Inventario[]>();

  for (const articulo of inventarios) {
    const codigo = String(articulo.codigo_interno ?? '').trim().toUpperCase();
    if (!codigo) {
      continue;
    }

    const registros = grupos.get(codigo) ?? [];
    registros.push(articulo);
    grupos.set(codigo, registros);
  }

  return [...grupos.entries()]
    .filter(([, registros]) => registros.length > 1)
    .map(([codigo, registros]) => ({
      codigo,
      registros: [...registros].sort((a, b) => a.id - b.id),
    }))
    .sort((a, b) => a.codigo.localeCompare(b.codigo));
}
