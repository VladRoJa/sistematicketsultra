import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output, Input } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';

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

  categoriasDisponibles = [
    'Computadora Recepción', 'Computadora Gerente',
    'Torniquete 1 (Junto a Recepcion)', 'Torniquete 2 (Retirado de recepcion)',
    'Sonido Ambiental (Bocinas, Amplificador)', 'Sonido en Salones',
    'Tablet 1 (Computadora recepcion)', 'Tablet 2 (Computadora Gerente)',
    'Impresora multifuncional', 'Impresora termica (Recepcion)',
    'Impresora termica (Gerente)', 'Terminal (Recepcion)',
    'Terminal (Gerente)', 'Alarma', 'Teléfono', 'Internet', 'Cámaras'
  ];

  subcategoriasDisponibles = [
    'Alta de usuario', 'Baja de usuario',
    'Reparación', 'Configuración',
    'Compra de equipo', 'Otro'
  ];

  detallesDisponibles = [
    'Urgente', 'Preventivo',
    'Correctivo', 'Programado'
  ];

  constructor(private fb: FormBuilder) {}

  ngOnInit(): void {
    if (!this.parentForm) return;

    this.parentForm.addControl('categoria', this.fb.control('', Validators.required));
    this.parentForm.addControl('subcategoria', this.fb.control('', Validators.required));
    this.parentForm.addControl('detalle', this.fb.control('', Validators.required));
    this.parentForm.addControl('descripcion', this.fb.control('', Validators.required));
  }

  onCategoriaChange(): void {
    this.parentForm.patchValue({ subcategoria: '', detalle: '' });
  }

  onSubcategoriaChange(): void {
    this.parentForm.patchValue({ detalle: '' });
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
