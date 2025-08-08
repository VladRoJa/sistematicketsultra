import { Component } from '@angular/core';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-prueba-select',
  standalone: true,
  imports: [CommonModule, MatFormFieldModule, MatSelectModule, MatOptionModule],
  template: `
    <h2>🧪 Test Select</h2>
    <mat-form-field appearance="fill">
      <mat-label>Departamento Test</mat-label>
      <mat-select>
        <mat-option *ngFor="let item of items" [value]="item.id">
          {{ item.nombre }}
        </mat-option>
      </mat-select>
    </mat-form-field>
  `
})
export class PruebaSelectComponent {
  items = [
    { id: 1, nombre: 'A' },
    { id: 2, nombre: 'B' },
    { id: 3, nombre: 'C' }
  ];
}

