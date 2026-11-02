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
import { MantenimientoEquiposService } from '../../services/mantenimiento-equipos.service';
import { FamiliaEquipoDTO } from '../../types/ticket';
import { normalizarTipoInventario } from '../movimientos/tipos-inventario.helper';

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
  guardando = false;
  sucursales: any[] = [];

  // Catálogos completos
  marcas: CatalogoElemento[] = [];
  proveedores: CatalogoElemento[] = [];
  categorias: CatalogoElemento[] = [];
  unidades: CatalogoElemento[] = [];
  tiposInventario: CatalogoElemento[] = [];
  gruposMusculares: CatalogoElemento[] = [];
  familiasEquipo: FamiliaEquipoDTO[] = [];

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
    private mantenimientoEquiposService: MantenimientoEquiposService,
    private dialog: MatDialog,
  ) {
    this.modo = data?.modo || 'crear';

    this.form = this.fb.group({
      nombre: [data?.item?.nombre || '', Validators.required],
      descripcion: [data?.item?.descripcion || ''],
      tipo: [data?.item?.tipo || '', Validators.required],
      familia_equipo_id: [data?.item?.familia_equipo_id ?? null],
      marca: [data?.item?.marca || '', Validators.required],
      proveedor: [data?.item?.proveedor || ''],
      categoria: [data?.item?.categoria || '', Validators.required],
      categoria_inventario_id: [
        data?.item?.categoria_inventario_id ?? null,
        this.modo === 'crear' ? [Validators.required] : [],
      ],
      // Se mapea a unidad_medida al guardar
      unidad: [data?.item?.unidad || '', Validators.required],

      // NUEVOS: esquema compra↔base
      unidad_compra: [data?.item?.unidad_compra || ''],                // p.ej. "caja" (opcional)
      factor_compra: [
        data?.item?.factor_compra ?? 1,
        [Validators.required, Validators.min(1), Validators.pattern(/^[1-9]\d*$/)]
      ],

      codigo_interno: [data?.item?.codigo_interno || ''],
      grupo_muscular: [data?.item?.grupo_muscular || ''],
      no_equipo: [data?.item?.no_equipo || ''],
      gasto_sem: [data?.item?.gasto_sem || 0],
      gasto_mes: [data?.item?.gasto_mes || 0],
      pedido_mes: [data?.item?.pedido_mes || 0],
      semana_pedido: [data?.item?.semana_pedido || ''],
      subcategoria: [data?.item?.subcategoria || '']
    });
  }

  // 1) Helper para aplicar validadores según tipo
  private aplicarValidadoresPorTipo(tipoValor: any) {
    const tipo = (tipoValor || '').toString().trim().toLowerCase();

    // Normalizamos sinónimos/plurales
    const esAparato = (tipo === 'aparato' || tipo === 'aparatos');
    const esSistemaODispositivo = (
      tipo === 'sistema' || tipo === 'sistemas' ||
      tipo === 'dispositivo' || tipo === 'dispositivos'
    );

    // codigo_interno: requerido para aparatos y sistemas/dispositivos
    const codigoCtrl = this.form.get('codigo_interno');
    if (esAparato || esSistemaODispositivo) {
      codigoCtrl?.setValidators([Validators.required]);
    } else {
      codigoCtrl?.clearValidators();
    }
    codigoCtrl?.updateValueAndValidity({ emitEvent: false });

    // Grupo muscular es descriptivo: no todos los aparatos tienen uno
    // (racks, bancas, equipo aeróbico). La familia sí alimenta Tickets.
    const familiaCtrl = this.form.get('familia_equipo_id');
    if (esAparato && this.modo === 'crear') {
      familiaCtrl?.setValidators([Validators.required]);
    } else {
      familiaCtrl?.clearValidators();
    }
    familiaCtrl?.updateValueAndValidity({ emitEvent: false });

    if (!esAparato) {
      familiaCtrl?.setValue(null, { emitEvent: false });
      this.form.get('grupo_muscular')?.setValue('', { emitEvent: false });
    }
    if (!esAparato && !esSistemaODispositivo) {
      this.form.get('no_equipo')?.setValue('', { emitEvent: false });
    }
  }

  get esTipoAparato(): boolean {
    const tipo = String(this.form.get('tipo')?.value || '').trim().toLowerCase();
    return tipo === 'aparato' || tipo === 'aparatos';
  }

  get requiereCodigoInterno(): boolean {
    const tipo = String(this.form.get('tipo')?.value || '').trim().toLowerCase();
    return ['aparato', 'aparatos', 'sistema', 'sistemas', 'dispositivo', 'dispositivos']
      .includes(tipo);
  }

  get detalleConversionCompra(): string {
    const valores = this.form.value;
    if (!valores.unidad_compra || !valores.factor_compra) {
      return '';
    }
    return `1 ${valores.unidad_compra} = ${valores.factor_compra} ${valores.unidad || 'pieza'}`;
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
    this.catalogoService.getCategoriasInventario().subscribe(res => {
      this.categorias = res;
      this.categoriasFiltradas = res;
      // Al editar registros legacy sin ID, preseleccionar si su nombre
      // coincide inequívocamente con una categoría del catálogo oficial.
      if (this.modo === 'editar' && !this.form.get('categoria_inventario_id')?.value) {
        const nombre = String(this.form.get('categoria')?.value || '').trim().toLowerCase();
        const coincidencias = res.filter(item => item.nombre.trim().toLowerCase() === nombre);
        if (coincidencias.length === 1) {
          this.form.get('categoria_inventario_id')?.setValue(coincidencias[0].id);
        }
      }
    });
    this.catalogoService.getUnidades().subscribe(res => {
      this.unidades = res;
      this.unidadesFiltradas = res;
    });
    this.catalogoService.getTiposInventario().subscribe(res => {
      // Presentar una opción por clase, sin modificar el catálogo legado.
      const opciones = new Map<string, CatalogoElemento>();
      for (const tipo of res) {
        const nombre = normalizarTipoInventario(tipo.nombre);
        if (!nombre || opciones.has(nombre)) continue;
        opciones.set(nombre, {
          ...tipo,
          nombre: nombre.charAt(0).toUpperCase() + nombre.slice(1),
        });
      }
      this.tiposInventario = [...opciones.values()];
      this.tiposFiltrados = this.tiposInventario;
    });
    this.catalogoService.getGrupoMuscular().subscribe(res => {
      this.gruposMusculares = res;
      this.gruposMuscularesFiltrados = res;
    });
    this.mantenimientoEquiposService.obtenerFamilias().subscribe({
      next: (familias) => {
        this.familiasEquipo = familias;
      },
      error: () => {
        mostrarAlertaToast('No se pudieron cargar las familias de equipo.', 'error');
      },
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

    // Aplica validadores en base al valor inicial (modo edición)
    this.aplicarValidadoresPorTipo(this.form.get('tipo')?.value);

    // Suscríbete a cambios de tipo y aplica validadores consistentes
    this.form.get('tipo')?.valueChanges.subscribe(val => {
      this.aplicarValidadoresPorTipo(val);
    });
    // ID oficial como fuente única de la categoría visible y persistida.
    this.form.get('categoria_inventario_id')?.valueChanges.subscribe(id => {
      const categoria = this.categorias.find(item => item.id === Number(id));
      this.form.get('categoria')?.setValue(categoria?.nombre || '', { emitEvent: false });
    });
  }

  get categoriaOficialSeleccionada(): CatalogoElemento | undefined {
    const value = Number(this.form.get('categoria_inventario_id')?.value);
    return this.categorias.find(item => item.id === value);
  }

  private _toNumberOrNull(v: any): number | null {
    if (v === '' || v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  guardar() {
    if (this.guardando) return;
    if (this.form.invalid) {
      // Encuentra los campos requeridos que faltan
      const camposFaltantes: string[] = [];
      const nombresLegibles: Record<string, string> = {
        nombre: 'Nombre',
        descripcion: 'Descripción',
        tipo: 'Tipo',
        marca: 'Marca',
        proveedor: 'Proveedor',
        categoria: 'Categoría',
        categoria_inventario_id: 'Categoría oficial',
        familia_equipo_id: 'Familia de equipo',
        unidad: 'Unidad',
        unidad_compra: 'Unidad de compra',
        factor_compra: 'Factor de compra',
        codigo_interno: 'Código Interno',
        grupo_muscular: 'Grupo Muscular',
        no_equipo: 'No. de Equipo',
        gasto_sem: 'Gasto Semanal',
        gasto_mes: 'Gasto Mensual',
        pedido_mes: 'Pedido Mensual',
        semana_pedido: 'Semana de Pedido',
      };

      Object.keys(this.form.controls).forEach(key => {
        const control = this.form.get(key);
        if (control && control.invalid && control.errors?.['required']) {
          camposFaltantes.push(nombresLegibles[key] || key);
        }
      });

      mostrarAlertaToast(
        `❗Faltan datos obligatorios: ${camposFaltantes.join(', ')}`,
        'error'
      );
      this.form.markAllAsTouched();
      return;
    }

    const f = this.form.value;
    const categoriaOficial = this.categoriaOficialSeleccionada;
    if (f.categoria_inventario_id != null && !categoriaOficial) {
      mostrarAlertaToast('Selecciona una categoría del catálogo oficial.', 'error');
      return;
    }

    // Payload limpio y compatible con backend (unidad_medida, compra↔base, trims, números)
    const body: any = {
      nombre: (f.nombre || '').trim(),
      descripcion: (f.descripcion || '').trim(),
      tipo: (f.tipo || '').trim(),
      marca: (f.marca || '').trim(),
      proveedor: (f.proveedor || '').trim(),
      categoria: categoriaOficial?.nombre || (f.categoria || '').trim(),
      categoria_inventario_id: categoriaOficial?.id ?? null,
      familia_equipo_id: this.esTipoAparato
        ? this._toNumberOrNull(f.familia_equipo_id)
        : null,
      // Backend espera 'unidad_medida'
      unidad_medida: (f.unidad || '').trim(),

      // Compra ↔ base
      unidad_compra: (f.unidad_compra || '').trim(),
      factor_compra: Number(f.factor_compra),

      // Otros campos
      subcategoria: (f.subcategoria || '').trim(),
      codigo_interno: (f.codigo_interno || '').trim().toUpperCase() || '',
      grupo_muscular: (f.grupo_muscular || '').trim(),
      no_equipo: (f.no_equipo || '').trim(),

      // Numéricos opcionales → null si vienen vacíos
      gasto_sem: this._toNumberOrNull(f.gasto_sem),
      gasto_mes: this._toNumberOrNull(f.gasto_mes),
      pedido_mes: this._toNumberOrNull(f.pedido_mes),
      semana_pedido: (f.semana_pedido || '').trim(),
      // No enviamos stock_actual ni fecha_inventario (los maneja backend)
    };

    this.guardando = true;
    if (this.modo === 'crear') {
      this.inventarioService.crearInventario(body).subscribe({
        next: () => {
          this.guardando = false;
          mostrarAlertaToast('Inventario creado correctamente.');
          this.dialogRef.close({ status: 'creado' });
        },
        error: (error) => this.mostrarErrorGuardado(error),
      });
    } else {
      this.inventarioService.editarInventario(this.data.item.id, body).subscribe({
        next: () => {
          this.guardando = false;
          mostrarAlertaToast('Inventario actualizado correctamente.');
          this.dialogRef.close({ status: 'actualizado' });
        },
        error: (error) => this.mostrarErrorGuardado(error),
      });
    }
  }

  private mostrarErrorGuardado(error: any): void {
    this.guardando = false;
    const detalle = error?.error?.detail || error?.error?.error
      || 'No se pudo guardar el artículo.';
    mostrarAlertaToast(String(detalle), 'error');
  }

  cancelar() {
    if (!this.guardando) this.dialogRef.close(null);
  }

}
