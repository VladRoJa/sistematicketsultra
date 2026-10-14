import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  CampaignV2QuotaEvidence,
  CampaignV2QuotaPolicyRequest,
  CampaignV2QuotaAttestationRequest,
  CampaignV2ChannelBinding,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { isCampaignV2NominalLimitValid, isCampaignV2RemainingCountValid, isCampaignV2ZonedDateString } from './marketing-campaign-v2-admin-validation.logic';

@Component({
  selector: 'app-marketing-campaign-v2-quota-admin-dialog',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatButtonModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatSelectModule],
  templateUrl: './marketing-campaign-v2-quota-admin-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-quota-admin-dialog.component.css'],
})
export class MarketingCampaignV2QuotaAdminDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2QuotaAdminDialogComponent>);
  evidence: CampaignV2QuotaEvidence | null = null;
  channels: CampaignV2ChannelBinding[] = [];
  busy = false;
  error = '';
  success = '';
  showPolicyForm = false;
  showCapacityForm = false;

  readonly channelId = new FormControl('', { nonNullable: true });
  readonly portfolioKey = new FormControl('', { nonNullable: true });
  readonly accountKey = new FormControl('', { nonNullable: true });
  readonly phoneAlias = new FormControl('', { nonNullable: true });
  readonly nominalLimit = new FormControl('', { nonNullable: true });
  readonly timezone = new FormControl('America/Tijuana', { nonNullable: true });
  readonly policySource = new FormControl('', { nonNullable: true });

  readonly scopeKind = new FormControl<'PORTFOLIO' | 'CHANNEL'>('PORTFOLIO', { nonNullable: true });
  readonly scopeKey = new FormControl('', { nonNullable: true });
  readonly remaining = new FormControl('', { nonNullable: true });
  readonly observedAt = new FormControl('', { nonNullable: true });
  readonly expiresAt = new FormControl('', { nonNullable: true });
  readonly windowEndsAt = new FormControl('', { nonNullable: true });
  readonly capacitySource = new FormControl('', { nonNullable: true });

  ngOnInit(): void { this.reload(); }
  close(): void { this.dialogRef.close(); }
  togglePolicyForm(): void {
    if (!this.busy) { this.showPolicyForm = !this.showPolicyForm; }
  }
  toggleCapacityForm(): void {
    if (!this.busy) { this.showCapacityForm = !this.showCapacityForm; }
  }

  get canSavePolicy(): boolean {
    const n = this.nominalLimit.value.trim();
    return !this.busy && this.channels.some(c => c.is_active &&
      c.provider_channel_id === this.channelId.value)
      && [this.portfolioKey, this.accountKey, this.phoneAlias,
        this.timezone, this.policySource].every(c => c.value.trim().length > 0)
      && isCampaignV2NominalLimitValid(n);
  }

  get canSaveCapacity(): boolean {
    const n = this.remaining.value.trim();
    const iso = [this.observedAt.value, this.expiresAt.value, this.windowEndsAt.value];
    const times = iso.map(s => Date.parse(s));
    const key = this.scopeKey.value.trim();
    const registered = (this.evidence?.policies || []).some(p =>
      (this.scopeKind.value === 'CHANNEL' ? p.provider_channel_id : p.portfolio_key) === key);
    return !this.busy && registered && this.capacitySource.value.trim().length > 0
      && isCampaignV2RemainingCountValid(n)
      && iso.every(isCampaignV2ZonedDateString)
      && times.every(t => Number.isFinite(t))
      && times[0] < times[1] && times[1] <= times[2]
      && times[0] <= Date.now() && times[1] - times[0] <= 24 * 3600_000;
  }

  reload(): void {
    if (this.busy) { return; }
    this.busy = true;
    this.error = '';
    this.api.listQuotaEvidence().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: evidence => {
        this.evidence = evidence;
        this.api.listDispatchChannelBindings().pipe(
          takeUntilDestroyed(this.destroyRef),
        ).subscribe({
          next: bindings => { this.channels = bindings.rows; this.busy = false; },
          error: err => this.handleError(err),
        });
      },
      error: err => this.handleError(err),
    });
  }

  savePolicy(): void {
    if (!this.canSavePolicy) { return; }
    const payload: CampaignV2QuotaPolicyRequest = {
      provider_channel_id: this.channelId.value,
      portfolio_key: this.portfolioKey.value.trim(),
      account_key: this.accountKey.value.trim(),
      phone_alias: this.phoneAlias.value.trim(),
      nominal_channel_limit: this.nominalLimit.value.trim()
        ? Number(this.nominalLimit.value) : null,
      reset_timezone: this.timezone.value.trim(),
      source_reference: this.policySource.value.trim(),
    };
    this.busy = true; this.error = '';
    this.api.registerQuotaPolicy(payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: row => {
        this.busy = false;
        this.success = 'Política #' + row.revision_id + ' registrada. Cupo real pendiente de observar.';
        this.showPolicyForm = false;
        this.reload();
      },
      error: err => this.handleError(err),
    });
  }

  saveCapacity(): void {
    if (!this.canSaveCapacity) { return; }
    const payload: CampaignV2QuotaAttestationRequest = {
      scope_kind: this.scopeKind.value,
      scope_key: this.scopeKey.value.trim(),
      remaining_messages: Number(this.remaining.value),
      observed_at: this.observedAt.value.trim(),
      expires_at: this.expiresAt.value.trim(),
      window_ends_at: this.windowEndsAt.value.trim(),
      source_reference: this.capacitySource.value.trim(),
    };
    this.busy = true; this.error = '';
    this.api.registerQuotaAttestation(payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: row => {
        this.busy = false;
        this.success = 'Evidencia #' + row.attestation_id + ' guardada; no equivale a verificación automática con Meta.';
        this.showCapacityForm = false;
        this.reload();
      },
      error: err => this.handleError(err),
    });
  }

  private handleError(error: HttpErrorResponse): void {
    this.busy = false;
    this.error = String(error.error?.message ||
      'No se pudo guardar la evidencia. Verifica vigencia, permisos y catálogo.');
  }
}
