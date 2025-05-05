//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\services\productos.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment'; 

@Injectable({ providedIn: 'root' })
export class ProductosService {
  private url = `${environment.apiUrl}/inventario/productos`;

  constructor(private http: HttpClient) {}

  obtenerProductos(): Observable<any[]> {
    return this.http.get<any[]>(this.url);
  }
}
