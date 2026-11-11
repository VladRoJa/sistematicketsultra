import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { firstValueFrom, forkJoin } from 'rxjs';

import {
  CampaignV2PreflightResponse,
  CampaignV2TemplateProbeRow,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

interface ReviewedQa {
  campaignId: number;
  channel: string;
  sender: string;
  recipientMasked: string;
  dispatchFingerprint: string;
  quoteFingerprint: string;
  maximumUsd: string;
}

type QaResult = 'SIN ENVÍO' | 'PENDIENTE' | 'ACEPTADA POR IVENTAS' | 'RECHAZADA POR IVENTAS' | 'REQUIERE REVISIÓN';

@Component({
  selector: 'app-campaign-template-qa-bulk',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatFormFieldModule, MatInputModule],
  templateUrl: './marketing-campaign-v2-qa-bulk.component.html',
  styleUrls: ['./marketing-campaign-v2-qa-bulk.component.css'],
})
export class MarketingCampaignV2QaBulkComponent implements OnChanges, OnDestroy {
  private readonly api = inject(MarketingCampaignV2Service);
  @Input() templateId: number | null = null;
  @Input() rows: CampaignV2TemplateProbeRow[] = [];
  @Input() disabled = false;
  @Output() finished = new EventEmitter<void>();

  readonly selected = new Set<number>();
  readonly confirmed = new FormControl(false, { nonNullable: true });
  readonly phrase = new FormControl('', { nonNullable: true });
  readonly password = new FormControl('', { nonNullable: true });
  reviewed: ReviewedQa[] = [];
  results: Record<number, QaResult> = {};
  busy = false;
  error = '';
  notice = '';
  stage = '';
  private generation = 0;
  private blocked = false;
  private destroyed = false;

  ngOnChanges(): void {
    // Parent reads refresh after preparing or executing. Never carry consent
    // or a stale manifest across template/catalog updates.
    this.generation++;
    this.selected.clear();
    this.reviewed = [];
    this.confirmed.setValue(false);
    this.phrase.setValue('');
    this.password.setValue('');
    this.blocked = false;
    this.error = '';
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.generation++;
  }

  private ensureActive(generation: number): void {
    if (this.destroyed || this.generation !== generation) {
      throw new Error('La pantalla cambió o se cerró; se detuvo la operación.');
    }
  }

  get candidates(): CampaignV2TemplateProbeRow[] {
    return this.rows.filter(row => this.eligible(row));
  }

  eligible(row: CampaignV2TemplateProbeRow): boolean {
    return row.result === 'PENDIENTE' && row.stale !== true &&
      !!row.qa_campaign_id && row.qa_campaign_id > 0 && !row.child_id &&
      !!row.recipient_phone_masked;
  }

  toggle(row: CampaignV2TemplateProbeRow, checked: boolean): void {
    if (this.busy || this.reviewed.length || this.disabled || !this.eligible(row) ||
        !row.qa_campaign_id) return;
    if (checked) this.selected.add(row.qa_campaign_id);
    else this.selected.delete(row.qa_campaign_id);
    this.confirmed.setValue(false);
    this.phrase.setValue('');
    this.password.setValue('');
    this.error = '';
  }

  get selectedRows(): CampaignV2TemplateProbeRow[] {
    return this.rows.filter(row => row.qa_campaign_id && this.selected.has(row.qa_campaign_id) &&
      this.eligible(row));
  }

  get canReview(): boolean {
    return !this.destroyed && !this.busy && !this.disabled && !this.blocked && !!this.templateId &&
      this.selected.size >= 1 && this.selectedRows.length === this.selected.size &&
      new Set(this.selectedRows.map(row => row.channel_id)).size === this.selected.size;
  }

  get maximumUsd(): string {
    const total = this.reviewed.reduce((sum, row) => sum + Number(row.maximumUsd), 0);
    return total.toFixed(4);
  }

