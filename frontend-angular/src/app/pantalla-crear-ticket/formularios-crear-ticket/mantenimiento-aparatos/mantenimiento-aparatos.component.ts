//frontend-angular\src\app\pantalla-crear-ticket\formularios-crear-ticket\mantenimiento-aparatos\mantenimiento-aparatos.component.ts


import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { FormGroup, ReactiveFormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

// Services
import { SucursalesService } from 'src/app/services/sucursales.service';
import { SelectorEquipoComponent } from 'src/app/components/selector-equipo/selector-equipo.component';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { EquiposService } from 'src/app/services/equipos.service';


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
    SelectorEquipoComponent,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ReactiveFormsModule
  ],
  templateUrl: './mantenimiento-aparatos.component.html',
  styleUrls: []
})
export class MantenimientoAparatosComponent implements OnInit, OnDestroy {
  @Input() parentForm!: FormGroup;
  @Input() tipo: 'aparato' | 'dispositivo' = 'aparato';
  @Output() formularioValido = new EventEmitter<any>();

  usuario: any = {};
  rol: string = '';
  esAdmin: boolean = false;
  sucursales: any[] = [];
  sucursalSeleccionada: number = 1;
  equipos: any[] = [];



  private valueChangesSub?: Subscription;

  constructor(
    private sucursalesService: SucursalesService,
    private equiposService: EquiposService
  ) 
  
  {}

  ngOnInit(): void {
    if (!this.parentForm) {
      console.error('[Hijo][ngOnInit] parentForm no existe');
      return;
    }

    this.initUser();
    this.cargarEquiposPorSucursal(this.sucursalSeleccionada);

    this.valueChangesSub = this.parentForm.valueChanges.subscribe(val => {
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.mantenimiento, this.formularioValido);
    });
  }

  ngOnDestroy(): void {
    if (this.valueChangesSub) this.valueChangesSub.unsubscribe();
  }

  private initUser() {
    this.usuario = JSON.parse(localStorage.getItem('user') || '{}');
    this.rol = (this.usuario.rol || '').trim().toLowerCase();
    this.sucursalSeleccionada = Number(this.usuario.sucursal_id) || 1;
    this.esAdmin = (this.rol === 'administrador' || this.sucursalSeleccionada === 1000);

    if (this.esAdmin && this.sucursales.length === 0) {
      this.sucursalesService.obtenerSucursales().subscribe({
        next: (sucs) => {
          this.sucursales = sucs || [];
        },
        error: (err) => console.error('❌ Error al obtener sucursales', err)
      });
    }
  }

  onSucursalChange(sucursal_id: number) {
    this.sucursalSeleccionada = sucursal_id;
    this.parentForm.get('detalle')?.reset();
    this.parentForm.get('subcategoria')?.reset();
    this.parentForm.get('aparato_id')?.reset();
    this.cargarEquiposPorSucursal(sucursal_id); 
  }

  onEquipoSeleccionado(eq: any) {
    console.log(this.parentForm.value)
    if (!eq) {
      this.parentForm.get('detalle')?.reset();
      this.parentForm.get('subcategoria')?.reset();
      this.parentForm.get('aparato_id')?.reset();
      return;
    }
    this.parentForm.get('detalle')?.setValue(`${eq.nombre} - ${eq.codigo_interno} (${eq.marca})`);
    this.parentForm.get('subcategoria')?.setValue(eq.categoria || 'General');
    this.parentForm.get('aparato_id')?.setValue(eq.id);
    limpiarCamposDependientes(this.parentForm, ['descripcion', 'necesita_refaccion', 'descripcion_refaccion']);
  }

  get nombreTipo(): string {
  return this.tipo === 'dispositivo' ? 'Dispositivo' : 'Aparato';
}

cargarEquiposPorSucursal(sucursalId: number) {
  this.equiposService.obtenerEquipos({ sucursal_id: sucursalId, tipo: this.tipo }).subscribe({
    next: (resp) => { 
      console.log('Equipos recibidos:', resp); 
      this.equipos = resp || []; 
    },
    error: (err) => { 
      this.equipos = [];
      console.error('Error al cargar equipos:', err);
    }
  });
}
}
