import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxChange, MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import {
  buildCampaignV2AudienceRequest,
  buildCampaignV2FreezeRequest,
  buildCampaignV2ReportingQuery,
  campaignV2DownloadBlob,
  campaignV2FilterApplies,
  campaignV2FreezeErrorInvalidatesPreview,
  campaignV2HistoryBreakdownRows,
  campaignV2HistoricalTargetingMatchLabel,
  campaignV2HistoricalTargetingModeLabel,
  campaignV2HistoryDeliveryLabel,
  campaignV2HistoryOutcomeLabel,
  campaignV2IventasCurrentStatusLabel,
  historicalTargetingHasConditions,
  campaignV2MetricBucket,
  campaignV2ReportingAudienceFamilyLabel,
  campaignV2ReportingBranchLabel,
  campaignV2ReportingCostLabel,
  campaignV2ReportingFilterValidation,
  campaignV2ReportingPercent,
  campaignV2ReportingSnapshotLabel,
  campaignV2ReportingValue,
  canFreezeCampaignV2,
  isCampaignV2AudienceValid,
  parseCampaignV2LookbackDays,
  selectAllCampaignV2Families,
  toggleCampaignV2Family,
  toggleCampaignV2IventasCurrentStatus,
  toggleCampaignV2HistoryDeliveryBucket,
  toggleCampaignV2HistoryOutcome,
} from './marketing-campaign-v2.logic';
import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2AudienceFamily,
  CampaignV2CampaignSummary,
  CampaignV2ConsolidatedReport,
  CampaignV2HistoryDeliveryBucket,
  CampaignV2HistoricalTargetingMatch,
  CampaignV2HistoricalTargetingMode,
  CampaignV2HistoricalTargetingWindowMode,
  CampaignV2HistoryOutcome,
  CampaignV2IventasCurrentStatus,
  CampaignV2ObservedFamily,
  CampaignV2OptionsResponse,
  CampaignV2PreviewBucket,
  CampaignV2PreviewResponse,
  CampaignV2Purpose,
  CampaignV2ReportingSnapshotStatus,
  CampaignV2Source,
  CampaignV2SourceMetadata,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { MarketingSalesFunnelService } from '../marketing-sales-funnel/marketing-sales-funnel.service';
import { DateRangeSelectorComponent } from '../shared/date-range-selector/date-range-selector.component';
import {
  MarketingCampaignV2PreviewDetailDialogComponent,
  MarketingCampaignV2PreviewDetailDialogData,
} from './marketing-campaign-v2-preview-detail-dialog.component';
import {
  MarketingCampaignV2CampaignDetailDialogComponent,
  MarketingCampaignV2CampaignDetailDialogData,
} from './marketing-campaign-v2-campaign-detail-dialog.component';
import {
  MarketingCampaignV2TariffClassifierDialogComponent,
  MarketingCampaignV2TariffClassifierDialogData,
} from './marketing-campaign-v2-tariff-classifier-dialog.component';

