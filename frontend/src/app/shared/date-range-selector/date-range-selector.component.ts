import { CommonModule } from '@angular/common';
import {
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
} from '@angular/core';
import {
  MAT_DATE_LOCALE,
  MatNativeDateModule,
} from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

@Component({
  selector: 'app-suite-date-range-selector',
  standalone: true,
  imports: [
    CommonModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatInputModule,
    MatNativeDateModule,
  ],
  providers: [
    {
      provide: MAT_DATE_LOCALE,
      useValue: 'es-MX',
    },
  ],
  templateUrl: './date-range-selector.component.html',
  styleUrls: ['./date-range-selector.component.css'],
})
export class DateRangeSelectorComponent implements OnChanges {
  @Input() dateFrom = '';
  @Input() dateTo = '';
  @Input() minDate: string | null = null;
  @Input() maxDate: string | null = null;
  @Input() label = 'Periodo';
  @Input() hint = 'Selecciona el rango de fechas a analizar.';

  @Output() dateFromChange = new EventEmitter<string>();
  @Output() dateToChange = new EventEmitter<string>();

  startDate: Date | null = null;
  endDate: Date | null = null;
  minDateValue: Date | null = null;
  maxDateValue: Date | null = null;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['dateFrom']) {
      this.startDate = this.parseIsoDate(
        this.dateFrom,
      );
    }

    if (changes['dateTo']) {
      this.endDate = this.parseIsoDate(
        this.dateTo,
      );
    }

    if (changes['minDate']) {
      this.minDateValue = this.parseIsoDate(
        this.minDate,
      );
    }

    if (changes['maxDate']) {
      this.maxDateValue = this.parseIsoDate(
        this.maxDate,
      );
    }
  }

  onDateFromChange(value: Date | null): void {
    this.startDate = value;
    const isoDate = this.formatIsoDate(value);
    this.dateFrom = isoDate;
    this.dateFromChange.emit(isoDate);
  }

  onDateToChange(value: Date | null): void {
    this.endDate = value;
    const isoDate = this.formatIsoDate(value);
    this.dateTo = isoDate;
    this.dateToChange.emit(isoDate);
  }

  private parseIsoDate(
    value: string | null | undefined,
  ): Date | null {
    if (!value) {
      return null;
    }

    const match =
      /^(\d{4})-(\d{2})-(\d{2})$/.exec(
        value,
      );
    if (!match) {
      return null;
    }

    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const parsed = new Date(
      year,
      month - 1,
      day,
    );

    if (
      parsed.getFullYear() !== year
      || parsed.getMonth() !== month - 1
      || parsed.getDate() !== day
    ) {
      return null;
    }

    return parsed;
  }

  private formatIsoDate(
    value: Date | null,
  ): string {
    if (!value) {
      return '';
    }

    const year = value.getFullYear();
    const month = String(
      value.getMonth() + 1,
    ).padStart(2, '0');
    const day = String(
      value.getDate(),
    ).padStart(2, '0');

    return `${year}-${month}-${day}`;
  }
}
