// src/app/inventario/existencias/existencias.component.ts

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatSelectModule } from '@angular/material/select';
import { FormsModule } from '@angular/forms';
import { InventarioService } from '../../services/inventario.service';

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
  user = JSON.parse(localStorage.getItem('user') || '{}');
  esAdmin = this.user?.rol === 'ADMINISTRADOR';

  sucursales: any[] = [];
  sucursalSeleccionada: number | 'global' = this.user?.sucursal_id || 1;
  existencias: any[] = [];
  displayedColumns: string[] = [
    'id', 'nombre', 'tipo', 'marca', 'proveedor', 'categoria', 'unidad', 'stock', 'sucursal'
  ];

  loading = false;

  constructor(private inventarioService: InventarioService) {}

  ngOnInit(): void {
    if (this.esAdmin) this.cargarSucursales();
    this.cargarExistencias();
  }

  cargarSucursales(): void {
    this.inventarioService.listarSucursales().subscribe({
      next: (data) => {
        this.sucursales = data.filter(
          s => !['corporativo', 'administrador'].includes((s.sucursal || '').toLowerCase())
        );
      },
      error: (err) => console.error('Error al cargar sucursales', err)
    });
  }

  cargarExistencias(): void {
    this.loading = true;
    this.inventarioService.verExistencias().subscribe({
      next: (data) => {
        // Si es admin y selecciona "global", muestra todas
        if (this.esAdmin && this.sucursalSeleccionada === 'global') {
          this.existencias = data;
        } else {
          // Sucursal específica (la del usuario, o la que admin elija)
          const id = this.sucursalSeleccionada === 'global'
            ? this.user?.sucursal_id || 1
            : this.sucursalSeleccionada;
          this.existencias = data.filter((inv: any) => inv.sucursal_id == id);
        }
        this.loading = false;
      },
      error: (err) => {
        this.existencias = [];
        this.loading = false;
        console.error('Error al cargar existencias', err);
      }
    });
  }

  onSucursalChange() {
    this.cargarExistencias();
  }
}
