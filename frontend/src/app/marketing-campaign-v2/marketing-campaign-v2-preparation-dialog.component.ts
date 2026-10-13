import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Inject, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  CampaignV2BranchReview, CampaignV2PreviousContactReview,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

export interface CampaignV2PreparationDialogData {
  campaignId: number;
  canManageDispatchConfig: boolean;
}

@Component({
  selector: 'app-marketing-campaign-v2-preparation-dialog',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatDialogModule,
    MatButtonModule, MatFormFieldModule, MatInputModule],
  templateUrl: './marketing-campaign-v2-preparation-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-preparation-dialog.component.css'],
})
export class MarketingCampaignV2PreparationDialogComponent {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2PreparationDialogComponent>);

  branchReview: CampaignV2BranchReview | null = null;
  previousReview: CampaignV2PreviousContactReview | null = null;
  busy = false;
  error = '';
  success = '';
  sourceIdsControl = new FormControl('', { nonNullable: true });
  confirmBranchControl = new FormControl('', { nonNullable: true });
  confirmPreviousControl = new FormControl('', { nonNullable: true });
  private sourceIds: number[] = [];

  constructor(@Inject(MAT_DIALOG_DATA) public readonly data: CampaignV2PreparationDialogData) {}

  changed = false;

  close(): void { this.dialogRef.close(this.changed); }

  reviewBranches(page = 1): void {
    if (this.busy) { return; }
    this.busy = true;
    this.error = '';
    this.confirmBranchControl.setValue('');
    this.api.reviewAmbiguousBranches(this.data.campaignId, page)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: review => { this.branchReview = review; this.busy = false; },
        error: error => this.onError(error),
      });
  }

  reviewPreviousContacts(): void {
    if (this.busy) { return; }
    const pieces = this.sourceIdsControl.value.split(',').map(x => x.trim());
    if (!pieces.length || pieces.length > 20 ||
        pieces.some(x => !/^[1-9]\\d*$/.test(x))) {
      this.error = 'Proporciona hasta 20 IDs positivos separados por comas.';
      return;
    }
    const ids = pieces.map(x => Number(x));
    if (ids.some(id => !Number.isSafeInteger(id) || id === this.data.campaignId)
        || new Set(ids).size !== ids.length) {
      this.error = 'Los orígenes deben ser distintos y anteriores a esta campaña.';
      return;
    }
    this.sourceIds = ids;
    this.busy = true;
    this.error = '';
    this.previousReview = null;
    this.confirmPreviousControl.setValue('');
    this.api.reviewPreviousContacts(this.data.campaignId, ids)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: review => { this.previousReview = review; this.busy = false; },
        error: error => this.onError(error),
      });
  }

  previousBranchesPage(): void {
    if (this.branchReview && this.branchReview.page > 1) {
      this.reviewBranches(this.branchReview.page - 1);
    }
  }

  nextBranchesPage(): void {
    if (this.branchReview && this.branchReview.rows.length === 25) {
      this.reviewBranches(this.branchReview.page + 1);
    }
  }

  get canApplyBranches(): boolean {
    return Boolean(this.data.canManageDispatchConfig && !this.busy
      && this.branchReview?.can_apply
      && this.branchReview.new_exclusions > 0
      && this.confirmBranchControl.value ===
      'EXCLUIR ' + this.branchReview.new_exclusions);
  }

  get canApplyPrevious(): boolean {
    return Boolean(this.data.canManageDispatchConfig && !this.busy
      && this.previousReview?.can_apply
      && this.previousReview.new_exclusions > 0
      && this.confirmPreviousControl.value ===
      'EXCLUIR ' + this.previousReview.new_exclusions);
  }

  applyBranches(): void {
    const review = this.branchReview;
    if (!review || !this.canApplyBranches) { return; }
    this.busy = true;
    this.error = '';
    this.api.applyAmbiguousBranches(this.data.campaignId, {
      expected_fingerprint: review.review_fingerprint,
      expected_count: review.new_exclusions,
      allow_bulk: review.new_exclusions >= 10,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.busy = false;
        this.changed = true;
        this.success = result.added + ' exclusiones auditadas. Revisa nuevamente el preflight.';
        this.branchReview = null;
        this.previousReview = null;
        this.confirmBranchControl.setValue('');
      },
      error: error => this.onError(error),
    });
  }

  applyPrevious(): void {
    const review = this.previousReview;
    if (!review || !this.canApplyPrevious) { return; }
    this.busy = true;
    this.error = '';
    this.api.applyPreviousContacts(this.data.campaignId, this.sourceIds, {
      expected_fingerprint: review.review_fingerprint,
      expected_count: review.new_exclusions,
      allow_bulk: review.new_exclusions >= 10,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.busy = false;
        this.changed = true;
        this.success = result.added + ' contactos anteriores excluidos; el preflight anterior ya no sirve.';
        this.branchReview = null;
        this.previousReview = null;
        this.confirmPreviousControl.setValue('');
      },
      error: error => this.onError(error),
    });
  }

  private onError(error: HttpErrorResponse): void {
    this.busy = false;
    this.error = String(error.error?.message || 'No se pudo completar la operación.');
  }
}
