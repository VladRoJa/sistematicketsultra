import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, Input } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes, emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';


@Component({
  selector: 'app-recursos-humanos',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatFormFieldModule, MatSelectModule, MatInputModule],
  templateUrl: './recursos-humanos.component.html',
  styleUrls: []
})
export class RecursosHumanosComponent implements OnInit {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();
  formRH!: FormGroup;

  categorias = [
    {
      nombre: 'Incidencias en nómina',
      subcategorias: [
        { nombre: 'Horas extras', detalles: ['Corrección de cálculo', 'Ajuste extraordinario', 'Validación de evidencia'] },
        { nombre: 'Deducciones', detalles: ['Corrección de cálculo', 'Ajuste extraordinario', 'Validación de evidencia'] },
        { nombre: 'Bonos', detalles: ['Corrección de cálculo', 'Ajuste extraordinario', 'Validación de evidencia'] },
        { nombre: 'Faltas', detalles: ['Corrección de cálculo', 'Ajuste extraordinario', 'Validación de evidencia'] }
      ]
    },
    {
      nombre: 'Vacantes',
      subcategorias: [
        { nombre: 'Recepcionista', detalles: ['Publicación de vacante', 'Proceso de entrevista', 'Contratación pendiente'] },
        { nombre: 'Instructores de piso', detalles: ['Publicación de vacante', 'Proceso de entrevista', 'Contratación pendiente'] },
        { nombre: 'Personal limpieza', detalles: ['Publicación de vacante', 'Proceso de entrevista', 'Contratación pendiente'] },
        { nombre: 'Gerente', detalles: ['Publicación de vacante', 'Proceso de entrevista', 'Contratación pendiente'] },
        { nombre: 'Otros', detalles: ['Publicación de vacante', 'Proceso de entrevista', 'Contratación pendiente'] }
      ]
    },
    {
      nombre: 'Uniformes',
      subcategorias: [
        { nombre: 'Recepción', detalles: ['Solicitud nueva dotación', 'Reposición', 'Cambio de talla'] },
        { nombre: 'Gerencia', detalles: ['Solicitud nueva dotación', 'Reposición', 'Cambio de talla'] },
        { nombre: 'Instructores', detalles: ['Solicitud nueva dotación', 'Reposición', 'Cambio de talla'] },
        { nombre: 'Mantenimiento', detalles: ['Solicitud nueva dotación', 'Reposición', 'Cambio de talla'] }
      ]
    },
    {
      nombre: 'Tarjeta de nómina',
      subcategorias: [
        { nombre: 'Nueva emisión', detalles: ['Error de datos', 'Tarjeta bloqueada', 'Extraviada'] },
        { nombre: 'Reposición', detalles: ['Error de datos', 'Tarjeta bloqueada', 'Extraviada'] },
        { nombre: 'Activación', detalles: ['Error de datos', 'Tarjeta bloqueada', 'Extraviada'] }
      ]
    },
    {
      nombre: 'Entrega de finiquitos',
      subcategorias: [
        { nombre: 'Baja voluntaria', detalles: ['Pago programado', 'Pago urgente', 'Documentación pendiente'] },
        { nombre: 'Baja por término de contrato', detalles: ['Pago programado', 'Pago urgente', 'Documentación pendiente'] },
        { nombre: 'Baja por despido', detalles: ['Pago programado', 'Pago urgente', 'Documentación pendiente'] }
      ]
    },
    {
      nombre: 'Bajas de personal',
      subcategorias: [
        { nombre: 'Voluntaria', detalles: ['Proceso iniciado', 'Proceso concluido', 'Documentación incompleta'] },
        { nombre: 'Involuntaria', detalles: ['Proceso iniciado', 'Proceso concluido', 'Documentación incompleta'] }
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
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.rh, this.formularioValido);
    });
  }

  onCategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formRH.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.detallesDisponibles = [];

    limpiarCamposDependientes(this.formRH, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formRH.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formRH.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];

    limpiarCamposDependientes(this.formRH, ['detalle']);
  }


  enviarFormulario() {
    if (this.formRH.valid) {
      const payload = {
        departamento_id: 5,
        categoria: this.formRH.value.categoria,
        subcategoria: this.formRH.value.subcategoria,
        subsubcategoria: this.formRH.value.detalle,
        descripcion: this.formRH.value.descripcion,
        criticidad: this.formRH.value.criticidad
      };
      this.formularioValido.emit(payload);
    }
  }
}
