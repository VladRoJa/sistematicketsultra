import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  FormArray, FormBuilder, FormControl, FormGroup,
  FormsModule, ReactiveFormsModule, Validators,
} from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatIconModule } from '@angular/material/icon';
import { Observable, map, startWith } from 'rxjs';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { InventarioService } from '../../../services/inventario.service';
import { mostrarAlertaStockInsuficiente, mostrarAlertaToast } from 'src/app/utils/alertas';
import { environment } from 'src/environments/environment';

interface ArticuloMovimiento {
  id: number;
  nombre: string;
  codigo_interno?: string;
  marca?: string;
  proveedor?: string;
  categoria?: string;
  tipo?: string;
  unidad_medida?: string;
}

@Component({
  selector: 'app-dialogo-registrar-movimiento',
  standalone: true,
  templateUrl: './dialogo-registrar-movimiento.component.html',
  styleUrls: ['./dialogo-registrar-movimiento.component.css'],
  imports: [
    CommonModule, ReactiveFormsModule, FormsModule, MatDialogModule,
    MatAutocompleteModule, MatIconModule,
  ],
})
export class DialogoRegistrarMovimientoComponent implements OnInit {
  form: FormGroup;
  inventariosDisponibles: ArticuloMovimiento[] = [];
  sucursales: { sucursal_id: number; sucursal: string }[] = [];
  sucursalAsignada = '';
  errorSucursales = false;
  esAdmin = false;
  cargando = false;

