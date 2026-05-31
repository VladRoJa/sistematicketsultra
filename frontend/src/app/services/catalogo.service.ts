// src/app/services/catalogo.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { Observable, throwError } from 'rxjs';
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
  activo?: boolean;
  hijos?: ClasificacionElemento[];
  jerarquia?: string[];
}

@Injectable({
  providedIn: 'root'
})
export class CatalogoService {
  private apiUrl = `${environment.apiUrl}/catalogos`;

  constructor(private http: HttpClient) {}

  // ============================================================================
  // Catálogos planos
  // ============================================================================
  // Estos métodos son seguros para catálogos simples como marcas, proveedores,
  // unidades, grupos musculares y tipos. No deben usarse para acciones delicadas
  // del árbol de clasificaciones de tickets.

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

  // ============================================================================
  // CRUD genérico para catálogos planos
  // ============================================================================
  // Nota importante:
  // Clasificaciones de tickets tiene reglas propias de jerarquía, histórico y
  // activación. Por eso se agregan métodos específicos más abajo.

  crearElemento(catalogo: string, datos: any): Observable<any> {
    return this.http.post(`${this.apiUrl}/${catalogo}`, datos);
  }

  editarElemento(catalogo: string, id: number, datos: any): Observable<any> {
    return this.http.put(`${this.apiUrl}/${catalogo}/${id}`, datos);
  }

  eliminarElemento(catalogo: string, id: number): Observable<any> {
    const catalogoNormalizado = (catalogo || '').trim().toLowerCase();

    // Protección frontend: aunque backend ya bloquea el borrado físico, evitamos
    // que nuevos componentes sigan usando DELETE para clasificaciones de tickets.
    if (catalogoNormalizado === 'clasificaciones') {
      return throwError(() => new Error(
        'No se permite eliminar físicamente clasificaciones de tickets. Usa desactivarClasificacion().'
      ));
    }

    return this.http.delete(`${this.apiUrl}/${catalogo}/${id}`);
  }

  buscarElemento(catalogo: string, termino: string): Observable<CatalogoElemento[]> {
    return this.http
      .get<any>(`${this.apiUrl}/${catalogo}/buscar?q=${encodeURIComponent(termino)}`)
      .pipe(map(res => res.data || []));
  }

  listarElemento(catalogo: string): Observable<CatalogoElemento[]> {
    // Redirección explícita para categorías de inventario.
    // Evita confundirlas con catalogo_clasificacion, que pertenece a tickets.
    if (catalogo === 'categorias') {
      return this.http
        .get<{ data: CatalogoElemento[] }>(`${environment.apiUrl}/catalogos/inventario/categorias`)
        .pipe(map(resp => resp.data ?? []));
    }

    return this.http
      .get<any>(`${this.apiUrl}/${catalogo}`)
      .pipe(map(res => res.data || []));
  }

  importarArchivo(catalogo: string, file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post(`${this.apiUrl}/${catalogo}/importar`, formData);
  }

  exportarArchivo(catalogo: string): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/${catalogo}/exportar`, { responseType: 'blob' });
  }

  // ============================================================================
  // Clasificaciones de tickets
  // ============================================================================
  // Fuente única: catalogo_clasificacion.
  // Estas funciones administran el árbol usado al crear tickets.
  // No se debe borrar físicamente: se desactiva/reactiva para conservar histórico.

  getClasificacionesArbol(
    departamentoId?: number,
    includeInactive = false
  ): Observable<ClasificacionElemento[]> {
    const params: string[] = [];

    if (departamentoId) {
      params.push(`departamento_id=${departamentoId}`);
    }

    if (includeInactive) {
      params.push('include_inactive=true');
    }

    const query = params.length ? `?${params.join('&')}` : '';

    return this.http
      .get<any>(`${this.apiUrl}/clasificaciones/arbol${query}`)
      .pipe(map(res => res.data || []));
  }

  getClasificacionesPlanas(
    departamentoId?: number,
    parentId?: number,
    includeInactive = false
  ): Observable<ClasificacionElemento[]> {
    const params: string[] = [];

    if (departamentoId) {
      params.push(`departamento_id=${departamentoId}`);
    }

    if (parentId) {
      params.push(`parent_id=${parentId}`);
    }

    if (includeInactive) {
      params.push('include_inactive=true');
    }

    const query = params.length ? `?${params.join('&')}` : '';

    return this.http
      .get<any>(`${this.apiUrl}/clasificaciones${query}`)
      .pipe(map(res => res.data || []));
  }

  crearClasificacion(datos: {
    nombre: string;
    departamento_id: number;
    parent_id?: number | null;
  }): Observable<any> {
    return this.http.post(`${this.apiUrl}/clasificaciones`, datos);
  }

  editarClasificacion(
    id: number,
    datos: {
      nombre: string;
    }
  ): Observable<any> {
    return this.http.put(`${this.apiUrl}/clasificaciones/${id}`, datos);
  }

  desactivarClasificacion(id: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/clasificaciones/${id}/desactivar`, {});
  }

  reactivarClasificacion(id: number): Observable<any> {
    return this.http.post(`${this.apiUrl}/clasificaciones/${id}/reactivar`, {});
  }
}