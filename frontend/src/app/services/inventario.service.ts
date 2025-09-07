// frontend/src/app/services/inventario.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

@Injectable({ providedIn: 'root' })
export class InventarioService {
  private url = `${environment.apiUrl}/inventario`;

  constructor(private http: HttpClient) {}

  // ✅ Ahora puede filtrar por sucursal_id (opcional)
obtenerInventario(opts?: { sucursal_id?: number }): Observable<any[]> {
  let params = new HttpParams();
  if (opts?.sucursal_id) params = params.set('sucursal_id', String(opts.sucursal_id));
  return this.http.get<any[]>(`${this.url}/`, { params });
}

  // (opcional) wrapper para mantener compatibilidad donde lo uses así
  obtenerInventarioPorSucursal(sucursal_id: number): Observable<any[]> {
    return this.obtenerInventario({ sucursal_id });
  }

  obtenerInventarioPorId(id: number): Observable<any> {
    return this.http.get<any>(`${this.url}/${id}`);
  }

  crearInventario(data: any): Observable<any> {
    return this.http.post(`${this.url}/`, data);
  }

  editarInventario(id: number, data: any): Observable<any> {
    return this.http.put(`${this.url}/${id}`, data);
  }

  eliminarInventario(id: number): Observable<any> {
    return this.http.delete(`${this.url}/${id}`);
  }

  buscarInventario(termino: string): Observable<any[]> {
    return this.http.get<any[]>(
      `${this.url}/buscar?nombre=${encodeURIComponent(termino)}`
    );
  }

  listarSucursales(): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/sucursales`);
  }

  verExistencias(): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/existencias`);
  }

  registrarMovimiento(data: any): Observable<any> {
    return this.http.post(`${this.url}/movimientos`, data);
  }

  obtenerMovimientos(): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/movimientos`);
  }

  importarInventario(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post(`${this.url}/importar`, formData);
  }

  descargarPlantilla(): Observable<Blob> {
    return this.http.get(`${this.url}/plantilla`, { responseType: 'blob' });
  }

  exportarInventario(): Observable<Blob> {
    return this.http.get(`${this.url}/exportar`, { responseType: 'blob' });
  }

  listarCategoriasInventario(params?: { parent_id?: number; nivel?: number; nombre?: string }): Observable<any[]> {
  let httpParams = new HttpParams();
  if (params?.parent_id != null) httpParams = httpParams.set('parent_id', String(params.parent_id));
  if (params?.nivel != null)     httpParams = httpParams.set('nivel', String(params.nivel));
  if (params?.nombre)            httpParams = httpParams.set('nombre', params.nombre);
  return this.http.get<any[]>(`${this.url}/categorias-inventario`, { params: httpParams });
}

listarInventarioPorCategoriaYSucursal(params: {
  categoria_inventario_id: number;
  sucursal_id?: number;
}): Observable<any[]> {
  let httpParams = new HttpParams().set(
    'categoria_inventario_id',
    String(params.categoria_inventario_id)
  );
  if (params.sucursal_id != null) {
    httpParams = httpParams.set('sucursal_id', String(params.sucursal_id));
  }
  return this.http.get<any[]>(`${this.url}/`, { params: httpParams });
}


}

