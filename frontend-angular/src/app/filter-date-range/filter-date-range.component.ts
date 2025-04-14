// filter-date-range.component.ts

import { Component, Output, EventEmitter, ViewChild } from '@angular/core';
import { FormGroup, FormControl } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatDatepickerModule, MatDateRangePicker } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuTrigger } from '@angular/material/menu';

@Component({
  selector: 'app-filter-date-range',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatInputModule,
    MatNativeDateModule,
    MatButtonModule,
    MatIconModule
  ],
  templateUrl: './filter-date-range.component.html',
  styleUrls: ['./filter-date-range.component.css']
})
export class FilterDateRangeComponent {
  @ViewChild('picker') picker!: MatDateRangePicker<Date>;
  @ViewChild(MatMenuTrigger) menuTrigger!: MatMenuTrigger;



  @Output() rangoSeleccionado = new EventEmitter<{ start: Date | null; end: Date | null }>();

  range = new FormGroup({
    start: new FormControl<Date | null>(null),
    end: new FormControl<Date | null>(null),
  });

  fechasSolucionDisponibles = new Set<string>([ '2025-03-20', '2025-03-24', '2025-03-25' ]);

  dateClass = (cellDate: Date, view: 'month' | 'year' | 'multi-year'): string => {
    const fechaStr = cellDate.toISOString().slice(0, 10);
    return this.fechasSolucionDisponibles?.has(fechaStr) ? 'mat-calendar-body-cell-valid' : '';
  };


  aplicarRango(): void {
    const start = this.range.value.start;
    const end = this.range.value.end;
    if (start && end) {
      this.rangoSeleccionado.emit({ start, end });
    }
  }

  borrarRango(): void {
    this.range.reset(); // Limpia los campos de fecha
  
    // Emitimos valores nulos para que el padre sepa que se quiere limpiar el filtro
    this.rangoSeleccionado.emit({ start: null, end: null });
  
    // Cierra el menú si existe un mat-menu activo
    if (this.menuTrigger) {
      this.menuTrigger.closeMenu();
    }
  }
  
}
