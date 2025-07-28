//frontend-angular\src\app\inventario\catalogos\clasificacion-crud\clasificacion-crud.component.ts


import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { CatalogoService } from 'src/app/services/catalogo.service';
import { ArbolClasificacionComponent, ClasificacionNode } from './arbol-clasificacion.component';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatTreeModule } from '@angular/material/tree';

@Component({
  selector: 'app-clasificacion-crud',
  templateUrl: './clasificacion-crud.component.html',
  styleUrls: ['./clasificacion-crud.component.css'],
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule, 
    MatIconModule, 
    MatTreeModule,
    ArbolClasificacionComponent
  ]
})
export class ClasificacionCrudComponent implements OnInit {
  clasificaciones: ClasificacionNode[] = [];
  departamentos: { id: number, nombre: string }[] = [];
  loading = false;
  mostrarFormulario = false;
  todasLasClasificaciones: ClasificacionNode[] = [];

  form: FormGroup;
  modo: 'crear' | 'editar' = 'crear';
  nodoEditando: ClasificacionNode | null = null;

  constructor(
    private fb: FormBuilder,
    private catalogoService: CatalogoService,
    private dialog: MatDialog
  ) {
    this.form = this.fb.group({
      nombre: ['', Validators.required],
      departamento_id: [null, Validators.required],
      parent_id: [null], // Solo si no es raíz
      nivel: [1, Validators.required]
    });
  }

  ngOnInit(): void {
    this.cargarDepartamentos();
    this.cargarClasificaciones();
  }

  cargarDepartamentos() {
    // Puedes traerlos del backend, aquí van hardcodeados para pruebas
    this.departamentos = [
      { id: 1, nombre: 'Mantenimiento' },
      { id: 2, nombre: 'Finanzas' },
      { id: 3, nombre: 'Marketing' },
      { id: 4, nombre: 'Gerencia Deportiva' },
      { id: 5, nombre: 'Recursos Humanos' },
      { id: 6, nombre: 'Compras' },
      { id: 7, nombre: 'Sistemas' },
      { id: 8, nombre: 'Corporativo' }
    ];
  }

cargarClasificaciones() {
  this.loading = true;
  this.catalogoService.listarElemento('clasificaciones').subscribe({
      next: (items: ClasificacionNode[]) => {
        console.log('Clasificaciones planas:', items);
        // ¡Asegura aquí!
        items.forEach(item => { if (!item.hijos) item.hijos = []; });
        this.clasificaciones = this.armarArbolClasificaciones(items);
        this.todasLasClasificaciones = items; // <- plano
        this.loading = false;
      },
    error: err => {
      mostrarAlertaToast('Error al cargar clasificaciones', 'error');
      this.loading = false;
    }
  });
}

  /**
   * Convierte el array plano a jerárquico para el árbol.
   */
  armarArbolClasificaciones(items: ClasificacionNode[]): ClasificacionNode[] {
    const idMap: { [key: number]: ClasificacionNode } = {};
    const roots: ClasificacionNode[] = [];

    // Asigna hijos y corrige nivel raíz
    items.forEach(item => {
      idMap[item.id] = { ...item, hijos: [] };
    });

    items.forEach(item => {
      if (item.parent_id) {
        idMap[item.parent_id]?.hijos?.push(idMap[item.id]);
      } else {
        idMap[item.id].nivel = 0;  // <-- Cambia la raíz a nivel 0
        roots.push(idMap[item.id]);
      }
    });

    return roots;
  }




  iniciarCrear(parent?: ClasificacionNode) {
    this.modo = 'crear';
    this.nodoEditando = null;
    this.form.reset();
    if (parent) {
      this.form.patchValue({
        parent_id: parent.id,
        departamento_id: parent.departamento_id,
        nivel: parent.nivel + 1
      });
    } else {
      this.form.patchValue({ nivel: 1 });
    }
  }

