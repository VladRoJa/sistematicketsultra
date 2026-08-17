// frontend/src/app/pantalla-ver-tickets/modals/evidencia-preview.component.ts

import {
  Component,
  Inject,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import {
  HttpClient,
  HttpHeaders,
} from '@angular/common/http';

import { environment } from '../../../environments/environment';

interface EvidenciaPreviewData {
  url?: string;
  ticketId?: number;
  titulo?: string;
}

interface TicketAttachmentMetadata {
  id: number;
  ticket_id: number;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  available: boolean;
}

@Component({
  standalone: true,
  selector: 'app-evidencia-preview',
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './evidencia-preview.component.html',
  styleUrls: ['./evidencia-preview.component.css'],
})
export class EvidenciaPreviewComponent
  implements OnInit, OnDestroy {

  previewUrl: string | null = null;
  filename = 'evidencia';
  loading = false;
  errorMessage = '';

  private privateBlob: Blob | null = null;
  private objectUrl: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public data: EvidenciaPreviewData,
    private ref: MatDialogRef<EvidenciaPreviewComponent>,
    private http: HttpClient,
  ) {}

  ngOnInit(): void {
    if (this.data?.ticketId) {
      this.cargarAdjuntoPrivado(this.data.ticketId);
      return;
    }

    const legacyUrl = (this.data?.url || '').trim();

    if (legacyUrl) {
      this.previewUrl = legacyUrl;
    }
  }

  ngOnDestroy(): void {
    this.liberarObjectUrl();
  }

  private getAuthHeaders(): HttpHeaders | undefined {
    const token = localStorage.getItem('token');

    return token
      ? new HttpHeaders().set(
          'Authorization',
          `Bearer ${token}`
        )
      : undefined;
  }

  private cargarAdjuntoPrivado(ticketId: number): void {
    this.loading = true;
    this.errorMessage = '';

    const headers = this.getAuthHeaders();

    this.http.get<TicketAttachmentMetadata>(
      `${environment.apiUrl}/tickets/${ticketId}/attachment`,
      { headers }
    ).subscribe({
      next: (metadata) => {
        if (!metadata?.available) {
          this.loading = false;
          this.errorMessage =
            'La imagen adjunta ya no está disponible.';
          return;
        }

        this.filename =
          metadata.original_filename || 'evidencia';

        this.cargarArchivoPrivado(
          ticketId,
          headers
        );
      },
      error: (err) => {
        this.loading = false;

        if (err?.status === 410) {
          this.errorMessage =
            'La imagen adjunta ya no está disponible.';
          return;
        }

        if (err?.status === 404) {
          this.errorMessage =
            'No se encontró la imagen adjunta.';
          return;
        }

        this.errorMessage =
          'No se pudo cargar la imagen adjunta.';
      },
    });
  }

  private cargarArchivoPrivado(
    ticketId: number,
    headers?: HttpHeaders,
  ): void {
    this.http.get(
      `${environment.apiUrl}/tickets/${ticketId}/attachment/file`,
      {
        headers,
        responseType: 'blob',
      }
    ).subscribe({
      next: (blob) => {
        this.liberarObjectUrl();

        this.privateBlob = blob;
        this.objectUrl = URL.createObjectURL(blob);
        this.previewUrl = this.objectUrl;
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;

        if (err?.status === 410) {
          this.errorMessage =
            'La imagen adjunta ya no está disponible.';
          return;
        }

        if (err?.status === 404) {
          this.errorMessage =
            'No se encontró la imagen adjunta.';
          return;
        }

        this.errorMessage =
          'No se pudo cargar la imagen adjunta.';
      },
    });
  }

  descargar(): void {
    if (!this.previewUrl) {
      return;
    }

    const link = document.createElement('a');

    link.href = this.previewUrl;
    link.download = this.filename || 'evidencia';

    if (!this.privateBlob) {
      link.target = '_blank';
      link.rel = 'noopener';
    }

    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  close(): void {
    this.ref.close();
  }

  private liberarObjectUrl(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }

    this.privateBlob = null;
  }
}