  tipoFiltro = 'todos';
  tiposDisponibles: string[] = ['todos'];
  inventarioFiltrado$: Observable<ArticuloMovimiento[]>[] = [];

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<DialogoRegistrarMovimientoComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { inventariosDisponibles?: ArticuloMovimiento[] },
    private inventarioService: InventarioService,
    private http: HttpClient,
  ) {
    this.inventariosDisponibles = data.inventariosDisponibles || [];
    this.form = this.fb.group({
      sucursal_id: [null, Validators.required],
      tipo_movimiento: ['entrada', Validators.required],
      observaciones: [''],
      productos: this.fb.array([]),
    });
  }

  ngOnInit(): void {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    this.esAdmin = user?.rol === 'ADMINISTRADOR';
    this.sucursalAsignada = String(user?.sucursal || user?.sucursal_nombre || user?.sucursal_id || '');

    if (this.esAdmin) {
      // Requiere elegir destino: jamás asumir ULTRA DEMO o la primera sucursal.
      this.inventarioService.listarSucursales().subscribe({
        next: (data) => {
          this.sucursales = data;
          this.errorSucursales = false;
        },
        error: () => {
          this.errorSucursales = true;
          mostrarAlertaToast('No se pudieron cargar las sucursales.', 'error');
        },
      });
    } else {
      this.form.get('sucursal_id')?.setValue(user?.sucursal_id ?? null);
    }

    this.tiposDisponibles = [
      'todos',
      ...Array.from(new Set(
        this.inventariosDisponibles
          .map(item => String(item.tipo || '').trim().toLowerCase())
          .filter(Boolean),
      )).sort(),
    ];

    this.agregarProducto();
  }

  get productosFormArray(): FormArray {
    return this.form.get('productos') as FormArray;
  }

  get productosSeleccionados(): number {
    return this.productosFormArray.controls.filter(grupo => !!grupo.get('inventario_id')?.value).length;
  }

  get nombreSucursalSeleccionada(): string {
    const id = this.form.get('sucursal_id')?.value;
    if (!id) return 'Sucursal pendiente';
    if (!this.esAdmin) return this.sucursalAsignada || `Sucursal #${id}`;
    return this.sucursales.find(s => String(s.sucursal_id) === String(id))?.sucursal || 'Sucursal pendiente';
  }

  get etiquetaTipoMovimiento(): string {
    return this.form.get('tipo_movimiento')?.value === 'salida' ? 'Salida' : 'Entrada';
  }

  cambiarTipoFiltro(tipo: string): void {
    this.tipoFiltro = tipo || 'todos';
    // El filtro sólo cambia opciones de búsqueda, no borra selecciones existentes.
    this.actualizarFiltrados();
  }

  private actualizarFiltrados(): void {
    this.inventarioFiltrado$ = this.productosFormArray.controls.map((_, i) => this.filteredInventarios(i));
  }

  filteredInventarios(index: number): Observable<ArticuloMovimiento[]> {
    const control = this.productosFormArray.at(index).get('inventarioControl') as FormControl;
    return control.valueChanges.pipe(
      startWith(control.value),
      map(valor => this.filtrarInventarios(valor)),
    );
  }

  private filtrarInventarios(valor: unknown): ArticuloMovimiento[] {
    const texto = typeof valor === 'string' ? valor.trim().toLowerCase() : '';
    return this.inventariosDisponibles.filter(inv => {
      const tipoCorrecto = this.tipoFiltro === 'todos' ||
        String(inv.tipo || '').trim().toLowerCase() === this.tipoFiltro;
      if (!tipoCorrecto) return false;

      const campos = [
        inv.codigo_interno, inv.nombre, inv.marca, inv.proveedor, inv.categoria,
      ];
      return !texto || campos.some(campo => String(campo || '').toLowerCase().includes(texto));
    }).slice(0, 40);
  }

  agregarProducto(): void {
    if (this.cargando) return;

    const grupo = this.fb.group({
      inventario_id: [null, Validators.required],
      inventarioControl: [null, Validators.required],
      unidad_medida: [{ value: '', disabled: true }],
      cantidad: [1, [Validators.required, Validators.min(1), Validators.pattern(/^[1-9]\d*$/)]],
    });

    grupo.get('inventarioControl')!.valueChanges.subscribe(valor => {
      // Escribir texto nuevo invalida el ID anterior; no guardar el producto equivocado.
      if (!valor || typeof valor === 'string') {
        grupo.get('inventario_id')?.setValue(null, { emitEvent: false });
        grupo.get('unidad_medida')?.setValue('', { emitEvent: false });
      }
    });

    this.productosFormArray.push(grupo);
    this.actualizarFiltrados();
  }

  eliminarProducto(index: number): void {
    if (this.cargando || this.productosFormArray.length <= 1) return;
    this.productosFormArray.removeAt(index);
    this.actualizarFiltrados();
  }

  onInventarioSeleccionado(inv: ArticuloMovimiento, index: number): void {
    const grupo = this.productosFormArray.at(index);
    const yaSeleccionado = this.productosFormArray.controls.some(
      (otro, i) => i !== index && String(otro.get('inventario_id')?.value) === String(inv.id),
    );

    if (yaSeleccionado) {
      grupo.get('inventarioControl')?.setValue(null);
      mostrarAlertaToast('Ese código ya está seleccionado en otro renglón.', 'warning');
      return;
    }

    grupo.get('inventario_id')?.setValue(inv.id, { emitEvent: false });
    grupo.get('unidad_medida')?.setValue(inv.unidad_medida || '', { emitEvent: false });
    grupo.get('inventarioControl')?.setValue(inv, { emitEvent: false });
  }

  articuloSeleccionado(index: number): ArticuloMovimiento | null {
    const control = this.productosFormArray.at(index).get('inventarioControl')?.value;
    return control && typeof control === 'object' ? control as ArticuloMovimiento : null;
  }

  displayInventario = (inv?: ArticuloMovimiento | string | null): string => {
    if (!inv) return '';
    if (typeof inv === 'string') return inv;
    return [inv.codigo_interno, inv.nombre, inv.marca].filter(Boolean).join(' · ');
  };

  registrarMovimiento(): void {
    if (this.cargando) return;
    if (this.form.invalid || this.productosFormArray.length === 0) {
      this.form.markAllAsTouched();
      mostrarAlertaToast('Selecciona la sucursal y todos los artículos de la lista.', 'warning');
      return;
    }

    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('No autorizado.', 'error');
      return;
    }

    const sucursal_id = this.form.value.sucursal_id;
    const tipo_movimiento = this.form.value.tipo_movimiento;
    const productos = this.productosFormArray.getRawValue().map((p: any) => ({
      inventario_id: p.inventario_id,
      unidad_medida: p.unidad_medida,
      cantidad: p.cantidad,
    }));

    this.cargando = true;

    if (tipo_movimiento === 'salida') {
      this.http.get<any[]>(`${environment.apiUrl}/inventario/existencias`).subscribe({
        next: existencias => {
          const sinStock = productos.some((item: any) => {
            const ex = existencias.find(e =>
              String(e.inventario_id) === String(item.inventario_id) &&
              String(e.sucursal_id) === String(sucursal_id),
            );
            return item.cantidad > (ex?.stock || 0);
          });
          if (sinStock) {
            this.cargando = false;
            mostrarAlertaStockInsuficiente('algún producto seleccionado');
            return;
          }
          this.enviarMovimiento(sucursal_id, tipo_movimiento, productos, token);
        },
        error: () => {
          this.cargando = false;
          mostrarAlertaToast('No se pudo validar existencias.', 'error');
        },
      });
    } else {
      this.enviarMovimiento(sucursal_id, tipo_movimiento, productos, token);
    }
  }

  private enviarMovimiento(sucursal_id: number, tipo_movimiento: string, productos: any[], token: string): void {
    const body = {
      tipo_movimiento,
      sucursal_id,
      usuario_id: JSON.parse(localStorage.getItem('user') || '{}').id,
      inventarios: productos,
      observaciones: this.form.value.observaciones,
    };
    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
    this.http.post(`${environment.apiUrl}/inventario/movimientos`, body, { headers }).subscribe({
      next: () => {
        this.cargando = false;
        this.dialogRef.close('ok');
        mostrarAlertaToast('Movimiento registrado correctamente.');
      },
      error: err => {
        this.cargando = false;
        mostrarAlertaToast(
          err?.error?.detail || err?.error?.error || 'Error al registrar movimiento',
          'error',
        );
      },
    });
  }

  cancelar(): void {
    if (!this.cargando) this.dialogRef.close(null);
  }
}
