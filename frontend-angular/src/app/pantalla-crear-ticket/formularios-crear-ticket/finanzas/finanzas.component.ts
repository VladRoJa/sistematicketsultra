// finanzas.component.ts

import { CommonModule } from '@angular/common';
import { Component, EventEmitter, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
  selector: 'app-finanzas',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './finanzas.component.html',
  styleUrls: ['./finanzas.component.css']
})
export class FinanzasComponent implements OnInit {

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
    this.formFinanzas = this.fb.group({
      categoria: ['', Validators.required],
      subcategoria: ['', Validators.required],
      detalle: ['', Validators.required],
      descripcion: ['', Validators.required],
      criticidad: [null, Validators.required]
    });
  }

  onCategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formFinanzas.value.categoria);
    this.subcategoriasDisponibles = catSeleccionada ? catSeleccionada.subcategorias : [];
    this.formFinanzas.patchValue({ subcategoria: '', detalle: '' });
    this.detallesDisponibles = [];
  }

  onSubcategoriaChange() {
    const catSeleccionada = this.categorias.find(c => c.nombre === this.formFinanzas.value.categoria);
    const subcatSeleccionada = catSeleccionada?.subcategorias.find(s => s.nombre === this.formFinanzas.value.subcategoria);
    this.detallesDisponibles = subcatSeleccionada ? subcatSeleccionada.detalles : [];
    this.formFinanzas.patchValue({ detalle: '' });
  }

  enviarFormulario() {
    if (this.formFinanzas.valid) {
      const payload = {
        departamento_id: 2,
        categoria: this.formFinanzas.value.categoria,
        subcategoria: this.formFinanzas.value.subcategoria,
        subsubcategoria: this.formFinanzas.value.detalle,
        descripcion: this.formFinanzas.value.descripcion,
        criticidad: this.formFinanzas.value.criticidad
      };
      this.formularioValido.emit(payload);
    }
  }
}
