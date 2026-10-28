import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, OnInit, Output, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';

import {
  PermissionB5BetaPayload, PermissionB5BetaPreview, PermissionB5BetaStatus,
  PermissionGrant, PermissionsObservabilityService,
} from './permissions-observability.service';

@Component({
  selector: 'app-permission-b5-beta-editor',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './permission-b5-beta-editor.component.html',
  styleUrls: ['./permission-b5-beta-editor.component.css'],
})
export class PermissionB5BetaEditorComponent implements OnInit, OnChanges {
  @Input() grant: PermissionGrant | null = null;
  @Output() grantsChanged = new EventEmitter<void>();

  status: PermissionB5BetaStatus | null = null;
  statusError = '';
  errorMessage = '';
  successMessage = '';
  preview: PermissionB5BetaPreview | null = null;
  busy = false;
  private previewRevision = 0;
  userIdInput = '';
  effect: 'allow' | 'deny' = 'allow';
  scopeType: 'branch' | 'branch_list' = 'branch';
  branchIdInput = '';
  branchListInput = '';
  startsAtInput = '';
  expiresAtInput = '';
  reason = '';

  constructor(private readonly service: PermissionsObservabilityService) {}

  ngOnInit(): void {
    this.service.getB5Status().subscribe({
      next: result => { this.status = result; this.statusError = ''; },
      error: () => { this.statusError = 'No se pudo consultar el estado del editor B5.'; },
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['grant']) {
      this.loadGrant(this.grant);
    }
  }

  get enabled(): boolean {
    return this.status?.enabled === true;
  }

  get isEditing(): boolean {
    return this.grant !== null;
  }

  get canSave(): boolean {
    return this.enabled && !this.busy && this.preview !== null;
  }

  private loadGrant(grant: PermissionGrant | null): void {
    this.userIdInput = grant?.principal_user_id ? String(grant.principal_user_id) : '';
    this.effect = grant?.effect === 'deny' ? 'deny' : 'allow';
    this.scopeType = grant?.scope_type === 'branch_list' ? 'branch_list' : 'branch';
    this.branchIdInput = grant?.scope_branch_id ? String(grant.scope_branch_id) : '';
    this.branchListInput = (grant?.scope_branch_ids || []).join(', ');
    this.startsAtInput = grant?.starts_at || '';
    this.expiresAtInput = grant?.expires_at || '';
    this.reason = '';
    this.invalidate();
  }

  invalidate(): void {
    ++this.previewRevision;
    this.preview = null;
    this.errorMessage = '';
    this.successMessage = '';
  }

  private payload(): PermissionB5BetaPayload {
    const data: PermissionB5BetaPayload = {
      principal_user_id: Number(this.userIdInput),
      action_full_key: 'internal_documents.view',
      effect: this.effect,
      scope_type: this.scopeType,
      scope_branch_id: this.scopeType === 'branch' ? Number(this.branchIdInput) : null,
      scope_branch_ids: this.scopeType === 'branch_list'
        ? this.branchListInput.split(',').map(value => Number(value.trim())) : [],
      starts_at: this.startsAtInput.trim() || null,
      expires_at: this.expiresAtInput.trim() || null,
      reason: this.reason.trim(),
    };
    if (this.grant) {
      data.grant_id = this.grant.id;
      data.expected_updated_at = this.grant.updated_at || '';
    }
    return data;
  }

  private message(error: unknown): string {
    const response = error as { error?: { detail?: string } };
    return response?.error?.detail || 'La solicitud B5 no pudo completarse.';
  }

  runPreview(): void {
    if (this.busy) { return; }
    this.invalidate();
    const revision = this.previewRevision;
    this.busy = true;
    this.service.previewB5Grant(this.payload())
      .pipe(finalize(() => { this.busy = false; }))
      .subscribe({
        next: result => {
          if (revision === this.previewRevision) { this.preview = result; }
        },
        error: error => {
          if (revision === this.previewRevision) {
            this.errorMessage = this.message(error);
          }
        },
      });
  }

  save(): void {
    if (!this.canSave) { return; }
    this.busy = true;
    const payload = this.payload();
    const call = this.grant
      ? this.service.updateB5Grant(this.grant.id, payload)
      : this.service.createB5Grant(payload);
    call.pipe(finalize(() => { this.busy = false; })).subscribe({
      next: () => {
        this.successMessage = 'Configuración registrada; no equivale a autorización HTTP.';
        this.preview = null;
        this.grantsChanged.emit();
      },
      error: error => {
        this.preview = null;
        this.errorMessage = this.message(error);
      },
    });
  }

  disable(): void {
    if (!this.enabled || this.busy || !this.grant || this.reason.trim().length < 8) {
      return;
    }
    if (!this.grant.updated_at) {
      this.errorMessage = 'No hay versión de concurrencia del grant.';
      return;
    }
    this.busy = true;
    this.service.disableB5Grant(this.grant.id, this.reason.trim(), this.grant.updated_at)
      .pipe(finalize(() => { this.busy = false; }))
      .subscribe({
        next: () => {
          this.successMessage = 'Grant seleccionado desactivado con auditoría.';
          this.preview = null;
          this.grantsChanged.emit();
        },
        error: error => { this.errorMessage = this.message(error); },
      });
  }
}
