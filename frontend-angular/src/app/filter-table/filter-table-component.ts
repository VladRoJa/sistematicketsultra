import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

export interface FiltrosTabla {
  estado: string;
  criticidad: string;
  departamento: string;
  fechaCreacion: string;
  fechaFinalizacion: string;
  categoria: string;
  descripcion: string;
  username: string;
}

@Component({
  selector: 'app-filter-table',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule],
  template: `
    <tr class="filtro-row" [ngClass]="{ 'aplicado': filtroAplicado }">
      <th>
        <!-- Puedes dejar vacío o poner título para la columna ID -->
      </th>
      <th>
        <!-- Filtro para Categoría (ejemplo con un input) -->
        <input
          type="text"
          placeholder="Filtrar Categoría"
          [(ngModel)]="filtros.categoria">
      </th>
      <th>
        <input
          type="text"
          placeholder="Filtrar Descripción"
          [(ngModel)]="filtros.descripcion">
      </th>
      <th>
        <input
          type="text"
          placeholder="Filtrar Usuario"
          [(ngModel)]="filtros.username">
      </th>
      <th>
        <select [(ngModel)]="filtros.estado">
          <option value="">Todos</option>
          <option value="pendiente">Pendiente</option>
          <option value="en progreso">En Progreso</option>
          <option value="finalizado">Finalizado</option>
        </select>
      </th>
      <th>
        <select [(ngModel)]="filtros.criticidad">
          <option value="">Todas</option>
          <option value="1">1 - Muy Baja</option>
          <option value="2">2 - Baja</option>
          <option value="3">3 - Media</option>
          <option value="4">4 - Alta</option>
          <option value="5">5 - Crítica</option>
        </select>
      </th>
      <th>
        <input type="date" [(ngModel)]="filtros.fechaCreacion">
      </th>
      <th>
        <input type="date" [(ngModel)]="filtros.fechaFinalizacion">
      </th>
      <th>
        <input
          type="text"
          placeholder="Filtrar Departamento"
          [(ngModel)]="filtros.departamento">
      </th>
      <th colspan="2">
        <!-- Botón de aplicar filtro -->
        <button (click)="aplicarFiltro()" class="btn-aplicar-filtro">
          Aplicar Filtro
        </button>
      </th>
    </tr>
  `,
  styles: [`
    .filtro-row {
      background-color: #f5f5f5;
      transition: background-color 0.5s ease;
    }
    .filtro-row.aplicado {
      background-color: #e0f7fa;
    }
    input, select {
      width: 100%;
      padding: 0.25rem;
      box-sizing: border-box;
    }
    .btn-aplicar-filtro {
      padding: 0.5rem 1rem;
      background-color: #1976d2;
      color: #fff;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }
  `]
})
export class FilterTableComponent {
  // Modelo de filtros (puedes extenderlo según tus necesidades)
  filtros: FiltrosTabla = {
    estado: '',
    criticidad: '',
    departamento: '',
    fechaCreacion: '',
    fechaFinalizacion: '',
    // Puedes agregar otros filtros, como categoría, descripción, username, etc.
    // Ejemplo: categoria, descripcion, username
    categoria: '',
    descripcion: '',
    username: '',
  };

  // Bandera para feedback visual
  filtroAplicado: boolean = false;

  // Evento para comunicar al componente padre los filtros aplicados
  @Output() filtroAplicadoEvent = new EventEmitter<FiltrosTabla>();

  constructor(private snackBar: MatSnackBar) {}

  aplicarFiltro() {
    // Emitir los filtros al componente padre
    this.filtroAplicadoEvent.emit(this.filtros);

    // Dar feedback visual: se activa la clase "aplicado" en la fila
    this.filtroAplicado = true;

    // Mostrar snack-bar (opcional)
    this.snackBar.open('Filtro aplicado', 'Cerrar', {
      duration: 3000,
      panelClass: ['snack-bar-custom']
    });

    // Después de 2 segundos, remover la clase aplicada
    setTimeout(() => {
      this.filtroAplicado = false;
    }, 2000);
  }
}
