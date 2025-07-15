// src/app/inventario/dialogo-inventario/dialogo-inventario.component.ts

import { Component, Inject, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormControl } from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule, MatDialog } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { InventarioService } from '../../services/inventario.service';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { ModalAlertaCamposRequeridosComponent } from 'src/app/shared/modal-alerta-campos-requeridos/modal-alerta-campos-requeridos.component';
import { CatalogoService, CatalogoElemento } from '../../services/catalogo.service';

@Component({
  selector: 'app-dialogo-inventario',
  standalone: true,
  templateUrl: './dialogo-inventario.component.html',
  styleUrls: ['./dialogo-inventario.component.css'],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule,
  ]
})
export class DialogoInventarioComponent implements OnInit {
  form: FormGroup;
  modo: 'crear' | 'editar';
  sucursales: any[] = [];

  // Catálogos completos
  marcas: CatalogoElemento[] = [];
  proveedores: CatalogoElemento[] = [];
  categorias: CatalogoElemento[] = [];
  unidades: CatalogoElemento[] = [];
  tiposInventario: CatalogoElemento[] = [];
  gruposMusculares: CatalogoElemento[] = [];

  // Filtros y opciones filtradas
  marcaFiltroControl = new FormControl('');
  proveedorFiltroControl = new FormControl('');
  categoriaFiltroControl = new FormControl('');
  unidadFiltroControl = new FormControl('');
  tipoFiltroControl = new FormControl('');
  grupoMuscularFiltroControl = new FormControl('');

  marcasFiltradas: CatalogoElemento[] = [];
  proveedoresFiltradas: CatalogoElemento[] = [];
  categoriasFiltradas: CatalogoElemento[] = [];
  unidadesFiltradas: CatalogoElemento[] = [];
  tiposFiltrados: CatalogoElemento[] = [];
  gruposMuscularesFiltrados: CatalogoElemento[] = [];

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<DialogoInventarioComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private inventarioService: InventarioService,
    private catalogoService: CatalogoService,
    private dialog: MatDialog,
  ) {
    this.modo = data?.modo || 'crear';

    this.form = this.fb.group({
      nombre: [data?.item?.nombre || '', Validators.required],
      descripcion: [data?.item?.descripcion || ''],
      tipo: [data?.item?.tipo || '', Validators.required],
      marca: [data?.item?.marca || '', Validators.required],
      proveedor: [data?.item?.proveedor || ''],
      categoria: [data?.item?.categoria || '', Validators.required],
      unidad: [data?.item?.unidad || '', Validators.required],
      stock_actual: [data?.item?.stock_actual ?? 0, [Validators.required, Validators.min(0)]],
      codigo_interno: [data?.item?.codigo_interno || '', Validators.required],
      grupo_muscular: [data?.item?.grupo_muscular || '', Validators.required],
      no_equipo: [data?.item?.no_equipo || ''],
      gasto_sem: [data?.item?.gasto_sem || 0],
      gasto_mes: [data?.item?.gasto_mes || 0],
      pedido_mes: [data?.item?.pedido_mes || 0],
      semana_pedido: [data?.item?.semana_pedido || ''],
      fecha_inventario: [data?.item?.fecha_inventario || ''],
    });
  }

  ngOnInit(): void {
    // Cargar catálogos y setear filtrados iniciales
    this.catalogoService.getMarcas().subscribe(res => {
      this.marcas = res;
      this.marcasFiltradas = res;
    });
    this.catalogoService.getProveedores().subscribe(res => {
      this.proveedores = res;
      this.proveedoresFiltradas = res;
    });
    this.catalogoService.getCategorias().subscribe(res => {
      this.categorias = res;
      this.categoriasFiltradas = res;
    });
    this.catalogoService.getUnidades().subscribe(res => {
      this.unidades = res;
      this.unidadesFiltradas = res;
    });
    this.catalogoService.getTiposInventario().subscribe(res => {
      this.tiposInventario = res;
      this.tiposFiltrados = res;
    });
    this.catalogoService.getGrupoMucular().subscribe(res => {
      this.gruposMusculares = res;
      this.gruposMuscularesFiltrados = res;
    });

    // Buscadores para cada select
    this.marcaFiltroControl.valueChanges.subscribe(val => {
      const v = (val || '').toLowerCase();
      this.marcasFiltradas = this.marcas.filter(m => m.nombre.toLowerCase().includes(v));
    });
    this.proveedorFiltroControl.valueChanges.subscribe(val => {
      const v = (val || '').toLowerCase();
      this.proveedoresFiltradas = this.proveedores.filter(m => m.nombre.toLowerCase().includes(v));
    });
    this.categoriaFiltroControl.valueChanges.subscribe(val => {
      const v = (val || '').toLowerCase();
      this.categoriasFiltradas = this.categorias.filter(m => m.nombre.toLowerCase().includes(v));
    });
    this.unidadFiltroControl.valueChanges.subscribe(val => {
      const v = (val || '').toLowerCase();
      this.unidadesFiltradas = this.unidades.filter(m => m.nombre.toLowerCase().includes(v));
    });
    this.tipoFiltroControl.valueChanges.subscribe(val => {
      const v = (val || '').toLowerCase();
      this.tiposFiltrados = this.tiposInventario.filter(m => m.nombre.toLowerCase().includes(v));
    });
    this.grupoMuscularFiltroControl.valueChanges.subscribe(val => {
      const v = (val || '').toLowerCase();
      this.gruposMuscularesFiltrados = this.gruposMusculares.filter(m => m.nombre.toLowerCase().includes(v));
    });

    // Grupo muscular solo requerido si tipo === 'aparato'
    this.form.get('tipo')?.valueChanges.subscribe(val => {
      if (val === 'aparato') {
        this.form.get('grupo_muscular')?.setValidators([Validators.required]);
      } else {
        this.form.get('grupo_muscular')?.clearValidators();
        this.form.get('grupo_muscular')?.setValue('');
      }
      this.form.get('grupo_muscular')?.updateValueAndValidity();
    });
  }

  guardar() {
    if (this.form.invalid) {
      this.dialog.open(ModalAlertaCamposRequeridosComponent);
      this.form.markAllAsTouched();
      return;
    }
    const valores = this.form.value;
    if (this.modo === 'crear') {
      this.inventarioService.crearInventario(valores).subscribe({
        next: () => {
          mostrarAlertaToast('Inventario creado correctamente.');
          this.dialogRef.close({ status: 'creado' });
        },
        error: () => {
          mostrarAlertaToast('Error al crear inventario', 'error');
        }
      });
    } else {
      this.inventarioService.editarInventario(this.data.item.id, valores).subscribe({
        next: () => {
          mostrarAlertaToast('Inventario actualizado correctamente.');
          this.dialogRef.close({ status: 'actualizado' });
        },
        error: () => {
          mostrarAlertaToast('Error al actualizar inventario', 'error');
        }
      });
    }
  }

  cancelar() {
    this.dialogRef.close(null);
  }
}
