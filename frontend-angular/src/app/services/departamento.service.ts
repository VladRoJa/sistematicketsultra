//departamento.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class DepartamentoService {
  private departamentos = [
    { id: 1, nombre: 'Mantenimiento' },
    { id: 2, nombre: 'Finanzas' },
    { id: 3, nombre: 'Marketing' },
    { id: 4, nombre: 'Gerencia Deportiva' },
    { id: 5, nombre: 'Recursos Humanos' },
    { id: 6, nombre: 'Compras' },
    { id: 7, nombre: 'Sistemas' }
  ];

  private apiUrl = 'http://localhost:5000/api/departamentos'; // Reemplaza con la URL de tu API

  constructor(private http: HttpClient) { }

  obtenerDepartamentos(): Observable<any> {
    const token = localStorage.getItem('token'); // 🔹 Recupera el token del almacenamiento local
    if (!token) {
      console.error("❌ No hay token, no se puede hacer la solicitud");
      return new Observable(observer => {
        observer.error("No hay token disponible");
      });
    }

    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

    return this.http.get<any>(`${this.apiUrl}/listar`, { headers }); // 🔹 Ahora se envía el token en la solicitud
  }


  obtenerNombrePorId(id: number): string {
    const depto = this.departamentos.find(d => d.id === id);
    return depto ? depto.nombre : 'Desconocido';
  }
}
