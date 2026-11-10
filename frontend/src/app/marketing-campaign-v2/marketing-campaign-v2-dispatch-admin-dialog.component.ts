import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { forkJoin } from 'rxjs';

import {
  CampaignV2CatalogBranch,
  CampaignV2BulkInventoryPreview,
  CampaignV2ChannelBinding,
  CampaignV2ChannelBindingRequest,
  CampaignV2BudgetRateRevision,
  CampaignV2DispatchTemplate,
  CampaignV2TemplateProbeRow,
  CampaignV2Purpose,
  CampaignV2TemplateConfigRequest,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2TemplateProbesComponent } from './marketing-campaign-v2-template-probes.component';
import { MarketingCampaignV2GovernedConsoleDialogComponent } from './marketing-campaign-v2-governed-console-dialog.component';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { isDispatchTemplateDraftValid } from './marketing-campaign-v2-dispatch-admin.logic';
import { isCampaignV2MxnUnitCostValid } from './marketing-campaign-v2-admin-validation.logic';

interface VariableMappingRow {
  position: number;
  source: FormControl<string>;
}

@Component({
  selector: 'app-marketing-campaign-v2-dispatch-admin-dialog',
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
    MarketingCampaignV2TemplateProbesComponent,
  ],
  templateUrl: './marketing-campaign-v2-dispatch-admin-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-dispatch-admin-dialog.component.css'],
})
export class MarketingCampaignV2DispatchAdminDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly dialogs = inject(MatDialog);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2DispatchAdminDialogComponent>);

  readonly purposes: CampaignV2Purpose[] = ['REACTIVATION', 'NEW_SALE', 'ACTIVE_MEMBERS', 'UNCLASSIFIED'];
  readonly variableSources = [
    { value: 'first_name', label: 'Nombre' },
    { value: 'expiration_date', label: 'Vencimiento' },
    { value: 'tariff', label: 'Tarifa' },
    { value: 'branch', label: 'Sucursal' },
    { value: 'member_id', label: 'ID socio' },
    { value: 'member_pin', label: 'PIN socio' },
    { value: 'amount', label: 'Adeudo / monto' },
  ];

  templates: CampaignV2DispatchTemplate[] = [];
  bindings: CampaignV2ChannelBinding[] = [];
  branches: CampaignV2CatalogBranch[] = [];
  budgetRates: CampaignV2BudgetRateRevision[] = [];
  savingBudgetRate = false;
  budgetRateSuccess = '';
  loading = false;
  savingTemplate = false;
  savingBinding = false;
  error = '';
  notice = '';
  editingTemplateId: number | null = null;
  certificationTemplateId: number | null = null;
  editingBindingId: number | null = null;
  pendingDeactivateId: number | null = null;
  showChannels = false;
  showTemplateEditor = false;
  showBudgetEditor = false;

  bulkTemplateId: number | null = null;
  bulkTemplateName = '';
  bulkPreview: CampaignV2BulkInventoryPreview | null = null;
  bulkBusy = false;
  bulkError = '';
  bulkMessage = '';
  readonly bulkInventoryJson = new FormControl('', { nonNullable: true });
  readonly bulkObservedAt = new FormControl('', { nonNullable: true });
  readonly bulkReference = new FormControl('', { nonNullable: true });
  readonly bulkConfirmed = new FormControl(false, { nonNullable: true });

  readonly templateName = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(255)] });
  readonly templateLabel = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(255)] });
  readonly templatePurposes = new FormControl<CampaignV2Purpose[]>([], { nonNullable: true });
  readonly templateChannels = new FormControl<string[]>([], { nonNullable: true });
  readonly templateActive = new FormControl(true, { nonNullable: true });
  readonly templateFileUrl = new FormControl('', { nonNullable: true });
  variableRows: VariableMappingRow[] = [];
  private templateMetadata: Record<string, unknown> = {};

  readonly pricingTemplateId = new FormControl<number | null>(null, { validators: [Validators.required] });
  readonly pricingChannelId = new FormControl('', { nonNullable: true, validators: [Validators.required] });
  readonly pricingUnitCostMxn = new FormControl('', { nonNullable: true, validators: [Validators.required] });
  readonly pricingSourceReference = new FormControl('', { nonNullable: true, validators: [Validators.required] });

  readonly bindingBranchId = new FormControl<number | null>(null, { validators: [Validators.required] });
  readonly bindingChannelId = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(255)] });
  readonly bindingActive = new FormControl(true, { nonNullable: true });
  readonly bindingDefault = new FormControl(true, { nonNullable: true });
  readonly bindingRouteViaBindingId = new FormControl<number | null>(null);
  private bindingMetadata: Record<string, unknown> = {};

  ngOnInit(): void {
    this.bulkInventoryJson.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.bulkPreview = null;
        this.bulkMessage = '';
      });
    this.reload();
  }

  get availableChannels(): CampaignV2ChannelBinding[] {
    return this.bindings.filter(binding => binding.is_active);
  }

  get canSaveTemplate(): boolean {
    return !this.savingTemplate
      && this.templateName.valid
      && this.templateLabel.valid
      && isDispatchTemplateDraftValid({
        templateName: this.templateName.value,
        label: this.templateLabel.value,
        purposes: this.templatePurposes.value,
        channelIds: this.templateChannels.value,
        activeChannelIds: this.availableChannels.map(channel => channel.provider_channel_id),
        variables: this.variableRows.map(row => row.source.value),
        fileUrl: this.templateFileUrl.value,
      });
  }

  get canSaveBudgetRate(): boolean {
    const template = this.templates.find(row => row.id === this.pricingTemplateId.value);
    return !this.savingBudgetRate
      && Boolean(template?.is_active)
      && this.pricingChannelId.valid
      && this.availableChannels.some(row => row.provider_channel_id === this.pricingChannelId.value)
      && Boolean(template && (!template.compatible_channel_ids.length || template.compatible_channel_ids.includes(this.pricingChannelId.value)))
      && this.pricingSourceReference.valid
      && this.pricingSourceReference.value.trim().length > 0
      && isCampaignV2MxnUnitCostValid(this.pricingUnitCostMxn.value);
  }

  get latestBudgetRates(): CampaignV2BudgetRateRevision[] {
    const seen = new Set<string>();
    return [...this.budgetRates]
      .sort((a, b) => b.valid_from.localeCompare(a.valid_from) || b.revision_id - a.revision_id)
      .filter(row => {
        const key = row.template_id + ':' + row.provider_channel_id;
        if (seen.has(key)) { return false; }
        seen.add(key);
        return true;
      });
  }

  get isIndependenciaBinding(): boolean {
    return this.branches.some(branch =>
      branch.sucursal_id === this.bindingBranchId.value &&
      branch.sucursal_canon === 'INDEPENDENCIA');
  }

  get availableSenderBindings(): CampaignV2ChannelBinding[] {
    return this.bindings.filter(binding => binding.is_active && binding.is_default &&
      binding.sucursal_canon === 'TEC_MXL');
  }

  senderForBinding(binding: CampaignV2ChannelBinding): string {
    const route = binding.metadata?.['dispatch_via_binding_id'];
    if (typeof route !== 'number') { return 'Canal propio'; }
    return this.bindings.find(row => row.id === route)?.sucursal_canon ?? 'Emisor inválido';
  }

  get canSaveBinding(): boolean {
    return !this.savingBinding && this.bindingBranchId.valid && this.bindingChannelId.valid
      && (this.bindingRouteViaBindingId.value === null || (
        this.isIndependenciaBinding &&
        this.availableSenderBindings.some(row => row.id === this.bindingRouteViaBindingId.value)
      ));
  }

  reload(): void {
    if (this.loading) {
      return;
    }
    this.loading = true;
    this.error = '';
    forkJoin({
      templates: this.api.listDispatchTemplatesAdmin(),
      bindings: this.api.listDispatchChannelBindings(),
      branches: this.api.listDispatchCatalogBranches(),
      budgetRates: this.api.listBudgetRateRevisions(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.loading = false;
        this.templates = result.templates.rows;
        this.bindings = result.bindings.rows;
        this.branches = result.branches.rows;
        this.budgetRates = result.budgetRates.rows;
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.error = this.errorMessage(error, 'No se pudo cargar la configuración.');
      },
    });
  }

  closeBulkInventory(): void {
    this.bulkTemplateId = null;
    this.bulkPreview = null;
    this.bulkError = '';
  }

  openBulkInventory(template: CampaignV2DispatchTemplate): void {
    this.bulkTemplateId = this.bulkTemplateId === template.id ? null : template.id;
    this.bulkTemplateName = template.template_name;
    this.bulkPreview = null;
    this.bulkInventoryJson.setValue('');
    this.bulkObservedAt.setValue('');
    this.bulkReference.setValue('');
    this.bulkConfirmed.setValue(false);
    this.bulkError = '';
    this.bulkMessage = '';
  }

  onBulkInventoryFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) { return; }
    if (file.size > 750000) {
      this.bulkError = 'El inventario JSON no puede superar 750 KB.';
      return;
    }
    file.text().then(text => {
      this.bulkInventoryJson.setValue(text);
      this.bulkError = '';
    }).catch(() => {
      this.bulkError = 'No fue posible leer el archivo JSON.';
    });
    input.value = '';
  }

  private parseBulkInventory(): unknown[] | null {
    try {
      const parsed: unknown = JSON.parse(this.bulkInventoryJson.value);
      if (Array.isArray(parsed)) { return parsed; }
    } catch {
      // The validation message below covers invalid JSON.
    }
    this.bulkError = 'Se necesita un arreglo JSON válido de iVentas.';
    return null;
  }

  previewBulkInventory(): void {
    if (this.bulkTemplateId === null || this.bulkBusy) { return; }
    this.bulkError = '';
    const inventory = this.parseBulkInventory();
    if (!inventory) { return; }
    this.bulkBusy = true;
    this.api.previewBulkTemplateInventory(this.bulkTemplateId, inventory)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: preview => {
          this.bulkBusy = false;
          this.bulkPreview = preview;
        },
        error: (error: HttpErrorResponse) => {
          this.bulkBusy = false;
          this.bulkError = this.errorMessage(error, 'No se pudo revisar el inventario.');
        },
      });
  }

  registerBulkInventory(): void {
    const templateId = this.bulkTemplateId;
    const preview = this.bulkPreview;
    if (templateId === null || !preview || !this.bulkConfirmed.value
        || this.bulkBusy || !this.bulkObservedAt.value.trim()
        || !this.bulkReference.value.trim()) { return; }
    this.bulkError = '';
    const inventory = this.parseBulkInventory();
    if (!inventory) { return; }
    this.bulkBusy = true;
    this.api.registerBulkTemplateInventory(templateId, {
      inventory,
      observed_at: this.bulkObservedAt.value.trim(),
      source_reference: this.bulkReference.value.trim(),
      expected_fingerprint: preview.candidate_fingerprint,
      confirmed_provider_capture: true,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.bulkBusy = false;
        this.bulkMessage = 'Aprobados: ' + result.recorded +
          ' · no aprobados: ' + result.revoked +
          ' · sin dato/incompatibles: ' + result.pending + '. Válida hasta ' +
          result.expires_at + '. No se enviaron mensajes.';
        this.bulkConfirmed.setValue(false);
      },
      error: (error: HttpErrorResponse) => {
        this.bulkBusy = false;
        this.bulkError = this.errorMessage(error, 'No se pudo registrar el inventario.');
      },
    });
  }

  editTemplate(template: CampaignV2DispatchTemplate): void {
    this.pendingDeactivateId = null;
    this.editingTemplateId = template.id;
    this.showTemplateEditor = true;
    this.templateName.setValue(template.template_name);
    this.templateLabel.setValue(template.label);
    this.templatePurposes.setValue([...template.purposes]);
    this.templateChannels.setValue([...template.compatible_channel_ids]);
    this.templateActive.setValue(template.is_active);
    this.templateMetadata = { ...template.metadata };
    this.templateFileUrl.setValue(String(template.metadata['file_url'] || ''));
    this.variableRows = Object.keys(template.variables).sort((a, b) => Number(a) - Number(b))
      .map((key, index) => ({
        position: index + 1,
        source: new FormControl(template.variables[key], { nonNullable: true }),
      }));
    this.notice = '';
    this.error = '';
  }

  showCertification(template: CampaignV2DispatchTemplate): void {
    this.certificationTemplateId = this.certificationTemplateId === template.id ? null : template.id;
  }

  reviewCertificationQa(row: CampaignV2TemplateProbeRow): void {
    if (!row.qa_campaign_id || !this.certificationTemplateId ||
        row.stale || row.result === 'VALIDADA' ||
        row.result === 'RECHAZADA' || row.result === 'INCIERTA') return;
    this.dialogs.open(MarketingCampaignV2GovernedConsoleDialogComponent, {
      width: '1200px', maxWidth: '96vw', disableClose: true,
      data: { campaignId: row.qa_campaign_id,
              campaignName: 'QA plantilla · ' + row.sender,
              probeTemplateId: this.certificationTemplateId },
    });
  }

  startNewTemplate(): void {
    this.resetTemplate();
    this.showTemplateEditor = true;
  }

  closeTemplateEditor(): void {
    if (this.savingTemplate) { return; }
    this.resetTemplate();
    this.showTemplateEditor = false;
  }

  openBudgetEditor(): void { this.showBudgetEditor = true; }

  closeBudgetEditor(): void {
    if (!this.savingBudgetRate) { this.showBudgetEditor = false; }
  }

  resetTemplate(): void {
    this.editingTemplateId = null;
    this.pendingDeactivateId = null;
    this.templateName.setValue('');
    this.templateLabel.setValue('');
    this.templatePurposes.setValue([]);
    this.templateChannels.setValue([]);
    this.templateActive.setValue(true);
    this.templateFileUrl.setValue('');
    this.templateMetadata = {};
    this.variableRows = [];
    this.error = '';
  }

  addVariable(): void {
    this.variableRows = [
      ...this.variableRows,
      { position: this.variableRows.length + 1, source: new FormControl('', { nonNullable: true }) },
    ];
  }

  removeVariable(index: number): void {
    this.variableRows = this.variableRows.filter((_, i) => i !== index)
      .map((row, i) => ({ ...row, position: i + 1 }));
  }

  selectAllActiveChannels(): void {
    this.templateChannels.setValue(this.availableChannels.map(row => row.provider_channel_id));
  }

  clearChannels(): void {
    this.templateChannels.setValue([]);
  }

  saveTemplate(): void {
    if (!this.canSaveTemplate) {
      this.error = 'Completa nombre, propósito y al menos un canal activo; revisa las variables.';
      return;
    }
    const variables: Record<string, string> = {};
    this.variableRows.forEach(row => { variables[String(row.position)] = row.source.value; });
    const metadata = { ...this.templateMetadata };
    if (this.templateFileUrl.value.trim()) {
      metadata['file_url'] = this.templateFileUrl.value.trim();
    } else {
      delete metadata['file_url'];
    }
    const payload: CampaignV2TemplateConfigRequest = {
      provider: 'IVENTAS',
      template_name: this.templateName.value.trim(),
      label: this.templateLabel.value.trim(),
      purposes: this.templatePurposes.value,
      variables,
      compatible_channel_ids: [...this.templateChannels.value],
      is_active: this.templateActive.value,
      metadata,
    };
    this.savingTemplate = true;
    this.error = '';
    const operation = this.editingTemplateId === null
      ? this.api.createDispatchTemplate(payload)
      : this.api.updateDispatchTemplate(this.editingTemplateId, payload);
    operation.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.savingTemplate = false;
        this.notice = 'Plantilla guardada localmente. No confirma aprobación en iVentas.';
        this.resetTemplate();
        this.showTemplateEditor = false;
        this.reload();
      },
      error: (error: HttpErrorResponse) => {
        this.savingTemplate = false;
        this.error = this.errorMessage(error, 'No se pudo guardar la plantilla.');
      },
    });
  }

  requestDeactivate(template: CampaignV2DispatchTemplate): void {
    this.pendingDeactivateId = template.id;
    this.notice = 'Confirma desactivar la plantilla ' + template.template_name + '.';
  }

  cancelDeactivate(): void {
    this.pendingDeactivateId = null;
    this.notice = '';
  }

  confirmDeactivate(): void {
    const row = this.templates.find(t => t.id === this.pendingDeactivateId);
    if (!row || !row.is_active || this.savingTemplate) {
      return;
    }
    this.savingTemplate = true;
    this.error = '';
    this.api.updateDispatchTemplate(row.id, {
      provider: 'IVENTAS',
      template_name: row.template_name,
      label: row.label,
      purposes: [...row.purposes],
      variables: { ...row.variables },
      compatible_channel_ids: [...row.compatible_channel_ids],
      is_active: false,
      metadata: { ...row.metadata },
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.savingTemplate = false;
        this.pendingDeactivateId = null;
        this.notice = 'Plantilla desactivada para nuevos preflights.';
        this.reload();
      },
      error: (error: HttpErrorResponse) => {
        this.savingTemplate = false;
        this.error = this.errorMessage(error, 'No se pudo desactivar la plantilla.');
      },
    });
  }

  editBinding(binding: CampaignV2ChannelBinding): void {
    this.editingBindingId = binding.id;
    this.bindingBranchId.setValue(binding.sucursal_id);
    this.bindingChannelId.setValue(binding.provider_channel_id);
    this.bindingActive.setValue(binding.is_active);
    this.bindingDefault.setValue(binding.is_default);
    this.bindingMetadata = { ...binding.metadata };
    const route = binding.metadata?.['dispatch_via_binding_id'];
    this.bindingRouteViaBindingId.setValue(typeof route === 'number' ? route : null);
    this.notice = '';
    this.error = '';
    this.showChannels = true;
  }

  resetBinding(): void {
    this.editingBindingId = null;
    this.bindingBranchId.setValue(null);
    this.bindingChannelId.setValue('');
    this.bindingActive.setValue(true);
    this.bindingDefault.setValue(true);
    this.bindingMetadata = {};
    this.bindingRouteViaBindingId.setValue(null);
  }

  saveBinding(): void {
    if (!this.canSaveBinding || this.bindingBranchId.value === null) {
      this.error = 'Selecciona una sucursal y captura el ID exacto del canal.';
      return;
    }
    const metadata = { ...this.bindingMetadata };
    if (this.isIndependenciaBinding && this.bindingRouteViaBindingId.value !== null) {
      metadata['dispatch_via_binding_id'] = this.bindingRouteViaBindingId.value;
    } else {
      delete metadata['dispatch_via_binding_id'];
    }
    const payload: CampaignV2ChannelBindingRequest = {
      provider: 'IVENTAS',
      sucursal_id: this.bindingBranchId.value,
      provider_channel_id: this.bindingChannelId.value.trim(),
      is_active: this.bindingActive.value,
      is_default: this.bindingActive.value && this.bindingDefault.value,
      metadata,
    };
    this.savingBinding = true;
    this.error = '';
    const operation = this.editingBindingId === null
      ? this.api.createDispatchChannelBinding(payload)
      : this.api.updateDispatchChannelBinding(this.editingBindingId, payload);
    operation.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.savingBinding = false;
        this.notice = 'Binding guardado; comprueba la plantilla compatible antes de enviar.';
        this.resetBinding();
        this.reload();
      },
      error: (error: HttpErrorResponse) => {
        this.savingBinding = false;
        this.error = this.errorMessage(error, 'No se pudo guardar el canal.');
      },
    });
  }

  registerBudgetRate(): void {
    if (!this.canSaveBudgetRate || this.pricingTemplateId.value === null) {
      this.error = 'Selecciona plantilla/canal vigentes, costo decimal en MXN y fuente documental.';
      return;
    }
    this.savingBudgetRate = true;
    this.budgetRateSuccess = '';
    this.error = '';
    this.api.registerBudgetRateRevision({
      template_id: this.pricingTemplateId.value,
      provider_channel_id: this.pricingChannelId.value,
      unit_cost_mxn: this.pricingUnitCostMxn.value.trim(),
      source_reference: this.pricingSourceReference.value.trim(),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: saved => {
        this.savingBudgetRate = false;
        this.budgetRateSuccess = 'Revisión #' + saved.revision_id + ' guardada. Es una estimación manual, no una factura.';
        this.showBudgetEditor = false;
        this.pricingUnitCostMxn.setValue('');
        this.pricingSourceReference.setValue('');
        this.reload();
      },
      error: (error: HttpErrorResponse) => {
        this.savingBudgetRate = false;
        this.error = this.errorMessage(error, 'No se pudo registrar esta cotización.');
      },
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  private errorMessage(error: HttpErrorResponse, fallback: string): string {
    if (error.status === 403) {
      return 'No tienes permisos globales para administrar plantillas y canales.';
    }
    if (error.status === 409) {
      return String(error.error?.message || 'Conflicto con configuración existente o lotes auditados.');
    }
    return String(error.error?.message || fallback);
  }
}
