import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
  selector: 'app-marketing',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './marketing.component.html',
  styleUrls: ['./marketing.component.css']
})
export class MarketingComponent implements OnInit {

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
    this.formMarketing = this.fb.group({
      categoria: ['', Validators.required],
      subcategoria: ['', Validators.required],
      detalle: ['', Validators.required],
      descripcion: ['', Validators.required],
      criticidad: [null, Validators.required]
    });
  }

  onCategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formMarketing.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.formMarketing.patchValue({ subcategoria: '', detalle: '' });
    this.detallesDisponibles = [];
  }

  onSubcategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formMarketing.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formMarketing.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];
    this.formMarketing.patchValue({ detalle: '' });
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
