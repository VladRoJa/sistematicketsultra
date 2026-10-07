import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';

export interface MarketingCampaignV2SubmitConfirmBatch {
  trackLabel: string;
  sucursalCanon: string;
  channelId: string;
  recipientCount: number;
}

export interface MarketingCampaignV2SubmitConfirmDialogData {
  campaignName: string;
  purposeLabel: string;
  templateName: string;
  frozenCount: number;
  blacklistedCount: number;
  recipientCount: number;
  providerCampaignCount: number;
  fingerprintVersion: string;
  fingerprint: string;
  batches: MarketingCampaignV2SubmitConfirmBatch[];
}

@Component({
  selector: 'app-marketing-campaign-v2-submit-confirm-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
  ],
  templateUrl: './marketing-campaign-v2-submit-confirm-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-submit-confirm-dialog.component.css'],
})
export class MarketingCampaignV2SubmitConfirmDialogComponent {
  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MarketingCampaignV2SubmitConfirmDialogData,
    private readonly dialogRef: MatDialogRef<
      MarketingCampaignV2SubmitConfirmDialogComponent,
      boolean
    >,
  ) {}

  cancel(): void {
    this.dialogRef.close(false);
  }

  confirm(): void {
    this.dialogRef.close(true);
  }
}