  get sendWord(): string {
    return 'ENVIAR QA ' + this.reviewed.length;
  }

  get canSend(): boolean {
    return !this.destroyed && !this.busy && !this.disabled && !this.blocked && !!this.templateId &&
      this.reviewed.length >= 1 && this.reviewed.length === this.selected.size &&
      this.confirmed.value && this.phrase.value.trim() === this.sendWord &&
      this.password.value.length > 0 && this.password.value.length <= 256;
  }

  private validatePlan(row: CampaignV2TemplateProbeRow, plan: CampaignV2PreflightResponse): ReviewedQa {
    const budget = plan.budget_usd;
    if (!row.qa_campaign_id || !this.templateId ||
        plan.campaign_id !== row.qa_campaign_id ||
        plan.template?.id !== this.templateId ||
        plan.mode !== 'IMMEDIATE' || !plan.ready ||
        plan.sendable_count !== 1 || plan.frozen_count !== 1 ||
        plan.batches.length !== 1 || !plan.batches[0].ready ||
        plan.batches[0].recipient_count !== 1 ||
        plan.batches[0].provider_channel_id !== row.channel_id ||
        plan.provider_campaign_count !== 1 ||
        !budget || budget.status !== 'COMPLETE' ||
        budget.currency !== 'USD' || budget.sendable_recipients !== 1 ||
        !budget.quote_fingerprint ||
        !Number.isFinite(Number(budget.maximum_estimated_usd)) ||
        Number(budget.maximum_estimated_usd) < 0 ||
        plan.quota?.status !== 'REVIEWABLE') {
      throw new Error('QA #' + row.qa_campaign_id +
        ' no tiene destinatario, plantilla, canal, presupuesto o cuota verificables.');
    }
    return {
      campaignId: row.qa_campaign_id, channel: row.channel_id, sender: row.sender,
      recipientMasked: row.recipient_phone_masked!,
      dispatchFingerprint: plan.dispatch_fingerprint,
      quoteFingerprint: budget.quote_fingerprint,
      maximumUsd: budget.maximum_estimated_usd,
    };
  }

  async reviewAll(): Promise<void> {
    if (!this.canReview) return;
    const current = ++this.generation;
    const rows = [...this.selectedRows];
    const templateId = this.templateId!;
    this.busy = true;
    this.error = '';
    this.notice = '';
    this.stage = 'Consultando preflight y controles de cada QA';
    try {
      const reviewed: ReviewedQa[] = [];
      for (const row of rows) {
        const id = row.qa_campaign_id!;
        const state = await firstValueFrom(forkJoin({
          plan: this.api.preflightCampaign(id, templateId),
          approval: this.api.getGovernedApproval(id),
          monitor: this.api.getGovernedMonitor(id),
        }));
        if (this.generation !== current) return;
        if (state.approval.approval || state.monitor.children_count !== 0 ||
            state.monitor.children.length !== 0) {
          throw new Error('QA #' + id + ' ya tiene preparación o intento previo. ' +
            'Revísala individualmente antes de agrupar.');
        }
        reviewed.push(this.validatePlan(row, state.plan));
      }
      if (this.generation !== current || reviewed.length !== rows.length) return;
      // An explicit group is only assembled from these exact persisted QAs.
      this.reviewed = reviewed;
      this.notice = 'Revisión completada; todavía no se reservó cupo ni se enviaron mensajes.';
    } catch (err) {
      this.reviewed = [];
      this.error = this.describe(err, 'No se completó la revisión. No se enviaron mensajes.');
    } finally {
      if (this.generation === current) { this.busy = false; this.stage = ''; }
    }
  }

