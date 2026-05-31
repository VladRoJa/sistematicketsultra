// frontend\src\app\inventario\catalogos\clasificacion-crud\clasificacion-crud.component.ts

import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { CatalogoService } from 'src/app/services/catalogo.service';
import { ArbolClasificacionComponent, ClasificacionNode } from './arbol-clasificacion.component';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatTreeModule } from '@angular/material/tree';
import { DepartamentoService } from 'src/app/services/departamento.service';

type ClasificacionNodeConEstado = ClasificacionNode & {
  activo?: boolean;
};

@Component({
  selector: 'app-clasificacion-crud',
  templateUrl: './clasificacion-crud.component.html',
  styleUrls: ['./clasificacion-crud.component.css'],
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatIconModule,
    MatTreeModule,
    ArbolClasificacionComponent
  ]
})
export class ClasificacionCrudComponent implements OnInit {
  clasificaciones: ClasificacionNodeConEstado[] = [];
  departamentos: { id: number; nombre: string }[] = [];
  loading = false;
  mostrarFormulario = false;
  todasLasClasificaciones: ClasificacionNodeConEstado[] = [];

  form: FormGroup;
  modo: 'crear' | 'editar' = 'crear';
  nodoEditando: ClasificacionNodeConEstado | null = null;

  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;

  constructor(
    private fb: FormBuilder,
    private catalogoService: CatalogoService,
    private departamentoService: DepartamentoService,
  ) {
    this.form = this.fb.group({
      nombre: ['', Validators.required],
      departamento_id: [null, Validators.required],
      parent_id: [null],
      nivel: [{ value: 1, disabled: true }, Validators.required]
    });
  }

  ngOnInit(): void {
    this.cargarDepartamentos();
    this.cargarClasificaciones();
  }

  cargarDepartamentos(): void {
    this.departamentoService.obtenerDepartamentos().subscribe({
      next: (resp: any) => {
        const departamentos = Array.isArray(resp)
          ? resp
          : Array.isArray(resp?.departamentos)
            ? resp.departamentos
            : [];

        this.departamentos = departamentos
          .map((depto: any) => ({
            id: Number(depto.id),
            nombre: String(depto.nombre || '').trim()
          }))
          .filter((depto: { id: number; nombre: string }) =>
            Number.isFinite(depto.id) && Boolean(depto.nombre)
          );
      },
      error: () => {
        mostrarAlertaToast('Error al cargar departamentos', 'error');
        this.departamentos = [];
      }
    });
  }

  cargarClasificaciones(): void {
    this.loading = true;

    // En administración sí cargamos activos e inactivos para poder reactivar.
    this.catalogoService.getClasificacionesArbol(undefined, true).subscribe({
      next: (respuesta: any[]) => {
        this.clasificaciones = this.normalizarRespuestaArbol(respuesta);
        this.todasLasClasificaciones = this.aplanarNodos(this.clasificaciones);
        this.loading = false;
      },
      error: () => {
        mostrarAlertaToast('Error al cargar clasificaciones', 'error');
        this.clasificaciones = [];
        this.todasLasClasificaciones = [];
        this.loading = false;
      }
    });
  }

  private normalizarRespuestaArbol(respuesta: any[]): ClasificacionNodeConEstado[] {
    if (!Array.isArray(respuesta)) {
      return [];
    }

    // Cuando el endpoint se pide sin departamento_id, responde agrupado por departamento:
    // [{ departamento_id, arbol: [...] }]
    const vieneAgrupadoPorDepartamento = respuesta.some((item: any) =>
      Array.isArray(item?.arbol)
    );

    if (vieneAgrupadoPorDepartamento) {
      return respuesta.flatMap((dep: any) => dep.arbol || []);
    }

    // Cuando se pide por departamento_id, responde directamente el árbol.
    return respuesta;
  }

  private aplanarNodos(nodos: ClasificacionNodeConEstado[]): ClasificacionNodeConEstado[] {
    const resultado: ClasificacionNodeConEstado[] = [];

    const recorrer = (items: ClasificacionNodeConEstado[]) => {
      items.forEach((item) => {
        resultado.push(item);

        if (Array.isArray(item.hijos) && item.hijos.length > 0) {
          recorrer(item.hijos as ClasificacionNodeConEstado[]);
        }
      });
    };

    recorrer(nodos || []);
    return resultado;
  }

  abrirFormulario(nodo: ClasificacionNodeConEstado | null = null, esHijo = false): void {
    this.mostrarFormulario = true;

    if (!nodo) {
      this.modo = 'crear';
      this.nodoEditando = null;
      this.form.reset();
      this.form.patchValue({
        nivel: 1,
        parent_id: null,
        departamento_id: null
      });
      return;
    }

    if (esHijo) {
      this.modo = 'crear';
      this.nodoEditando = null;
      this.form.reset();
      this.form.patchValue({
        parent_id: nodo.id,
        departamento_id: nodo.departamento_id,
        nivel: Number(nodo.nivel || 1) + 1
      });
      return;
    }

    this.modo = 'editar';
    this.nodoEditando = nodo;
    this.form.patchValue({
      nombre: nodo.nombre,
      departamento_id: nodo.departamento_id,
      parent_id: nodo.parent_id || null,
      nivel: nodo.nivel
    });
  }

