// frontend\src\app\services\inventario.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

@Injectable({ providedIn: 'root' })
export class InventarioService {
  private url = `${environment.apiUrl}/inventario`;

  constructor(private http: HttpClient) {}

  // Obtener todos los registros de inventario
  obtenerInventario(): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/`);
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
    return this.http.get<any[]>(`${this.url}/buscar?nombre=${encodeURIComponent(termino)}`);
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

  obtenerInventarioPorSucursal(sucursal_id: number): Observable<any[]> {
  return this.http.get<any[]>(`${this.url}?sucursal_id=${sucursal_id}`);
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



}

