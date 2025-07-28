//src/app/formularios-crear-ticket/formulario-dinamico.component.ts

import {
  Component, Input, OnInit, QueryList, ViewChildren, ElementRef, AfterViewInit, ChangeDetectorRef
} from '@angular/core';
import { FormGroup, FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { animate, style, transition, trigger } from '@angular/animations';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';



export interface ClasificacionNode {
  id: number;
  nombre: string;
  parent_id: number | null;
  departamento_id: number;
  nivel: number;
}

@Component({
  selector: 'app-formulario-dinamico',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatFormFieldModule,
    MatSelectModule, 
    MatInputModule, 
    MatButtonModule
  ],
  templateUrl: './formulario-dinamico.component.html',
  styleUrls: ['./formulario-dinamico.component.css'],
  animations: [
    trigger('fade', [
      transition(':enter', [style({ opacity: 0 }), animate('160ms', style({ opacity: 1 }))]),
      transition(':leave', [animate('120ms', style({ opacity: 0 }))])
    ])
  ]
})
export class FormularioDinamicoClasificacionComponent implements OnInit, AfterViewInit {
  @Input() parentForm!: FormGroup;
  @Input() catalogoPlano: ClasificacionNode[] = [];
  @Input() loading: boolean = false;

  niveles: number[] = [];
  busquedas: { [nivel: number]: string } = {};
  seleccionados: { [nivel: number]: ClasificacionNode | null } = {};

  // Para enfoque
  @ViewChildren('selectNivel') selectsRefs!: QueryList<ElementRef>;
  @ViewChildren('autoInput') autoInputs!: QueryList<ElementRef>;

  editandoNivel: number | null = null;

  constructor(private fb: FormBuilder, private cd: ChangeDetectorRef) {}

  ngOnInit() {
    this.niveles = Array.from(new Set(this.catalogoPlano.map(c => c.nivel))).sort((a, b) => a - b);
    this.niveles.forEach(nivel => {
      const controlName = this.getControlName(nivel);
      if (!this.parentForm.get(controlName)) {
        this.parentForm.addControl(controlName, this.fb.control('', Validators.required));
      }
      this.busquedas[nivel] = '';
      this.seleccionados[nivel] = null;
    });
  }

  ngAfterViewInit() {
    // Autoenfoque si el usuario comienza a editar desde el breadcrumb
    this.cd.detectChanges();
  }

  getControlName(nivel: number) {
    return `nivel_${nivel}`;
  }

  opcionesPorNivel(nivel: number): ClasificacionNode[] {
    const filtro = this.busquedas[nivel]?.toLowerCase() ?? '';
    let opciones: ClasificacionNode[];

    if (nivel === Math.min(...this.niveles)) {
      opciones = this.catalogoPlano.filter(n => n.nivel === nivel && !n.parent_id);
    } else {
      const parentId = this.parentForm.get(this.getControlName(nivel - 1))?.value;
      if (!parentId) return [];
      opciones = this.catalogoPlano.filter(n => n.nivel === nivel && n.parent_id === parentId);
    }

    return filtro
      ? opciones.filter(op => op.nombre.toLowerCase().includes(filtro))
      : opciones;
  }

  onSeleccionar(nivel: number) {
    // Actualiza selección
    const id = this.parentForm.get(this.getControlName(nivel))?.value;
    this.seleccionados[nivel] = this.catalogoPlano.find(n => n.id === id) || null;

    // Limpia hijos
    this.niveles.filter(n => n > nivel).forEach(n => {
      this.parentForm.get(this.getControlName(n))?.reset();
      this.seleccionados[n] = null;
      this.busquedas[n] = '';
    });

    // Sale del modo editar breadcrumb
    this.editandoNivel = null;

    // Enfoque al siguiente campo
    setTimeout(() => {
      const idx = this.niveles.findIndex(n => n === nivel);
      const nextInput = this.autoInputs?.get(idx + 1);
      if (nextInput) nextInput.nativeElement.focus();
    }, 200);
  }

  onBuscar(nivel: number, value: string) {
    this.busquedas[nivel] = value;
  }

  getLabel(nivel: number): string {
    switch (nivel) {
      case 2: return 'Categoría';
      case 3: return 'Subcategoría';
      case 4: return 'Detalle específico';
      case 5: return 'Variante';
      default: return 'Nivel ' + nivel;
    }
  }

  getRutaSeleccionada(): { nivel: number, label: string }[] {
    return this.niveles
      .filter(nivel => this.seleccionados[nivel])
      .map(nivel => ({
        nivel,
        label: this.seleccionados[nivel]?.nombre || ''
      }));
  }

  // Permite editar desde el breadcrumb
  editarDesdeRuta(nivel: number) {
    // Limpia niveles posteriores
    this.niveles.filter(n => n > nivel).forEach(n => {
      this.parentForm.get(this.getControlName(n))?.reset();
      this.seleccionados[n] = null;
      this.busquedas[n] = '';
    });
    this.editandoNivel = nivel;
    setTimeout(() => {
      const idx = this.niveles.findIndex(n => n === nivel);
      const input = this.autoInputs?.get(idx);
      if (input) input.nativeElement.focus();
    }, 180);
  }

  isCompleto(): boolean {
    return this.niveles.every(nivel => this.parentForm.get(this.getControlName(nivel))?.valid);
  }
}