  guardar(): void {
    if (this.form.invalid) {
      return;
    }

    const raw = this.form.getRawValue();
    const nombre = String(raw.nombre || '').trim();

    if (!nombre) {
      mostrarAlertaToast('El nombre es obligatorio', 'error');
      return;
    }

    if (this.modo === 'crear') {
      this.crearClasificacion(nombre, raw);
      return;
    }

    this.editarClasificacion(nombre);
  }

  private crearClasificacion(nombre: string, raw: any): void {
    const departamentoId = Number(raw.departamento_id);
    const parentId = raw.parent_id === null || raw.parent_id === undefined || raw.parent_id === ''
      ? null
      : Number(raw.parent_id);

    if (!Number.isFinite(departamentoId)) {
      mostrarAlertaToast('Selecciona un departamento válido', 'error');
      return;
    }

    this.catalogoService.crearClasificacion({
      nombre,
      departamento_id: departamentoId,
      parent_id: parentId
    }).subscribe({
      next: () => {
        mostrarAlertaToast('Clasificación creada');
        this.cargarClasificaciones();
        this.cerrarFormulario();
      },
      error: (err) => {
        const msg = err?.error?.message || 'Error al crear clasificación';
        mostrarAlertaToast(msg, 'error');
      }
    });
  }

  private editarClasificacion(nombre: string): void {
    if (!this.nodoEditando) {
      return;
    }

    this.catalogoService.editarClasificacion(this.nodoEditando.id, { nombre }).subscribe({
      next: () => {
        mostrarAlertaToast('Clasificación actualizada');
        this.cargarClasificaciones();
        this.cerrarFormulario();
      },
      error: (err) => {
        const msg = err?.error?.message || 'Error al actualizar clasificación';
        mostrarAlertaToast(msg, 'error');
      }
    });
  }

  // Compatibilidad temporal con el output actual del árbol:
  // el HTML hijo todavía emite "eliminar", pero aquí ya no eliminamos físicamente.
  eliminar(nodo: ClasificacionNodeConEstado): void {
    this.desactivar(nodo);
  }

  desactivar(nodo: ClasificacionNodeConEstado): void {
    const confirmar = window.confirm(
      `¿Desactivar "${nodo.nombre}"?\n\n` +
      'Ya no aparecerá para tickets nuevos, pero se conservará el histórico.'
    );

    if (!confirmar) {
      return;
    }

    this.catalogoService.desactivarClasificacion(nodo.id).subscribe({
      next: (resp: any) => {
        mostrarAlertaToast(resp?.message || 'Clasificación desactivada');
        this.cargarClasificaciones();
      },
      error: (err) => {
        const msg = err?.error?.message || 'Error al desactivar clasificación';
        mostrarAlertaToast(msg, 'error');
      }
    });
  }

  reactivar(nodo: ClasificacionNodeConEstado): void {
    const confirmar = window.confirm(
      `¿Reactivar "${nodo.nombre}"?\n\n` +
      'Volverá a estar disponible para tickets nuevos.'
    );

    if (!confirmar) {
      return;
    }

    this.catalogoService.reactivarClasificacion(nodo.id).subscribe({
      next: (resp: any) => {
        mostrarAlertaToast(resp?.message || 'Clasificación reactivada');
        this.cargarClasificaciones();
      },
      error: (err) => {
        const msg = err?.error?.message || 'Error al reactivar clasificación';
        mostrarAlertaToast(msg, 'error');
      }
    });
  }

  cerrarFormulario(): void {
    this.mostrarFormulario = false;
    this.form.reset();
    this.nodoEditando = null;
    this.modo = 'crear';
  }

  cancelar(): void {
    this.cerrarFormulario();
  }

  abrirDialogoImportar(): void {
    mostrarAlertaToast(
      'La importación masiva de clasificaciones está deshabilitada temporalmente para proteger la jerarquía.',
      'error'
    );
  }

  importar(event: Event): void {
    const input = event.target as HTMLInputElement;
    input.value = '';
    this.abrirDialogoImportar();
  }

  exportar(): void {
    this.catalogoService.exportarArchivo('clasificaciones').subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');

        a.href = url;
        a.download = 'clasificaciones.xlsx';
        a.click();

        window.URL.revokeObjectURL(url);
      },
      error: () => {
        mostrarAlertaToast('Error al exportar clasificaciones', 'error');
      }
    });
  }

  descargarPlantilla(): void {
    mostrarAlertaToast(
      'La plantilla de importación está deshabilitada hasta tener validación robusta de jerarquía.',
      'error'
    );
  }
}