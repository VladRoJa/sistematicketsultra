import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import { ReactivationCampaign } from './marketing-reactivation.models';
import {
  CampaignDeliveryBranch,
  CampaignDeliveryDetailResponse,
  CampaignDeliveryStatus,
  CampaignWithDelivery,
} from './marketing-campaign-delivery.models';
import { MarketingCampaignDeliveryService } from './marketing-campaign-delivery.service';

@Component({
  selector: 'app-marketing-campaign-delivery',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './marketing-campaign-delivery.component.html',
  styleUrls: ['./marketing-campaign-delivery.component.css'],
})
export class MarketingCampaignDeliveryComponent implements OnInit {
  private readonly service = inject(MarketingCampaignDeliveryService);
  private readonly destroyRef = inject(DestroyRef);

  readonly campaignId = new FormControl<number | null>(null);
  readonly sentDate = new FormControl('', { nonNullable: true });
  readonly sentTime = new FormControl('', { nonNullable: true });

  campaigns: CampaignWithDelivery[] = [];
  detail: CampaignDeliveryDetailResponse | null = null;
  selectedPending = new Set<string>();
  loadingCampaigns = false;
  loadingDetail = false;
  saving = false;
  error = '';
  success = '';

  ngOnInit(): void {
    this.setCurrentDateTime();
    this.campaignId.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(campaignId => {
        if (campaignId === null) {
          this.detail = null;
          this.selectedPending.clear();
          return;
        }
        this.loadDetail(campaignId);
      });
    this.loadCampaigns();
  }

  get pendingBranches(): CampaignDeliveryBranch[] {
    return (this.detail?.delivery.branches ?? []).filter(branch => !branch.sent);
  }

  get selectedBranchCount(): number {
    return this.selectedPending.size;
  }

  get selectedContactCount(): number {
    return this.pendingBranches
      .filter(branch => this.selectedPending.has(branch.sucursal))
      .reduce((total, branch) => total + branch.recipient_count, 0);
  }

  get allPendingSelected(): boolean {
    return this.pendingBranches.length > 0
      && this.pendingBranches.every(branch => this.selectedPending.has(branch.sucursal));
  }

  get partiallyPendingSelected(): boolean {
    return this.selectedPending.size > 0 && !this.allPendingSelected;
  }

  get remainingBranchesAfterSave(): number {
    if (!this.detail) return 0;
    return Math.max(
      this.detail.delivery.pending_branches - this.selectedBranchCount,
      0,
    );
  }

  get canSave(): boolean {
    return !this.saving
      && this.selectedPending.size > 0
      && !!this.sentDate.value
      && !!this.sentTime.value;
  }

  loadCampaigns(): void {
    this.loadingCampaigns = true;
    this.error = '';
    this.service.getCampaigns()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: response => {
          const eligible = response.rows.filter(campaign =>
            campaign.status === 'EXPORTED' || campaign.status === 'SENT',
          );
          this.campaigns = eligible;
          if (!eligible.length) {
            this.loadingCampaigns = false;
            return;
          }
          this.loadSummaries(eligible);
        },
        error: error => {
          this.loadingCampaigns = false;
          this.error = this.readError(error, 'No fue posible cargar las campañas.');
        },
      });
  }

  loadDetail(campaignId: number): void {
    this.loadingDetail = true;
    this.error = '';
    this.success = '';
    this.service.getDelivery(campaignId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: detail => {
          this.detail = detail;
          this.selectedPending = new Set(
            detail.delivery.branches
              .filter(branch => !branch.sent)
              .map(branch => branch.sucursal),
          );
          this.loadingDetail = false;
        },
        error: error => {
          this.detail = null;
          this.selectedPending.clear();
          this.loadingDetail = false;
          this.error = this.readError(error, 'No fue posible cargar el control de envíos.');
        },
      });
  }

  toggleBranch(branch: CampaignDeliveryBranch, checked: boolean): void {
    if (branch.sent) return;
    const next = new Set(this.selectedPending);
    if (checked) next.add(branch.sucursal);
    else next.delete(branch.sucursal);
    this.selectedPending = next;
  }

  toggleAllPending(checked: boolean): void {
    this.selectedPending = checked
      ? new Set(this.pendingBranches.map(branch => branch.sucursal))
      : new Set<string>();
  }

  save(): void {
    const campaignId = this.campaignId.value;
    if (campaignId === null || !this.canSave) return;

    const sucursales = this.pendingBranches
      .filter(branch => this.selectedPending.has(branch.sucursal))
      .map(branch => branch.sucursal);
    if (!sucursales.length) return;

    this.saving = true;
    this.error = '';
    this.success = '';
    this.service.saveDelivery(campaignId, {
      sucursales,
      sent_at_local: `${this.sentDate.value}T${this.sentTime.value}:00`,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: detail => {
        this.detail = detail;
        this.selectedPending = new Set(
          detail.delivery.branches
            .filter(branch => !branch.sent)
            .map(branch => branch.sucursal),
        );
        this.saving = false;
        this.success = `Se registraron ${sucursales.length} sucursales como enviadas.`;
        this.refreshCampaignSummary(detail);
      },
      error: error => {
        this.saving = false;
        this.error = this.readError(error, 'No fue posible guardar los envíos.');
      },
    });
  }

  deliveryStatusLabel(campaign: CampaignWithDelivery): string {
    const status = campaign.delivery?.status ?? campaign.status;
    return this.statusLabel(status);
  }

  statusLabel(status: CampaignDeliveryStatus | ReactivationCampaign['status']): string {
    const labels: Record<string, string> = {
      DRAFT: 'Borrador',
      EXPORTED: 'Exportada',
      PARTIALLY_SENT: 'Parcialmente enviada',
      SENT: 'Enviada',
      CANCELLED: 'Cancelada',
    };
    return labels[status] ?? status;
  }

  formatSentAt(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat('es-MX', {
      timeZone: 'America/Tijuana',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  private loadSummaries(campaigns: CampaignWithDelivery[]): void {
    this.service.getDeliverySummaries(campaigns.map(campaign => campaign.id))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: response => {
          const byId = new Map(response.rows.map(row => [row.id, row.delivery]));
          this.campaigns = campaigns.map(campaign => ({
            ...campaign,
            delivery: byId.get(campaign.id),
          }));
          this.loadingCampaigns = false;
        },
        error: () => {
          this.campaigns = campaigns;
          this.loadingCampaigns = false;
        },
      });
  }

  private refreshCampaignSummary(detail: CampaignDeliveryDetailResponse): void {
    this.campaigns = this.campaigns.map(campaign =>
      campaign.id === detail.campaign_id
        ? { ...campaign, delivery: detail.delivery }
        : campaign,
    );
  }

  private setCurrentDateTime(): void {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hour = String(now.getHours()).padStart(2, '0');
    const minute = String(now.getMinutes()).padStart(2, '0');
    this.sentDate.setValue(`${year}-${month}-${day}`, { emitEvent: false });
    this.sentTime.setValue(`${hour}:${minute}`, { emitEvent: false });
  }

  private readError(error: HttpErrorResponse, fallback: string): string {
    const message = error.error?.message;
    return typeof message === 'string' && message.trim() ? message : fallback;
  }
}
