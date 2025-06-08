import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
  selector: 'app-sistemas',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './sistemas.component.html',
  styleUrls: ['./sistemas.component.css']
})
export class SistemasComponent implements OnInit {

  @Output() formularioValido = new EventEmitter<any>();
  formSistemas!: FormGroup;

  categorias = [
    'Computadora Recepción', 'Computadora Gerente',
    'Torniquete 1 (Junto a Recepcion)', 'Torniquete 2 (Retirado de recepcion)',
    'Sonido Ambiental (Bocinas, Amplificador)', 'Sonido en Salones',
    'Tablet 1 (Computadora recepcion)', 'Tablet 2 (Computadora Gerente)',
    'Impresora multifuncional', 'Impresora termica (Recepcion)',
    'Impresora termica (Gerente)', 'Terminal (Recepcion)',
    'Terminal (Gerente)', 'Alarma', 'Teléfono', 'Internet', 'Cámaras'
  ];

  subcategorias = [
    'Alta de usuario', 'Baja de usuario',
    'Reparación', 'Configuración',
    'Compra de equipo', 'Otro'
  ];

  detalles = [
    'Urgente', 'Preventivo',
    'Correctivo', 'Programado'
  ];

  constructor(private fb: FormBuilder) {}

  ngOnInit(): void {
    this.formSistemas = this.fb.group({
      categoria: ['', Validators.required],
      subcategoria: ['', Validators.required],
      detalle: ['', Validators.required],
      descripcion: ['', Validators.required],
      criticidad: [null, Validators.required]
    });
  }

  enviarFormulario() {
    if (this.formSistemas.valid) {
      const payload = {
        departamento_id: 7,
        categoria: this.formSistemas.value.categoria,
        subcategoria: this.formSistemas.value.subcategoria,
        subsubcategoria: this.formSistemas.value.detalle,
        descripcion: this.formSistemas.value.descripcion,
        criticidad: this.formSistemas.value.criticidad
      };
      this.formularioValido.emit(payload);
    }
  }
}
