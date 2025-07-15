// src/app/inventario/carga-masiva/carga-masiva-archivo.component.ts

import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpHeaders, HttpClientModule } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-carga-masiva-archivo',
  standalone: true,
  imports: [
    CommonModule,
    HttpClientModule,
    MatCardModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './carga-masiva-archivo.component.html',
  styleUrls: ['./carga-masiva-archivo.component.css']
})
export class CargaMasivaArchivoComponent {
  @Input() tipo: 'catalogo' | 'existencias' = 'catalogo';
  mensaje = '';
  cargando = false;
  archivo: File | null = null;

  constructor(private http: HttpClient) {}

  subirArchivo(event: any): void {
    this.archivo = event.target.files[0];
    if (!this.archivo) {
      this.mensaje = 'Selecciona un archivo primero.';
      return;
    }

    const formData = new FormData();
    formData.append('archivo', this.archivo);

    this.cargando = true;
    this.mensaje = '';

    // Endpoint depende del tipo
    const url = `${environment.apiUrl}/importar/${this.tipo}`;
    const token = localStorage.getItem('token');
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });

    this.http.post(url, formData, { headers }).subscribe({
      next: (res: any) => {
        this.mensaje = res?.mensaje || 'Carga exitosa.';
        this.cargando = false;
      },
      error: (err) => {
        this.mensaje = err.error?.error || 'Error al subir el archivo';
        this.cargando = false;
      }
    });
  }

  descargarLayout() {
    const url = `${environment.apiUrl}/importar/layout/${this.tipo}`;
    const token = localStorage.getItem('token');
    const headers = new HttpHeaders({ Authorization: `Bearer ${token}` });
    this.cargando = true;

    this.http.get(url, { headers, responseType: 'blob' }).subscribe({
      next: (blob: Blob) => {
        const urlBlob = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = urlBlob;
        a.download = `layout_${this.tipo}.xlsx`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          window.URL.revokeObjectURL(urlBlob);
        }, 0);
        this.cargando = false;
      },
      error: () => {
        this.mensaje = 'No se pudo descargar el layout.';
        this.cargando = false;
      }
    });
  }
}
