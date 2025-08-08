//frontend-angular\src\app\helpers\inventario\registrar-movimiento.helper.ts


import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export interface MovimientoPayload {
  tipo_movimiento: string;
  usuario_id: number;
  sucursal_id: number;
  observaciones?: string;
  ticket_id?: number;
  inventarios: {
    inventario_id: number;
    cantidad: number;
    unidad_medida?: string;
  }[];
}

export function registrarMovimiento(http: HttpClient, payload: MovimientoPayload) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders()
    .set("Authorization", `Bearer ${token}`)
    .set("Content-Type", "application/json");

  return http.post(`${environment.apiUrl}/inventario/movimientos`, payload, { headers });
}
