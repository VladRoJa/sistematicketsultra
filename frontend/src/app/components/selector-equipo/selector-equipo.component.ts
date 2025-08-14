// frontend-angular/src/app/components/selector-equipo/selector-equipo.component.ts

import { Component, EventEmitter, Input, OnInit, Output, OnChanges, SimpleChanges } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Observable, map, startWith } from 'rxjs';
import { EquiposService } from 'src/app/services/equipos.service';
import { CommonModule } from '@angular/common';
// Angular Material
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatOptionModule } from '@angular/material/core';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-selector-equipo',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatAutocompleteModule,
    MatOptionModule,
    MatIconModule,
  ],
  templateUrl: './selector-equipo.component.html',
  styleUrls: []
})
export class SelectorEquipoComponent implements OnInit, OnChanges {
  @Input() sucursalId: number = Number(localStorage.getItem('sucursal_id')) || 1;
  @Input() tipo: string = 'aparato';
  @Input() placeholder: string = 'Buscar equipo';
  @Input() required: boolean = true;
  @Input() mostrarEmoji: boolean = false;
  @Output() equipoSeleccionado = new EventEmitter<any>();
  @Input() equipos: any[] = [];
  @Input() modoAutocomplete: boolean = true;


  filtroControl = new FormControl('', this.required ? { nonNullable: true } : undefined);
  equiposFiltrados$!: Observable<any[]>;
  equipoSeleccionadoInterno: any = null;

  constructor(private equiposService: EquiposService) {}

  ngOnInit(): void {
    this.setupBusqueda();
    this.filtroControl.valueChanges.subscribe(value => {
      if (typeof value === 'string' && value.trim() === '') {
        this.equipoSeleccionadoInterno = null;
        this.equipoSeleccionado.emit(null);
      }
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['equipos']) {
      this.setupBusqueda();
    }
  }

  private normalize(s: string): string {
    return (s || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')   // acentos
      .replace(/[\s-_/]/g, '');          // separadores comunes
  }

  setupBusqueda() {
    this.equiposFiltrados$ = this.filtroControl.valueChanges.pipe(
      startWith(''),
      map(value => {
        if (typeof value === 'string') return this.filtrar(value);
        return this.equipos;
      })
    );
  }

  filtrar(valor: string): any[] {
    if (!valor) return this.equipos;

    const needle = this.normalize(valor);

    return this.equipos.filter(eq => {
      const nombre = this.normalize(eq?.nombre ?? '');
      const codigo = this.normalize(eq?.codigo_interno ?? '');
      const marca  = this.normalize(eq?.marca ?? '');

      return (
        nombre.includes(needle) ||
        codigo.includes(needle) ||
        marca.includes(needle)
      );
    });
  }


  seleccionarEquipo(eq: any) {
    if (!eq) return;
    this.equipoSeleccionadoInterno = eq;
    this.filtroControl.setValue(eq, { emitEvent: false }); // ¡Setea el objeto!
    this.equipoSeleccionado.emit(eq);
  }

  displayEquipo(eq: any): string {
    if (!eq) return '';
    return `${this.mostrarEmoji ? this.obtenerEmoji(eq.nombre) + ' ' : ''}${eq.nombre} - ${eq.codigo_interno} (${eq.marca})`;
  }

  limpiarBusqueda() {
    this.filtroControl.setValue('');
    this.equipoSeleccionadoInterno = null;
    this.equipoSeleccionado.emit(null);
  }

  obtenerEmoji(descripcion: string): string {
    const desc = (descripcion || '').toLowerCase();
    if (desc.includes('bicicleta')) return '🚴';
    if (desc.includes('caminadora')) return '🏃';
    if (desc.includes('eliptica')) return '🌀';
    if (desc.includes('escalera')) return '🪜';
    return '🏋️';
  }
}
