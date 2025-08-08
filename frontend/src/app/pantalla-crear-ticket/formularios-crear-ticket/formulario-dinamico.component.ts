//frontend-angular\src\app\pantalla-crear-ticket\formularios-crear-ticket\formulario-dinamico.component.ts

import {
  Component, Input, OnInit, OnChanges, SimpleChanges, ChangeDetectorRef
} from '@angular/core';
import { FormGroup, FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { animate, style, transition, trigger } from '@angular/animations';
import { JsonPipe } from '@angular/common';

export interface ClasificacionNode {
  id: number;
  nombre: string;
  parent_id: number | null;
  departamento_id: number;
  nivel: number;
}

@Component({
  selector: 'app-formulario-dinamico-clasificacion',
  standalone: true,
  imports: [ReactiveFormsModule, JsonPipe],
  templateUrl: './formulario-dinamico.component.html',
  styleUrls: ['./formulario-dinamico.component.css'],
  animations: [
    trigger('fade', [
      transition(':enter', [style({ opacity: 0 }), animate('160ms', style({ opacity: 1 }))]),
      transition(':leave', [animate('120ms', style({ opacity: 0 }))])
    ])
  ]
})
export class FormularioDinamicoClasificacionComponent implements OnInit, OnChanges {
  @Input() parentForm!: FormGroup;
  @Input() catalogoPlano: ClasificacionNode[] = [];
  @Input() loading: boolean = false;

  niveles: number[] = [];
  seleccionados: { [nivel: number]: ClasificacionNode | null } = {};
  root: ClasificacionNode | null = null;

  constructor(private fb: FormBuilder, private cd: ChangeDetectorRef) {}

  ngOnInit() {
    this.initSelects();

    console.log('[HIJO] root:', this.root);
  console.log('[HIJO] niveles:', this.niveles);
  console.log('[HIJO] catalogoPlano:', this.catalogoPlano);
  }

  ngOnChanges(changes: SimpleChanges) {
    if (changes['catalogoPlano']) {
      this.initSelects();
    }
  }

  // Inicializa niveles y controles según el árbol recibido
  initSelects() {
    // Busca el nodo raíz (nivel 1)
    this.root = this.catalogoPlano.find(n => n.nivel === 1) || null;

    // Detecta niveles existentes en el árbol
    const nivelesUnicos = [...new Set(this.catalogoPlano.map(n => n.nivel))];
    this.niveles = nivelesUnicos
      .filter(n => n > 1)   // solo niveles descendientes
      .sort((a, b) => a - b);

    // Crea un control para cada nivel, si no existe
    this.niveles.forEach(nivel => {
      const ctrlName = this.getControlName(nivel);
      if (!this.parentForm.get(ctrlName)) {
        this.parentForm.addControl(ctrlName, this.fb.control('', ));
      }
      this.seleccionados[nivel] = null;
    });
  }

  getControlName(nivel: number) { return `nivel_${nivel}`; }

opcionesPorNivel(nivel: number): ClasificacionNode[] {
  if (nivel === 2 && this.root) {
    return this.catalogoPlano.filter(n => n.nivel === 2 && n.parent_id === this.root!.id);
  }
  // Para los siguientes niveles, el parent es el seleccionado del nivel anterior
  const prevNivel = nivel - 1;
  const prevId = this.parentForm.get(this.getControlName(prevNivel))?.value;
  if (prevId) {
    return this.catalogoPlano.filter(n => n.nivel === nivel && n.parent_id === prevId);
  }
  return [];
}

  onSeleccionar(nivel: number) {
    const id = this.parentForm.get(this.getControlName(nivel))?.value;
    this.seleccionados[nivel] = this.catalogoPlano.find(n => n.id === id) || null;
    // Limpia niveles siguientes
    this.niveles.filter(n => n > nivel).forEach(n => {
      this.parentForm.get(this.getControlName(n))?.reset();
      this.seleccionados[n] = null;
    });
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
}
