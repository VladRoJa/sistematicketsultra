// frontend-angular\src\app\inventario\catalogos\clasificacion-crud\arbol-clasificacion.component.ts

import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { MatTreeModule } from '@angular/material/tree';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { FlatTreeControl } from '@angular/cdk/tree';
import { MatTreeFlatDataSource, MatTreeFlattener } from '@angular/material/tree';

export interface ClasificacionNode {
  id: number;
  nombre: string;
  departamento_id: number;
  parent_id?: number;
  nivel: number;
  hijos?: ClasificacionNode[];
}

@Component({
  selector: 'app-arbol-clasificacion',
  standalone: true,
  templateUrl: './arbol-clasificacion.component.html',
  imports: [MatTreeModule, MatIconModule, MatButtonModule],
  styleUrls: ['./arbol-clasificacion.component.css']
})
export class ArbolClasificacionComponent implements OnChanges {
  @Input() nodos: ClasificacionNode[] = [];
  @Output() editar = new EventEmitter<ClasificacionNode>();
  @Output() crearHijo = new EventEmitter<ClasificacionNode>();
  @Output() eliminar = new EventEmitter<ClasificacionNode>();

  // Flat Tree helpers:
  treeFlattener = new MatTreeFlattener<ClasificacionNode, any>(
    (node: ClasificacionNode, level: number) => ({
      ...node,
      level, // OJO: aquí Angular espera 'level', no 'nivel'
      expandable: !!node.hijos && node.hijos.length > 0
    }),
    node => node.level,
    node => node.expandable,
    node => node.hijos
  );

  treeControl = new FlatTreeControl<any>(
    node => node.level,
    node => node.expandable
  );

  dataSource = new MatTreeFlatDataSource(this.treeControl, this.treeFlattener);


  ngOnChanges(changes: SimpleChanges) {
    console.log('ARBOLES RECIBIDOS:', JSON.stringify(this.nodos, null, 2));
    if (changes['nodos']) {
      // FORZAR referencia nueva: para asegurar cambio detectado
      this.dataSource.data = [...(this.nodos || [])];
      this.treeControl.dataNodes = this.dataSource.data;

      // Forzar expand después de un ciclo de cambio (por si MatTree necesita tiempo)
      setTimeout(() => this.treeControl.expandAll(), 50);

      console.log('Nodos recibidos en árbol:', this.nodos);
    }
  }

  hasChild = (_: number, node: any) => node.expandable;

}