//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\productos\productos.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';

@Component({
  selector: 'app-productos',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule
  ],
  templateUrl: './productos.component.html',
})
export class ProductosComponent implements OnInit {
  private http = inject(HttpClient);

  productos: any[] = [];

  ngOnInit(): void {
    this.cargarProductos();
  }

  cargarProductos(): void {
    this.http.get<any[]>('http://localhost:5000/api/inventario/productos')
      .subscribe({
        next: (data) => {
          this.productos = data;
        },
        error: (error) => {
          console.error('Error al cargar productos', error);
        }
      });
  }
}
