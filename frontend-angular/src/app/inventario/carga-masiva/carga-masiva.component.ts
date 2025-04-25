// src/app/inventario/carga-masiva/carga-masiva.component.ts
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as XLSX from 'xlsx';
import * as Papa from 'papaparse';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-carga-masiva',
  standalone: true,
  imports: [CommonModule, HttpClientModule, FormsModule],
  templateUrl: './carga-masiva.component.html',
  styleUrls: ['./carga-masiva.component.css']
})
export class CargaMasivaComponent {
  datosPreview: any[] = [];
  columnas: string[] = [];
  mapeo: { [key: string]: string } = {};
  archivo: File | null = null;

  constructor(private http: HttpClient) {}

  onFileChange(event: any): void {
    const file = event.target.files[0];
    this.archivo = file;
    const reader = new FileReader();

    reader.onload = (e: any) => {
      const contenido = e.target.result;

      if (file.name.endsWith('.xlsx')) {
        const workbook = XLSX.read(contenido, { type: 'binary' });
        const hoja = workbook.SheetNames[0];
        const datos = XLSX.utils.sheet_to_json(workbook.Sheets[hoja], { defval: '' });
        this.prepararPreview(datos);
      } else if (file.name.endsWith('.csv')) {
        Papa.parse(contenido, {
          header: true,
          skipEmptyLines: true,
          complete: (result) => {
            this.prepararPreview(result.data);
          }
        });
      }
    };

    reader.readAsBinaryString(file);
  }

  prepararPreview(datos: any[]): void {
    this.datosPreview = datos.slice(0, 10);
    this.columnas = Object.keys(datos[0] || {});
    this.mapeo = {};
    this.columnas.forEach(col => this.mapeo[col] = '');
  }

  enviarDatos(): void {
    const datosFinales = this.datosPreview.map(fila => {
      const obj: any = {};
      for (const [columna, campoSistema] of Object.entries(this.mapeo)) {
        obj[campoSistema] = (fila[columna] || '').toString().toUpperCase().trim().replace(/\s+/g, ' ');
      }
      return obj;
    });

    this.http.post('/api/importar-inventario', datosFinales).subscribe(res => {
      alert('Datos cargados correctamente');
    });
  }
}