@Component({
  selector: 'app-marketing-campaign-v2-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    DateRangeSelectorComponent,
  ],
  templateUrl: './marketing-campaign-v2-page.component.html',
  styleUrls: ['./marketing-campaign-v2-page.component.css'],
})
export class MarketingCampaignV2PageComponent implements OnInit {
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly funnelService = inject(MarketingSalesFunnelService);
  private readonly dialog = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);

  readonly source = new FormControl<CampaignV2Source>('EXPIRED_MEMBERS', {
    nonNullable: true,
  });
  readonly expirationDateFrom = new FormControl('', { nonNullable: true });
  readonly expirationDateTo = new FormControl('', { nonNullable: true });
  readonly funnelMonth = new FormControl('', { nonNullable: true });
  readonly funnelCutoffDate = new FormControl('', { nonNullable: true });
  readonly funnelMonthOptions = this.buildFunnelMonthOptions();
  readonly historyTargetingEnabled = new FormControl(false, { nonNullable: true });
  readonly historyMode = new FormControl<CampaignV2HistoricalTargetingMode>('EXCLUDE', {
    nonNullable: true,
  });
  readonly historyMatch = new FormControl<CampaignV2HistoricalTargetingMatch>('ANY', {
    nonNullable: true,
  });
  readonly historyButtonInteracted = new FormControl(false, { nonNullable: true });
  readonly historyWindowMode = new FormControl<CampaignV2HistoricalTargetingWindowMode>(
    'ALL_HISTORY',
    { nonNullable: true },
  );
  readonly historyLookbackDays = new FormControl('', { nonNullable: true });
  readonly name = new FormControl('', { nonNullable: true });
  readonly purpose = new FormControl<CampaignV2Purpose>('UNCLASSIFIED', {
    nonNullable: true,
  });
  readonly historyPurpose = new FormControl<CampaignV2Purpose | ''>('', {
    nonNullable: true,
  });
  readonly historySource = new FormControl<CampaignV2Source | ''>('', {
    nonNullable: true,
  });
  readonly reportingObservedFrom = new FormControl('', { nonNullable: true });
  readonly reportingObservedTo = new FormControl('', { nonNullable: true });
  readonly reportingPurpose = new FormControl<CampaignV2Purpose | ''>('', {
    nonNullable: true,
  });
  readonly reportingSource = new FormControl<CampaignV2Source | ''>('', {
    nonNullable: true,
  });
  readonly reportingProvider = new FormControl('', { nonNullable: true });
  readonly reportingSnapshotStatus = new FormControl<
    CampaignV2ReportingSnapshotStatus | ''
  >('', { nonNullable: true });

  options: CampaignV2OptionsResponse | null = null;
  selectedFamilies: CampaignV2AudienceFamily[] = [];
  selectedIventasCurrentStatuses: CampaignV2IventasCurrentStatus[] = [];
  selectedHistoryDeliveryBuckets: CampaignV2HistoryDeliveryBucket[] = [];
  selectedHistoryOutcomes: CampaignV2HistoryOutcome[] = [];
  get iventasCurrentStatusOptions(): CampaignV2IventasCurrentStatus[] {
    return this.options?.iventas_current_statuses ?? [];
  }

  get historyDeliveryOptions(): CampaignV2HistoryDeliveryBucket[] {
    return this.options?.historical_targeting?.delivery_buckets ?? [];
  }

  get historyOutcomeOptions(): CampaignV2HistoryOutcome[] {
    return this.options?.historical_targeting?.outcomes ?? [];
  }

  get historyModeOptions(): CampaignV2HistoricalTargetingMode[] {
    return this.options?.historical_targeting?.modes ?? [];
  }

  get historyMatchOptions(): CampaignV2HistoricalTargetingMatch[] {
    return this.options?.historical_targeting?.matches ?? [];
  }

  get historyWindowOptions(): CampaignV2HistoricalTargetingWindowMode[] {
    return this.options?.historical_targeting?.window_modes ?? [];
  }
  preview: CampaignV2PreviewResponse | null = null;
  campaigns: CampaignV2CampaignSummary[] = [];
  reporting: CampaignV2ConsolidatedReport | null = null;
  funnelCutoffDates: string[] = [];

  loadingOptions = false;
  loadingPreview = false;
  loadingFunnelCutoffs = false;
  creating = false;
  loadingCampaigns = false;
  loadingReporting = false;
  exportingReporting = false;
  accessDenied = false;
  lastFreezeCompleted = false;
  error = '';
  success = '';
  reportingError = '';
  reportingSuccess = '';

  campaignPage = 1;
  readonly campaignPageSize = 25;
  campaignTotal = 0;
  campaignTotalPages = 0;

  private previewRequest: CampaignV2AudienceDefinitionRequest | null = null;

  ngOnInit(): void {
    this.source.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(source => {
        if (!this.showsExpirationRange) {
          this.expirationDateFrom.setValue('', { emitEvent: false });
          this.expirationDateTo.setValue('', { emitEvent: false });
        }
        if (source === 'FUNNEL_PORTFOLIO') {
          this.loadFunnelCutoffs();
        }
        this.invalidatePreview();
      });

    this.expirationDateFrom.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.expirationDateTo.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.funnelMonth.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.funnelCutoffDate.setValue('', { emitEvent: false });
        this.funnelCutoffDates = [];
        this.invalidatePreview();
        if (this.isFunnelSource) {
          this.loadFunnelCutoffs();
        }
      });
    this.funnelCutoffDate.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());

    this.historyTargetingEnabled.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.historyMode.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.historyMatch.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.historyButtonInteracted.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.historyWindowMode.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.historyLookbackDays.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());

    this.reportingObservedFrom.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidateReporting());
    this.reportingObservedTo.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidateReporting());
    this.reportingPurpose.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidateReporting());
    this.reportingSource.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidateReporting());
    this.reportingProvider.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidateReporting());
    this.reportingSnapshotStatus.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidateReporting());

    this.loadOptions();
  }

  get isExpiredSource(): boolean {
    return this.source.value === 'EXPIRED_MEMBERS';
  }

  get isFunnelSource(): boolean {
    return this.source.value === 'FUNNEL_PORTFOLIO';
  }

  get showsExpirationRange(): boolean {
    return campaignV2FilterApplies(
      this.options,
      this.source.value,
      'expiration_date_from',
    );
  }

  get showsAudienceFamilies(): boolean {
    return campaignV2FilterApplies(
      this.options,
      this.source.value,
      'audience_families',
    );
  }

  get showsFunnelFilters(): boolean {
    return campaignV2FilterApplies(
      this.options,
      this.source.value,
      'funnel_month',
    );
  }

  get funnelCutoffPolicy(): string | null {
    return this.options?.source_filters?.[this.source.value]?.cutoff_policy ?? null;
  }

  get funnelCutoffPolicyHint(): string {
    return this.funnelCutoffPolicy === 'EXACT_COMPLETE'
      ? 'Sólo se muestran cortes completos y alineados por el Funnel.'
      : 'El backend valida el corte disponible para esta fuente.';
  }

  formatFunnelCutoffDate(value: string): string {
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) {
      return value;
    }
    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(new Date(year, month - 1, day));
  }

  private buildFunnelMonthOptions(): Array<{ value: string; label: string }> {
    const firstMonth = new Date(2026, 0, 1);
    const currentMonth = new Date();
    const formatter = new Intl.DateTimeFormat('es-MX', {
      month: 'long',
      year: 'numeric',
    });
    const options: Array<{ value: string; label: string }> = [];
    const cursor = new Date(
      currentMonth.getFullYear(),
      currentMonth.getMonth(),
      1,
    );

    while (cursor >= firstMonth) {
      const year = cursor.getFullYear();
      const month = String(cursor.getMonth() + 1).padStart(2, '0');
      const formatted = formatter.format(cursor);
      options.push({
        value: `${year}-${month}`,
        label: formatted.charAt(0).toUpperCase() + formatted.slice(1),
      });
      cursor.setMonth(cursor.getMonth() - 1);
    }

    return options;
  }

  get canReviewAudience(): boolean {
    return Boolean(
      this.options
      && !this.loadingPreview
      && !this.creating
      && !this.loadingFunnelCutoffs
      && isCampaignV2AudienceValid(this.audienceState(), this.options),
    );
  }

  get historyTargetingMissingConditions(): boolean {
    return Boolean(
      this.historyTargetingEnabled.value
      && !historicalTargetingHasConditions(this.audienceState()),
    );
  }

  get historyLookbackInvalid(): boolean {
    return Boolean(
      this.historyTargetingEnabled.value
      && !this.historyTargetingMissingConditions
      && this.historyWindowMode.value === 'LOOKBACK_DAYS'
      && parseCampaignV2LookbackDays(this.historyLookbackDays.value) === null,
    );
  }

  get isCanonicalHistoryPreview(): boolean {
    return Boolean(this.preview?.filters.historical_targeting);
  }


  get canFreeze(): boolean {
    return canFreezeCampaignV2({
      preview: this.preview,
      name: this.name.value,
      purpose: this.purpose.value,
      creating: this.creating || this.loadingPreview,
    });
  }

  get scopeLabel(): string {
    if (!this.options) {
      return '';
    }
    if (this.options.scope.is_global) {
      return 'Alcance: todas las sucursales autorizadas';
    }
    const count = this.options.scope.allowed_sucursal_keys?.length ?? 0;
    return count === 1
      ? 'Alcance backend: 1 sucursal autorizada'
      : `Alcance backend: ${count} sucursales autorizadas`;
  }

  get observedFamilies(): CampaignV2ObservedFamily[] {
    const selectable = this.options?.selectable_audience_families ?? [];
    return [...selectable, 'MES', 'OUT_OF_SEGMENT'];
  }

  loadOptions(): void {
    if (this.loadingOptions) {
      return;
    }
    this.loadingOptions = true;
    this.accessDenied = false;
    this.error = '';

    this.service.getOptions()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: options => {
          this.loadingOptions = false;
          this.options = options;
          this.ensureOptionDefaults(options);
          this.loadCampaigns(1);
        },
        error: (error: HttpErrorResponse) => {
          this.loadingOptions = false;
          this.options = null;
          this.campaigns = [];
          if (error.status === 403) {
            this.accessDenied = true;
            this.error = 'No tienes acceso a Campañas V2.';
            return;
          }
          this.error = this.errorMessage(error, 'No fue posible cargar Campañas V2.');
        },
      });
  }

  loadFunnelCutoffs(): void {
    const month = this.funnelMonth.value.trim();
    if (!this.isFunnelSource || !/^\d{4}-\d{2}$/.test(month)) {
      this.funnelCutoffDates = [];
      this.funnelCutoffDate.setValue('', { emitEvent: false });
      return;
    }

    this.loadingFunnelCutoffs = true;
    this.error = '';
    this.funnelService.getDashboard(month)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.loadingFunnelCutoffs = false;
          this.funnelCutoffDates = [...result.available_cutoff_dates];
          const selected = result.selected_cutoff_date || this.funnelCutoffDates[0] || '';
          this.funnelCutoffDate.setValue(selected, { emitEvent: false });
          this.invalidatePreview();
        },
        error: (error: HttpErrorResponse) => {
          this.loadingFunnelCutoffs = false;
          this.funnelCutoffDates = [];
          this.funnelCutoffDate.setValue('', { emitEvent: false });
          this.invalidatePreview();
          this.error = this.errorMessage(
            error,
            'No fue posible consultar los cortes completos del Funnel.',
          );
        },
      });
  }

  onExpirationDateFromChange(value: string): void {
    this.expirationDateFrom.setValue(value);
  }

  onExpirationDateToChange(value: string): void {
    this.expirationDateTo.setValue(value);
  }

  setFamilySelected(
    family: CampaignV2AudienceFamily,
    change: MatCheckboxChange,
  ): void {
    const available = this.options?.selectable_audience_families ?? [];
    this.selectedFamilies = toggleCampaignV2Family(
      this.selectedFamilies,
      family,
      change.checked,
      available,
    );
    this.invalidatePreview();
  }

  isFamilySelected(family: CampaignV2AudienceFamily): boolean {
    return this.selectedFamilies.includes(family);
  }

  setIventasCurrentStatusSelected(
    status: CampaignV2IventasCurrentStatus,
    change: MatCheckboxChange,
  ): void {
    this.selectedIventasCurrentStatuses = toggleCampaignV2IventasCurrentStatus(
      this.selectedIventasCurrentStatuses,
      status,
      change.checked,
    );
    this.invalidatePreview();
  }

  isIventasCurrentStatusSelected(status: CampaignV2IventasCurrentStatus): boolean {
    return this.selectedIventasCurrentStatuses.includes(status);
  }

  iventasCurrentStatusLabel(status: CampaignV2IventasCurrentStatus): string {
    return campaignV2IventasCurrentStatusLabel(status);
  }

  setHistoryDeliverySelected(
    bucket: CampaignV2HistoryDeliveryBucket,
    change: MatCheckboxChange,
  ): void {
    this.selectedHistoryDeliveryBuckets = toggleCampaignV2HistoryDeliveryBucket(
      this.selectedHistoryDeliveryBuckets,
      bucket,
      change.checked,
    );
    this.invalidatePreview();
  }

  isHistoryDeliverySelected(bucket: CampaignV2HistoryDeliveryBucket): boolean {
    return this.selectedHistoryDeliveryBuckets.includes(bucket);
  }

  setHistoryOutcomeSelected(
    outcome: CampaignV2HistoryOutcome,
    change: MatCheckboxChange,
  ): void {
    this.selectedHistoryOutcomes = toggleCampaignV2HistoryOutcome(
      this.selectedHistoryOutcomes,
      outcome,
      change.checked,
    );
    this.invalidatePreview();
  }

  isHistoryOutcomeSelected(outcome: CampaignV2HistoryOutcome): boolean {
    return this.selectedHistoryOutcomes.includes(outcome);
  }

  historyDeliveryLabel(value: CampaignV2HistoryDeliveryBucket): string {
    return campaignV2HistoryDeliveryLabel(value);
  }

  historyOutcomeLabel(value: CampaignV2HistoryOutcome): string {
    return campaignV2HistoryOutcomeLabel(value);
  }

  historyModeLabel(value: CampaignV2HistoricalTargetingMode): string {
    return campaignV2HistoricalTargetingModeLabel(value);
  }

  historyMatchLabel(value: CampaignV2HistoricalTargetingMatch): string {
    return campaignV2HistoricalTargetingMatchLabel(value);
  }

  historyWindowLabel(value: CampaignV2HistoricalTargetingWindowMode): string {
    return value === 'ALL_HISTORY' ? 'Todo el historial' : 'Últimos N días';
  }

  historyDiagnosticCards(): Array<{
    label: string;
    count: number;
    metric?: 'history_included' | 'history_excluded';
  }> {
    if (!this.preview) {
      return [];
    }
    if (this.isCanonicalHistoryPreview) {
      return [
        {
          label: 'Coincidieron con historial',
          count: this.preview.history_matched_count ?? 0,
        },
        {
          label: 'No coincidieron',
          count: this.preview.history_not_matched_count ?? 0,
        },
        {
          label: 'Incluidos por regla histórica',
          count: this.preview.history_included_count ?? 0,
          metric: 'history_included',
        },
        {
          label: 'Excluidos por regla histórica',
          count: this.preview.history_excluded_count ?? 0,
          metric: 'history_excluded',
        },
      ];
    }
    return [
      {
        label: 'Antes del filtro histórico',
        count: this.preview.before_history_filter_count ?? 0,
      },
      {
        label: 'Excluidos por historial',
        count: this.preview.history_excluded_count ?? 0,
        metric: 'history_excluded',
      },
      {
        label: 'Después del filtro histórico',
        count: this.preview.after_history_filter_count ?? 0,
      },
    ];
  }

  openHistoryDiagnostic(metric: 'history_included' | 'history_excluded' | undefined, count: number): void {
    if (!metric || count <= 0) {
      return;
    }
    this.openMetric(metric, count);
  }

  historyBreakdownRows(): Array<{ label: string; count: number }> {
    return this.preview
      ? campaignV2HistoryBreakdownRows(this.preview)
      : [];
  }

  historyEvaluationRows(): Array<{ label: string; value: string }> {
    const evaluation = this.preview?.source_metadata.history_evaluation;
    if (!evaluation) {
      return [];
    }
    const rows: Array<{ label: string; value: string }> = [];
    if (evaluation.observed_after) {
      rows.push({
        label: 'Historial observado desde',
        value: this.formatObservedAt(evaluation.observed_after),
      });
    }
    if (evaluation.observed_before) {
      rows.push({
        label: 'Historial evaluado hasta',
        value: this.formatObservedAt(evaluation.observed_before),
      });
    }
    return rows;
  }

  selectAllFamilies(): void {
    this.selectedFamilies = selectAllCampaignV2Families(
      this.options?.selectable_audience_families ?? [],
    );
    this.invalidatePreview();
  }

  clearFamilies(): void {
    this.selectedFamilies = [];
    this.invalidatePreview();
  }

  reviewAudience(): void {
    if (!this.canReviewAudience) {
      this.error = this.audienceValidationMessage();
      return;
    }

    const request = buildCampaignV2AudienceRequest(this.audienceState(), this.options);
    this.loadingPreview = true;
    this.error = '';
    this.success = '';
    this.preview = null;
    this.previewRequest = null;

    this.service.preview(request)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: preview => {
          this.loadingPreview = false;
          this.preview = preview;
          this.previewRequest = request;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingPreview = false;
          this.error = this.errorMessage(error, 'No fue posible revisar la audiencia.');
        },
      });
  }

  openMetric(
    metric:
      | 'recipients'
      | 'invalid_phone'
      | 'duplicates'
      | 'out_of_segment'
      | 'unclassified'
      | 'current_status_blocked'
      | 'history_excluded'
      | 'history_included'
      | 'funnel_candidates'
      | 'funnel_buyer_excluded'
      | 'active_member_suppression',
    count: number,
  ): void {
    if (count <= 0) {
      return;
    }
    this.openPreviewDetail(campaignV2MetricBucket(metric));
  }

  openFamily(family: CampaignV2ObservedFamily): void {
    const count = this.preview?.family_counts?.[family] ?? 0;
    if (count <= 0) {
      return;
    }
    this.openPreviewDetail('FAMILY', family);
  }

  openTariffClassifier(): void {
    if (!this.previewRequest || (this.preview?.unclassified_family_count ?? 0) <= 0) {
      return;
    }

    const ref = this.dialog.open<
      MarketingCampaignV2TariffClassifierDialogComponent,
      MarketingCampaignV2TariffClassifierDialogData
    >(MarketingCampaignV2TariffClassifierDialogComponent, {
      width: 'min(1180px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '90vh',
      data: {
        audience: this.previewRequest,
        categories: this.options?.tariff_categories ?? [],
        families: this.observedFamilies,
      },
    });

    ref.componentInstance.classificationSaved
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.invalidatePreview();
        this.success = 'Clasificación guardada. Revisa la audiencia nuevamente antes de congelar.';
      });
  }

  freezeCampaign(): void {
    if (!this.canFreeze || !this.preview || !this.previewRequest) {
      return;
    }

    this.creating = true;
    this.error = '';
    this.success = '';

    const request = buildCampaignV2FreezeRequest(
      this.previewRequest,
      this.name.value,
      this.purpose.value,
      this.preview.preview_fingerprint,
    );

    this.service.freeze(request)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.creating = false;
          this.success = `Campaña "${result.name}" creada con ${result.recipient_count} destinatarios.`;
          this.resetBuilderAfterFreeze();
          this.lastFreezeCompleted = true;
          this.loadCampaigns(1);
        },
        error: (error: HttpErrorResponse) => {
          this.creating = false;
          if (campaignV2FreezeErrorInvalidatesPreview(error.status)) {
            const serverMessage = this.serverMessage(error);
            this.invalidatePreview();
            this.error = serverMessage?.toLowerCase().includes('vacía')
              ? 'La audiencia ya no es congelable. Vuelve a revisar la audiencia.'
              : 'La audiencia cambió desde la última revisión. Vuelve a revisar antes de crear la campaña.';
            return;
          }
          this.error = this.errorMessage(error, 'No fue posible crear la campaña.');
        },
      });
  }


  get reportingFilterError(): string | null {
    return campaignV2ReportingFilterValidation({
      observedFromDate: this.reportingObservedFrom.value,
      observedToDate: this.reportingObservedTo.value,
      purpose: this.reportingPurpose.value,
      source: this.reportingSource.value,
      provider: this.reportingProvider.value,
      snapshotStatus: this.reportingSnapshotStatus.value,
    });
  }

  loadReporting(): void {
    if (this.loadingReporting) {
      return;
    }
    const validation = this.reportingFilterError;
    if (validation) {
      this.reportingError = validation;
      return;
    }

    const filters = this.reportingQuery();
    this.loadingReporting = true;
    this.reportingError = '';
    this.reportingSuccess = '';

    this.service.getReporting(filters)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: report => {
          this.loadingReporting = false;
          this.reporting = report;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingReporting = false;
          this.reporting = null;
          this.reportingError = this.errorMessage(
            error,
            'No fue posible cargar Reporting Campaign V2.',
          );
        },
      });
  }

  exportReporting(): void {
    if (this.exportingReporting) {
      return;
    }
    const validation = this.reportingFilterError;
    if (validation) {
      this.reportingError = validation;
      return;
    }

    const filters = this.reportingQuery();
    this.exportingReporting = true;
    this.reportingError = '';
    this.reportingSuccess = '';

    this.service.exportReporting(filters)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: blob => {
          this.exportingReporting = false;
          campaignV2DownloadBlob(
            blob,
            `campaign_v2_reporting_${new Date().toISOString().slice(0, 10)}.xlsx`,
          );
          this.reportingSuccess = 'Reporte Excel generado.';
        },
        error: (error: HttpErrorResponse) => {
          this.exportingReporting = false;
          this.reportingError = this.errorMessage(
            error,
            'No fue posible exportar Reporting Campaign V2.',
          );
        },
      });
  }

  reportingPercent(value: number | null | undefined): string {
    return campaignV2ReportingPercent(value);
  }

  reportingValue(value: number | string | null | undefined): string {
    return campaignV2ReportingValue(value);
  }

  reportingSnapshotLabel(
    observation: CampaignV2ConsolidatedReport['campaigns'][number]['observation'],
  ): string {
    return campaignV2ReportingSnapshotLabel(observation);
  }

  reportingObservedAt(value: string | null): string {
    return value ? this.formatObservedAt(value) : 'Sin observación';
  }

  reportingBranchLabel(value: string): string {
    return campaignV2ReportingBranchLabel(value);
  }

  reportingAudienceFamilyLabel(value: string): string {
    return campaignV2ReportingAudienceFamilyLabel(value);
  }

  reportingCostLabel(status: string): string {
    return campaignV2ReportingCostLabel(status);
  }

  private reportingQuery() {
    return buildCampaignV2ReportingQuery({
      observedFromDate: this.reportingObservedFrom.value,
      observedToDate: this.reportingObservedTo.value,
      purpose: this.reportingPurpose.value,
      source: this.reportingSource.value,
      provider: this.reportingProvider.value,
      snapshotStatus: this.reportingSnapshotStatus.value,
    });
  }

  private invalidateReporting(): void {
    this.reporting = null;
    this.reportingError = '';
    this.reportingSuccess = '';
  }

  loadCampaigns(page = this.campaignPage): void {
    if (!this.options || this.accessDenied || this.loadingCampaigns) {
      return;
    }

    this.loadingCampaigns = true;
    this.error = '';
    this.service.listCampaigns({
      page,
      page_size: this.campaignPageSize,
      purpose: this.historyPurpose.value || undefined,
      source: this.historySource.value || undefined,
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.loadingCampaigns = false;
          this.campaigns = result.rows;
          this.campaignPage = result.page;
          this.campaignTotal = result.total;
          this.campaignTotalPages = result.total_pages;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingCampaigns = false;
          if (error.status === 403) {
            this.accessDenied = true;
            this.campaigns = [];
            this.error = 'No tienes acceso a Campañas V2.';
            return;
          }
          this.error = this.errorMessage(error, 'No fue posible cargar el historial.');
        },
      });
  }

  previousCampaignPage(): void {
    if (this.campaignPage > 1) {
      this.loadCampaigns(this.campaignPage - 1);
    }
  }

  nextCampaignPage(): void {
    if (this.campaignPage < this.campaignTotalPages) {
      this.loadCampaigns(this.campaignPage + 1);
    }
  }

  openCampaign(campaign: CampaignV2CampaignSummary): void {
    const ref = this.dialog.open<
      MarketingCampaignV2CampaignDetailDialogComponent,
      MarketingCampaignV2CampaignDetailDialogData,
      boolean
    >(MarketingCampaignV2CampaignDetailDialogComponent, {
      width: 'min(1180px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '92vh',
      data: {
        campaignId: campaign.id,
        purposes: this.options?.purposes ?? [],
      },
    });

    ref.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(updated => {
        if (updated) {
          this.loadCampaigns(this.campaignPage);
        }
      });
  }

  familyCount(family: CampaignV2ObservedFamily): number {
    return this.preview?.family_counts?.[family] ?? 0;
  }

  familyLabel(value: CampaignV2ObservedFamily | CampaignV2AudienceFamily): string {
    const labels: Record<CampaignV2ObservedFamily, string> = {
      DOMICILIADO: 'Domiciliado',
      TRIMESTRAL: 'Trimestral',
      CONVENIO: 'Convenio',
      SEMESTRE: 'Semestre',
      ESTUDIANTE: 'Estudiante',
      MES: 'Mes',
      OUT_OF_SEGMENT: 'Fuera de segmento',
    };
    return labels[value];
  }

  sourceLabel(value: CampaignV2Source): string {
    const labels: Record<CampaignV2Source, string> = {
      EXPIRED_MEMBERS: 'Socios vencidos',
      ACTIVE_MEMBERS: 'Socios activos',
      FUNNEL_PORTFOLIO: 'Cartera Funnel / Venta Nueva',
    };
    return labels[value];
  }

  purposeLabel(value: CampaignV2Purpose): string {
    const labels: Record<CampaignV2Purpose, string> = {
      NEW_SALE: 'Venta nueva',
      REACTIVATION: 'Reactivación',
      ACTIVE_MEMBERS: 'Socios activos',
      UNCLASSIFIED: 'Sin clasificar',
    };
    return labels[value];
  }

  metadataRows(metadata: CampaignV2SourceMetadata): Array<{ label: string; value: string }> {
    const rows: Array<{ label: string; value: string }> = [];
    if (metadata.activos_cutoff_date) {
      rows.push({ label: 'Corte activos', value: String(metadata.activos_cutoff_date) });
    }
    if (metadata.activos_captured_at) {
      rows.push({ label: 'Captura activos', value: String(metadata.activos_captured_at) });
    }
    if (metadata.snapshot_kind) {
      rows.push({ label: 'Snapshot', value: String(metadata.snapshot_kind) });
    }
    if (metadata.expiration_date_from) {
      rows.push({ label: 'Vencimiento desde', value: String(metadata.expiration_date_from) });
    }
    if (metadata.expiration_date_to) {
      rows.push({ label: 'Vencimiento hasta', value: String(metadata.expiration_date_to) });
    }
    if (metadata.current_status_activos_cutoff_date) {
      rows.push({
        label: 'Corte usado para estado actual',
        value: String(metadata.current_status_activos_cutoff_date),
      });
    }
    if (metadata.funnel_month) {
      rows.push({ label: 'Mes Funnel', value: String(metadata.funnel_month) });
    }
    if (metadata.funnel_cutoff_date) {
      rows.push({ label: 'Corte Funnel', value: String(metadata.funnel_cutoff_date) });
    }
    if (metadata.active_members_cutoff_date) {
      rows.push({
        label: 'Corte Socios Activos',
        value: String(metadata.active_members_cutoff_date),
      });
    }
    return rows;
  }

  private openPreviewDetail(
    bucket: CampaignV2PreviewBucket,
    audienceFamily?: CampaignV2ObservedFamily,
  ): void {
    if (!this.previewRequest) {
      return;
    }
    this.dialog.open<
      MarketingCampaignV2PreviewDetailDialogComponent,
      MarketingCampaignV2PreviewDetailDialogData
    >(MarketingCampaignV2PreviewDetailDialogComponent, {
      width: 'min(1080px, 96vw)',
      maxWidth: '96vw',
      maxHeight: '90vh',
      data: {
        audience: this.previewRequest,
        bucket,
        audienceFamily,
      },
    });
  }

  private audienceState() {
    return {
      source: this.source.value,
      audienceFamilies: this.selectedFamilies,
      expirationDateFrom: this.expirationDateFrom.value,
      expirationDateTo: this.expirationDateTo.value,
      funnelMonth: this.funnelMonth.value,
      funnelCutoffDate: this.funnelCutoffDate.value,
      iventasCurrentStatuses: this.selectedIventasCurrentStatuses,
      historyTargetingEnabled: this.historyTargetingEnabled.value,
      historyMode: this.historyMode.value,
      historyMatch: this.historyMatch.value,
      historyDeliveryBuckets: this.selectedHistoryDeliveryBuckets,
      historyOutcomes: this.selectedHistoryOutcomes,
      historyButtonInteracted: this.historyButtonInteracted.value,
      historyWindowMode: this.historyWindowMode.value,
      historyLookbackDays: this.historyLookbackDays.value,
    };
  }

  private invalidatePreview(): void {
    this.preview = null;
    this.previewRequest = null;
    this.lastFreezeCompleted = false;
  }

  private resetBuilderAfterFreeze(): void {
    this.invalidatePreview();
    this.selectedFamilies = [];
    this.expirationDateFrom.setValue('', { emitEvent: false });
    this.expirationDateTo.setValue('', { emitEvent: false });
    this.funnelMonth.setValue('', { emitEvent: false });
    this.funnelCutoffDate.setValue('', { emitEvent: false });
    this.funnelCutoffDates = [];
    this.selectedIventasCurrentStatuses = [];
    this.historyTargetingEnabled.setValue(false, { emitEvent: false });
    this.historyMode.setValue('EXCLUDE', { emitEvent: false });
    this.historyMatch.setValue('ANY', { emitEvent: false });
    this.historyButtonInteracted.setValue(false, { emitEvent: false });
    this.historyWindowMode.setValue('ALL_HISTORY', { emitEvent: false });
    this.historyLookbackDays.setValue('', { emitEvent: false });
    this.selectedHistoryDeliveryBuckets = [];
    this.selectedHistoryOutcomes = [];
    this.name.setValue('', { emitEvent: false });
    const nextPurpose = this.options?.purposes.includes('UNCLASSIFIED')
      ? 'UNCLASSIFIED'
      : this.options?.purposes[0];
    if (nextPurpose) {
      this.purpose.setValue(nextPurpose, { emitEvent: false });
    }
  }

  private ensureOptionDefaults(options: CampaignV2OptionsResponse): void {
    if (!options.sources.includes(this.source.value) && options.sources.length) {
      this.source.setValue(options.sources[0], { emitEvent: false });
    }
    if (!options.purposes.includes(this.purpose.value)) {
      const purpose = options.purposes.includes('UNCLASSIFIED')
        ? 'UNCLASSIFIED'
        : options.purposes[0];
      if (purpose) {
        this.purpose.setValue(purpose, { emitEvent: false });
      }
    }
    this.selectedFamilies = this.selectedFamilies.filter(value =>
      options.selectable_audience_families.includes(value),
    );
    const iventasOptions = options.iventas_current_statuses ?? [];
    this.selectedIventasCurrentStatuses = this.selectedIventasCurrentStatuses.filter(
      value => iventasOptions.includes(value),
    );

    const historyOptions = options.historical_targeting;
    if (historyOptions) {
      if (!historyOptions.modes.includes(this.historyMode.value)) {
        this.historyMode.setValue(
          historyOptions.modes.includes('EXCLUDE') ? 'EXCLUDE' : historyOptions.modes[0],
          { emitEvent: false },
        );
      }
      if (!historyOptions.matches.includes(this.historyMatch.value)) {
        this.historyMatch.setValue(
          historyOptions.matches.includes('ANY') ? 'ANY' : historyOptions.matches[0],
          { emitEvent: false },
        );
      }
      if (!historyOptions.window_modes.includes(this.historyWindowMode.value)) {
        this.historyWindowMode.setValue(
          historyOptions.window_modes.includes('ALL_HISTORY')
            ? 'ALL_HISTORY'
            : historyOptions.window_modes[0],
          { emitEvent: false },
        );
      }
      this.selectedHistoryDeliveryBuckets = this.selectedHistoryDeliveryBuckets.filter(
        value => historyOptions.delivery_buckets.includes(value),
      );
      this.selectedHistoryOutcomes = this.selectedHistoryOutcomes.filter(
        value => historyOptions.outcomes.includes(value),
      );
    }
  }

  private audienceValidationMessage(): string {
    if (this.showsAudienceFamilies && !this.selectedFamilies.length) {
      return 'Selecciona al menos una familia comercial.';
    }
    if (this.isFunnelSource && !this.funnelMonth.value) {
      return 'Selecciona el Mes Funnel.';
    }
    if (this.isFunnelSource && !this.funnelCutoffDate.value) {
      return 'Selecciona un Corte Funnel completo.';
    }
    if (this.historyTargetingMissingConditions) {
      return 'Selecciona al menos una condición histórica.';
    }
    if (this.historyLookbackInvalid) {
      return 'Indica un número entero de días mayor a cero para la ventana histórica.';
    }
    if (this.showsExpirationRange) {
      if (!this.expirationDateFrom.value || !this.expirationDateTo.value) {
        return 'Indica las dos fechas de vencimiento.';
      }
      if (this.expirationDateFrom.value > this.expirationDateTo.value) {
        return 'La fecha inicial no puede ser posterior a la fecha final.';
      }
    }
    return 'Revisa la definición de audiencia.';
  }

  private formatObservedAt(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/Tijuana',
    }).format(parsed);
  }

  private serverMessage(error: HttpErrorResponse): string | null {
    const body = error.error as { message?: string } | null;
    return typeof body?.message === 'string' && body.message.trim()
      ? body.message.trim()
      : null;
  }

  private errorMessage(error: HttpErrorResponse, fallback: string): string {
    if (error.status === 404) {
      return 'Campaña no encontrada o no disponible.';
    }
    if (error.status === 401) {
      return 'Tu sesión no es válida. Inicia sesión nuevamente.';
    }
    if (error.status === 403) {
      return 'No tienes acceso a Campañas V2.';
    }
    return this.serverMessage(error) ?? fallback;
  }
}
