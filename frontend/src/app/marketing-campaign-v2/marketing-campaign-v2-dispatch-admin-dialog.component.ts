import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { forkJoin } from 'rxjs';

import {
  CampaignV2CatalogBranch,
  CampaignV2ChannelBinding,
  CampaignV2ChannelBindingRequest,
  CampaignV2BudgetRateRevision,
  CampaignV2DispatchTemplate,
  CampaignV2Purpose,
  CampaignV2TemplateConfigRequest,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { isDispatchTemplateDraftValid } from './marketing-campaign-v2-dispatch-admin.logic';

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
  ],
  templateUrl: './marketing-campaign-v2-dispatch-admin-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-dispatch-admin-dialog.component.css'],
})
export class MarketingCampaignV2DispatchAdminDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
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
  editingBindingId: number | null = null;
  pendingDeactivateId: number | null = null;
  showChannels = false;

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
  private bindingMetadata: Record<string, unknown> = {};

  ngOnInit(): void {
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
    const parsed = Number(this.pricingUnitCostMxn.value.trim());
    const template = this.templates.find(row => row.id === this.pricingTemplateId.value);
    return !this.savingBudgetRate
      && Boolean(template?.is_active)
      && this.pricingChannelId.valid
      && this.availableChannels.some(row => row.provider_channel_id === this.pricingChannelId.value)
      && Boolean(template && (!template.compatible_channel_ids.length || template.compatible_channel_ids.includes(this.pricingChannelId.value)))
      && this.pricingSourceReference.valid
      && this.pricingSourceReference.value.trim().length > 0
      && this.pricingUnitCostMxn.value.trim().length > 0
      && /^\\d+(\\.\\d{1,6})?$/.test(this.pricingUnitCostMxn.value.trim())
      && Number.isFinite(parsed) && parsed > 0 && parsed <= 1000;
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

  get canSaveBinding(): boolean {
    return !this.savingBinding && this.bindingBranchId.valid && this.bindingChannelId.valid;
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

  editTemplate(template: CampaignV2DispatchTemplate): void {
    this.pendingDeactivateId = null;
    this.editingTemplateId = template.id;
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
  }

  saveBinding(): void {
    if (!this.canSaveBinding || this.bindingBranchId.value === null) {
      this.error = 'Selecciona una sucursal y captura el ID exacto del canal.';
      return;
    }
    const payload: CampaignV2ChannelBindingRequest = {
      provider: 'IVENTAS',
      sucursal_id: this.bindingBranchId.value,
      provider_channel_id: this.bindingChannelId.value.trim(),
      is_active: this.bindingActive.value,
      is_default: this.bindingActive.value && this.bindingDefault.value,
      metadata: { ...this.bindingMetadata },
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
