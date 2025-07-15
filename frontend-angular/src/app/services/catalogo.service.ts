// src/app/services/catalogo.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { Observable } from 'rxjs';

// Puedes definir interfaces si gustas
export interface CatalogoElemento {
  id: number;
  nombre: string;
  abreviatura?: string; // Para unidades de medida
}

@Injectable({
  providedIn: 'root'
})
export class CatalogoService {
  private apiUrl = `${environment.apiUrl}/catalogos`;

  constructor(private http: HttpClient) {}

  // ---- GETTERS GENERALES PARA CADA CATÁLOGO ----

  getProveedores(): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/proveedores`);
  }

  getMarcas(): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/marcas`);
  }

  getCategorias(): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/categorias`);
  }

  getUnidades(): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/unidades`);
  }

    getGrupoMucular(): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/gruposmusculares`);
  }

    getTiposInventario(): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/tipos`);
  }

  // ---- CRUD GENÉRICO PARA TODOS LOS CATÁLOGOS ----

  crearElemento(catalogo: string, nombre: string, abreviatura?: string): Observable<any> {
    // Abreviatura solo aplica a unidades de medida
    const body: any = { nombre };
    if (abreviatura) body.abreviatura = abreviatura;
    return this.http.post(`${this.apiUrl}/${catalogo}`, body);
  }

  editarElemento(catalogo: string, id: number, nombre: string, abreviatura?: string): Observable<any> {
    const body: any = { nombre };
    if (abreviatura) body.abreviatura = abreviatura;
    return this.http.put(`${this.apiUrl}/${catalogo}/${id}`, body);
  }

  eliminarElemento(catalogo: string, id: number): Observable<any> {
    return this.http.delete(`${this.apiUrl}/${catalogo}/${id}`);
  }

  buscarElemento(catalogo: string, termino: string): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/${catalogo}/buscar?nombre=${encodeURIComponent(termino)}`);
  }

  listarElemento(catalogo: string): Observable<CatalogoElemento[]> {
    return this.http.get<CatalogoElemento[]>(`${this.apiUrl}/${catalogo}`);
}
}