  /** One confirmation, existing audited approval/authorization per QA.
   * Every provider call is still subject to server-side guards, quota and
   * step-up password. No automatic retry, no autonomous background execution.
   */
  async sendAll(): Promise<void> {
    if (!this.canSend) return;
    const current = ++this.generation;
    const reviewed = [...this.reviewed];
    const password = this.password.value;
    this.password.setValue('');
    this.phrase.setValue('');
    this.confirmed.setValue(false);
    this.busy = true;
    this.blocked = true;
    this.error = '';
    this.notice = '';
    this.results = Object.fromEntries(reviewed.map(row => [row.campaignId, 'SIN ENVÍO']));
    let sendingStarted = false;
    try {
      // Re-read *every* plan before creating the first approval.
      for (const item of reviewed) {
        this.ensureActive(current);
        this.stage = 'Revalidando ' + item.sender;
        const [plan, approval, monitor] = await firstValueFrom(forkJoin([
          this.api.preflightCampaign(item.campaignId, this.templateId!),
          this.api.getGovernedApproval(item.campaignId),
          this.api.getGovernedMonitor(item.campaignId),
        ]));
        if (this.generation !== current || this.destroyed || approval.approval || monitor.children_count !== 0) {
          throw new Error('Cambió la preparación de QA #' + item.campaignId);
        }
        const row = this.rows.find(candidate => candidate.qa_campaign_id === item.campaignId);
        if (!row || !this.eligible(row)) throw new Error('La QA ya no está pendiente.');
        const fresh = this.validatePlan(row, plan);
        if (fresh.channel !== item.channel ||
            fresh.dispatchFingerprint !== item.dispatchFingerprint ||
            fresh.quoteFingerprint !== item.quoteFingerprint ||
            fresh.maximumUsd !== item.maximumUsd) {
          throw new Error('Cambió la huella de QA #' + item.campaignId + '. Revisa de nuevo.');
        }
      }
      // No provider sends until all selected QAs are separately approved,
      // materialized and authorized by the existing audited backend.
      for (const item of reviewed) {
        this.ensureActive(current);
        this.stage = 'Reservando cupo para ' + item.sender;
        await firstValueFrom(this.api.approveGovernedCampaign(item.campaignId, {
          template_id: this.templateId!,
          expected_dispatch_fingerprint: item.dispatchFingerprint,
          expected_quote_fingerprint: item.quoteFingerprint,
          expected_recipients: 1,
          pricing_currency: 'USD',
          held_sucursal_canons: [],
          held_source_references: {},
        }));
      }
      for (const item of reviewed) {
        this.ensureActive(current);
        this.stage = 'Preparando y autorizando ' + item.sender + ' (sin envío)';
        await firstValueFrom(this.api.materializeGovernedCampaign(item.campaignId));
        const state = await firstValueFrom(this.api.getGovernedExecution(item.campaignId));
        this.ensureActive(current);
        if (!('manifest' in state) || state.execution ||
            state.manifest.batches.length !== 1 ||
            state.manifest.batches[0].planned_status !== 'READY' ||
            state.manifest.batches[0].recipients !== 1) {
          throw new Error('Manifiesto de QA #' + item.campaignId + ' no coincide.');
        }
        await firstValueFrom(this.api.authorizeGovernedCampaign(item.campaignId, {
          approval_id: state.approval_id,
          expected_manifest_digest: state.manifest_digest,
          expected_ready_recipients: 1,
          confirm_dispatch: true,
        }));
      }

      // In-memory group order is frozen by operator confirmation. A fresh
      // server monitor/manifest/preflight is required before EVERY POST.
      for (const item of reviewed) {
        this.ensureActive(current);
        this.stage = 'Enviando ' + item.sender + ' mediante iVentas';
        const state = await firstValueFrom(forkJoin({
          plan: this.api.preflightCampaign(item.campaignId, this.templateId!),
          monitor: this.api.getGovernedMonitor(item.campaignId),
          execution: this.api.getGovernedExecution(item.campaignId),
        }));
        this.ensureActive(current);
        const row = this.rows.find(candidate => candidate.qa_campaign_id === item.campaignId);
        if (!row || !('manifest' in state.execution) || !state.execution.execution ||
            state.execution.execution.status !== 'AUTHORIZED' ||
            state.monitor.execution?.status !== 'AUTHORIZED' ||
            state.monitor.quota.all_current !== true ||
            state.monitor.children.length !== 1 ||
            state.monitor.children[0].status !== 'READY' ||
            state.monitor.children[0].needs_manual_review ||
            state.monitor.children[0].provider_channel_id !== item.channel ||
            state.execution.manifest_digest !== state.monitor.approval?.manifest_digest ||
            state.execution.manifest.batches.length !== 1 ||
            state.execution.manifest.batches[0].planned_status !== 'READY') {
          throw new Error('La autorización, el canal o el estado de QA #' +
            item.campaignId + ' cambió. No se repetirá ningún envío.');
        }
        const fresh = this.validatePlan(row, state.plan);
        if (fresh.dispatchFingerprint !== item.dispatchFingerprint ||
            fresh.quoteFingerprint !== item.quoteFingerprint) {
          throw new Error('La huella de QA #' + item.campaignId + ' cambió.');
        }
        this.ensureActive(current);
        this.results[item.campaignId] = 'PENDIENTE';
        sendingStarted = true;
        try {
          const result = await firstValueFrom(this.api.executeGovernedChild(item.campaignId, {
            execution_id: state.execution.execution.execution_id,
            child_id: state.monitor.children[0].child_id,
            expected_manifest_digest: state.execution.manifest_digest,
            operator_password: password,
          }));
          if (result.status !== 'SUBMITTED' ||
              result.child_id !== state.monitor.children[0].child_id) {
            throw new Error('Resultado no confirmado de iVentas para ' + item.sender);
          }
          this.results[item.campaignId] = 'ACEPTADA POR IVENTAS';
        } catch (error) {
          // HTTP 502 is safe to continue ONLY when the existing backend
          // explicitly attests a known deterministic, non-accepted response.
          // Timeouts, unknown 4xx/5xx or an uncertain persistence NEVER resume.
          const err = error as HttpErrorResponse;
          const body = err?.error;
          if (err.status === 502 && body?.status === 'PROVIDER_ERROR' &&
              body?.child_id === state.monitor.children[0].child_id &&
              body?.definitively_not_accepted === true &&
              body?.error_code === 'TEMPLATE_NOT_FOUND' &&
              body?.provider_campaign_id == null) {
            this.ensureActive(current);
            this.results[item.campaignId] = 'RECHAZADA POR IVENTAS';
            continue;
          }
          throw error;
        }
      }
      const accepted = reviewed.filter(item =>
        this.results[item.campaignId] === 'ACEPTADA POR IVENTAS').length;
      const rejected = reviewed.filter(item =>
        this.results[item.campaignId] === 'RECHAZADA POR IVENTAS').length;
      this.notice = 'Operación concluida: ' + accepted + ' aceptadas y ' + rejected +
        ' rechazadas de forma confirmada por iVentas. La entrega real se verifica por separado.';
    } catch (err) {
      // Safe failure: never reattempt any previous POST on ambiguous responses.
      const next = reviewed.find(row =>
        !['ACEPTADA POR IVENTAS', 'RECHAZADA POR IVENTAS'].includes(this.results[row.campaignId]));
      if (next && sendingStarted) this.results[next.campaignId] = 'REQUIERE REVISIÓN';
      this.error = this.describe(err, 'La operación quedó incompleta o incierta.') +
        ' Consulta los estados individuales antes de otra acción. No se reintenta automáticamente.';
    } finally {
      if (this.generation === current) {
        this.busy = false;
        this.stage = '';
        this.reviewed = [];
        if (!this.error) this.finished.emit(); // GET-only refresh of provider evidence
      }
    }
  }

  private describe(err: unknown, fallback: string): string {
    if (err instanceof Error && !(err instanceof HttpErrorResponse)) return err.message;
    const http = err as HttpErrorResponse;
    return typeof http?.error?.message === 'string' ? http.error.message : fallback;
  }
}
