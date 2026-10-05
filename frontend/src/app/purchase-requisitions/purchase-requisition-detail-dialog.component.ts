import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { finalize } from 'rxjs';

import { PurchaseRequisitionAccess } from './purchase-requisition-access.service';
import {
  PurchaseRequisition,
  PurchaseRequisitionAttachment,
  PurchaseRequisitionService,
} from './purchase-requisition.service';
import {
  PurchaseRequisitionBranchOption,
  PurchaseRequisitionFormDialogComponent,
} from './purchase-requisition-form-dialog.component';

type WorkflowAction = 'REQUEST_INFO' | 'APPROVE' | 'REJECT' | 'RESUBMIT' | null;

export interface PurchaseRequisitionDetailDialogData {
  requisitionId: number;
  access: PurchaseRequisitionAccess;
  branches: PurchaseRequisitionBranchOption[];
}

@Component({
  selector: 'app-purchase-requisition-detail-dialog',
  standalone: true,
  templateUrl: './purchase-requisition-detail-dialog.component.html',
  styleUrls: ['./purchase-requisition-detail-dialog.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
})
export class PurchaseRequisitionDetailDialogComponent implements OnInit {
  requisition: PurchaseRequisition | null = null;
  loading = true;
  loadError = '';

  actionMode: WorkflowAction = null;
  actionComment = '';
  actionBusy = false;
  actionError = '';

  selectedFile: File | null = null;
  attachmentType: 'EVIDENCE' | 'QUOTE' | 'OTHER' = 'EVIDENCE';
  attachmentBusy = false;
  attachmentError = '';

  changed = false;

  constructor(
    private readonly requisitionService: PurchaseRequisitionService,
    private readonly dialog: MatDialog,
    private readonly dialogRef: MatDialogRef<PurchaseRequisitionDetailDialogComponent>,
    @Inject(MAT_DIALOG_DATA)
    readonly data: PurchaseRequisitionDetailDialogData,
  ) {}

  ngOnInit(): void {
    this.loadDetail();
  }

  get isCreator(): boolean {
    return Boolean(
      this.requisition
      && this.data.access.user?.id === this.requisition.created_by_user_id
    );
  }

  get canReview(): boolean {
    return Boolean(
      this.requisition?.status === 'PENDING_REVIEW'
      && this.data.access.can_review
    );
  }

  get canEdit(): boolean {
    return Boolean(
      this.requisition?.status === 'NEEDS_INFO'
      && this.isCreator
    );
  }

  get canResubmit(): boolean {
    return this.canEdit;
  }

  get canUploadEvidence(): boolean {
    return Boolean(
      this.isCreator
      && ['PENDING_REVIEW', 'NEEDS_INFO'].includes(
        String(this.requisition?.status || ''),
      )
    );
  }

  get canUploadQuote(): boolean {
    return Boolean(
      this.requisition?.status === 'IN_QUOTATION'
      && this.data.access.can_manage_quotation
    );
  }

  get canUploadAttachment(): boolean {
    return this.canUploadEvidence || this.canUploadQuote;
  }

  get actionTitle(): string {
    const labels: Record<string, string> = {
      REQUEST_INFO: 'Solicitar información',
      APPROVE: 'Aprobar requisición',
      REJECT: 'Rechazar requisición',
      RESUBMIT: 'Reenviar a revisión',
    };
    return this.actionMode ? labels[this.actionMode] : '';
  }

  get actionPlaceholder(): string {
    if (this.actionMode === 'REQUEST_INFO') {
      return 'Indica qué información debe corregir o completar el solicitante.';
    }
    if (this.actionMode === 'REJECT') {
      return 'Motivo del rechazo.';
    }
    if (this.actionMode === 'APPROVE') {
      return 'Comentario de aprobación (opcional).';
    }
    return 'Comentario de reenvío (opcional).';
  }

  get actionCommentRequired(): boolean {
    return this.actionMode === 'REQUEST_INFO' || this.actionMode === 'REJECT';
  }

  loadDetail(): void {
    this.loading = true;
    this.loadError = '';

    this.requisitionService.get(this.data.requisitionId).subscribe({
      next: (response) => {
        this.requisition = response.requisition;
        this.loading = false;
        this.normalizeAttachmentType();
      },
      error: (error) => {
        this.loadError = String(
          error?.error?.mensaje || 'No fue posible cargar la requisición.',
        );
        this.loading = false;
      },
    });
  }

  close(): void {
    this.dialogRef.close(this.changed);
  }

  openEdit(): void {
    if (!this.canEdit || !this.requisition) {
      return;
    }

    const ref = this.dialog.open(PurchaseRequisitionFormDialogComponent, {
      width: '860px',
      maxWidth: '96vw',
      autoFocus: false,
      restoreFocus: false,
      data: {
        branches: this.data.branches,
        requisition: this.requisition,
      },
    });

    ref.afterClosed().subscribe((updated) => {
      if (updated) {
        this.changed = true;
        this.loadDetail();
      }
    });
  }

  chooseAction(action: Exclude<WorkflowAction, null>): void {
    this.actionMode = action;
    this.actionComment = '';
    this.actionError = '';
  }

  cancelAction(): void {
    this.actionMode = null;
    this.actionComment = '';
    this.actionError = '';
  }

  submitAction(): void {
    if (!this.requisition || !this.actionMode) {
      return;
    }

    const comment = this.actionComment.trim();
    if (this.actionCommentRequired && !comment) {
      this.actionError = 'El comentario es obligatorio para esta acción.';
      return;
    }

    this.actionBusy = true;
    this.actionError = '';

    const request$ = this.actionMode === 'REQUEST_INFO'
      ? this.requisitionService.requestInfo(this.requisition.id, comment)
      : this.actionMode === 'APPROVE'
        ? this.requisitionService.approve(this.requisition.id, comment)
        : this.actionMode === 'REJECT'
          ? this.requisitionService.reject(this.requisition.id, comment)
          : this.requisitionService.resubmit(this.requisition.id, comment);

    request$
      .pipe(finalize(() => {
        this.actionBusy = false;
      }))
      .subscribe({
        next: (response) => {
          this.requisition = response.requisition;
          this.changed = true;
          this.cancelAction();
          this.loadDetail();
        },
        error: (error) => {
          this.actionError = String(
            error?.error?.mensaje || 'No fue posible completar la acción.',
          );
        },
      });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] || null;
    this.attachmentError = '';
  }

  uploadAttachment(): void {
    if (!this.requisition || !this.selectedFile || !this.canUploadAttachment) {
      return;
    }

    this.attachmentBusy = true;
    this.attachmentError = '';

    this.requisitionService.uploadAttachment(
      this.requisition.id,
      this.attachmentType,
      this.selectedFile,
    )
      .pipe(finalize(() => {
        this.attachmentBusy = false;
      }))
      .subscribe({
        next: () => {
          this.selectedFile = null;
          this.changed = true;
          this.loadDetail();
        },
        error: (error) => {
          this.attachmentError = String(
            error?.error?.mensaje || 'No fue posible subir el adjunto.',
          );
        },
      });
  }

  downloadAttachment(attachment: PurchaseRequisitionAttachment): void {
    if (!this.requisition) {
      return;
    }

    this.requisitionService.downloadAttachment(
      this.requisition.id,
      attachment.id,
    ).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = attachment.original_filename;
        anchor.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.attachmentError = 'No fue posible descargar el adjunto.';
      },
    });
  }

  branchLabel(branchId: number): string {
    return this.data.branches.find(branch => branch.id === branchId)?.name
      || `Sucursal #${branchId}`;
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      PENDING_REVIEW: 'Pendiente de revisión',
      NEEDS_INFO: 'Requiere información',
      IN_QUOTATION: 'En cotización',
      REJECTED: 'Rechazada',
      CLOSED: 'Cerrada',
    };
    return labels[status] || status;
  }

  priorityLabel(priority: string): string {
    const labels: Record<string, string> = {
      NORMAL: 'Normal',
      HIGH: 'Alta',
      CRITICAL: 'Crítica',
    };
    return labels[priority] || priority;
  }

  reasonLabel(reason: string): string {
    const labels: Record<string, string> = {
      REPLACEMENT: 'Reemplazo',
      NEW_EQUIPMENT: 'Equipo nuevo',
      DAMAGE: 'Daño',
      EXPANSION: 'Expansión',
      OTHER: 'Otro',
    };
    return labels[reason] || reason;
  }

  eventLabel(eventType: string): string {
    const labels: Record<string, string> = {
      CREATED: 'Creada',
      INFO_REQUESTED: 'Información solicitada',
      RESUBMITTED: 'Reenviada',
      APPROVED: 'Aprobada',
      REJECTED: 'Rechazada',
      ROUTED_TO_MAINTENANCE: 'Enviada a Mantenimiento',
      ATTACHMENT_ADDED: 'Adjunto agregado',
    };
    return labels[eventType] || eventType;
  }

  attachmentTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      EVIDENCE: 'Evidencia',
      QUOTE: 'Cotización',
      OTHER: 'Otro',
    };
    return labels[type] || type;
  }

  fileSizeLabel(sizeBytes: number): string {
    if (sizeBytes < 1024 * 1024) {
      return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
    }
    return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private normalizeAttachmentType(): void {
    if (this.canUploadQuote) {
      this.attachmentType = 'QUOTE';
      return;
    }
    this.attachmentType = 'EVIDENCE';
  }
}
