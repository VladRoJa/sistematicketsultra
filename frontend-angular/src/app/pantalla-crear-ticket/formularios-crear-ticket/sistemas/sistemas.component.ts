// src/app/formularios-crear-ticket/sistemas/sistemas.component.ts
import { Component, EventEmitter, Input, OnInit, OnDestroy, Output } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule }  from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';

import { InventarioService } from 'src/app/services/inventario.service';
import { SelectorEquipoComponent } from 'src/app/components/selector-equipo/selector-equipo.component';
import { emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';
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
})
export class SistemasComponent implements OnInit, OnDestroy {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

  inventario: any[] = [];
  categorias: string[] = [];
  equiposFiltrados: any[] = [];

  private subs?: Subscription;

  constructor(
    private fb: FormBuilder,
    private inventarioService: InventarioService
  ) {}

  ngOnInit(): void {
    if (!this.parentForm) {
      console.warn('[SistemasComponent] parentForm no está definido');
      return;
    }

    // Solo añado los controles propios de "Sistemas"
    this.parentForm.addControl('categoria',  this.fb.control('', ));
    this.parentForm.addControl('aparato_id', this.fb.control('', ));
    this.parentForm.addControl('subcategoria', this.fb.control('', ));
    this.parentForm.addControl('descripcion',  this.fb.control('', ));

    // Cargo inventario (su parentForm ya trae 'sucursal_id')
    this.cargarInventario();

    // Cuando cambie la sucursal (control del padre), recargo inventario
    this.subs = this.parentForm.get('sucursal_id')!
      .valueChanges
      .subscribe((sucId: number) => {
        this.cargarInventario();
      });

    // Cuando cambia la categoría, filtro equipos
    this.parentForm.get('categoria')!
      .valueChanges
      .subscribe(cat => {
        this.equiposFiltrados = this.inventario.filter(eq => eq.categoria === cat);
        this.parentForm.get('aparato_id')!.reset();
      });

    // Emito cambios al padre
    this.parentForm.valueChanges
      .subscribe(() => emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.sistemas, this.formularioValido));
  }

  ngOnDestroy(): void {
    this.subs?.unsubscribe();
  }

  private cargarInventario() {
    const sucursalId = this.parentForm.get('sucursal_id')!.value;
    this.inventarioService.obtenerInventarioPorSucursal(sucursalId).subscribe({
      next: inv => {
        this.inventario = inv || [];
        this.categorias = [...new Set(this.inventario.map(eq => eq.categoria).filter(Boolean))];
      },
      error: err => console.error('❌ Error al cargar inventario', err)
    });
  }

  onEquipoSeleccionado(eq: any) {
    this.parentForm.get('aparato_id')!.setValue(eq?.id || null);
  }
}
