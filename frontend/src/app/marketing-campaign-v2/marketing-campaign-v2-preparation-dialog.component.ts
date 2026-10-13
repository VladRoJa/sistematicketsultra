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

  close(): void { this.dialogRef.close(); }

  private onError(error: HttpErrorResponse): void {
    this.busy = false;
    this.error = String(error.error?.message || 'No se pudo completar la operación.');
  }
}
