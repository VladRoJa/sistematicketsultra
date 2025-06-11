import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, Input } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes, emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';

@Component({
  selector: 'app-sistemas',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatFormFieldModule, MatSelectModule, MatInputModule],
  templateUrl: './sistemas.component.html',
  styleUrls: []
})
export class SistemasComponent implements OnInit {

  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

  categorias = [
    {
      nombre: 'Computadora Recepción',
      subcategorias: [
        { nombre: 'Alta de usuario', detalles: ['Urgente', 'Preventivo'] },
        { nombre: 'Reparación', detalles: ['Correctivo', 'Programado'] },
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Otro', detalles: ['Correctivo', 'Urgente'] }
      ]
    },
    {
      nombre: 'Computadora Gerente',
      subcategorias: [
        { nombre: 'Alta de usuario', detalles: ['Urgente', 'Preventivo'] },
        { nombre: 'Reparación', detalles: ['Correctivo', 'Programado'] },
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Otro', detalles: ['Correctivo', 'Urgente'] }
      ]
    },
    {
      nombre: 'Torniquete 1 (Junto a Recepcion)',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Compra de equipo', detalles: ['Urgente'] },
        { nombre: 'Reparación', detalles: ['Correctivo'] },
        { nombre: 'Otro', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Torniquete 2 (Retirado de recepcion)',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Compra de equipo', detalles: ['Urgente'] },
        { nombre: 'Reparación', detalles: ['Correctivo'] }
      ]
    },
    {
      nombre: 'Sonido Ambiental (Bocinas, Amplificador)',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Correctivo', 'Urgente'] }
      ]
    },
    {
      nombre: 'Sonido en Salones',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Correctivo', 'Urgente'] }
      ]
    },
    {
      nombre: 'Tablet 1 (Computadora recepcion)',
      subcategorias: [
        { nombre: 'Reparación', detalles: ['Correctivo', 'Preventivo'] },
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Otro', detalles: ['Correctivo', 'Urgente'] }
      ]
    },
    {
      nombre: 'Tablet 2 (Computadora Gerente)',
      subcategorias: [
        { nombre: 'Reparación', detalles: ['Correctivo', 'Preventivo'] },
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Otro', detalles: ['Correctivo', 'Urgente'] }
      ]
    },
    {
      nombre: 'Impresora multifuncional',
      subcategorias: [
        { nombre: 'Reparación', detalles: ['Correctivo'] },
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Otro', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Impresora termica (Recepcion)',
      subcategorias: [
        { nombre: 'Reparación', detalles: ['Correctivo'] },
        { nombre: 'Configuración', detalles: ['Programado'] }
      ]
    },
    {
      nombre: 'Impresora termica (Gerente)',
      subcategorias: [
        { nombre: 'Reparación', detalles: ['Correctivo'] },
        { nombre: 'Configuración', detalles: ['Programado'] }
      ]
    },
    {
      nombre: 'Terminal (Recepcion)',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Terminal (Gerente)',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Alarma',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Teléfono',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Internet',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Urgente'] }
      ]
    },
    {
      nombre: 'Cámaras',
      subcategorias: [
        { nombre: 'Configuración', detalles: ['Programado'] },
        { nombre: 'Reparación', detalles: ['Urgente'] }
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
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.sistemas, this.formularioValido);
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

  enviarFormulario() {
    if (this.parentForm.valid) {
      const payload = {
        departamento_id: 7,
        categoria: this.parentForm.value.categoria,
        subcategoria: this.parentForm.value.subcategoria,
        subsubcategoria: this.parentForm.value.detalle,
        descripcion: this.parentForm.value.descripcion
      };
      this.formularioValido.emit(payload);
    }
  }
}
