// filter-date-range.component.ts

import { 
  Component, 
  OnInit, 
  Output, 
  EventEmitter, 
  ViewChild, 
  AfterViewInit 
} from '@angular/core';
import { FormGroup, FormControl } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { 
  MatDatepickerModule, 
  DateFilterFn, 
  MatDateRangePicker 
} from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';

/**
 * Componente de rango de fechas (standalone).
 * Muestra un Date Range Picker con botones "Borrar" y "Aplicar",
 * y emite el rango seleccionado al padre.
 */
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
  ],
  templateUrl: './filter-date-range.component.html',
  styleUrls: ['./filter-date-range.component.css']
})
export class FilterDateRangeComponent implements OnInit, AfterViewInit {
  /**
   * Referencia al componente MatDateRangePicker en la plantilla.
   * Se utiliza para abrir el calendario programáticamente.
   */
  @ViewChild('picker') picker!: MatDateRangePicker<Date>;

  /**
   * Emite el rango de fechas seleccionado (start, end) al padre.
   */
  @Output() rangoSeleccionado = new EventEmitter<{start: Date, end: Date}>();

  /**
   * FormGroup para controlar las fechas de inicio (start) y fin (end).
   */
  range = new FormGroup({
    start: new FormControl<Date | null>(null),
    end: new FormControl<Date | null>(null),
  });

  /**
   * (Opcional) Fechas "válidas" que, si quieres, se podrían marcar
   * o filtrar en el calendario. Aquí a modo de ejemplo.
   */
  private fechasConDatos: Date[] = [
    new Date('2025-03-20T12:45:00'),
    new Date('2025-03-20T08:27:00'),
    new Date('2025-03-24T09:41:00'),
    new Date('2025-03-25T12:32:00'),
  ];

  /**
   * Set que contiene las fechas válidas en formato string,
   * para usarse en la función de filtro del calendario.
   */
  private fechasValidasSet: Set<string> = new Set();

  /**
   * Función para bloquear/deshabilitar fechas no incluidas en `fechasValidasSet`.
   * Angular Material la llama para cada día del calendario.
   */
  soloFechasValidas: DateFilterFn<Date> = (date: Date | null): boolean => {
    if (!date) return false;
    return this.fechasValidasSet.has(date.toDateString());
  };

  /**
   * Asigna clases CSS a los días en el calendario (por ejemplo, para opacarlos).
   */
  dateClass = (cellDate: Date, view: 'month' | 'year' | 'multi-year'): string => {
    if (view === 'month') {
      if (!this.fechasValidasSet.has(cellDate.toDateString())) {
        return 'disabled-date';
      }
    }
    return '';
  };

  /**
   * Inicializa la estructura de datos y llena el Set de fechas válidas.
   */
  ngOnInit(): void {
    this.fechasConDatos.forEach(fecha => {
      this.fechasValidasSet.add(fecha.toDateString());
    });
  }

  /**
   * Abre el date range picker automáticamente después de que la vista cargue.
   */
  ngAfterViewInit(): void {
    // Abre el calendario de forma programática.
    // Puedes quitar esta línea si prefieres no abrirlo de inmediato.
   
  }

  /**
   * Se llama cuando el usuario cambia la fecha (start o end).
   * Si ambas fechas están seleccionadas, emite el rango.
   */
  onDateRangeChange(): void {
    const start = this.range.value.start;
    const end = this.range.value.end;

    if (start && end) {
      // Emitimos el rango para que el componente padre realice el filtrado.
      this.rangoSeleccionado.emit({ start, end });
    }
  }
}
