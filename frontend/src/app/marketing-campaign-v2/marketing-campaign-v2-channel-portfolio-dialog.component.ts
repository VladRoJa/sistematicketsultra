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
import { forkJoin } from 'rxjs';

import {
  CampaignV2ChannelBinding, CampaignV2ChannelPortfolioEvidence,
  CampaignV2ChannelPortfolioEvidenceKind, CampaignV2PortfolioReference,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

interface ChannelAssociationRow {
  binding: CampaignV2ChannelBinding;
  association: CampaignV2ChannelPortfolioEvidence | null;
}

@Component({
  selector: 'app-marketing-campaign-v2-channel-portfolio-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-channel-portfolio-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-channel-portfolio-dialog.component.css'],
})
export class MarketingCampaignV2ChannelPortfolioDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2ChannelPortfolioDialogComponent>);

  readonly channelId = new FormControl('', { nonNullable: true });
  readonly businessId = new FormControl('', { nonNullable: true });
  readonly wabaId = new FormControl('', { nonNullable: true });
  readonly evidenceKind = new FormControl<CampaignV2ChannelPortfolioEvidenceKind>(
    'OPERATOR_STATEMENT', { nonNullable: true },
  );
  readonly sourceReference = new FormControl('', { nonNullable: true });
  readonly acknowledgment = new FormControl(false, { nonNullable: true });

  loading = false;
  saving = false;
  error = '';
  success = '';
  portfolios: CampaignV2PortfolioReference[] = [];
  channelRows: ChannelAssociationRow[] = [];
  history: CampaignV2ChannelPortfolioEvidence[] = [];
  historyIsLimited = false;

  ngOnInit(): void {
    this.channelId.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.selectCurrent());
    this.reload();
  }

  close(): void { this.dialogRef.close(); }

  get selected(): CampaignV2ChannelPortfolioEvidence | null {
    return this.channelRows.find(row => row.binding.provider_channel_id === this.channelId.value)
      ?.association ?? null;
  }

  get selectedHistory(): CampaignV2ChannelPortfolioEvidence[] {
    return this.history.filter(row => row.provider_channel_id === this.channelId.value);
  }

  get declaredCount(): number {
    return this.channelRows.filter(row => row.association?.state === 'DECLARED').length;
  }

  get canDeclare(): boolean {
    return !this.loading && !this.saving && this.acknowledgment.value &&
      Boolean(this.channelId.value && this.portfolios.some(p => p.business_id === this.businessId.value)) &&
      (!this.wabaId.value.trim() || /^[1-9][0-9]{5,31}$/.test(this.wabaId.value.trim())) &&
      this.validEvidence;
  }

  get canWithdraw(): boolean {
    return !this.loading && !this.saving && this.acknowledgment.value &&
      this.selected?.state === 'DECLARED' && this.validEvidence;
  }

  private get validEvidence(): boolean {
    const source = this.sourceReference.value.trim();
    return source.length > 0 && source.length <= 255;
  }

  reload(): void {
    if (this.loading || this.saving) { return; }
    this.loading = true;
    this.error = '';
    forkJoin({
      portfolios: this.api.listPortfolioReferences(),
      channels: this.api.listDispatchChannelBindings(),
      evidence: this.api.listChannelPortfolioEvidence(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        this.portfolios = response.portfolios.rows;
        this.history = response.evidence.history;
        this.historyIsLimited = response.evidence.history_is_limited;
        const byChannel = new Map(
          response.evidence.rows.map(row => [row.provider_channel_id, row]),
        );
        this.channelRows = response.channels.rows
          .filter(row => row.is_active && row.is_default && row.provider === 'IVENTAS')
          .map(binding => ({ binding, association: byChannel.get(binding.provider_channel_id) ?? null }))
          .sort((a, b) => a.binding.sucursal_canon.localeCompare(b.binding.sucursal_canon));
        if (!this.channelRows.some(row => row.binding.provider_channel_id === this.channelId.value)) {
          this.channelId.setValue(this.channelRows[0]?.binding.provider_channel_id ?? '', { emitEvent: false });
        }
        this.loading = false;
        this.selectCurrent();
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.error = String(err.error?.message || 'No se pudo consultar la evidencia de canales.');
      },
    });
  }

  save(state: 'DECLARED' | 'WITHDRAWN'): void {
    if (state === 'DECLARED' ? !this.canDeclare : !this.canWithdraw) { return; }
    const expectedRevision = this.selected?.revision_id ?? null;
    this.saving = true;
    this.error = '';
    this.success = '';
    this.api.registerChannelPortfolioEvidence({
      provider_channel_id: this.channelId.value,
      business_id: state === 'DECLARED' ? this.businessId.value : null,
      waba_id: state === 'DECLARED' ? this.wabaId.value.trim() || null : null,
      state,
      evidence_kind: this.evidenceKind.value,
      source_reference: this.sourceReference.value.trim(),
      expected_revision_id: expectedRevision,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.saving = false;
        this.success = result.state === 'WITHDRAWN'
          ? 'Asociación retirada con auditoría; ninguna cuota fue alterada.'
          : 'Asociación declarada y auditada; Meta no ha verificado la pertenencia.';
        this.sourceReference.setValue('');
        this.acknowledgment.setValue(false);
        this.reload();
      },
      error: (err: HttpErrorResponse) => {
        this.saving = false;
        this.error = String(err.error?.message ||
          'No se pudo registrar. Si cambió la revisión, actualiza y vuelve a revisar.');
      },
    });
  }

  private selectCurrent(): void {
    const row = this.selected;
    this.businessId.setValue(row?.state === 'DECLARED' ? row.business_id ?? '' : '', { emitEvent: false });
    this.wabaId.setValue(row?.state === 'DECLARED' ? row.waba_id ?? '' : '', { emitEvent: false });
    this.evidenceKind.setValue(row?.evidence_kind ?? 'OPERATOR_STATEMENT', { emitEvent: false });
    this.sourceReference.setValue('', { emitEvent: false });
    this.acknowledgment.setValue(false, { emitEvent: false });
  }
}
