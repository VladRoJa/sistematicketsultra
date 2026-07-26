import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router } from '@angular/router';
import { SessionService } from '../../core/auth/session.service';

import {
  ROUTINE_CONTROL_NO_ROUTINE_REASON_OPTIONS,
  RoutineControlMemberDetail,
  RoutineControlNoRoutineReasonCode,
} from '../models/routine-control.models';
import { RoutineControlService } from '../services/routine-control.service';

type RoutineControlDecision =
  RoutineControlMemberDetail['decisions'][number];

@Component({
  selector: 'app-routine-control-member-detail',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
  ],
  templateUrl:
    './routine-control-member-detail.component.html',
  styleUrls: [
    './routine-control-member-detail.component.css',
  ],
})
export class RoutineControlMemberDetailComponent
  implements OnInit
{
  private readonly decisionWriteRoles = new Set([
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'GERENTE',
    'GERENTE_REGIONAL',
  ]);

  readonly reasonOptions =
    ROUTINE_CONTROL_NO_ROUTINE_REASON_OPTIONS;

  readonly createDecisionForm = new FormGroup({
    reason_code:
      new FormControl<
        RoutineControlNoRoutineReasonCode | ''
      >('', {
        nonNullable: true,
        validators: [Validators.required],
      }),
    notes: new FormControl('', {
      nonNullable: true,
    }),
    confirmed: new FormControl(false, {
      nonNullable: true,
      validators: [Validators.requiredTrue],
    }),
  });

  readonly revokeDecisionForm = new FormGroup({
    revocation_reason: new FormControl('', {
      nonNullable: true,
      validators: [
        Validators.required,
        Validators.maxLength(500),
      ],
    }),
  });

  detail: RoutineControlMemberDetail | null = null;

  loading = true;
  savingDecision = false;
  revokingDecision = false;
  showCreateDecisionForm = false;
  showRevokeDecisionForm = false;

  errorMessage = '';
  actionErrorMessage = '';
  actionSuccessMessage = '';

  private memberId: number | null = null;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly service: RoutineControlService,
    private readonly session: SessionService,
  ) {}

  ngOnInit(): void {
    const memberId = Number(
      this.route.snapshot.paramMap.get('memberId'),
    );

    if (
      !Number.isInteger(memberId)
      || memberId <= 0
    ) {
      this.loading = false;
      this.errorMessage =
        'Identificador de socio inválido.';
      return;
    }

    this.memberId = memberId;
    this.loadDetail();
  }

  back(): void {
    this.router.navigate(['/control-rutinas']);
  }

  statusLabel(): string {
    if (
      this.detail?.member.classification_status
      === 'INCIDENT'
    ) {
      return 'Incidencia';
    }

    switch (this.detail?.member.current_status) {
      case 'CON_RUTINA':
        return 'Con rutina';
      case 'SIN_RUTINA':
        return 'Sin rutina';
      case 'NO_DESEA_RUTINA':
        return 'No requiere rutina de Ultra';
      default:
        return 'Sin estado';
    }
  }

  decisionLabel(): string {
    return 'No requiere rutina de Ultra';
  }

  reasonLabel(
    reasonCode: string | null | undefined,
  ): string {
    const option = this.reasonOptions.find(
      (item) => item.value === reasonCode,
    );

    return option?.label
      ?? reasonCode?.replace(/_/g, ' ')
      ?? 'Sin motivo';
  }

  canWriteDecisions(): boolean {
    const role = String(
      this.session.getUser()?.rol ?? '',
    )
      .trim()
      .toUpperCase();

    return this.decisionWriteRoles.has(role);
  }

  activeDecision(): RoutineControlDecision | null {
    return (
      this.detail?.decisions.find(
        (decision) => decision.is_active,
      ) ?? null
    );
  }

  canCreateDecision(): boolean {
    if (!this.detail) {
      return false;
    }

    return (
      this.canWriteDecisions()
      && this.detail.member.classification_status
        === 'CLASSIFIED'
      && this.detail.member.current_status
        === 'SIN_RUTINA'
      && this.activeDecision() === null
    );
  }

  openCreateDecisionForm(): void {
    if (!this.canWriteDecisions()) {
      return;
    }

    this.clearActionMessages();
    this.showRevokeDecisionForm = false;
    this.showCreateDecisionForm = true;
  }

  cancelCreateDecision(): void {
    this.showCreateDecisionForm = false;
    this.createDecisionForm.reset({
      reason_code: '',
      notes: '',
      confirmed: false,
    });
    this.clearActionMessages();
  }

  openRevokeDecisionForm(): void {
    if (!this.canWriteDecisions()) {
      return;
    }

    this.clearActionMessages();
    this.showCreateDecisionForm = false;
    this.showRevokeDecisionForm = true;
  }

  cancelRevokeDecision(): void {
    this.showRevokeDecisionForm = false;
    this.revokeDecisionForm.reset({
      revocation_reason: '',
    });
    this.clearActionMessages();
  }

  otherReasonRequiresNotes(): boolean {
    const reasonCode =
      this.createDecisionForm.controls
        .reason_code.value;

    const notes =
      this.createDecisionForm.controls
        .notes.value.trim();

    return reasonCode === 'OTRO' && !notes;
  }

  createDecision(): void {
    if (
      !this.canWriteDecisions()
      || this.memberId === null
      || this.savingDecision
    ) {
      return;
    }

    this.createDecisionForm.markAllAsTouched();

    if (
      this.createDecisionForm.invalid
      || this.otherReasonRequiresNotes()
    ) {
      this.actionErrorMessage =
        'Completa el motivo, la confirmación y las '
        + 'observaciones requeridas.';
      return;
    }

    const reasonCode =
      this.createDecisionForm.controls
        .reason_code.value;

    if (!reasonCode) {
      return;
    }

    const notes =
      this.createDecisionForm.controls
        .notes.value.trim();

    this.savingDecision = true;
    this.clearActionMessages();

    this.service.createNoRoutineDecision(
      this.memberId,
      {
        reason_code: reasonCode,
        notes: notes || null,
        confirmed: true,
      },
    ).subscribe({
      next: () => {
        this.savingDecision = false;
        this.showCreateDecisionForm = false;
        this.createDecisionForm.reset({
          reason_code: '',
          notes: '',
          confirmed: false,
        });
        this.actionSuccessMessage =
          'El socio quedó marcado como '
          + '“No requiere rutina de Ultra”.';
        this.loadDetail(false);
      },
      error: (error: HttpErrorResponse) => {
        this.savingDecision = false;
        this.actionErrorMessage =
          this.errorDetail(
            error,
            'No fue posible registrar la decisión.',
          );
      },
    });
  }

  revokeDecision(): void {
    const decision = this.activeDecision();

    if (
      !this.canWriteDecisions()
      || this.memberId === null
      || decision === null
      || this.revokingDecision
    ) {
      return;
    }

    this.revokeDecisionForm.markAllAsTouched();

    if (this.revokeDecisionForm.invalid) {
      this.actionErrorMessage =
        'Escribe el motivo de la reversión.';
      return;
    }

    const revocationReason =
      this.revokeDecisionForm.controls
        .revocation_reason.value.trim();

    this.revokingDecision = true;
    this.clearActionMessages();

    this.service.revokeNoRoutineDecision(
      this.memberId,
      decision.id,
      {
        revocation_reason: revocationReason,
      },
    ).subscribe({
      next: () => {
        this.revokingDecision = false;
        this.showRevokeDecisionForm = false;
        this.revokeDecisionForm.reset({
          revocation_reason: '',
        });
        this.actionSuccessMessage =
          'La decisión fue revertida. '
          + 'El estado del socio fue recalculado.';
        this.loadDetail(false);
      },
      error: (error: HttpErrorResponse) => {
        this.revokingDecision = false;
        this.actionErrorMessage =
          this.errorDetail(
            error,
            'No fue posible revertir la decisión.',
          );
      },
    });
  }

  private loadDetail(
    showLoading = true,
  ): void {
    if (this.memberId === null) {
      return;
    }

    if (showLoading) {
      this.loading = true;
    }

    this.errorMessage = '';

    this.service
      .getMemberDetail(this.memberId)
      .subscribe({
        next: (detail) => {
          this.detail = detail;
          this.loading = false;
        },
        error: () => {
          this.loading = false;
          this.errorMessage =
            'No fue posible consultar el detalle '
            + 'del socio.';
        },
      });
  }

  private clearActionMessages(): void {
    this.actionErrorMessage = '';
    this.actionSuccessMessage = '';
  }

  private errorDetail(
    error: HttpErrorResponse,
    fallback: string,
  ): string {
    const detail = error.error?.detail;

    return typeof detail === 'string'
      && detail.trim()
      ? detail
      : fallback;
  }
}
