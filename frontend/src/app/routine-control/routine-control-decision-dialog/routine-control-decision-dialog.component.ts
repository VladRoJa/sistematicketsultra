import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  Inject,
  OnInit,
} from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { SessionService } from '../../core/auth/session.service';
import {
  ROUTINE_CONTROL_NO_ROUTINE_REASON_OPTIONS,
  RoutineControlMemberDetail,
  RoutineControlNoRoutineReasonCode,
} from '../models/routine-control.models';
import { RoutineControlService } from '../services/routine-control.service';

export interface RoutineControlDecisionDialogData {
  memberId: number;
}

type RoutineControlDecision =
  RoutineControlMemberDetail['decisions'][number];

@Component({
  selector: 'app-routine-control-decision-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
  ],
  templateUrl:
    './routine-control-decision-dialog.component.html',
  styleUrls: [
    './routine-control-decision-dialog.component.css',
  ],
})
export class RoutineControlDecisionDialogComponent
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

  readonly createForm = new FormGroup({
    reason_code:
      new FormControl<
        RoutineControlNoRoutineReasonCode | ''
      >('', {
        nonNullable: true,
        validators: [Validators.required],
      }),
    notes: new FormControl('', {
      nonNullable: true,
      validators: [Validators.maxLength(500)],
    }),
    confirmed: new FormControl(false, {
      nonNullable: true,
      validators: [Validators.requiredTrue],
    }),
  });

  readonly revokeForm = new FormGroup({
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
  saving = false;
  revoking = false;
  showRevokeForm = false;
  errorMessage = '';

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: RoutineControlDecisionDialogData,
    private readonly dialogRef:
      MatDialogRef<
        RoutineControlDecisionDialogComponent,
        boolean
      >,
    private readonly service: RoutineControlService,
    private readonly session: SessionService,
  ) {}

  ngOnInit(): void {
    this.loadDetail();
  }

  close(): void {
    this.dialogRef.close(false);
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
    if (!this.detail || !this.canWriteDecisions()) {
      return false;
    }

    return (
      this.detail.member.classification_status
        === 'CLASSIFIED'
      && this.detail.member.current_status
        === 'SIN_RUTINA'
      && this.activeDecision() === null
    );
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

  reasonLabel(
    reasonCode: string | null | undefined,
  ): string {
    return (
      this.reasonOptions.find(
        (option) => option.value === reasonCode,
      )?.label
      ?? reasonCode?.replace(/_/g, ' ')
      ?? 'Sin motivo'
    );
  }

  otherReasonRequiresNotes(): boolean {
    return (
      this.createForm.controls.reason_code.value
        === 'OTRO'
      && !this.createForm.controls.notes.value.trim()
    );
  }

  openRevokeForm(): void {
    if (!this.canWriteDecisions()) {
      return;
    }

    this.errorMessage = '';
    this.showRevokeForm = true;
  }

  cancelRevoke(): void {
    this.showRevokeForm = false;
    this.errorMessage = '';
    this.revokeForm.reset({
      revocation_reason: '',
    });
  }

  createDecision(): void {
    if (!this.canCreateDecision() || this.saving) {
      return;
    }

    this.createForm.markAllAsTouched();

    if (
      this.createForm.invalid
      || this.otherReasonRequiresNotes()
    ) {
      this.errorMessage =
        'Completa el motivo, la confirmación y '
        + 'las observaciones requeridas.';
      return;
    }

    const reasonCode =
      this.createForm.controls.reason_code.value;

    if (!reasonCode) {
      return;
    }

    const notes =
      this.createForm.controls.notes.value.trim();

    this.saving = true;
    this.errorMessage = '';

    this.service.createNoRoutineDecision(
      this.data.memberId,
      {
        reason_code: reasonCode,
        notes: notes || null,
        confirmed: true,
      },
    ).subscribe({
      next: () => {
        this.saving = false;
        this.dialogRef.close(true);
      },
      error: (error: HttpErrorResponse) => {
        this.saving = false;
        this.errorMessage = this.errorDetail(
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
      || !decision
      || this.revoking
    ) {
      return;
    }

    this.revokeForm.markAllAsTouched();

    if (this.revokeForm.invalid) {
      this.errorMessage =
        'Escribe el motivo de la reversión.';
      return;
    }

    const reason =
      this.revokeForm.controls
        .revocation_reason.value.trim();

    this.revoking = true;
    this.errorMessage = '';

    this.service.revokeNoRoutineDecision(
      this.data.memberId,
      decision.id,
      {
        revocation_reason: reason,
      },
    ).subscribe({
      next: () => {
        this.revoking = false;
        this.dialogRef.close(true);
      },
      error: (error: HttpErrorResponse) => {
        this.revoking = false;
        this.errorMessage = this.errorDetail(
          error,
          'No fue posible revertir la decisión.',
        );
      },
    });
  }

  private loadDetail(): void {
    this.loading = true;
    this.errorMessage = '';

    this.service
      .getMemberDetail(this.data.memberId)
      .subscribe({
        next: (detail) => {
          this.detail = detail;
          this.loading = false;
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.errorMessage = this.errorDetail(
            error,
            'No fue posible consultar al socio.',
          );
        },
      });
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
