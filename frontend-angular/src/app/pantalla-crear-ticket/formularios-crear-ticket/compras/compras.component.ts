//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-crear-ticket\formularios-crear-ticket\compras\compras.component.ts

import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
  selector: 'app-compras',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './compras.component.html',
  styleUrls: []
})
export class ComprasComponent implements OnInit {

  @Output() formularioValido = new EventEmitter<any>();
  formCompras!: FormGroup;

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
    this.formCompras = this.fb.group({
      categoria: ['', Validators.required],
      subcategoria: ['', Validators.required],
      detalle: ['', Validators.required],
      descripcion: ['', Validators.required],
      criticidad: [null, Validators.required]
    });
  }

  onCategoriaChange(): void {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formCompras.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.formCompras.patchValue({ subcategoria: '', detalle: '' });
    this.detallesDisponibles = [];
  }

  onSubcategoriaChange(): void {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formCompras.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formCompras.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];
    this.formCompras.patchValue({ detalle: '' });
  }

  enviarFormulario(): void {
    if (this.formCompras.valid) {
      const payload = {
        departamento_id: 6,
        categoria: this.formCompras.value.categoria,
        subcategoria: this.formCompras.value.subcategoria,
        subsubcategoria: this.formCompras.value.detalle,
        descripcion: this.formCompras.value.descripcion,
        criticidad: this.formCompras.value.criticidad
      };
      this.formularioValido.emit(payload);
    }
  }
}
