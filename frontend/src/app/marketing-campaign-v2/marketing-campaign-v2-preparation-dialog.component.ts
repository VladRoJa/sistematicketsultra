import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Inject, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import {
  CampaignV2BranchReview, CampaignV2PreviousContactReview,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { parsePreviousCampaignIds } from './marketing-campaign-v2-preparation.logic';

export interface CampaignV2PreparationDialogData {
  campaignId: number;
  canManageDispatchConfig: boolean;
}

@Component({
  selector: 'app-marketing-campaign-v2-preparation-dialog',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatDialogModule,
    MatButtonModule, MatFormFieldModule, MatInputModule, MatProgressSpinnerModule],
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
  workingAction: 'branches-review' | 'branches-apply' | 'previous-review' | 'previous-apply' | null = null;
  error = '';
  previousError = '';
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
    this.workingAction = 'branches-review';
    this.error = '';
    this.confirmBranchControl.setValue('');
    this.api.reviewAmbiguousBranches(this.data.campaignId, page)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: review => { this.branchReview = review; this.busy = false; this.workingAction = null; },
        error: error => this.onError(error),
      });
  }

  reviewPreviousContacts(): void {
    if (this.busy) { return; }
    const parsed = parsePreviousCampaignIds(this.sourceIdsControl.value, this.data.campaignId);
    this.previousError = parsed.error;
    if (parsed.error) {
      this.previousReview = null;
      return;
    }
    this.sourceIds = parsed.ids;
    this.busy = true;
    this.workingAction = 'previous-review';
    this.error = '';
    this.previousReview = null;
    this.confirmPreviousControl.setValue('');
    this.api.reviewPreviousContacts(this.data.campaignId, parsed.ids)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: review => {
          this.previousReview = review;
          this.busy = false;
          this.workingAction = null;
          this.previousError = '';
        },
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
    this.workingAction = 'branches-apply';
    this.error = '';
    this.api.applyAmbiguousBranches(this.data.campaignId, {
      expected_fingerprint: review.review_fingerprint,
      expected_count: review.new_exclusions,
      allow_bulk: review.new_exclusions >= 10,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.busy = false;
        this.workingAction = null;
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
    this.workingAction = 'previous-apply';
    this.error = '';
    this.previousError = '';
    this.api.applyPreviousContacts(this.data.campaignId, this.sourceIds, {
      expected_fingerprint: review.review_fingerprint,
      expected_count: review.new_exclusions,
      allow_bulk: review.new_exclusions >= 10,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.busy = false;
        this.workingAction = null;
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
    const message = String(error.error?.message || 'No se pudo completar la operación.');
    this.previousError = this.workingAction?.startsWith('previous-') ? message : '';
    this.error = this.workingAction?.startsWith('branches-') ? message : '';
    this.busy = false;
    this.workingAction = null;
  }
}
