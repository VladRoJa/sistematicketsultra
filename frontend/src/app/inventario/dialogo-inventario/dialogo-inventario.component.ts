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
      // Se mapea a unidad_medida al guardar
      unidad: [data?.item?.unidad || '', Validators.required],

      // NUEVOS: esquema compra↔base
      unidad_compra: [data?.item?.unidad_compra || ''],                // p.ej. "caja" (opcional)
      factor_compra: [
        data?.item?.factor_compra ?? 1,
        [Validators.required, Validators.min(1)]
      ],

      stock_actual: [data?.item?.stock_actual ?? 0, [Validators.required, Validators.min(0)]],
      codigo_interno: [data?.item?.codigo_interno || ''],
      grupo_muscular: [data?.item?.grupo_muscular || ''],
      no_equipo: [data?.item?.no_equipo || ''],
      gasto_sem: [data?.item?.gasto_sem || 0],
      gasto_mes: [data?.item?.gasto_mes || 0],
      pedido_mes: [data?.item?.pedido_mes || 0],
      semana_pedido: [data?.item?.semana_pedido || ''],
      fecha_inventario: [data?.item?.fecha_inventario || ''],
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

    // grupo_muscular: requerido solo para aparatos
    const gmCtrl = this.form.get('grupo_muscular');
    if (esAparato) {
      gmCtrl?.setValidators([Validators.required]);
    } else {
      gmCtrl?.clearValidators();
    }
    gmCtrl?.updateValueAndValidity({ emitEvent: false });
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
    });
    this.catalogoService.getUnidades().subscribe(res => {
      this.unidades = res;
      this.unidadesFiltradas = res;
    });
    this.catalogoService.getTiposInventario().subscribe(res => {
      this.tiposInventario = res;
      this.tiposFiltrados = res;
    });
    this.catalogoService.getGrupoMuscular().subscribe(res => {
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

    // Aplica validadores en base al valor inicial (modo edición)
    this.aplicarValidadoresPorTipo(this.form.get('tipo')?.value);

    // Suscríbete a cambios de tipo y aplica validadores consistentes
    this.form.get('tipo')?.valueChanges.subscribe(val => {
      this.aplicarValidadoresPorTipo(val);
    });
  }

  private _toNumberOrNull(v: any): number | null {
    if (v === '' || v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  guardar() {
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
        unidad: 'Unidad',
        unidad_compra: 'Unidad de compra',
        factor_compra: 'Factor de compra',
        stock_actual: 'Stock Actual',
        codigo_interno: 'Código Interno',
        grupo_muscular: 'Grupo Muscular',
        no_equipo: 'No. de Equipo',
        gasto_sem: 'Gasto Semanal',
        gasto_mes: 'Gasto Mensual',
        pedido_mes: 'Pedido Mensual',
        semana_pedido: 'Semana de Pedido',
        fecha_inventario: 'Fecha de Inventario'
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

    // Payload limpio y compatible con backend (unidad_medida, compra↔base, trims, números)
    const body: any = {
      nombre: (f.nombre || '').trim(),
      descripcion: (f.descripcion || '').trim(),
      tipo: (f.tipo || '').trim(),
      marca: (f.marca || '').trim(),
      proveedor: (f.proveedor || '').trim(),
      categoria: (f.categoria || '').trim(),
      // Backend espera 'unidad_medida'
      unidad_medida: (f.unidad || '').trim(),

      // Compra ↔ base
      unidad_compra: (f.unidad_compra || '').trim(),
      factor_compra: (() => {
        const n = this._toNumberOrNull(f.factor_compra);
        // Si viene inválido o <1, que vaya 1 (el backend también refuerza)
        return n && n >= 1 ? n : 1;
      })(),

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

    if (this.modo === 'crear') {
      this.inventarioService.crearInventario(body).subscribe({
        next: () => {
          mostrarAlertaToast('Inventario creado correctamente.');
          this.dialogRef.close({ status: 'creado' });
        },
        error: () => {
          mostrarAlertaToast('Error al crear inventario', 'error');
        }
      });
    } else {
      this.inventarioService.editarInventario(this.data.item.id, body).subscribe({
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

  // Normaliza con la misma regla del backend (capitaliza y recorta)
private _normalizarCategoria(nombre: string): string {
  const n = (nombre || '').trim();
  if (!n) return '';
  // Capitaliza por palabra
  return n.toLowerCase().split(' ')
    .filter(Boolean)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

// Normaliza a minúsculas y sin espacios sobrantes
private _lc(v: any): string {
  return ((v ?? '') as string).toLowerCase().trim();
}

// ¿El texto escrito en el buscador NO existe aún en la lista de categorías?
categoriaEsNueva(): boolean {
  const val = this._lc(this.categoriaFiltroControl.value);
  if (!val) return false;
  return !this.categorias.some(c => this._lc(c.nombre) === val);
}

// Usar el valor del buscador como nueva categoría
usarCategoriaNuevaDesdeFiltro(): void {
  const texto = (this.categoriaFiltroControl.value || '').toString().trim();
  if (!texto) return;

  // Inserta la nueva categoría en memoria para que aparezca en el dropdown
  this.categorias = [...this.categorias, { id: Date.now(), nombre: texto }];
  this.categoriasFiltradas = [...this.categorias];

  // Asigna la categoría al formulario y limpia el buscador
  this.form.get('categoria')?.setValue(texto);
  this.categoriaFiltroControl.setValue('');

  // Opcional: feedback
  mostrarAlertaToast(`Categoría agregada: ${texto}`);
}


}
