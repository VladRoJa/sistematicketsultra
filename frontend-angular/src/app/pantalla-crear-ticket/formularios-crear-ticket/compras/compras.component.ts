//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-crear-ticket\formularios-crear-ticket\compras\compras.component.ts

import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, Input } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes } from 'src/app/utils/formularios.helper';

@Component({
  selector: 'app-compras',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatFormFieldModule, MatSelectModule, MatInputModule],
  templateUrl: './compras.component.html',
  styleUrls: []
})
export class ComprasComponent implements OnInit {

  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

  categorias = [
    {
      nombre: 'Insumos',
      subcategorias: [
        { nombre: 'Limpieza', detalles: ['Solicitud de compra', 'Cotización requerida', 'Autorización pendiente'] },
        { nombre: 'Oficina', detalles: ['Solicitud de compra', 'Cotización requerida', 'Autorización pendiente'] },
        { nombre: 'Cafetería', detalles: ['Solicitud de compra', 'Cotización requerida', 'Autorización pendiente'] },
        { nombre: 'Botanas y bebidas', detalles: ['Solicitud de compra', 'Cotización requerida', 'Autorización pendiente'] }
      ]
    },
    {
      nombre: 'Servicios',
      subcategorias: [
        { nombre: 'Mantenimiento externo', detalles: ['Contrato nuevo', 'Renovación de contrato', 'Ajuste de tarifa'] },
        { nombre: 'Publicidad', detalles: ['Contrato nuevo', 'Renovación de contrato', 'Ajuste de tarifa'] },
        { nombre: 'Seguridad', detalles: ['Contrato nuevo', 'Renovación de contrato', 'Ajuste de tarifa'] },
        { nombre: 'Transporte', detalles: ['Contrato nuevo', 'Renovación de contrato', 'Ajuste de tarifa'] }
      ]
    },
    {
      nombre: 'Herramientas',
      subcategorias: [
        { nombre: 'Gimnasio', detalles: ['Compra inicial', 'Reposición', 'Reparación'] },
        { nombre: 'Mantenimiento general', detalles: ['Compra inicial', 'Reposición', 'Reparación'] },
        { nombre: 'Oficina', detalles: ['Compra inicial', 'Reposición', 'Reparación'] }
      ]
    },
    {
      nombre: 'Refacciones',
      subcategorias: [
        { nombre: 'Equipos de cardio', detalles: ['Solicitud de refacción', 'Cotización', 'Pedido urgente'] },
        { nombre: 'Pesas libres', detalles: ['Solicitud de refacción', 'Cotización', 'Pedido urgente'] },
        { nombre: 'Selectorizados', detalles: ['Solicitud de refacción', 'Cotización', 'Pedido urgente'] },
        { nombre: 'Instalaciones generales', detalles: ['Solicitud de refacción', 'Cotización', 'Pedido urgente'] }
      ]
    },
    {
      nombre: 'Otros',
      subcategorias: [
        { nombre: 'Emergente', detalles: ['Solicitud especial', 'Requiere autorización', 'Compra inmediata'] },
        { nombre: 'No presupuestado', detalles: ['Solicitud especial', 'Requiere autorización', 'Compra inmediata'] },
        { nombre: 'Varios', detalles: ['Solicitud especial', 'Requiere autorización', 'Compra inmediata'] }
      ]
    }
  ];

  subcategoriasDisponibles: any[] = [];
  detallesDisponibles: string[] = [];

  constructor(private fb: FormBuilder) {}

  ngOnInit(): void {
    if (!this.parentForm) return;

    this.parentForm.addControl('categoria', this.fb.control('', Validators.required));
    this.parentForm.addControl('subcategoria', this.fb.control('', Validators.required));
    this.parentForm.addControl('detalle', this.fb.control('', Validators.required));
    this.parentForm.addControl('descripcion', this.fb.control('', Validators.required));

    this.parentForm.valueChanges.subscribe(() => {
      if (this.parentForm.valid) this.emitirFormulario();
    });
  }

  onCategoriaChange(): void {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.parentForm.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.detallesDisponibles = [];

    limpiarCamposDependientes(this.parentForm, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange(): void {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.parentForm.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.parentForm.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];

    limpiarCamposDependientes(this.parentForm, ['detalle']);
  }


  emitirFormulario() {
    if (this.parentForm.valid) {
      const payload = {
        departamento_id: 6,
        categoria: this.parentForm.value.categoria,
        subcategoria: this.parentForm.value.subcategoria,
        subsubcategoria: this.parentForm.value.detalle,
        descripcion: this.parentForm.value.descripcion
      };
      this.formularioValido.emit(payload);
    }
  }
}