  iniciarEditar(nodo: ClasificacionNode) {
    this.modo = 'editar';
    this.nodoEditando = nodo;
    this.form.patchValue({
      nombre: nodo.nombre,
      departamento_id: nodo.departamento_id,
      parent_id: nodo.parent_id || null,
      nivel: nodo.nivel
    });
  }

guardar() {
  if (this.form.invalid) return;
  const datos = this.form.value;

  if (this.modo === 'crear') {
    // Solo dos argumentos: catálogo, datos
    this.catalogoService.crearElemento('clasificaciones', datos).subscribe({
      next: () => {
        mostrarAlertaToast('Clasificación creada');
        this.cargarClasificaciones();
        this.form.reset();
      },
      error: err => mostrarAlertaToast('Error al crear', 'error')
    });
  } else if (this.nodoEditando) {
    // Solo tres argumentos: catálogo, id, datos
    this.catalogoService.editarElemento('clasificaciones', this.nodoEditando.id, datos).subscribe({
      next: () => {
        mostrarAlertaToast('Clasificación actualizada');
        this.cargarClasificaciones();
        this.form.reset();
        this.modo = 'crear';
        this.nodoEditando = null;
      },
      error: err => mostrarAlertaToast('Error al actualizar', 'error')
    });
  }
}


  eliminar(nodo: ClasificacionNode) {
    // Opcional: Diálogo de confirmación
    this.catalogoService.eliminarElemento('clasificaciones', nodo.id).subscribe({
      next: () => {
        mostrarAlertaToast('Clasificación eliminada');
        this.cargarClasificaciones();
      },
      error: err => mostrarAlertaToast('Error al eliminar', 'error')
    });
  }

  cancelar() {
    this.form.reset();
    this.modo = 'crear';
    this.nodoEditando = null;
  }

  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;

abrirDialogoImportar() { this.fileInput.nativeElement.click(); }

importar(event: Event) {
  const input = event.target as HTMLInputElement;
  if (!input.files || input.files.length === 0) return;
  const archivo = input.files[0];
  this.catalogoService.importarArchivo('clasificaciones', archivo).subscribe({
    next: () => {
      mostrarAlertaToast('Importación exitosa');
      this.cargarClasificaciones();
    },
    error: err => mostrarAlertaToast('Error al importar', 'error')
  });
  input.value = '';
}

exportar() {
  this.catalogoService.exportarArchivo('clasificaciones').subscribe(blob => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `clasificaciones.xlsx`;
    a.click();
    window.URL.revokeObjectURL(url);
  });
}

descargarPlantilla() {
  const csv = `nombre,parent_id,departamento_id,nivel
Mantenimiento,,1,1
Eléctrico,1,1,2
Lámparas,2,1,3
`;
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'plantilla_clasificacion.csv';
  a.click();
  window.URL.revokeObjectURL(url);
}


abrirFormulario(nodo: ClasificacionNode | null = null, esHijo = false) {
  this.mostrarFormulario = true;

  if (!nodo) {
    this.modo = 'crear';
    this.nodoEditando = null;
    this.form.reset();
    this.form.patchValue({ nivel: 1, parent_id: null });
  } else if (esHijo) {
    // Crear hijo de nodo actual
    this.modo = 'crear';
    this.nodoEditando = null;
    this.form.reset();
    this.form.patchValue({
      parent_id: nodo.id,
      departamento_id: nodo.departamento_id,
      nivel: nodo.nivel + 1
    });
  } else {
    // Editar
    this.modo = 'editar';
    this.nodoEditando = nodo;
    this.form.patchValue({
      nombre: nodo.nombre,
      departamento_id: nodo.departamento_id,
      parent_id: nodo.parent_id || null,
      nivel: nodo.nivel
    });
  }
}

cerrarFormulario() {
  this.mostrarFormulario = false;
  this.form.reset();
  this.nodoEditando = null;
  this.modo = 'crear';
}







}

