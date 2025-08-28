//frontend\src\app\pantalla-ver-tickets\modals\evidencia-preview.component.ts

import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule, MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  standalone: true,
  selector: 'app-evidencia-preview',
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <div class="wrap">
      <header class="bar">
        <strong>{{ data?.titulo || 'Evidencia' }}</strong>
        <span class="spacer"></span>
        <a *ngIf="data?.url" [href]="data.url" target="_blank" rel="noopener" mat-button>
          Abrir en pestaña
        </a>
        <button mat-icon-button (click)="close()" aria-label="Cerrar">
          <mat-icon>close</mat-icon>
        </button>
      </header>

      <section class="content">
        <img *ngIf="data?.url; else noImg" [src]="data.url" alt="Evidencia" />
      </section>

      <ng-template #noImg>
        <p>Sin evidencia para este ticket.</p>
      </ng-template>
    </div>
  `,
  styles: [`
    .wrap { max-width: 90vw; }
    .bar { display:flex; align-items:center; gap:8px; padding-bottom:8px; }
    .spacer { flex:1; }
    .content {
      max-height: 80vh; overflow:auto;
      display:flex; align-items:center; justify-content:center;
    }
    img { max-width: 100%; max-height: 80vh; object-fit: contain; border-radius: 8px; }
  `]
})
export class EvidenciaPreviewComponent {
  constructor(
    @Inject(MAT_DIALOG_DATA) public data: { url: string; titulo?: string },
    private ref: MatDialogRef<EvidenciaPreviewComponent>
  ) {}
  close() { this.ref.close(); }
}
