import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

export interface CobranzaSendDialogData {
  campaignId: number;
  campaignName: string;
  recipientCount: number;
  pilotBranch: string | null;
}

@Component({
  selector: 'app-campaign-v2-cobranza-send-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule, MatButtonModule,
    MatFormFieldModule, MatInputModule,
  ],
  templateUrl: './marketing-campaign-v2-cobranza-send-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-cobranza-send-dialog.component.css'],
})
export class MarketingCampaignV2CobranzaSendDialogComponent {
  readonly data = inject<CobranzaSendDialogData>(MAT_DIALOG_DATA);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2CobranzaSendDialogComponent>);
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  readonly password = new FormControl('', { nonNullable: true });
  submitting = false;
  error = '';

  close(): void {
    if (!this.submitting) { this.dialogRef.close(false); }
  }

  send(): void {
    if (this.submitting || !this.password.value) { return; }
    this.submitting = true;
    this.error = '';
    this.service.sendCobranza(this.data.campaignId, this.password.value)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.password.setValue('');
          this.dialogRef.close(result.job_id);
        },
        error: (error: HttpErrorResponse) => {
          this.password.setValue('');
          this.submitting = false;
          this.error = String(error.error?.message || 'No se pudo iniciar el envío de cobranza.');
        },
      });
  }
}
