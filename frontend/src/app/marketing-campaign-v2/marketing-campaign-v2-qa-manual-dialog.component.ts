import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import {
  CampaignV2ChannelBinding, CampaignV2Purpose,
  CampaignV2QaManualBaseRequest, CampaignV2QaManualFrozen, CampaignV2QaManualPreview,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

@Component({
  selector: 'app-marketing-campaign-v2-qa-manual-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-qa-manual-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-qa-manual-dialog.component.css'],
})
export class MarketingCampaignV2QaManualDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2QaManualDialogComponent>);

  readonly channelId = new FormControl('', { nonNullable: true });
  readonly campaignName = new FormControl('QA ', { nonNullable: true });
  readonly purpose = new FormControl<CampaignV2Purpose>('NEW_SALE', { nonNullable: true });
  readonly recipientName = new FormControl('', { nonNullable: true });
  readonly recipientPhone = new FormControl('', { nonNullable: true });
  readonly confirmFreeze = new FormControl(false, { nonNullable: true });

  channels: CampaignV2ChannelBinding[] = [];
  loading = false;
  previewing = false;
  freezing = false;
  error = '';
  success = '';
  preview: CampaignV2QaManualPreview | null = null;
  frozen: CampaignV2QaManualFrozen | null = null;
  private previewRequest: CampaignV2QaManualBaseRequest | null = null;

  ngOnInit(): void {
    for (const control of [
      this.channelId, this.campaignName, this.purpose, this.recipientName, this.recipientPhone,
    ]) {
      control.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.invalidatePreview());
    }
    this.loadChannels();
  }

  get selectedChannel(): CampaignV2ChannelBinding | undefined {
    return this.channels.find(binding => binding.provider_channel_id === this.channelId.value);
  }

  get canPreview(): boolean {
    const name = this.campaignName.value.trim();
    const phone = this.recipientPhone.value.trim();
    return !this.loading && !this.previewing && !this.freezing && !this.frozen &&
      Boolean(this.selectedChannel && name.length >= 4 && name.length <= 255 &&
        name.toUpperCase().startsWith('QA ') &&
        /^\\+?[0-9]{10,13}$/.test(phone) &&
        this.recipientName.value.trim().length <= 255);
  }

  get canFreeze(): boolean {
    return !this.loading && !this.previewing && !this.freezing && !this.frozen &&
      this.preview !== null && this.previewRequest !== null && this.confirmFreeze.value;
  }

  close(): void { this.dialogRef.close(); }

  loadChannels(): void {
    if (this.loading) { return; }
    this.loading = true;
    this.error = '';
    this.api.listDispatchChannelBindings().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        const candidates = result.rows.filter(
          binding => binding.provider === 'IVENTAS' && binding.is_active && binding.is_default,
        );
        const countByBranch = new Map<number, number>();
        for (const binding of candidates) {
          countByBranch.set(binding.sucursal_id, (countByBranch.get(binding.sucursal_id) ?? 0) + 1);
        }
        this.channels = candidates.filter(binding => countByBranch.get(binding.sucursal_id) === 1)
          .sort((a, b) => a.sucursal_canon.localeCompare(b.sucursal_canon));
        this.loading = false;
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.error = String(err.error?.message || 'No se pudieron consultar los canales iVentas.');
      },
    });
  }

  previewQa(): void {
    if (!this.canPreview) { return; }
    const selected = this.selectedChannel;
    if (!selected) { return; }
    const request: CampaignV2QaManualBaseRequest = {
      name: this.campaignName.value.trim(),
      purpose: this.purpose.value,
      sucursal_id: selected.sucursal_id,
      provider_channel_id: selected.provider_channel_id,
      recipients: [{
        name: this.recipientName.value.trim(),
        phone: this.recipientPhone.value.trim(),
      }],
    };
    this.previewing = true;
    this.error = '';
    this.success = '';
    this.api.previewQaManual(request).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.previewing = false;
        this.previewRequest = request;
        this.preview = result;
        this.confirmFreeze.setValue(false, { emitEvent: false });
      },
      error: (err: HttpErrorResponse) => {
        this.previewing = false;
        this.invalidatePreview();
        this.error = String(err.error?.message || 'Preview QA no disponible.');
      },
    });
  }

  freezeQa(): void {
    if (!this.canFreeze || !this.preview || !this.previewRequest) { return; }
    this.freezing = true;
    this.error = '';
    this.success = '';
    this.api.freezeQaManual({
      ...this.previewRequest,
      expected_preview_fingerprint: this.preview.preview_fingerprint,
      expected_channel_binding_id: this.preview.channel_binding_id,
      confirm_freeze: true,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.freezing = false;
        this.frozen = result;
        this.preview = null;
        this.previewRequest = null;
        this.confirmFreeze.setValue(false, { emitEvent: false });
        this.success = 'Cohorte QA congelada. No se enviaron mensajes.';
      },
      error: (err: HttpErrorResponse) => {
        this.freezing = false;
        this.invalidatePreview();
        this.error = String(err.error?.message || 'No se pudo congelar. Comprueba la lista antes de volver a intentar.');
      },
    });
  }

  private invalidatePreview(): void {
    this.preview = null;
    this.previewRequest = null;
    this.confirmFreeze.setValue(false, { emitEvent: false });
    if (!this.frozen) { this.success = ''; }
  }
}
