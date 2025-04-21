// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\reportes\reportes.component.ts

import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-reportes',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule
  ],
  templateUrl: './reportes.component.html',
})
export class ReportesComponent {
  constructor(private http: HttpClient) {}

  descargarInventario() {
    this.http.get('http://localhost:5000/api/reportes/exportar-inventario', {
      responseType: 'blob'
    }).subscribe(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'inventario.xlsx';
      a.click();
    });
  }

  descargarMovimientos() {
    this.http.get('http://localhost:5000/api/reportes/exportar-movimientos', {
      responseType: 'blob'
    }).subscribe(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'movimientos.xlsx';
      a.click();
    });
  }
}
