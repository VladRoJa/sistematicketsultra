// frontend-angular/src/app/pantalla-crear-ticket/formularios-crear-ticket/mantenimiento-aparatos/mantenimiento-aparatos.component.ts

import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { FormGroup, FormControl, FormBuilder, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

// Services & Components
import { SucursalesService } from 'src/app/services/sucursales.service';
import { EquiposService } from 'src/app/services/equipos.service';
import { SelectorEquipoComponent } from 'src/app/components/selector-equipo/selector-equipo.component';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

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
    SelectorEquipoComponent,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule
  ],
  templateUrl: './mantenimiento-aparatos.component.html',
})
export class MantenimientoAparatosComponent implements OnInit, OnDestroy {
  @Input() parentForm!: FormGroup;
  @Input() tipo: 'aparato' | 'dispositivo' = 'aparato';
  @Output() formularioValido = new EventEmitter<any>();

  sucursales: any[] = [];
  equipos: any[] = [];
  sucursalSeleccionada!: number;

  private formSub?: Subscription;

  constructor(
    private fb: FormBuilder,
    private sucursalesService: SucursalesService,
    private equiposService: EquiposService
  ) {}

ngOnInit(): void {
  if (!this.parentForm) {
    console.error('[MantenimientoAparatos] parentForm no definido');
    return;
  }

  const sucursalCtrl = this.parentForm.get('sucursal_id');
  if (!sucursalCtrl) {
    console.error('[MantenimientoAparatos] El control sucursal_id no existe en parentForm');
    return;
  }

  // --- Inicializar controles propios ---
  this.parentForm.addControl('detalle', this.fb.control(''));
  this.parentForm.addControl('subcategoria', this.fb.control(''));
  this.parentForm.addControl('aparato_id', this.fb.control(null));

  // --- Detectar sucursal desde el padre (ya viene en parentForm) ---
  this.sucursalSeleccionada = sucursalCtrl.value;

  // Carga inicial de equipos
  this.cargarEquiposPorSucursal(this.sucursalSeleccionada);

  // Escucha cambios de sucursal desde el padre
  sucursalCtrl.valueChanges.subscribe((sucId: number) => {
    this.sucursalSeleccionada = sucId;
    // Reset controles dependientes
    this.parentForm.get('detalle')!.reset();
    this.parentForm.get('subcategoria')!.reset();
    this.parentForm.get('aparato_id')!.reset();
    this.cargarEquiposPorSucursal(sucId);
  });

  // Emite validez al padre
  this.formSub = this.parentForm.valueChanges.subscribe(() => {
    emitirPayloadFormulario(
      this.parentForm,
      DEPARTAMENTO_IDS.mantenimiento,
      this.formularioValido
    );
  });
}


  ngOnDestroy(): void {
    this.formSub?.unsubscribe();
  }

  onEquipoSeleccionado(eq: any) {
    if (!eq) {
      this.parentForm.get('detalle')!.reset();
      this.parentForm.get('subcategoria')!.reset();
      this.parentForm.get('aparato_id')!.reset();
      return;
    }
    // Rellena los campos desde el objeto equipo
    this.parentForm.get('detalle')!.setValue(`${eq.nombre} (${eq.codigo_interno})`);
    this.parentForm.get('subcategoria')!.setValue(eq.categoria || 'General');
    this.parentForm.get('aparato_id')!.setValue(eq.id);
    limpiarCamposDependientes(this.parentForm, [
      'descripcion_general',
      'necesita_refaccion',
      'descripcion_refaccion'
    ]);
  }

  private cargarEquiposPorSucursal(sucursalId: number) {
    // 👇 Log para depuración
    console.log('[cargarEquiposPorSucursal] sucursalId:', sucursalId, 'tipo:', this.tipo);

    this.equiposService.obtenerEquipos({ sucursal_id: sucursalId, tipo: this.tipo })
      .subscribe({
        next: resp => {
          console.log('[cargarEquiposPorSucursal] Respuesta del backend:', resp);
          this.equipos = resp || [];
        },
        error: err => {
          console.error('Error al cargar equipos:', err);
          this.equipos = [];
        }
      });
}

  get nombreTipo(): string {
    return this.tipo === 'dispositivo' ? 'Dispositivo' : 'Aparato';
  }
}
