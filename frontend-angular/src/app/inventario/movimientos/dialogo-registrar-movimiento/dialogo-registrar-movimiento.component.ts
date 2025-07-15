// src/app/inventario/movimientos/dialogo-registrar-movimiento/dialogo-registrar-movimiento.component.ts

import { Component, Inject, OnInit } from '@angular/core';
import { FormArray, FormBuilder, FormControl, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { InventarioService } from '../../../services/inventario.service';
import { mostrarAlertaToast, mostrarAlertaStockInsuficiente } from 'src/app/utils/alertas';
import { Observable, startWith, map } from 'rxjs';
import { environment } from 'src/environments/environment';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { MatCheckboxModule } from '@angular/material/checkbox';

@Component({
  selector: 'app-dialogo-registrar-movimiento',
  standalone: true,
  templateUrl: './dialogo-registrar-movimiento.component.html',
  styleUrls: ['./dialogo-registrar-movimiento.component.css'],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatAutocompleteModule,
    FormsModule,
    ReactiveFormsModule,
    MatCheckboxModule
  ]
})
export class DialogoRegistrarMovimientoComponent implements OnInit {
  form: FormGroup;
  inventariosDisponibles: any[] = [];
  sucursales: any[] = [];
  esAdmin = false;
  cargando = false;

  // Nuevo: controla si solo filtra aparatos
  soloAparatos = false;

  // Observables para cada producto en el formarray
  inventarioFiltrado$: Observable<any[]>[] = [];

  constructor(
    private fb: FormBuilder,
    private dialogRef: MatDialogRef<DialogoRegistrarMovimientoComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private inventarioService: InventarioService,
    private http: HttpClient
  ) {
    this.inventariosDisponibles = data.inventariosDisponibles || [];
    this.form = this.fb.group({
      sucursal_id: [null],
      tipo_movimiento: ['entrada', Validators.required],
      observaciones: [''],
      productos: this.fb.array([])
    });
  }

  ngOnInit(): void {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    this.esAdmin = user?.rol === 'ADMINISTRADOR';

    if (this.esAdmin) {
      this.inventarioService.listarSucursales().subscribe({
        next: (data) => {
          this.sucursales = data;
          this.form.get('sucursal_id')?.setValue(this.sucursales[0]?.sucursal_id ?? null);
        }
      });
    } else {
      this.form.get('sucursal_id')?.setValue(user?.sucursal_id || 1);
    }

    if ((this.form.get('productos') as FormArray).length === 0) {
      this.agregarProducto();
    }
  }

  get productosFormArray(): FormArray {
    return this.form.get('productos') as FormArray;
  }

  // Actualiza todos los autocompletes cuando cambia el filtro de tipo de producto
  actualizarFiltrados() {
    this.inventarioFiltrado$ = this.productosFormArray.controls.map((_, i) =>
      this.filteredInventarios(i)
    );
  }

  // Observable de filtrado dinámico para cada input de inventario
  filteredInventarios(index: number): Observable<any[]> {
    const control = this.productosFormArray.at(index).get('inventarioControl') as FormControl;
    return control.valueChanges.pipe(
      startWith(''),
      map(valor => this._filtrarInventarios(valor))
    );
  }

  private _filtrarInventarios(valor: string): any[] {
    let lista = this.inventariosDisponibles;
    if (this.soloAparatos) {
      lista = lista.filter(i => (i.tipo || '').toLowerCase() === 'aparatos');
    } else {
      lista = lista.filter(i => (i.tipo || '').toLowerCase() !== 'aparatos');
    }
    const filtro = (valor || '').toLowerCase();
    return lista.filter(inv =>
      (inv.nombre || '').toLowerCase().includes(filtro) ||
      (inv.marca || '').toLowerCase().includes(filtro) ||
      (inv.proveedor || '').toLowerCase().includes(filtro) ||
      (inv.categoria || '').toLowerCase().includes(filtro)
    );
  }

