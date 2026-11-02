/**
 * Identidad de clase de inventario para filtros de UI.
 * No altera códigos, IDs, ni registros históricos.
 */
export function normalizarTipoInventario(tipo: unknown): string {
  const valor = String(tipo ?? '').trim().toLowerCase();
  if (valor === 'aparato' || valor === 'aparatos') return 'aparatos';
  if (['sistema', 'sistemas', 'dispositivo', 'dispositivos'].includes(valor)) {
    return 'dispositivos';
  }
  return valor;
}
