//frontend-angular\src\app\models\inventario.model.ts


export interface Inventario {
  id: number;
  nombre: string;
  descripcion?: string;
  tipo: string;
  marca?: string;
  proveedor?: string;
  categoria?: string;
  unidad?: string;
}