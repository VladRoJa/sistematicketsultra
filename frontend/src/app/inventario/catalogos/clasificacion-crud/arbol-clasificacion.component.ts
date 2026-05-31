// frontend/src/app/inventario/catalogos/clasificacion-crud/arbol-clasificacion.component.ts

import { CommonModule } from '@angular/common';
import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { FlatTreeControl } from '@angular/cdk/tree';
import { MatTreeFlatDataSource, MatTreeFlattener, MatTreeModule } from '@angular/material/tree';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

export interface ClasificacionNode {
  id: number;
  nombre: string;
  departamento_id: number;
  parent_id?: number | null;
  nivel: number;
  activo?: boolean;
  hijos?: ClasificacionNode[];
}

export type FlatClasificacionNode = ClasificacionNode & {
  level: number;
  expandable: boolean;
};

@Component({
  selector: 'app-arbol-clasificacion',
  standalone: true,
  templateUrl: './arbol-clasificacion.component.html',
  styleUrls: ['./arbol-clasificacion.component.css'],
  imports: [
    CommonModule,
    MatTreeModule,
    MatIconModule,
    MatButtonModule
  ]
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
    (node) => node.level,
    (node) => node.expandable,
    (node) => node.hijos
  );

  treeControl = new FlatTreeControl<FlatClasificacionNode>(
    (node) => node.level,
    (node) => node.expandable
  );

  dataSource = new MatTreeFlatDataSource(this.treeControl, this.treeFlattener);

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['nodos']) {
      return;
    }

    this.dataSource.data = [...(this.nodos || [])];

    // Estado inicial limpio: no expandimos todo por defecto.
    // El usuario abre solo la rama que necesita revisar.
    setTimeout(() => this.treeControl.collapseAll(), 0);
  }

  hasChild = (_: number, node: FlatClasificacionNode): boolean => node.expandable;

  estaActivo(node: ClasificacionNode): boolean {
    return node.activo !== false;
  }

  puedeAgregarHijo(node: ClasificacionNode): boolean {
    return this.estaActivo(node);
  }

  nombreEstado(node: ClasificacionNode): string {
    return this.estaActivo(node) ? 'Activa' : 'Inactiva';
  }

  iconoEstado(node: ClasificacionNode): string {
    return this.estaActivo(node) ? 'block' : 'restore';
  }

  tooltipEstado(node: ClasificacionNode): string {
    return this.estaActivo(node)
      ? 'Desactivar clasificación'
      : 'Reactivar clasificación';
  }

  toggleNodeDesdeClick(event: MouseEvent, node: FlatClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();

    if (!node.expandable) {
      return;
    }

    this.treeControl.toggle(node);
  }

  toggleNodeDesdeTeclado(event: KeyboardEvent, node: FlatClasificacionNode): void {
    const key = event.key;

    if (key !== 'Enter' && key !== ' ') {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    if (!node.expandable) {
      return;
    }

    this.treeControl.toggle(node);
  }

  emitirEditarDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();
    this.editar.emit(node);
  }

  emitirCrearHijoDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();

    if (!this.puedeAgregarHijo(node)) {
      return;
    }

    this.crearHijo.emit(node);
  }

  emitirDesactivarDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();
    this.desactivar.emit(node);
  }

  emitirReactivarDesdeClick(event: MouseEvent, node: ClasificacionNode): void {
    event.preventDefault();
    event.stopPropagation();
    this.reactivar.emit(node);
  }
}