// mantenimiento-aparatos.component.ts

import { Component, Input, OnInit } from '@angular/core';
import { FormGroup, FormControl, Validators, ReactiveFormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Observable, map, startWith } from 'rxjs';

// Angular Material
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatOptionModule } from '@angular/material/core';

@Component({
  selector: 'app-mantenimiento-aparatos',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    HttpClientModule,
    MatFormFieldModule,
    MatInputModule,
    MatAutocompleteModule,
    MatOptionModule
  ],
  templateUrl: './mantenimiento-aparatos.component.html',
  styleUrls: ['./mantenimiento-aparatos.component.css']
})
export class MantenimientoAparatosComponent implements OnInit {
  @Input() parentForm!: FormGroup;

  filtroControl = new FormControl('');
  aparatos: any[] = [];
  aparatosFiltrados$!: Observable<any[]>;
  inputResaltado = false;

  idSucursal = 1;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    if (!this.parentForm) return;
  
    this.parentForm.addControl('aparato_id', new FormControl(null, Validators.required));
    this.parentForm.addControl('problema_detectado', new FormControl('', Validators.required));
    this.parentForm.addControl('necesita_refaccion', new FormControl(false));
    this.parentForm.addControl('descripcion_refaccion', new FormControl(''));
    this.parentForm.addControl('criticidad', new FormControl(null, Validators.required));

  
    const token = localStorage.getItem('token');
    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
  
    this.http.get<any[]>(`http://localhost:5000/api/aparatos/${this.idSucursal}`, { headers })
      .subscribe({
        next: (data) => {
          this.aparatos = data;
          this.setupAutocomplete();
        },
        error: (err) => console.error('❌ Error al obtener aparatos', err)
      });
  }
  

  setupAutocomplete() {
    this.aparatosFiltrados$ = this.filtroControl.valueChanges.pipe(
      startWith(''),
      map(value => typeof value === 'string' ? this.filtrar(value) : this.aparatos)
    );
  }

  filtrar(valor: any): any[] {
    if (typeof valor !== 'string') return this.aparatos;
  
    const filtro = valor.toLowerCase();
    return this.aparatos.filter(ap =>
      `${ap.codigo} ${ap.descripcion} ${ap.marca}`.toLowerCase().includes(filtro)
    );
  }
  seleccionarAparato(ap: any) {
    this.filtroControl.setValue(`${ap.codigo} - ${ap.descripcion} (${ap.marca})`);
    this.parentForm.get('aparato_id')?.setValue(ap.id);
    this.inputResaltado = true; // 🔵 activa animación
  }

  obtenerEmoji(descripcion: string): string {
    const desc = descripcion.toLowerCase();
    if (desc.includes('bicicleta')) return '🚴';
    if (desc.includes('caminadora')) return '🏃';
    if (desc.includes('eliptica')) return '🌀';
    if (desc.includes('escalera')) return '🪜';
    return '🏋️'; // Default
  }

  
}
