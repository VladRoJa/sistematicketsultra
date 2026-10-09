import { CommonModule } from '@angular/common';
import {
  Component,
  Inject,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import {
  DomSanitizer,
  SafeResourceUrl,
} from '@angular/platform-browser';

import {
  PurchaseRequisitionAttachment,
  PurchaseRequisitionService,
} from './purchase-requisition.service';

export interface PurchaseRequisitionAttachmentPreviewDialogData {
  requisitionId: number;
  attachment: PurchaseRequisitionAttachment;
}

@Component({
  selector: 'app-purchase-requisition-attachment-preview-dialog',
  standalone: true,
  templateUrl: './purchase-requisition-attachment-preview-dialog.component.html',
  styleUrls: ['./purchase-requisition-attachment-preview-dialog.component.css'],
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
})
export class PurchaseRequisitionAttachmentPreviewDialogComponent
implements OnInit, OnDestroy {
  loading = true;
  error = '';
  objectUrl = '';
  safeResourceUrl: SafeResourceUrl | null = null;
  private fileBlob: Blob | null = null;

  constructor(
    private readonly requisitionService: PurchaseRequisitionService,
    private readonly sanitizer: DomSanitizer,
    private readonly dialogRef:
      MatDialogRef<PurchaseRequisitionAttachmentPreviewDialogComponent>,
    @Inject(MAT_DIALOG_DATA)
    readonly data: PurchaseRequisitionAttachmentPreviewDialogData,
  ) {}

  ngOnInit(): void {
    this.loadFile();
  }

  ngOnDestroy(): void {
    this.releaseObjectUrl();
  }

  get isImage(): boolean {
    const mimeType = String(this.data.attachment.mime_type || '').toLowerCase();
    const filename = this.data.attachment.original_filename.toLowerCase();

    return mimeType.startsWith('image/')
      || /\.(jpe?g|png|webp|gif)$/i.test(filename);
  }

  get isPdf(): boolean {
    const mimeType = String(this.data.attachment.mime_type || '').toLowerCase();
    const filename = this.data.attachment.original_filename.toLowerCase();

    return mimeType === 'application/pdf' || filename.endsWith('.pdf');
  }

  get canDownload(): boolean {
    return Boolean(this.fileBlob && !this.loading && !this.error);
  }

  get fileSizeLabel(): string {
    const bytes = Number(this.data.attachment.size_bytes || 0);
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  close(): void {
    this.dialogRef.close();
  }

  download(): void {
    if (!this.fileBlob) {
      return;
    }

    const url = URL.createObjectURL(this.fileBlob);
    const anchor = document.createElement('a');

    anchor.href = url;
    anchor.download = this.data.attachment.original_filename;
    anchor.click();

    URL.revokeObjectURL(url);
  }

  private loadFile(): void {
    this.loading = true;
    this.error = '';

    this.requisitionService.downloadAttachment(
      this.data.requisitionId,
      this.data.attachment.id,
    ).subscribe({
      next: (blob) => {
        const mimeType = String(this.data.attachment.mime_type || '');
        this.fileBlob = blob.type || !mimeType
          ? blob
          : new Blob([blob], { type: mimeType });

        this.objectUrl = URL.createObjectURL(this.fileBlob);
        if (this.isPdf) {
          this.safeResourceUrl = this.sanitizer.bypassSecurityTrustResourceUrl(
            this.objectUrl,
          );
        }
        this.loading = false;
      },
      error: () => {
        this.fileBlob = null;
        this.error = 'No fue posible cargar la vista previa del adjunto.';
        this.loading = false;
      },
    });
  }

  private releaseObjectUrl(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = '';
      this.safeResourceUrl = null;
    }
  }
}
