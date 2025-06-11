import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, Input } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes, emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';


@Component({
  selector: 'app-marketing',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatFormFieldModule, MatSelectModule, MatInputModule],
  templateUrl: './marketing.component.html',
  styleUrls: []
})
export class MarketingComponent implements OnInit {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();
  formMarketing!: FormGroup;

  categorias = [
    {
      nombre: 'Material promocional',
      subcategorias: [
        { nombre: 'Volantes', detalles: ['Diseño', 'Impresión', 'Instalación'] },
        { nombre: 'Carteles', detalles: ['Diseño', 'Impresión', 'Instalación'] },
        { nombre: 'Banners', detalles: ['Diseño', 'Impresión', 'Instalación'] },
        { nombre: 'Lonas', detalles: ['Diseño', 'Impresión', 'Instalación'] }
      ]
    },
    {
      nombre: 'Vinilos y publicidad interna',
      subcategorias: [
        { nombre: 'Vidrios', detalles: ['Diseño', 'Colocación', 'Remoción'] },
        { nombre: 'Paredes', detalles: ['Diseño', 'Colocación', 'Remoción'] },
        { nombre: 'Espejos', detalles: ['Diseño', 'Colocación', 'Remoción'] },
        { nombre: 'Maquinaria', detalles: ['Diseño', 'Colocación', 'Remoción'] }
      ]
    },
    {
      nombre: 'Landing page',
      subcategorias: [
        { nombre: 'Actualización de contenido', detalles: ['Texto', 'Imagen', 'Video', 'Formulario'] },
        { nombre: 'Creación de nueva página', detalles: ['Texto', 'Imagen', 'Video', 'Formulario'] },
        { nombre: 'Modificación de diseño', detalles: ['Texto', 'Imagen', 'Video', 'Formulario'] }
      ]
    },
    {
      nombre: 'Etiquetas y logos deportivos',
      subcategorias: [
        { nombre: 'Equipos de piso', detalles: ['Diseño', 'Producción', 'Colocación'] },
        { nombre: 'Uniformes', detalles: ['Diseño', 'Producción', 'Colocación'] },
        { nombre: 'Accesorios', detalles: ['Diseño', 'Producción', 'Colocación'] }
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
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.marketing, this.formularioValido);
    });
  }

  onCategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formMarketing.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.detallesDisponibles = [];

    limpiarCamposDependientes(this.formMarketing, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formMarketing.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formMarketing.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];

    limpiarCamposDependientes(this.formMarketing, ['detalle']);
  }


  enviarFormulario() {
    if (this.formMarketing.valid) {
      const payload = {
        departamento_id: 3,
        categoria: this.formMarketing.value.categoria,
        subcategoria: this.formMarketing.value.subcategoria,
        subsubcategoria: this.formMarketing.value.detalle,
        descripcion: this.formMarketing.value.descripcion,
        criticidad: this.formMarketing.value.criticidad
      };
      this.formularioValido.emit(payload);
    }
  }
}
