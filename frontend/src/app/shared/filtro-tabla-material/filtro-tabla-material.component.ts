// src/app/shared/filtro-tabla-material/filtro-tabla-material.component.ts

import { CommonModule } from '@angular/common';
import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

export interface OpcionFiltro {
  valor: string | number;
  etiqueta: string;
  seleccionado: boolean;
  visible?: boolean;
}

@Component({
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatButtonModule
  ],
  selector: 'app-filtro-tabla-material',
  templateUrl: './filtro-tabla-material.component.html',
  styleUrls: ['./filtro-tabla-material.component.css']
})
export class FiltroTablaMaterialComponent implements OnInit, OnChanges {
  @Input() label: string = '';
  @Input() opciones: OpcionFiltro[] = [];

  @Output() aplicarFiltro = new EventEmitter<OpcionFiltro[]>();
  @Output() borrarFiltro = new EventEmitter<void>();

  textoBusqueda: string = '';
  opcionesFiltradas: OpcionFiltro[] = [];
  seleccionarTodo: boolean = true;

  ngOnInit() {
    this.filtrarOpciones();
  }

  ngOnChanges(changes: SimpleChanges) {
    // Cada que cambian opciones desde el padre (incluido visible), refresca la lista y el "Seleccionar todo"
    if (changes['opciones']) {
      this.filtrarOpciones();
    }
  }

  filtrarOpciones() {
    const texto = this.textoBusqueda.toLowerCase();
    // Solo las opciones visibles
    this.opcionesFiltradas = this.opciones
      .filter(op => (op.visible !== false) && op.etiqueta.toLowerCase().includes(texto))
      .map(op => ({ ...op }));
    this.actualizarSeleccionTodo();
  }

  toggleSeleccionarTodo() {
    this.opcionesFiltradas.forEach(op => op.seleccionado = this.seleccionarTodo);
    this.sincronizarConOriginal();
  }

  actualizarSeleccionTodo() {
    const total = this.opcionesFiltradas.length;
    const seleccionados = this.opcionesFiltradas.filter(op => op.seleccionado).length;
    this.seleccionarTodo = total > 0 && seleccionados === total;
    this.sincronizarConOriginal();
  }

  onAplicar() {
    // Solo pasa los visibles filtrados y seleccionados
    this.aplicarFiltro.emit(this.opcionesFiltradas.filter(op => op.seleccionado));
  }

  onBorrarFiltro() {
    // Activa todos los visibles
    this.opcionesFiltradas.forEach(op => op.seleccionado = true);
    this.textoBusqueda = '';
    this.seleccionarTodo = true;
    this.borrarFiltro.emit();
    this.filtrarOpciones();
  }

  // Sincroniza el estado seleccionado de los filtrados con el array original (padre)
  sincronizarConOriginal() {
    for (let filtrada of this.opcionesFiltradas) {
      const original = this.opciones.find(op => op.valor === filtrada.valor);
      if (original) original.seleccionado = filtrada.seleccionado;
    }
  }
}
