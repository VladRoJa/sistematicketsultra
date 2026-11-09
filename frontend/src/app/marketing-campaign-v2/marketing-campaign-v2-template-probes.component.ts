import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, EventEmitter, Input, OnChanges, Output, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { CampaignV2TemplateProbeMatrix, CampaignV2TemplateProbeRow } from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

@Component({
  selector: 'app-campaign-template-probes', standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatFormFieldModule, MatInputModule],
  templateUrl: './marketing-campaign-v2-template-probes.component.html',
  styleUrls: ['./marketing-campaign-v2-template-probes.component.css'],
})
export class MarketingCampaignV2TemplateProbesComponent implements OnChanges {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  @Input() campaignId = 0;
  @Input() catalogMode = false;
  @Input() templateId: number | null = null;
  @Input() disabled = false;
  @Output() reviewQa = new EventEmitter<CampaignV2TemplateProbeRow>();
  readonly name = new FormControl('', { nonNullable: true });
  readonly phone = new FormControl('', { nonNullable: true });
  readonly reference = new FormControl('', { nonNullable: true });
  readonly authorized = new FormControl(false, { nonNullable: true });
  matrix: CampaignV2TemplateProbeMatrix | null = null;
  busy = false;
  error = '';
  private generation = 0;

  constructor() {
    for (const control of [this.name, this.phone, this.reference]) {
      control.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.authorized.setValue(false));
    }
  }

  ngOnChanges(): void {
    this.generation++;
    this.matrix = null;
    this.busy = false;
    this.error = '';
    this.authorized.setValue(false);
  }

  get allCertified(): boolean {
    return !!this.matrix?.rows.length && this.matrix.rows.every(row => row.result === 'VALIDADA');
  }

  get canPrepare(): boolean {
    return !this.allCertified && !this.busy && !this.disabled && !!this.templateId && this.authorized.value &&
      this.name.value.trim().length > 0 && this.name.value.trim().length <= 255 &&
      /^[+]?[0-9]{10,13}$/.test(this.phone.value.trim()) &&
      this.reference.value.trim().length >= 8 && this.reference.value.trim().length <= 255;
  }

  refresh(): void { this.request(false); }
  prepare(): void { if (this.canPrepare) this.request(true); }

  private request(prepare: boolean): void {
    if (this.busy || this.disabled || !this.templateId) return;
    const generation = ++this.generation;
    this.busy = true;
    this.error = '';
    const request = {
      recipient_name: this.name.value.trim(), phone: this.phone.value.trim(),
      authorization_reference: this.reference.value.trim(),
      confirmed_authorized: this.authorized.value,
    };
    const result = this.catalogMode
      ? (prepare
        ? this.api.prepareCatalogTemplateCertifications(this.templateId, request)
        : this.api.getCatalogTemplateCertifications(this.templateId))
      : (prepare
        ? this.api.prepareTemplateProbes(this.campaignId, { template_id: this.templateId, ...request })
        : this.api.getTemplateProbes(this.campaignId, this.templateId));
    result.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: matrix => {
        if (generation !== this.generation) return;
        this.matrix = matrix;
        this.busy = false;
        this.authorized.setValue(false);
        if (prepare) this.phone.setValue('');
      },
      error: (error: HttpErrorResponse) => {
        if (generation !== this.generation) return;
        this.busy = false;
        this.authorized.setValue(false);
        this.error = String(error.error?.message ||
          'No se pudo confirmar la preparación. Consulta la matriz antes de reintentar.');
      },
    });
  }
}
