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
import { finalize, forkJoin, of, switchMap } from 'rxjs';

import { PurchaseRequisitionAccess } from './purchase-requisition-access.service';
import {
  AdministrativeCorrectionPayload,
  PurchaseRequisition,
  PurchaseRequisitionAttachment,
  PurchaseRequisitionAttachmentType,
  PurchaseRequisitionQuote,
  PurchaseRequisitionReceiptIssueType,
  PurchaseRequisitionService,
  PurchaseRequisitionStatus,
} from './purchase-requisition.service';
import {
  PurchaseRequisitionBranchOption,
  PurchaseRequisitionFormDialogComponent,
} from './purchase-requisition-form-dialog.component';
import {
  PurchaseRequisitionAttachmentPreviewDialogComponent,
} from './purchase-requisition-attachment-preview-dialog.component';

type WorkflowAction = 'REQUEST_INFO' | 'APPROVE' | 'REJECT' | 'RESUBMIT' | null;
type FinanceAction = 'APPROVE' | 'REJECT' | null;
type ReceiptAction = 'CONFIRM' | 'ISSUE' | null;

interface StatusOption {
  value: PurchaseRequisitionStatus;
  label: string;
}

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
  attachmentType: PurchaseRequisitionAttachmentType = 'EVIDENCE';
  attachmentBusy = false;
  attachmentError = '';

  quoteAttachmentId: number | null = null;
  quoteSupplierName = '';
  quoteAmount: number | null = null;
  quoteCurrency = 'MXN';
  quoteDate = '';
  quoteNotes = '';
  quoteBusy = false;
  quoteError = '';

  financeAction: FinanceAction = null;
  financeComment = '';
  financeBusy = false;
  financeError = '';

  logisticsTarget: PurchaseRequisitionStatus | '' = '';
  logisticsBusy = false;
  logisticsError = '';

  receiptAction: ReceiptAction = null;
  receiptComment = '';
  receiptIssueType: PurchaseRequisitionReceiptIssueType = 'DAMAGED';
  receiptFiles: File[] = [];
  receiptEvidenceIds: number[] = [];
  receiptBusy = false;
  receiptError = '';

  resolutionComment = '';
  resolutionBusy = false;
  resolutionError = '';

  adminCorrectionOpen = false;
  adminCorrectionTarget: PurchaseRequisitionStatus | '' = '';
  adminCorrectionReason = '';
  adminCorrectionComment = '';
  adminCorrectionClosedConfirmed = false;
  adminCorrectionBusy = false;
  adminCorrectionError = '';

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

  get availableQuoteAttachments(): PurchaseRequisitionAttachment[] {
    const usedIds = new Set(
      (this.requisition?.quotes || []).map(quote => quote.attachment_id),
    );
    return (this.requisition?.attachments || []).filter(
      attachment => attachment.attachment_type === 'QUOTE'
        && !usedIds.has(attachment.id),
    );
  }

  get selectedQuote(): PurchaseRequisitionQuote | null {
    return (this.requisition?.quotes || []).find(quote => quote.is_selected) || null;
  }

  get canCreateStructuredQuote(): boolean {
    return this.canUploadQuote;
  }

  get canSubmitQuoteForFinance(): boolean {
    return Boolean(
      this.canUploadQuote
      && this.selectedQuote
      && this.selectedQuote.finance_status === 'DRAFT',
    );
  }

  get canFinanceDecide(): boolean {
    return Boolean(
      this.requisition?.status === 'QUOTE_PENDING_FINANCE_APPROVAL'
      && this.data.access.can_approve_requisition_quote,
    );
  }

  get financeActionTitle(): string {
    return this.financeAction === 'APPROVE'
      ? 'Aprobar cotización'
      : 'Rechazar cotización';
  }

  get financeActionPlaceholder(): string {
    return this.financeAction === 'REJECT'
      ? 'Motivo del rechazo financiero.'
      : 'Comentario de aprobación (opcional).';
  }

  get financeActionRequired(): boolean {
    return this.financeAction === 'REJECT';
  }

  get canAdvanceLogistics(): boolean {
    const status = this.requisition?.status;
    return Boolean(
      this.data.access.can_manage_requisition_logistics
      && status
      && ['PAYMENT_REQUESTED', 'SHIPPING_IN_PROGRESS', 'IMPORT_IN_PROGRESS'].includes(status),
    );
  }

  get logisticsOptions(): StatusOption[] {
    const status = this.requisition?.status;
    if (status === 'PAYMENT_REQUESTED') {
      return [{ value: 'SHIPPING_IN_PROGRESS', label: 'En proceso de envío' }];
    }
    if (status === 'SHIPPING_IN_PROGRESS') {
      return [
        { value: 'IMPORT_IN_PROGRESS', label: 'En proceso de importación' },
        { value: 'FINAL_DESTINATION_SHIPMENT', label: 'Envío a destino final' },
      ];
    }
    if (status === 'IMPORT_IN_PROGRESS') {
      return [{
        value: 'FINAL_DESTINATION_SHIPMENT',
        label: 'Envío a destino final',
      }];
    }
    return [];
  }

  get canSubmitLogisticsAdvance(): boolean {
    return Boolean(
      !this.logisticsBusy
      && this.logisticsTarget
      && this.logisticsOptions.some(
        option => option.value === this.logisticsTarget,
      ),
    );
  }

  get canReceive(): boolean {
    if (
      !this.requisition
      || this.requisition.status !== 'FINAL_DESTINATION_SHIPMENT'
      || !this.data.access.can_confirm_receipt
    ) {
      return false;
    }
    return this.data.access.allowed_branch_ids.includes(
      this.requisition.sucursal_id,
    );
  }

  get receiptActionTitle(): string {
    return this.receiptAction === 'ISSUE'
      ? 'Reportar incidencia de recepción'
      : 'Confirmar recibido';
  }

  get receiptActionPlaceholder(): string {
    return this.receiptAction === 'ISSUE'
      ? 'Describe el daño, faltante o diferencia encontrada.'
      : 'Observaciones de recepción (opcional).';
  }

  get receiptEvidenceRequired(): boolean {
    return this.receiptAction === 'ISSUE';
  }

  get receiptIssueActionActive(): boolean {
    return this.receiptAction === 'ISSUE';
  }

  get canResumeLogistics(): boolean {
    return Boolean(
      this.requisition?.status === 'RECEIPT_ISSUE'
      && this.data.access.can_manage_requisition_logistics,
    );
  }

  get latestReceiptIssueEvent() {
    return [...(this.requisition?.events || [])]
      .reverse()
      .find(event => event.event_type === 'RECEIPT_ISSUE_REPORTED') || null;
  }

  get latestReceiptIssueTypeLabel(): string {
    const issueType = String(
      this.latestReceiptIssueEvent?.metadata_json?.['issue_type'] || '',
    );
    const option = this.receiptIssueOptions.find(
      item => item.value === issueType,
    );
    return option?.label || 'Incidencia de recepción';
  }

  get receiptIssueOptions(): Array<{
    value: PurchaseRequisitionReceiptIssueType;
    label: string;
  }> {
    return [
      { value: 'DAMAGED', label: 'Recibido dañado' },
      { value: 'INCOMPLETE', label: 'Entrega incompleta / faltantes' },
      { value: 'WRONG_ITEM', label: 'Artículo o equipo incorrecto' },
      { value: 'OTHER', label: 'Otra no conformidad' },
    ];
  }

  get canAdminCorrect(): boolean {
    return Boolean(
      this.data.access.can_admin_correct_requisition
      && this.administrativeCorrectionTargets.length > 0,
    );
  }

  get administrativeCorrectionReopensClosed(): boolean {
    return this.requisition?.status === 'CLOSED';
  }

  get finalDestinationCorrectionTargets(): StatusOption[] {
    const event = [...(this.requisition?.events || [])]
      .reverse()
      .find(item => (
        item.event_type === 'FINAL_DESTINATION_SHIPMENT_STARTED'
      ));
    const importRequired = event?.metadata_json?.['import_required'];

    if (importRequired === true) {
      return [{
        value: 'IMPORT_IN_PROGRESS',
        label: 'En proceso de importación',
      }];
    }
    if (importRequired === false) {
      return [{
        value: 'SHIPPING_IN_PROGRESS',
        label: 'En proceso de envío',
      }];
    }
    return [];
  }

  get administrativeCorrectionSubmitDisabled(): boolean {
    if (this.adminCorrectionBusy || !this.adminCorrectionTarget) {
      return true;
    }
    if (
      this.administrativeCorrectionReopensClosed
      && !this.adminCorrectionClosedConfirmed
    ) {
      return true;
    }
    return false;
  }

  get administrativeCorrectionTargets(): StatusOption[] {
    const status = this.requisition?.status;
    const matrix: Partial<Record<PurchaseRequisitionStatus, StatusOption[]>> = {
      NEEDS_INFO: [
        { value: 'PENDING_REVIEW', label: 'Pendiente de revisión' },
      ],
      REJECTED: [
        { value: 'PENDING_REVIEW', label: 'Pendiente de revisión' },
      ],
      IN_QUOTATION: [
        { value: 'PENDING_REVIEW', label: 'Pendiente de revisión' },
      ],
      QUOTE_PENDING_FINANCE_APPROVAL: [
        { value: 'IN_QUOTATION', label: 'En cotización' },
      ],
      PAYMENT_REQUESTED: [
        {
          value: 'QUOTE_PENDING_FINANCE_APPROVAL',
          label: 'Pendiente de aprobación financiera',
        },
      ],
      SHIPPING_IN_PROGRESS: [
        { value: 'PAYMENT_REQUESTED', label: 'En solicitud de pago' },
      ],
      IMPORT_IN_PROGRESS: [
        { value: 'SHIPPING_IN_PROGRESS', label: 'En proceso de envío' },
      ],
      FINAL_DESTINATION_SHIPMENT: this.finalDestinationCorrectionTargets,
      RECEIPT_ISSUE: [
        {
          value: 'FINAL_DESTINATION_SHIPMENT',
          label: 'Envío a destino final',
        },
      ],
      CLOSED: [
        {
          value: 'FINAL_DESTINATION_SHIPMENT',
          label: 'Envío a destino final',
        },
        { value: 'RECEIPT_ISSUE', label: 'Incidencia de recepción' },
      ],
    };
    return status ? matrix[status] || [] : [];
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
        this.normalizeLogisticsTarget();
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
        next: (response) => {
          if (this.attachmentType === 'QUOTE') {
            this.quoteAttachmentId = response.attachment.id;
          }
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

  createStructuredQuote(): void {
    if (!this.requisition || !this.canCreateStructuredQuote) {
      return;
    }

    const supplierName = this.quoteSupplierName.trim();
    const currency = this.quoteCurrency.trim().toUpperCase();
    const notes = this.quoteNotes.trim();

    if (!this.quoteAttachmentId) {
      this.quoteError = 'Selecciona el archivo de cotización.';
      return;
    }
    if (!supplierName) {
      this.quoteError = 'El proveedor es obligatorio.';
      return;
    }
    if (!this.quoteAmount || this.quoteAmount <= 0) {
      this.quoteError = 'El monto debe ser mayor que cero.';
      return;
    }
    if (!currency) {
      this.quoteError = 'La moneda es obligatoria.';
      return;
    }
    if (!this.quoteDate) {
      this.quoteError = 'La fecha de cotización es obligatoria.';
      return;
    }

    this.quoteBusy = true;
    this.quoteError = '';

    this.requisitionService.createQuote(this.requisition.id, {
      supplier_name: supplierName,
      amount: this.quoteAmount,
      currency,
      quote_date: this.quoteDate,
      attachment_id: this.quoteAttachmentId,
      notes: notes || null,
    })
      .pipe(finalize(() => {
        this.quoteBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.resetQuoteForm();
          this.loadDetail();
        },
        error: (error) => {
          this.quoteError = String(
            error?.error?.mensaje || 'No fue posible registrar la cotización.',
          );
        },
      });
  }

  selectQuote(quote: PurchaseRequisitionQuote): void {
    if (!this.requisition || !this.canUploadQuote || quote.finance_status !== 'DRAFT') {
      return;
    }

    this.quoteBusy = true;
    this.quoteError = '';
    this.requisitionService.selectQuote(this.requisition.id, quote.id)
      .pipe(finalize(() => {
        this.quoteBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.loadDetail();
        },
        error: (error) => {
          this.quoteError = String(
            error?.error?.mensaje || 'No fue posible seleccionar la cotización.',
          );
        },
      });
  }

  submitQuoteForFinance(): void {
    if (!this.requisition || !this.canSubmitQuoteForFinance) {
      return;
    }

    this.quoteBusy = true;
    this.quoteError = '';
    this.requisitionService.submitQuoteForFinance(this.requisition.id)
      .pipe(finalize(() => {
        this.quoteBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.loadDetail();
        },
        error: (error) => {
          this.quoteError = String(
            error?.error?.mensaje || 'No fue posible enviar la cotización a Finanzas.',
          );
        },
      });
  }

  chooseFinanceAction(action: Exclude<FinanceAction, null>): void {
    this.financeAction = action;
    this.financeComment = '';
    this.financeError = '';
  }

  cancelFinanceAction(): void {
    this.financeAction = null;
    this.financeComment = '';
    this.financeError = '';
  }

  submitFinanceAction(): void {
    if (!this.requisition || !this.financeAction || !this.canFinanceDecide) {
      return;
    }

    const comment = this.financeComment.trim();
    if (this.financeAction === 'REJECT' && !comment) {
      this.financeError = 'El motivo del rechazo es obligatorio.';
      return;
    }

    this.financeBusy = true;
    this.financeError = '';
    const request$ = this.financeAction === 'APPROVE'
      ? this.requisitionService.approveQuoteByFinance(
          this.requisition.id,
          comment,
        )
      : this.requisitionService.rejectQuoteByFinance(
          this.requisition.id,
          comment,
        );

    request$
      .pipe(finalize(() => {
        this.financeBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.cancelFinanceAction();
          this.loadDetail();
        },
        error: (error) => {
          this.financeError = String(
            error?.error?.mensaje || 'No fue posible registrar la decisión financiera.',
          );
        },
      });
  }

  onLogisticsTargetChange(
    candidate: PurchaseRequisitionStatus | '',
  ): void {
    this.logisticsTarget = this.logisticsOptions.some(
      option => option.value === candidate,
    )
      ? candidate
      : '';
    this.logisticsError = '';
  }

  advanceLogistics(): void {
    if (
      !this.requisition
      || !this.canAdvanceLogistics
      || !this.canSubmitLogisticsAdvance
    ) {
      return;
    }

    const target = this.logisticsTarget;
    if (
      !target
      || !this.logisticsOptions.some(option => option.value === target)
    ) {
      this.logisticsError = 'Selecciona el siguiente estado permitido.';
      return;
    }

    this.logisticsBusy = true;
    this.logisticsError = '';
    this.requisitionService.advanceLogistics(this.requisition.id, target)
      .pipe(finalize(() => {
        this.logisticsBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.logisticsTarget = '';
          this.loadDetail();
        },
        error: (error) => {
          this.logisticsError = String(
            error?.error?.mensaje || 'No fue posible avanzar la logística.',
          );
        },
      });
  }

  chooseReceiptAction(action: Exclude<ReceiptAction, null>): void {
    this.receiptAction = action;
    this.receiptComment = '';
    this.receiptFiles = [];
    this.receiptEvidenceIds = [];
    this.receiptError = '';
  }

  cancelReceiptAction(): void {
    this.receiptAction = null;
    this.receiptComment = '';
    this.receiptFiles = [];
    this.receiptEvidenceIds = [];
    this.receiptError = '';
  }

  onReceiptFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.receiptFiles = Array.from(input.files || []);
    this.receiptEvidenceIds = [];
    this.receiptError = '';
  }

  submitReceiptAction(): void {
    if (!this.requisition || !this.receiptAction || !this.canReceive) {
      return;
    }

    const comment = this.receiptComment.trim();
    if (this.receiptAction === 'ISSUE' && !comment) {
      this.receiptError = 'Describe la incidencia de recepción.';
      return;
    }
    if (this.receiptAction === 'ISSUE' && this.receiptFiles.length === 0
        && this.receiptEvidenceIds.length === 0) {
      this.receiptError = 'Adjunta al menos una evidencia de la incidencia.';
      return;
    }

    this.receiptBusy = true;
    this.receiptError = '';

    const attachmentType: PurchaseRequisitionAttachmentType =
      this.receiptAction === 'ISSUE'
        ? 'RECEIPT_ISSUE_EVIDENCE'
        : 'RECEIPT_EVIDENCE';

    const upload$ = this.receiptEvidenceIds.length > 0
      ? of(this.receiptEvidenceIds)
      : this.uploadReceiptFiles(attachmentType);

    upload$
      .pipe(
        switchMap((evidenceIds) => {
          this.receiptEvidenceIds = evidenceIds;
          if (this.receiptAction === 'ISSUE') {
            return this.requisitionService.reportReceiptIssue(
              this.requisition!.id,
              {
                issue_type: this.receiptIssueType,
                comment,
                evidence_attachment_ids: evidenceIds,
              },
            );
          }
          return this.requisitionService.confirmReceipt(
            this.requisition!.id,
            {
              comment: comment || null,
              evidence_attachment_ids: evidenceIds,
            },
          );
        }),
        finalize(() => {
          this.receiptBusy = false;
        }),
      )
      .subscribe({
        next: () => {
          this.changed = true;
          this.cancelReceiptAction();
          this.loadDetail();
        },
        error: (error) => {
          this.receiptError = String(
            error?.error?.mensaje || 'No fue posible registrar la recepción.',
          );
        },
      });
  }

  resumeLogistics(): void {
    if (!this.requisition || !this.canResumeLogistics) {
      return;
    }
    const comment = this.resolutionComment.trim();
    if (!comment) {
      this.resolutionError = 'Describe la acción tomada para resolver la incidencia.';
      return;
    }

    this.resolutionBusy = true;
    this.resolutionError = '';
    this.requisitionService.resumeLogistics(this.requisition.id, comment)
      .pipe(finalize(() => {
        this.resolutionBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.resolutionComment = '';
          this.loadDetail();
        },
        error: (error) => {
          this.resolutionError = String(
            error?.error?.mensaje || 'No fue posible reanudar la logística.',
          );
        },
      });
  }

  openAdministrativeCorrection(): void {
    if (!this.canAdminCorrect) {
      return;
    }
    this.adminCorrectionOpen = true;
    this.adminCorrectionTarget = this.administrativeCorrectionTargets[0]?.value || '';
    this.adminCorrectionReason = '';
    this.adminCorrectionComment = '';
    this.adminCorrectionClosedConfirmed = false;
    this.adminCorrectionError = '';
  }

  cancelAdministrativeCorrection(): void {
    this.adminCorrectionOpen = false;
    this.adminCorrectionTarget = '';
    this.adminCorrectionReason = '';
    this.adminCorrectionComment = '';
    this.adminCorrectionClosedConfirmed = false;
    this.adminCorrectionError = '';
  }

  submitAdministrativeCorrection(): void {
    if (!this.requisition || !this.canAdminCorrect || !this.adminCorrectionTarget) {
      return;
    }

    const reason = this.adminCorrectionReason.trim();
    const comment = this.adminCorrectionComment.trim();
    if (!reason || !comment) {
      this.adminCorrectionError = 'Motivo y comentario son obligatorios.';
      return;
    }
    if (
      this.administrativeCorrectionReopensClosed
      && !this.adminCorrectionClosedConfirmed
    ) {
      this.adminCorrectionError = (
        'Confirma explícitamente que deseas reabrir una requisición cerrada.'
      );
      return;
    }

    const payload: AdministrativeCorrectionPayload = {
      target_status: this.adminCorrectionTarget,
      reason,
      comment,
    };

    this.adminCorrectionBusy = true;
    this.adminCorrectionError = '';
    this.requisitionService.administrativeCorrection(
      this.requisition.id,
      payload,
    )
      .pipe(finalize(() => {
        this.adminCorrectionBusy = false;
      }))
      .subscribe({
        next: () => {
          this.changed = true;
          this.cancelAdministrativeCorrection();
          this.loadDetail();
        },
        error: (error) => {
          this.adminCorrectionError = String(
            error?.error?.mensaje || 'No fue posible aplicar la corrección administrativa.',
          );
        },
      });
  }

  canSelectQuote(quote: PurchaseRequisitionQuote): boolean {
    return Boolean(
      this.canUploadQuote
      && quote.finance_status === 'DRAFT'
      && !quote.is_selected,
    );
  }

  quoteAttachmentName(quote: PurchaseRequisitionQuote): string {
    return (this.requisition?.attachments || []).find(
      attachment => attachment.id === quote.attachment_id,
    )?.original_filename || `Adjunto #${quote.attachment_id}`;
  }

  openQuoteAttachmentPreview(quote: PurchaseRequisitionQuote): void {
    const attachment = (this.requisition?.attachments || []).find(
      item => item.id === quote.attachment_id,
    );
    if (attachment) {
      this.openAttachmentPreview(attachment);
    }
  }

  quoteFinanceStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      DRAFT: 'Borrador',
      PENDING: 'Pendiente de aprobación',
      APPROVED: 'Aprobada',
      REJECTED: 'Rechazada',
    };
    return labels[status] || status;
  }

  openAttachmentPreview(
    attachment: PurchaseRequisitionAttachment,
  ): void {
    if (!this.requisition) {
      return;
    }

    this.dialog.open(PurchaseRequisitionAttachmentPreviewDialogComponent, {
      width: '960px',
      maxWidth: '96vw',
      maxHeight: '92vh',
      autoFocus: false,
      restoreFocus: false,
      data: {
        requisitionId: this.requisition.id,
        attachment,
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
      QUOTE_PENDING_FINANCE_APPROVAL: 'Pendiente de aprobación financiera',
      PAYMENT_REQUESTED: 'En solicitud de pago',
      SHIPPING_IN_PROGRESS: 'En proceso de envío',
      IMPORT_IN_PROGRESS: 'En proceso de importación',
      FINAL_DESTINATION_SHIPMENT: 'Envío a destino final',
      RECEIPT_ISSUE: 'Incidencia de recepción',
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
      QUOTE_ADDED: 'Cotización registrada',
      QUOTE_SELECTED: 'Cotización seleccionada',
      QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL: 'Cotización enviada a Finanzas',
      QUOTE_APPROVED_BY_FINANCE: 'Cotización aprobada por Finanzas',
      QUOTE_REJECTED_BY_FINANCE: 'Cotización rechazada por Finanzas',
      PAYMENT_REQUESTED: 'Solicitud de pago iniciada',
      SHIPPING_STARTED: 'Envío iniciado',
      IMPORT_STARTED: 'Importación iniciada',
      IMPORT_NOT_APPLICABLE: 'Importación no aplica',
      FINAL_DESTINATION_SHIPMENT_STARTED: 'Envío a destino final',
      RECEIVED: 'Recibido conforme',
      RECEIPT_ISSUE_REPORTED: 'Incidencia de recepción reportada',
      RECEIPT_ISSUE_RESOLUTION_STARTED: 'Resolución de incidencia iniciada',
      ADMINISTRATIVE_CORRECTION: 'Corrección administrativa',
    };
    return labels[eventType] || eventType;
  }

  attachmentTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      EVIDENCE: 'Evidencia',
      QUOTE: 'Cotización',
      OTHER: 'Otro',
      RECEIPT_EVIDENCE: 'Evidencia de recepción',
      RECEIPT_ISSUE_EVIDENCE: 'Evidencia de incidencia',
    };
    return labels[type] || type;
  }

  fileSizeLabel(sizeBytes: number): string {
    if (sizeBytes < 1024 * 1024) {
      return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
    }
    return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private normalizeLogisticsTarget(): void {
    if (
      this.logisticsTarget
      && !this.logisticsOptions.some(
        option => option.value === this.logisticsTarget,
      )
    ) {
      this.logisticsTarget = '';
    }
  }

  private uploadReceiptFiles(
    attachmentType: PurchaseRequisitionAttachmentType,
  ) {
    if (!this.requisition || this.receiptFiles.length === 0) {
      return of([] as number[]);
    }

    return forkJoin(
      this.receiptFiles.map(file => this.requisitionService.uploadAttachment(
        this.requisition!.id,
        attachmentType,
        file,
      )),
    ).pipe(
      switchMap(responses => of(
        responses.map(response => response.attachment.id),
      )),
    );
  }

  private resetQuoteForm(): void {
    this.quoteAttachmentId = null;
    this.quoteSupplierName = '';
    this.quoteAmount = null;
    this.quoteCurrency = 'MXN';
    this.quoteDate = '';
    this.quoteNotes = '';
    this.quoteError = '';
  }

  private normalizeAttachmentType(): void {
    if (this.canUploadQuote) {
      this.attachmentType = 'QUOTE';
      return;
    }
    this.attachmentType = 'EVIDENCE';
  }
}
