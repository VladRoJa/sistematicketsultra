import { Injectable } from '@angular/core';

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

  obtenerDepartamentos() {
    return this.departamentos;
  }

  obtenerNombrePorId(id: number): string {
    const depto = this.departamentos.find(d => d.id === id);
    return depto ? depto.nombre : 'Desconocido';
  }
}
