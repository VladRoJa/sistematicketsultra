// src/app/inventario/existencias/existencias.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatSelectModule } from '@angular/material/select';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-existencias',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule,
    MatSelectModule,
    FormsModule
  ],
  templateUrl: './existencias.component.html',
})
export class ExistenciasComponent implements OnInit {
  private http = inject(HttpClient);

  user = JSON.parse(localStorage.getItem('user') || '{}');
  esAdmin = this.user?.rol === 'ADMINISTRADOR';

  sucursales: any[] = [];
  sucursalesFiltradas: any[] = [];

  sucursalSeleccionada: number | 'global' = this.user?.id_sucursal || 1;
  existencias: any[] = [];

  ngOnInit(): void {
    if (this.esAdmin) this.cargarSucursales();
    this.cargarExistencias(this.sucursalSeleccionada);
  }

  cargarSucursales(): void {
    this.http.get<any[]>('http://localhost:5000/api/sucursales/listar')
      .subscribe({
        next: (data) => {
          // Filtramos antes de asignar
          this.sucursales = data;
          this.sucursalesFiltradas = data.filter(
            s => !['corporativo', 'administrador'].includes(s.sucursal.toLowerCase())
          );
        },
        error: (err) => console.error('Error al cargar sucursales', err)
      });
  }

  cargarExistencias(sucursal_id: number | 'global'): void {
    const url = (sucursal_id === 'global')
      ? 'http://localhost:5000/api/inventario/stock-total'
      : `http://localhost:5000/api/inventario/sucursal/${sucursal_id}`;

    this.http.get<any[]>(url).subscribe({
      next: (data) => this.existencias = data,
      error: (err) => console.error('Error al cargar existencias', err)
    });
  }
}

