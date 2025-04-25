//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\services\productos.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ProductosService {
  private url = 'http://localhost:5000/api/inventario/productos';

  constructor(private http: HttpClient) {}

  obtenerProductos(): Observable<any[]> {
    return this.http.get<any[]>(this.url);
  }
}
