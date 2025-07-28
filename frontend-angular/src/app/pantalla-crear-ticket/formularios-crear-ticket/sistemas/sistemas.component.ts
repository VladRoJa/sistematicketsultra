// src/app/formularios-crear-ticket/sistemas/sistemas.component.ts

import { Component, EventEmitter, Input, OnInit, OnDestroy, Output } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';

import { SucursalesService } from 'src/app/services/sucursales.service';
import { InventarioService } from 'src/app/services/inventario.service';
import { SelectorEquipoComponent } from 'src/app/components/selector-equipo/selector-equipo.component';
import { limpiarCamposDependientes, emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-sistemas',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatOptionModule,
    SelectorEquipoComponent
  ],
  templateUrl: './sistemas.component.html',
  styleUrls: []
})
export class SistemasComponent implements OnInit, OnDestroy {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

  sucursales: any[] = [];
  sucursalSeleccionada: number = 1;
  esAdmin: boolean = false;

  inventario: any[] = [];
  categorias: string[] = [];
  equiposFiltrados: any[] = [];

  // Subcategorías fijas (puedes cambiarlas después)
  subcategoriasDisponibles: string[] = ['Fallo', 'Reparación', 'Mantenimiento', 'Cambio', 'Actualización'];

  valueChangesSub?: Subscription;

  constructor(
    private fb: FormBuilder,
    private sucursalesService: SucursalesService,
    private inventarioService: InventarioService
  ) {}

  ngOnInit(): void {
    // Detectar usuario y permisos
    const usuario = JSON.parse(localStorage.getItem('user') || '{}');
    this.sucursalSeleccionada = Number(usuario.sucursal_id) || 1;
    const rol = (usuario.rol || '').trim().toLowerCase();
    this.esAdmin = (rol === 'administrador' || this.sucursalSeleccionada === 1000);

    // Controls requeridos para el formulario
    this.parentForm.addControl('sucursal_id', this.fb.control(this.sucursalSeleccionada, Validators.required));
    this.parentForm.addControl('categoria', this.fb.control('', Validators.required));
    this.parentForm.addControl('aparato_id', this.fb.control('', Validators.required));
    this.parentForm.addControl('subcategoria', this.fb.control('', Validators.required));
    this.parentForm.addControl('descripcion', this.fb.control('', Validators.required));

    // Cargar sucursales si es admin
    if (this.esAdmin) {
      this.sucursalesService.obtenerSucursales().subscribe({
        next: (sucs) => this.sucursales = sucs || [],
        error: (err) => console.error('❌ Error al obtener sucursales', err)
      });
    }

    // Cargar inventario de la sucursal inicial
    this.cargarInventario();

    // CASCADA: Cuando cambia sucursal, recarga inventario/categoría/equipos
    this.parentForm.get('sucursal_id')!.valueChanges.subscribe(id => {
      this.sucursalSeleccionada = id;
      this.parentForm.get('categoria')!.reset();
      this.parentForm.get('aparato_id')!.reset();
      this.cargarInventario();
    });

    // CASCADA: Cuando cambia categoría, filtra equipos
    this.parentForm.get('categoria')!.valueChanges.subscribe(cat => {
      this.parentForm.get('aparato_id')!.reset();
      this.equiposFiltrados = this.inventario.filter(eq => eq.categoria === cat);
    });

    // Sincroniza cambios para emitir payload hacia el padre
    this.valueChangesSub = this.parentForm.valueChanges.subscribe(() => {
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.sistemas, this.formularioValido);
    });
  }

  ngOnDestroy(): void {
    if (this.valueChangesSub) this.valueChangesSub.unsubscribe();
  }

  // Obtiene el inventario solo de la sucursal seleccionada
  cargarInventario() {
    this.inventarioService.obtenerInventarioPorSucursal(this.sucursalSeleccionada).subscribe({
      next: (inv) => {
        this.inventario = inv || [];
        // Saca categorías únicas SOLO de esa sucursal
        this.categorias = [...new Set(this.inventario.map(eq => eq.categoria).filter(Boolean))];
        // Reinicia el filtro de equipos
        this.equiposFiltrados = [];
      },
      error: (err) => console.error('❌ Error al cargar inventario', err)
    });
  }

  // Cuando el usuario selecciona un equipo (debe recibir el objeto equipo)
  onEquipoSeleccionado(eq: any) {
    if (!eq) {
      this.parentForm.get('aparato_id')?.reset();
      return;
    }
    this.parentForm.get('aparato_id')?.setValue(eq.id);
  }
}