  agregarProducto() {
    const grupo = this.fb.group({
      inventario_id: ['', Validators.required],
      inventarioControl: ['', Validators.required], // <- obligatorio para forzar selección
      unidad_medida: [{ value: '', disabled: true }],
      cantidad: [1, [Validators.required, Validators.min(1)]],
    });
    this.productosFormArray.push(grupo);

    // Inicializa observable de filtrado para el autocomplete
    this.actualizarFiltrados();

    // Cuando selecciona inventario, llena unidad automáticamente y fuerza que sea de la lista
    grupo.get('inventarioControl')?.valueChanges.subscribe(valor => {
      let inv;
      if (valor && typeof valor === 'object' && valor !== null && 'id' in (valor as object)) {
        inv = valor;
      }
    else if (valor) {
        inv = this.inventariosDisponibles.find(i => i.nombre === valor);
      }
      if (inv) {
        grupo.get('inventario_id')?.setValue(inv.id);
        grupo.get('unidad_medida')?.setValue(inv.unidad || '');
      } else {
        grupo.get('inventario_id')?.setValue('');
        grupo.get('unidad_medida')?.setValue('');
      }
    });


  }

  eliminarProducto(i: number) {
    this.productosFormArray.removeAt(i);
    this.actualizarFiltrados();
  }

  registrarMovimiento() {
    if (this.form.invalid) {
      mostrarAlertaToast('Por favor llena todos los campos.', 'warning');
      this.form.markAllAsTouched();
      return;
    }
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast('No autorizado.', 'error');
      return;
    }

    const sucursal_id = this.form.value.sucursal_id || user.sucursal_id;
    const tipo_movimiento = this.form.value.tipo_movimiento;
    const productos = this.productosFormArray.value.map((p: any) => ({
      inventario_id: p.inventario_id,
      unidad_medida: p.unidad_medida,
      cantidad: p.cantidad
    }));

    this.cargando = true;

    // Validación de stock solo para salidas
    if (tipo_movimiento === 'salida') {
      this.http.get<any[]>(`${environment.apiUrl}/inventario/existencias`).subscribe({
        next: existencias => {
          const sinStock = productos.some(item => {
            const ex = existencias.find(e =>
              String(e.inventario_id) === String(item.inventario_id) &&
              String(e.sucursal_id) === String(sucursal_id)
            );
            const stockDisponible = ex?.stock || 0;
            return item.cantidad > stockDisponible;
          });
          if (sinStock) {
            this.cargando = false;
            mostrarAlertaStockInsuficiente('algún producto seleccionado');
            return;
          } else {
            this._enviarMovimiento(sucursal_id, tipo_movimiento, productos, token);
          }
        },
        error: () => {
          this.cargando = false;
          mostrarAlertaToast('No se pudo validar existencias.', 'error');
        }
      });
    } else {
      this._enviarMovimiento(sucursal_id, tipo_movimiento, productos, token);
    }
  }

  private _enviarMovimiento(sucursal_id: number, tipo_movimiento: string, productos: any[], token: string) {
    const body = {
      tipo_movimiento,
      sucursal_id,
      usuario_id: JSON.parse(localStorage.getItem('user') || '{}').id,
      inventarios: productos,
      observaciones: this.form.value.observaciones
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
        mostrarAlertaToast('Error al registrar movimiento', 'error');
      }
    });
  }

  cancelar() {
    this.dialogRef.close(null);
  }

  // Usado para el displayWith del autocomplete, muestra solo el nombre
  displayInventario(inv?: any): string {
    return inv?.nombre || '';
  }

  // Limpia input si no eligieron de la lista (opcional, refuerza la selección controlada)
  onBlurInventario(i: number) {
    const control = this.productosFormArray.at(i).get('inventarioControl');
    const value = control?.value;
    if (typeof value === 'string' && value.trim() !== '') {
      control?.setValue('');
      this.productosFormArray.at(i).get('inventario_id')?.setValue('');
      this.productosFormArray.at(i).get('unidad_medida')?.setValue('');
    }
  }
}
