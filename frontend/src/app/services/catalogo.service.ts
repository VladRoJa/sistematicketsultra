// src/app/services/catalogo.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface CatalogoElemento {
  id: number;
  nombre: string;
  abreviatura?: string; // Para unidades de medida
}

export interface ClasificacionElemento extends CatalogoElemento {
  parent_id?: number | null;
  departamento_id?: number;
  nivel?: number;
  hijos?: ClasificacionElemento[];
  jerarquia?: string[];
}

@Injectable({
  providedIn: 'root'
})
export class CatalogoService {
  private apiUrl = `${environment.apiUrl}/catalogos`;

  constructor(private http: HttpClient) {}

  // ---- Métodos para catálogos planos ----

  getProveedores(): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/proveedores`)
      .pipe(map(res => res.data || []));
  }
  getMarcas(): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/marcas`)
      .pipe(map(res => res.data || []));
  }
  getCategorias(): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/categorias`)
      .pipe(map(res => res.data || []));
  }
  getUnidades(): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/unidades`)
      .pipe(map(res => res.data || []));
  }
  getGrupoMuscular(): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/gruposmusculares`)
      .pipe(map(res => res.data || []));
  }
  getTiposInventario(): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/tipos`)
      .pipe(map(res => res.data || []));
  }

  getCategoriasInventario(): Observable<CatalogoElemento[]> {
    return this.http
      .get<{ data: CatalogoElemento[] }>(`${environment.apiUrl}/catalogos/inventario/categorias`)
      .pipe(map(resp => resp.data ?? []));
  }

  // ---- CRUD genérico para todos los catálogos planos ----

  crearElemento(catalogo: string, datos: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/${catalogo}`, datos);
  }
  editarElemento(catalogo: string, id: number, datos: any): Observable<any> {
    return this.http.put(`${this.apiUrl}/${catalogo}/${id}`, datos);
  }
  eliminarElemento(catalogo: string, id: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/${catalogo}/${id}`);
  }
  buscarElemento(catalogo: string, termino: string): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/${catalogo}/buscar?nombre=${encodeURIComponent(termino)}`)
      .pipe(map(res => res.data || []));
  }
  listarElemento(catalogo: string): Observable<CatalogoElemento[]> {
    return this.http.get<any>(`${this.apiUrl}/${catalogo}`)
      .pipe(map(res => res.data || []));
  }
  importarArchivo(catalogo: string, file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post(`${this.apiUrl}/${catalogo}/importar`, formData);
  }
  exportarArchivo(catalogo: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/${catalogo}/exportar`, { responseType: 'blob' });
  }

  // ---- Métodos ESPECÍFICOS para clasificaciones jerárquicas ----

  // Obtener árbol completo por departamento
getClasificacionesArbol(departamentoId?: number): Observable<any[]> {
  let url = `${this.apiUrl}/clasificaciones/arbol`;
  if (departamentoId) url += `?departamento_id=${departamentoId}`;
  return this.http.get<any>(url).pipe(map(res => res.data || []));
}


  // Obtener clasificación plana por departamento (útil para selects)
getClasificacionesPlanas(departamentoId?: number, parentId?: number): Observable<any[]> {
  let url = `${this.apiUrl}/clasificaciones`;
  const params = [];
  if (departamentoId) params.push(`departamento_id=${departamentoId}`);
  if (parentId) params.push(`parent_id=${parentId}`);
  if (params.length) url += '?' + params.join('&');
  return this.http.get<any>(url).pipe(map(res => res.data || []));
}

}
