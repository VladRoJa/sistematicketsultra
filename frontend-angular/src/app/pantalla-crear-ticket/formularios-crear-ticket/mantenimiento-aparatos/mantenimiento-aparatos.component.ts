// mantenimiento-aparatos.component.ts

import { Component, Input, OnInit, Output, EventEmitter } from '@angular/core';
import { FormGroup, FormControl, Validators, ReactiveFormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Observable, map, startWith } from 'rxjs';
import { environment } from 'src/environments/environment';

// Angular Material
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatOptionModule } from '@angular/material/core';

// Helper
import {
  limpiarCamposDependientes,
  emitirPayloadFormulario,
  DEPARTAMENTO_IDS
} from 'src/app/utils/formularios.helper';

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
  styleUrls: []
})
export class MantenimientoAparatosComponent implements OnInit {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

  filtroControl = new FormControl('');
  aparatos: any[] = [];
  aparatosFiltrados$!: Observable<any[]>;
  inputResaltado = false;

  idSucursal = 1;

  constructor(private http: HttpClient) {}

ngOnInit(): void {
  if (!this.parentForm) return;

  // ✅ Asegurar existencia de controles antes de agregarlos
  if (!this.parentForm.get('categoria')) {
    this.parentForm.addControl('categoria', new FormControl('Aparatos', Validators.required));
  } else {
    this.parentForm.get('categoria')?.setValue('Aparatos');
  }

  if (!this.parentForm.get('subcategoria')) {
    this.parentForm.addControl('subcategoria', new FormControl('', Validators.required));
  }

  if (!this.parentForm.get('detalle')) {
    this.parentForm.addControl('detalle', new FormControl('', Validators.required));
  }

  if (!this.parentForm.get('descripcion')) {
    this.parentForm.addControl('descripcion', new FormControl('', Validators.required));
  }

  // ⚙️ Opcionales
  if (!this.parentForm.get('necesita_refaccion')) {
    this.parentForm.addControl('necesita_refaccion', new FormControl(false));
  }

  if (!this.parentForm.get('descripcion_refaccion')) {
    this.parentForm.addControl('descripcion_refaccion', new FormControl(''));
  }

  // 🛰 Emitir payload al padre
  this.parentForm.valueChanges.subscribe(() => {
    emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.mantenimiento, this.formularioValido);
  });

  // 🔄 Obtener aparatos
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

  this.http.get<any[]>(`${environment.apiUrl}/aparatos/${this.idSucursal}`, { headers }).subscribe({
    next: (data) => {
      this.aparatos = data;
      this.setupAutocomplete();

      // 🧽 Limpieza si el usuario borra manualmente el input
      this.filtroControl.valueChanges.subscribe(value => {
        if (typeof value === 'string') {
          this.parentForm.get('detalle')?.reset();
          this.parentForm.get('subcategoria')?.reset();
        }
      });
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
    this.parentForm.get('detalle')?.setValue(`${ap.codigo} - ${ap.descripcion} (${ap.marca})`);
    this.parentForm.get('subcategoria')?.setValue(ap.area || 'General');
    this.inputResaltado = true;

    limpiarCamposDependientes(this.parentForm, ['descripcion', 'necesita_refaccion', 'descripcion_refaccion']);
  }

  obtenerEmoji(descripcion: string): string {
    const desc = descripcion.toLowerCase();
    if (desc.includes('bicicleta')) return '🚴';
    if (desc.includes('caminadora')) return '🏃';
    if (desc.includes('eliptica')) return '🌀';
    if (desc.includes('escalera')) return '🪜';
    return '🏋️';
  }
}

