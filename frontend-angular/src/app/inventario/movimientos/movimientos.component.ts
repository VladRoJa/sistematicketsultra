//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\movimientos\movimientos.component.ts


import { Component, OnInit, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';

@Component({
  selector: 'app-movimientos',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule
  ],
  templateUrl: './movimientos.component.html',
})
export class MovimientosComponent implements OnInit {
  private http = inject(HttpClient);

  movimientos: any[] = [];

  ngOnInit(): void {
    this.cargarMovimientos();
  }

  cargarMovimientos(): void {
    this.http.get<any[]>('http://localhost:5000/api/inventario/movimientos')
      .subscribe({
        next: (data) => {
          this.movimientos = data;
        },
        error: (error) => {
          console.error('Error al cargar movimientos', error);
        }
      });
  }
}
