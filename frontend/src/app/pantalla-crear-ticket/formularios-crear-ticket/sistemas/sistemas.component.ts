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
  @Input() soloDescripcion = false;
  @Input() ocultarPickers: boolean = false; 

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

  const ensure = (name: string) => {
    if (!this.parentForm.contains(name)) {
      this.parentForm.addControl(name, this.fb.control(''));
    }
  };

  // Solo garantizamos que existan; si ya los tiene el padre, no los re-creamos
  ensure('categoria');
  ensure('subcategoria');
  ensure('aparato_id');
  ensure('descripcion');

  // Cargar inventario (aunque se oculte, no rompe; si quieres, puedes condicionar por !ocultarPickers)
  this.cargarInventario();

  this.subs = this.parentForm.get('sucursal_id')!
    .valueChanges
    .subscribe(() => this.cargarInventario());

  this.parentForm.get('categoria')!
    .valueChanges
    .subscribe(cat => {
      this.equiposFiltrados = this.inventario.filter(eq => eq.categoria === cat);
      this.parentForm.get('aparato_id')!.reset();
    });

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
        this.categorias = [...new Set(this.inventario.map(eq => eq.categoria).filter(cat => !!cat && cat.toLowerCase() !== 'maquinas')
    )
  ];
      },
      error: err => console.error('❌ Error al cargar inventario', err)
    });
  }

  onEquipoSeleccionado(eq: any) {
    this.parentForm.get('aparato_id')!.setValue(eq?.id || null);
  }
}
