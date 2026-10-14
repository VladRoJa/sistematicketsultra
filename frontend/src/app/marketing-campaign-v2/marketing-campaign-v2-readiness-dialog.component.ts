import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { forkJoin } from 'rxjs';

import {
  CampaignV2BudgetRateRevision,
  CampaignV2ChannelBinding,
  CampaignV2DispatchTemplate,
  CampaignV2QuotaPolicyRevision,
  CampaignV2PortfolioReference,
  CampaignV2ChannelPortfolioEvidence,
} from './marketing-campaign-v2.models';
import { campaignV2BuildReadinessRows, CampaignV2ReadinessRow } from './marketing-campaign-v2-readiness.logic';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { MarketingCampaignV2ChannelPortfolioDialogComponent } from './marketing-campaign-v2-channel-portfolio-dialog.component';
import { MarketingCampaignV2QuotaAdminDialogComponent } from './marketing-campaign-v2-quota-admin-dialog.component';
import { MarketingCampaignV2DispatchAdminDialogComponent } from './marketing-campaign-v2-dispatch-admin-dialog.component';

@Component({
  selector: 'app-marketing-campaign-v2-readiness-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatDialogModule,
    MatFormFieldModule, MatInputModule, MatProgressSpinnerModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-readiness-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-readiness-dialog.component.css'],
})
export class MarketingCampaignV2ReadinessDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2ReadinessDialogComponent>);

  readonly templateId = new FormControl<number | null>(null);
  templates: CampaignV2DispatchTemplate[] = [];
  rows: Array<CampaignV2ReadinessRow & {
    mappingBusinessId: string | null;
    mappingStatus: string;
    mappingSource: string | null;
  }> = [];
  private associationByChannel = new Map<string, CampaignV2ChannelPortfolioEvidence>();
  portfolios: CampaignV2PortfolioReference[] = [];
  portfolioSaving = false;
  portfolioError = '';
  portfolioSuccess = '';

  readonly portfolioBusinessId = new FormControl('', { nonNullable: true });
  readonly portfolioName = new FormControl('', { nonNullable: true });
  readonly portfolioAppId = new FormControl('', { nonNullable: true });
  readonly portfolioSource = new FormControl('', { nonNullable: true });
  loading = false;
  error = '';
  private bindings: CampaignV2ChannelBinding[] = [];
  private policies: CampaignV2QuotaPolicyRevision[] = [];
  private rates: CampaignV2BudgetRateRevision[] = [];

  ngOnInit(): void {
    this.templateId.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.rebuild());
    this.reload();
  }

  get canSavePortfolio(): boolean {
    const business = this.portfolioBusinessId.value.trim();
    const appId = this.portfolioAppId.value.trim();
    const name = this.portfolioName.value.trim();
    const source = this.portfolioSource.value.trim();
    return !this.loading && !this.portfolioSaving
      && /^[1-9][0-9]{5,31}$/.test(business)
      && (!appId || /^[1-9][0-9]{5,31}$/.test(appId))
      && name.length <= 160 && source.length > 0 && source.length <= 255;
  }

  savePortfolio(): void {
    if (!this.canSavePortfolio) { return; }
    this.portfolioSaving = true;
    this.portfolioError = '';
    this.portfolioSuccess = '';
    this.api.registerPortfolioReference({
      business_id: this.portfolioBusinessId.value.trim(),
      display_name: this.portfolioName.value.trim() || null,
      app_id: this.portfolioAppId.value.trim() || null,
      source_reference: this.portfolioSource.value.trim(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: row => {
        this.portfolioSaving = false;
        this.portfolioSuccess = 'Business ID ' + row.business_id + ' registrado sin verificar; no vincula canales ni habilita envíos.';
        this.portfolioBusinessId.reset('');
        this.portfolioName.reset('');
        this.portfolioAppId.reset('');
        this.portfolioSource.reset('');
        this.reload();
      },
      error: (error: HttpErrorResponse) => {
        this.portfolioSaving = false;
        this.portfolioError = String(error.error?.message || 'No se pudo registrar la referencia.');
      },
    });
  }

  get declaredMappingCount(): number {
    return this.rows.filter(row => row.mappingStatus === 'DECLARADA · NO VERIFICADA').length;
  }

  get configuredCount(): number { return this.rows.filter(row => row.configured).length; }
  get missingPolicyCount(): number { return this.rows.filter(row => !row.portfolioKey).length; }
  get missingRateCount(): number { return this.rows.filter(row => !row.unitCostMxn).length; }
  get knownPortfolioCount(): number {
    return new Set(this.rows.map(row => row.portfolioKey).filter(Boolean)).size;
  }

  reload(): void {
    if (this.loading) { return; }
    this.loading = true;
    this.error = '';
    forkJoin({
      templates: this.api.listDispatchTemplatesAdmin(),
      bindings: this.api.listDispatchChannelBindings(),
      quota: this.api.listQuotaEvidence(),
      rates: this.api.listBudgetRateRevisions(),
      portfolioReferences: this.api.listPortfolioReferences(),
      associations: this.api.listChannelPortfolioEvidence(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.templates = result.templates.rows.filter(t => t.is_active);
        this.bindings = result.bindings.rows;
        this.policies = result.quota.policies;
        this.rates = result.rates.rows;
        this.portfolios = result.portfolioReferences.rows;
        this.associationByChannel = new Map(
          result.associations.rows.map(row => [row.provider_channel_id, row]),
        );
        const selected = this.templateId.value;
        const defaultTemplate = this.templates.find(t => t.template_name === 'invita_y_gana_4800');
        if (!this.templates.some(t => t.id === selected)) {
          this.templateId.setValue(defaultTemplate?.id ?? this.templates[0]?.id ?? null, { emitEvent: false });
        }
        this.loading = false;
        this.rebuild();
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.error = String(error.error?.message || 'No fue posible consultar la preparación de canales.');
        this.rows = [];
      },
    });
  }

  openPortfolios(): void {
    const ref = this.dialog.open(MarketingCampaignV2QuotaAdminDialogComponent, {
      panelClass: 'campaign-v2-admin-dialog', width: 'min(1050px, 96vw)',
      maxWidth: '96vw', maxHeight: '94vh', autoFocus: false,
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.reload());
  }

  openChannelPortfolioMap(): void {
    const ref = this.dialog.open(MarketingCampaignV2ChannelPortfolioDialogComponent, {
      panelClass: 'campaign-v2-admin-dialog', width: 'min(1080px, 96vw)',
      maxWidth: '96vw', maxHeight: '94vh', autoFocus: false,
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.reload());
  }

  openRates(): void {
    const ref = this.dialog.open(MarketingCampaignV2DispatchAdminDialogComponent, {
      panelClass: 'campaign-v2-admin-dialog', width: 'min(1050px, 96vw)',
      maxWidth: '96vw', maxHeight: '94vh', autoFocus: false,
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.reload());
  }

  close(): void { this.dialogRef.close(); }

  private rebuild(): void {
    this.rows = campaignV2BuildReadinessRows(
      this.templates.find(t => t.id === this.templateId.value) ?? null,
      this.bindings, this.policies, this.rates,
    ).map(row => {
      const mapping = this.associationByChannel.get(row.channelId);
      return {
        ...row,
        mappingBusinessId: mapping?.state === 'DECLARED' ? mapping.business_id : null,
        mappingStatus: mapping?.state === 'DECLARED'
          ? 'DECLARADA · NO VERIFICADA'
          : mapping?.state === 'WITHDRAWN' ? 'RETIRADA' : 'PENDIENTE',
        mappingSource: mapping?.source_reference ?? null,
      };
    });
  }
}
