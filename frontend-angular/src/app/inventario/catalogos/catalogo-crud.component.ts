// src/app/inventario/catalogos/catalogo-crud.component.ts

import { Component, Input, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { CatalogoService, CatalogoElemento } from '../../services/catalogo.service';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { DialogoConfirmacionComponent } from '../../shared/dialogo-confirmacion/dialogo-confirmacion.component';
import { Observable, map, startWith } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
@Component({
  selector: 'app-catalogo-crud',
  standalone: true,
  templateUrl: './catalogo-crud.component.html',
  styleUrls: ['./catalogo-crud.component.css'],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatTableModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatAutocompleteModule,
    DialogoConfirmacionComponent
  ]
})
export class CatalogoCrudComponent implements OnInit {
  @Input() tipo: string = ''; // 'marcas', 'proveedores', 'categorias', 'unidades_medida'
  @Input() titulo: string = ''; // Ej: "Marcas"
  elementos: CatalogoElemento[] = [];
  form: FormGroup;
  modo: 'crear' | 'editar' = 'crear';
  elementoEditando: CatalogoElemento | null = null;
  loading = false;
  displayedColumns: string[] = ['id', 'nombre', 'acciones'];
  // Autocomplete
  elementosFiltrados$!: Observable<CatalogoElemento[]>;

  constructor(
    private catalogoService: CatalogoService,
    private fb: FormBuilder,
    private dialog: MatDialog,
    private route: ActivatedRoute,
  ) {
    this.tipo = this.route.snapshot.data['tipo'];
    this.titulo = this.route.snapshot.data['titulo'];
    this.form = this.fb.group({
      nombre: ['', Validators.required],
      abreviatura: [''] // Solo para unidades de medida, lo puedes ocultar por tipo
    });
  }

  ngOnInit(): void {
    this.cargarElementos();
    this.elementosFiltrados$ = this.form.get('nombre')!.valueChanges.pipe(
      startWith(''),
      map(value => this.filtrarElementos(value || ''))
    );
  }

  cargarElementos() {
    this.loading = true;
    this.catalogoService.listarElemento(this.tipo).subscribe({
      next: elementos => {
        this.elementos = elementos;
        this.loading = false;
      },
      error: err => {
        mostrarAlertaToast('Error al cargar el catálogo', 'error');
        this.loading = false;
      }
    });
  }

  filtrarElementos(valor: string): CatalogoElemento[] {
    const filtro = valor.toLowerCase();
    return this.elementos.filter(e => e.nombre.toLowerCase().includes(filtro));
  }

  iniciarAgregar() {
    this.form.reset();
    this.modo = 'crear';
    this.elementoEditando = null;
  }

  iniciarEditar(elem: CatalogoElemento) {
    this.form.patchValue({ nombre: elem.nombre, abreviatura: elem.abreviatura });
    this.modo = 'editar';
    this.elementoEditando = elem;
  }

  guardar() {
    if (this.form.invalid) return;
    const nombre = this.form.value.nombre.trim();
    const abreviatura = this.form.value.abreviatura?.trim() || undefined;

    // Validar duplicados (case insensitive)
    const existe = this.elementos.some(e => e.nombre.trim().toLowerCase() === nombre.toLowerCase() && (!this.elementoEditando || e.id !== this.elementoEditando.id));
    if (existe) {
      mostrarAlertaToast('Ya existe un elemento con ese nombre.', 'warning');
      return;
    }

    if (this.modo === 'crear') {
      this.catalogoService.crearElemento(this.tipo, nombre, abreviatura).subscribe({
        next: () => {
          mostrarAlertaToast('Elemento creado');
          this.cargarElementos();
          this.form.reset();
        },
        error: err => {
          mostrarAlertaToast('Error al crear', 'error');
        }
      });
    } else if (this.elementoEditando) {
      this.catalogoService.editarElemento(this.tipo, this.elementoEditando.id, nombre, abreviatura).subscribe({
        next: () => {
          mostrarAlertaToast('Elemento actualizado');
          this.cargarElementos();
          this.form.reset();
          this.modo = 'crear';
          this.elementoEditando = null;
        },
        error: err => {
          mostrarAlertaToast('Error al actualizar', 'error');
        }
      });
    }
  }

  eliminar(elem: CatalogoElemento) {
    const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
      data: {
        titulo: `¿Eliminar ${this.titulo}?`,
        mensaje: `¿Seguro que quieres eliminar "${elem.nombre}"?`,
        textoAceptar: 'Eliminar',
        textoCancelar: 'Cancelar'
      }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.catalogoService.eliminarElemento(this.tipo, elem.id).subscribe({
          next: () => {
            mostrarAlertaToast('Elemento eliminado');
            this.cargarElementos();
          },
          error: err => {
            mostrarAlertaToast('Error al eliminar', 'error');
          }
        });
      }
    });
  }

  cancelar() {
    this.form.reset();
    this.modo = 'crear';
    this.elementoEditando = null;
  }
}
