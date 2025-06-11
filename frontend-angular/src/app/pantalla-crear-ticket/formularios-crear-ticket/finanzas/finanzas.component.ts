// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-crear-ticket\formularios-crear-ticket\finanzas\finanzas.component.ts

import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes, emitirPayloadFormulario, DEPARTAMENTO_IDS } from 'src/app/utils/formularios.helper';

@Component({
  selector: 'app-finanzas',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, MatFormFieldModule, MatSelectModule, MatInputModule],
  templateUrl: './finanzas.component.html',
  styleUrls: []
})
export class FinanzasComponent implements OnInit {
  
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();
  formFinanzas!: FormGroup;

  categorias = [
    {
      nombre: 'Pagos a proveedores',
      subcategorias: [
        { nombre: 'Servicios', detalles: ['Pago único', 'Contrato mensual', 'Anticipo', 'Regularización de saldo'] },
        { nombre: 'Insumos', detalles: ['Pago único', 'Contrato mensual', 'Anticipo', 'Regularización de saldo'] },
        { nombre: 'Arrendamientos', detalles: ['Pago único', 'Contrato mensual', 'Anticipo', 'Regularización de saldo'] },
        { nombre: 'Honorarios', detalles: ['Pago único', 'Contrato mensual', 'Anticipo', 'Regularización de saldo'] },
        { nombre: 'Mantenimiento externo', detalles: ['Pago único', 'Contrato mensual', 'Anticipo', 'Regularización de saldo'] },
        { nombre: 'Publicidad / Marketing', detalles: ['Pago único', 'Contrato mensual', 'Anticipo', 'Regularización de saldo'] }
      ]
    },
    {
      nombre: 'Reembolsos',
      subcategorias: [
        { nombre: 'Viáticos', detalles: ['Factura', 'Ticket', 'Sin comprobante'] },
        { nombre: 'Compras menores', detalles: ['Factura', 'Ticket', 'Sin comprobante'] },
        { nombre: 'Gastos operativos', detalles: ['Factura', 'Ticket', 'Sin comprobante'] },
        { nombre: 'Capacitaciones', detalles: ['Factura', 'Ticket', 'Sin comprobante'] },
        { nombre: 'Emergencias', detalles: ['Factura', 'Ticket', 'Sin comprobante'] }
      ]
    },
    {
      nombre: 'Nómina y personal',
      subcategorias: [
        { nombre: 'Finiquitos', detalles: ['Pago extraordinario', 'Pago programado', 'Corrección de cálculo'] },
        { nombre: 'Liquidaciones', detalles: ['Pago extraordinario', 'Pago programado', 'Corrección de cálculo'] },
        { nombre: 'Préstamos personales', detalles: ['Pago extraordinario', 'Pago programado'] },
        { nombre: 'Ajustes de nómina', detalles: ['Pago extraordinario', 'Corrección de cálculo'] },
        { nombre: 'Bonos e incentivos', detalles: ['Pago extraordinario', 'Pago programado'] }
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
      emitirPayloadFormulario(this.parentForm, DEPARTAMENTO_IDS.finanzas, this.formularioValido);
    });
  }

  onCategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formFinanzas.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.detallesDisponibles = [];

    limpiarCamposDependientes(this.formFinanzas, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formFinanzas.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formFinanzas.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];

    limpiarCamposDependientes(this.formFinanzas, ['detalle']);
  }


  enviarFormulario() {
    if (this.parentForm.valid) {
      const payload = {
        departamento_id: 2,
        categoria: this.parentForm.value.categoria,
        subcategoria: this.parentForm.value.subcategoria,
        subsubcategoria: this.parentForm.value.detalle,
        descripcion: this.parentForm.value.descripcion
      };
      this.formularioValido.emit(payload);
    }
  }
}
