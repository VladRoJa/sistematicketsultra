//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\carga-masiva\carga-masiva-sinmapeo.component.ts

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { environment } from 'src/environments/environment';


@Component({
  selector: 'app-carga-masiva-sinmapeo',
  standalone: true,
  imports: [CommonModule, HttpClientModule],
  templateUrl: './carga-masiva-sinmapeo.component.html',
  styleUrls: ['./carga-masiva-sinmapeo.component.css']
})
export class CargaMasivaSinMapeoComponent {
  mensaje: string = '';
  cargando = false;

  constructor(private http: HttpClient) {}

  subirArchivo(event: any): void {
    const archivo = event.target.files[0];
    if (!archivo) return;

    const formData = new FormData();
    formData.append('archivo', archivo);

    this.cargando = true;
    this.http.post(`${environment.apiUrl}/importar-archivo`, formData).subscribe({
      next: (res: any) => {
        this.mensaje = res.mensaje || 'Carga exitosa';
        this.cargando = false;
      },
      error: (err) => {
        this.mensaje = err.error?.error || 'Error al subir el archivo';
        this.cargando = false;
      }
    });
  }
}
