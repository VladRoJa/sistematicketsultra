// src/app/inventario/reportes/reportes.component.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { environment } from 'src/environments/environment';
import { mostrarAlertaToast } from 'src/app/utils/alertas';

@Component({
  selector: 'app-reportes',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    FormsModule,
  ],
  templateUrl: './reportes.component.html',
  styleUrls: ['./reportes.component.css'],
})
export class ReportesComponent implements OnInit {
  esAdmin = true; // Cambia a tu lógica real de permisos
  sucursales: any[] = [];
  sucursalSeleccionada: number | null = null; // null es 'Todas'

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.cargarSucursales();
  }

  cargarSucursales() {
    const token = localStorage.getItem('token');
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });
    // Endpoint real para listar sucursales
    this.http.get<any[]>(`${environment.apiUrl}/inventario/sucursales`, { headers }).subscribe({
      next: (data) => {
        this.sucursales = data;
      },
      error: () => {
        this.sucursales = [];
        mostrarAlertaToast('Error al cargar sucursales', 'error');
      }
    });
  }

  descargarInventario() {
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('No autorizado', 'error');
      return;
    }
    let url = `${environment.apiUrl}/reportes/exportar-inventario`;
    if (this.sucursalSeleccionada) {
      url += `?sucursal_id=${this.sucursalSeleccionada}`;
    }
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.get(url, { headers, responseType: 'blob' }).subscribe({
      next: (blob: Blob) => {
        const a = document.createElement('a');
        a.href = window.URL.createObjectURL(blob);
        a.download = 'reporte_inventario.xlsx';
        a.click();
        mostrarAlertaToast('Inventario exportado.');
      },
      error: () => mostrarAlertaToast('Error al exportar inventario', 'error')
    });
  }

  descargarMovimientos() {
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('No autorizado', 'error');
      return;
    }
    let url = `${environment.apiUrl}/reportes/exportar-movimientos`;
    if (this.sucursalSeleccionada) {
      url += `?sucursal_id=${this.sucursalSeleccionada}`;
    }
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.get(url, { headers, responseType: 'blob' }).subscribe({
      next: (blob: Blob) => {
        const a = document.createElement('a');
        a.href = window.URL.createObjectURL(blob);
        a.download = 'reporte_movimientos.xlsx';
        a.click();
        mostrarAlertaToast('Movimientos exportados.');
      },
      error: () => mostrarAlertaToast('Error al exportar movimientos', 'error')
    });
  }
}
