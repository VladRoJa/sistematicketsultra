export interface Inventario {
  id: number;
  tipo?: string;
  nombre: string;
  descripcion?: string;
  marca?: string;
  proveedor?: string;
  categoria?: string;
  subcategoria?: string;
  unidad?: string;
  unidad_medida?: string;
  unidad_compra?: string;
  factor_compra?: number;
  codigo_interno?: string;
  no_equipo?: string;
  gasto_sem?: number | null;
  gasto_mes?: number | null;
  pedido_mes?: number | null;
  semana_pedido?: string;
  fecha_inventario?: string | null;
  grupo_muscular?: string;
  stock?: number;
  categoria_inventario_id?: number | null;
  familia_equipo_id?: number | null;
  familia_equipo?: unknown;
  [key: string]: any;
}
