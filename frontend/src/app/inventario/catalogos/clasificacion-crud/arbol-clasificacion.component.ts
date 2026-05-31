// frontend/src/app/inventario/catalogos/clasificacion-crud/arbol-clasificacion.component.ts

import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { MatTreeModule } from '@angular/material/tree';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';
import { FlatTreeControl } from '@angular/cdk/tree';
import { MatTreeFlatDataSource, MatTreeFlattener } from '@angular/material/tree';

export interface ClasificacionNode {
  id: number;
  nombre: string;
  departamento_id: number;
  parent_id?: number | null;
  nivel: number;
  activo?: boolean;
  hijos?: ClasificacionNode[];
}

type FlatClasificacionNode = ClasificacionNode & {
  level: number;
  expandable: boolean;
};

@Component({
  selector: 'app-arbol-clasificacion',
  standalone: true,
  templateUrl: './arbol-clasificacion.component.html',
  imports: [MatTreeModule, MatIconModule, MatButtonModule, CommonModule],
  styleUrls: ['./arbol-clasificacion.component.css']
})
export class ArbolClasificacionComponent implements OnChanges {
  @Input() nodos: ClasificacionNode[] = [];

  @Output() editar = new EventEmitter<ClasificacionNode>();
  @Output() crearHijo = new EventEmitter<ClasificacionNode>();
  @Output() desactivar = new EventEmitter<ClasificacionNode>();
  @Output() reactivar = new EventEmitter<ClasificacionNode>();

  treeFlattener = new MatTreeFlattener<ClasificacionNode, FlatClasificacionNode>(
    (node: ClasificacionNode, level: number) => ({
      ...node,
      level,
      expandable: Boolean(node.hijos?.length)
    }),
    node => node.level,
    node => node.expandable,
    node => node.hijos
  );

  treeControl = new FlatTreeControl<FlatClasificacionNode>(
    node => node.level,
    node => node.expandable
  );

  dataSource = new MatTreeFlatDataSource(this.treeControl, this.treeFlattener);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['nodos']) {
      this.dataSource.data = [...(this.nodos || [])];

      // Por defecto dejamos el árbol colapsado para que la pantalla no cargue
      // saturada. El usuario decide qué rama abrir según el departamento/categoría.
      setTimeout(() => this.treeControl.collapseAll(), 0);
    }
  }

  hasChild = (_: number, node: FlatClasificacionNode): boolean => node.expandable;

  estaActivo(node: ClasificacionNode): boolean {
    return node.activo !== false;
  }

  puedeAgregarHijo(node: ClasificacionNode): boolean {
    return this.estaActivo(node);
  }

  emitirEditar(node: ClasificacionNode): void {
    this.editar.emit(node);
  }

  emitirCrearHijo(node: ClasificacionNode): void {
    if (!this.puedeAgregarHijo(node)) {
      return;
    }

    this.crearHijo.emit(node);
  }

  emitirDesactivar(node: ClasificacionNode): void {
    this.desactivar.emit(node);
  }

  emitirReactivar(node: ClasificacionNode): void {
    this.reactivar.emit(node);
  }

  emitirEditarDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
  event.preventDefault();
  event.stopPropagation();
  this.emitirEditar(node);
}

  emitirCrearHijoDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();
    this.emitirCrearHijo(node);
  }

  emitirDesactivarDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();
    this.emitirDesactivar(node);
  }

  emitirReactivarDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();
    this.emitirReactivar(node);
  }
}