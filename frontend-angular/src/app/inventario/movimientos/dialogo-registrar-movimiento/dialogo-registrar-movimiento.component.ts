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
import { seleccionarObjetoAutocomplete } from 'src/app/utils/autocomplete.helper';

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
    MatCheckboxModule
  ]
})
export class DialogoRegistrarMovimientoComponent implements OnInit {
  form: FormGroup;
  inventariosDisponibles: any[] = [];
  sucursales: any[] = [];
  esAdmin = false;
  cargando = false;

  tipoFiltro: string = 'todos';
  tiposDisponibles: string[] = ['todos'];
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

    // Log inventarios recibidos
    console.log('Inventarios recibidos en el diálogo:', this.inventariosDisponibles);

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

    this.actualizarTiposDisponibles();

    if (this.productosFormArray.length === 0) {
      this.agregarProducto();
    }
  }

  get productosFormArray(): FormArray {
    return this.form.get('productos') as FormArray;
  }

  actualizarTiposDisponibles() {
    // Normaliza todo a minúscula
    const tiposSet = new Set(
      this.inventariosDisponibles
        .map(i => (i.tipo || '').trim().toLowerCase())
        .filter(t => !!t)
    );

    // Log de los tipos detectados
    console.log('Tipos únicos detectados:', Array.from(tiposSet));

    this.tiposDisponibles = ['todos', ...Array.from(tiposSet)];
    // Corrige tipoFiltro si no existe
    if (!this.tiposDisponibles.includes(this.tipoFiltro)) {
      this.tipoFiltro = 'todos';
    }
    this.actualizarFiltrados();
  }


  onTipoFiltroChange() {
    this.actualizarFiltrados();
    // Limpia autocompletes y sus valores
    this.productosFormArray.controls.forEach(grupo => {
      grupo.get('inventarioControl')?.setValue('');
      grupo.get('inventario_id')?.setValue('');
      grupo.get('unidad_medida')?.setValue('');
    });
  }

  actualizarFiltrados() {
    this.inventarioFiltrado$ = this.productosFormArray.controls.map((_, i) =>
      this.filteredInventarios(i)
    );
  }

  filteredInventarios(index: number): Observable<any[]> {
    const control = this.productosFormArray.at(index).get('inventarioControl') as FormControl;
    return control.valueChanges.pipe(
      startWith(''),
      map(valor => this._filtrarInventarios(valor))
    );
  }

    private _filtrarInventarios(valor: any): any[] {
    let lista = this.inventariosDisponibles;
    if (this.tipoFiltro && this.tipoFiltro !== 'todos') {
      lista = lista.filter(i =>
        (i.tipo || '').trim().toLowerCase() === this.tipoFiltro
      );
    }
    // SOLO buscar si valor es string, si es objeto, valor = ''
    const filtro = (typeof valor === 'string' ? valor.toLowerCase() : '');
    return lista.filter(inv =>
      (inv.nombre || '').toLowerCase().includes(filtro) ||
      (inv.marca || '').toLowerCase().includes(filtro) ||
      (inv.proveedor || '').toLowerCase().includes(filtro) ||
      (inv.categoria || '').toLowerCase().includes(filtro) ||
      (inv.codigo_interno || '').toLowerCase().includes(filtro)
    );
  }



  agregarProducto() {
    const grupo = this.fb.group({
      inventario_id: ['', Validators.required],
      inventarioControl: ['', Validators.required],
      unidad_medida: [{ value: '', disabled: true }],
      cantidad: [1, [Validators.required, Validators.min(1)]],
    });
    this.productosFormArray.push(grupo);
    this.inventarioFiltrado$.push(this.filteredInventarios(this.productosFormArray.length - 1));

    
    grupo.get('inventarioControl')!.valueChanges.subscribe(valor => {
      if (valor === '') {
        grupo.get('inventario_id')?.setValue('', { emitEvent: false });
        grupo.get('unidad_medida')?.setValue('', { emitEvent: false });
      }
    });
  }





  eliminarProducto(i: number) {
    this.productosFormArray.removeAt(i);
    this.inventarioFiltrado$.splice(i, 1);
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

  displayInventario = (inv?: any): string => {
    // Soporta string o el objeto real
    if (!inv) return '';
    if (typeof inv === 'string') return inv;
    return inv.nombre || '';
  };

  // Limpia si el usuario se sale sin seleccionar objeto válido (no deja valores colgados)
  onBlurInventario(i: number) {
    const control = this.productosFormArray.at(i).get('inventarioControl');
    const value = control?.value;
    if (typeof value === 'string' && value.trim() !== '') {
      // Busca en inventarios ignorando mayúsculas
      const encontrado = this.inventariosDisponibles.find(j =>
        j.nombre.trim().toLowerCase() === value.trim().toLowerCase()
      );
      if (!encontrado) {
        control?.setValue('');
        this.productosFormArray.at(i).get('inventario_id')?.setValue('');
        this.productosFormArray.at(i).get('unidad_medida')?.setValue('');
      }
    }
  }
    onInventarioSeleccionado(inv: any, index: number) {
      const grupo = this.productosFormArray.at(index);
      seleccionarObjetoAutocomplete(
        grupo.get('inventarioControl'),
        inv,
        (obj) => {
          grupo.get('inventario_id')?.setValue(obj.id, { emitEvent: false });
          grupo.get('unidad_medida')?.setValue(obj.unidad_medida || '', { emitEvent: false });
        }
      );
    }

    forzarInventario(inv: any, i: number, event: MouseEvent) {
    // Previene el cierre inmediato del autocomplete y forza el valor
    event.preventDefault(); // detiene el cierre por defecto
    setTimeout(() => {
      this.onInventarioSeleccionado(inv, i);
      // Cierra el panel (esto es por si el panel sigue abierto)
      document.activeElement && (document.activeElement as HTMLElement).blur();
    }, 0);
  }


}
