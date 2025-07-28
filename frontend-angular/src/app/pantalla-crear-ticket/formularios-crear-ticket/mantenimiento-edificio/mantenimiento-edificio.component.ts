// src/app/mantenimiento-edificio/mantenimiento-edificio.component.ts

import { Component, Input, OnInit, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormGroup, FormControl, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import {
  limpiarCamposDependientes,
  emitirPayloadFormulario,
  DEPARTAMENTO_IDS
} from 'src/app/utils/formularios.helper';
import { MatIconModule } from '@angular/material/icon';
import { CatalogoService } from 'src/app/services/catalogo.service';
import { ClasificacionElemento } from 'src/app/services/catalogo.service';

@Component({
  selector: 'app-mantenimiento-edificio',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    FormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatIconModule,
  ],
  templateUrl: './mantenimiento-edificio.component.html',
  styleUrls: []
})
export class MantenimientoEdificioComponent implements OnInit {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

  clasificaciones: ClasificacionElemento[] = [];

  jerarquiaMantenimiento: { [categoria: string]: { [sub: string]: string[] } } = {
  };

  constructor(private catalogoService: CatalogoService) {}

  ngOnInit(): void {
    this.registrarControles();
    this.cargarClasificaciones();

    this.parentForm.valueChanges.subscribe(() => {
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.mantenimiento, this.formularioValido);
    });
  }

  registrarControles(): void {
    const campos = ['categoria', 'subcategoria', 'detalle', 'descripcion', 'ubicacion', 'equipo', 'clasificacion_id'];
    for (const campo of campos) {
      if (!this.parentForm.get(campo)) {
        this.parentForm.addControl(
          campo,
          new FormControl('', Validators.required)
        );
      }
    }
  }

    cargarClasificaciones() {
      this.catalogoService.listarElemento('clasificaciones').subscribe((data: any[]) => {
        this.clasificaciones = data.map(clasif => ({
          ...clasif,
          jerarquia: clasif.jerarquia ? clasif.jerarquia : [clasif.nombre]
        }));
      });
    }

  // Puedes mostrar la jerarquía como string para el option:
  mostrarJerarquia(clasif: ClasificacionElemento): string {
    return clasif.jerarquia && Array.isArray(clasif.jerarquia)
      ? clasif.jerarquia.join(' > ')
      : clasif.nombre;
  }

  onCategoriaChange(): void {
    limpiarCamposDependientes(this.parentForm, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange(): void {
    limpiarCamposDependientes(this.parentForm, ['detalle']);
  }

  getCategorias(): string[] {
    return Object.keys(this.jerarquiaMantenimiento);
  }

  getSubcategorias(categoria: string): string[] {
    return this.jerarquiaMantenimiento[categoria]
      ? Object.keys(this.jerarquiaMantenimiento[categoria])
      : [];
  }

  getDetalles(categoria: string, subcategoria: string): string[] {
    return this.jerarquiaMantenimiento[categoria]?.[subcategoria] || [];
  }
}
