import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, Input } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes, emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';


@Component({
  selector: 'app-gerencia-deportiva',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatFormFieldModule, MatSelectModule, MatInputModule],
  templateUrl: './gerencia-deportiva.component.html',
  styleUrls: []
})
export class GerenciaDeportivaComponent implements OnInit {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();
  formGerencia!: FormGroup;

  categorias = [
    {
      nombre: 'Accesorios para equipos',
      subcategorias: [
        { nombre: 'Mancuernas', detalles: ['Reposición', 'Reparación', 'Mantenimiento preventivo'] },
        { nombre: 'Barras', detalles: ['Reposición', 'Reparación', 'Mantenimiento preventivo'] },
        { nombre: 'Discos', detalles: ['Reposición', 'Reparación', 'Mantenimiento preventivo'] },
        { nombre: 'Bandas elásticas', detalles: ['Reposición', 'Reparación', 'Mantenimiento preventivo'] }
      ]
    },
    {
      nombre: 'Accesorios para clases',
      subcategorias: [
        { nombre: 'Tapetes', detalles: ['Reposición', 'Reparación', 'Limpieza'] },
        { nombre: 'Pelotas', detalles: ['Reposición', 'Reparación', 'Limpieza'] },
        { nombre: 'Step', detalles: ['Reposición', 'Reparación', 'Limpieza'] },
        { nombre: 'Cuerdas', detalles: ['Reposición', 'Reparación', 'Limpieza'] }
      ]
    },
    {
      nombre: 'Analizador de composición corporal',
      subcategorias: [
        { nombre: 'Software', detalles: ['Actualización', 'Reparación', 'Mantenimiento'] },
        { nombre: 'Hardware', detalles: ['Actualización', 'Reparación', 'Mantenimiento'] },
        { nombre: 'Accesorios', detalles: ['Actualización', 'Reparación', 'Mantenimiento'] }
      ]
    },
    {
      nombre: 'App Ultra',
      subcategorias: [
        { nombre: 'Altas de usuarios', detalles: ['Alta manual', 'Validación de membresía'] },
        { nombre: 'Errores de registro', detalles: ['Validación de membresía'] },
        { nombre: 'Problemas de acceso', detalles: ['Reseteo de contraseña'] }
      ]
    },
    {
      nombre: 'Instructores',
      subcategorias: [
        { nombre: 'Horarios', detalles: ['Solicitud de cambio'] },
        { nombre: 'Asignación de clases', detalles: ['Solicitud de cambio'] },
        { nombre: 'Capacitación', detalles: ['Capacitación pendiente', 'Evaluación'] }
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
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.gerencia, this.formularioValido);
    });
  }

  onCategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formGerencia.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.detallesDisponibles = [];

    limpiarCamposDependientes(this.formGerencia, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formGerencia.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formGerencia.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];

    limpiarCamposDependientes(this.formGerencia, ['detalle']);
  }


  enviarFormulario() {
    if (this.formGerencia.valid) {
      const payload = {
        departamento_id: 4,
        categoria: this.formGerencia.value.categoria,
        subcategoria: this.formGerencia.value.subcategoria,
        subsubcategoria: this.formGerencia.value.detalle,
        descripcion: this.formGerencia.value.descripcion,
        criticidad: this.formGerencia.value.criticidad
      };
      this.formularioValido.emit(payload);
    }
  }
}
