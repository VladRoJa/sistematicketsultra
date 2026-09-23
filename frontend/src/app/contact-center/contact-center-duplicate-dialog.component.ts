import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { ContactCenterContact } from './contact-center.models';
import { ContactCenterService } from './contact-center.service';


export interface ContactCenterDuplicateDialogData {
  baseContact: ContactCenterContact;
  candidates: ContactCenterContact[];
  canMerge: boolean;
}


type ContactSide = 'BASE' | 'CANDIDATE';


@Component({
  selector: 'app-contact-center-duplicate-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './contact-center-duplicate-dialog.component.html',
  styleUrls: ['./contact-center-duplicate-dialog.component.css'],
})
export class ContactCenterDuplicateDialogComponent {
  selectedCandidateId: number | null;
  survivorSide: ContactSide = 'BASE';
  nameSource: ContactSide = 'BASE';
  phoneSource: ContactSide = 'BASE';
  emailSource: ContactSide = 'BASE';
  branchSource: ContactSide = 'BASE';

  merging = false;
  errorMessage = '';

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public readonly data: ContactCenterDuplicateDialogData,
    private readonly dialogRef: MatDialogRef<ContactCenterDuplicateDialogComponent>,
    private readonly contactCenter: ContactCenterService,
  ) {
    this.selectedCandidateId = data.candidates[0]?.id ?? null;
    this.applySmartDefaults();
  }

  get candidate(): ContactCenterContact | null {
    return (
      this.data.candidates.find(
        (row) => row.id === this.selectedCandidateId,
      ) ?? null
    );
  }

  selectCandidate(contactId: number): void {
    this.selectedCandidateId = contactId;
    this.applySmartDefaults();
  }

  openCandidate(): void {
    const candidate = this.candidate;
    if (!candidate) {
      return;
    }

    this.dialogRef.close({
      contactId: candidate.id,
      merged: false,
    });
  }

  merge(): void {
    const candidate = this.candidate;
    if (!candidate || !this.data.canMerge) {
      return;
    }

    const base = this.data.baseContact;
    const survivor =
      this.survivorSide === 'BASE' ? base : candidate;
    const merged =
      this.survivorSide === 'BASE' ? candidate : base;

    this.merging = true;
    this.errorMessage = '';

    this.contactCenter.mergeContacts({
      survivor_contact_id: survivor.id,
      merged_contact_id: merged.id,
      field_resolution: {
        display_name: this.valueFrom(
          this.nameSource,
          base.display_name,
          candidate.display_name,
        ),
        primary_phone_raw: this.valueFrom(
          this.phoneSource,
          base.primary_phone_raw,
          candidate.primary_phone_raw,
        ),
        email: this.valueFrom(
          this.emailSource,
          base.email,
          candidate.email,
        ),
        preferred_sucursal_id: this.valueFrom(
          this.branchSource,
          base.preferred_sucursal?.id ?? null,
          candidate.preferred_sucursal?.id ?? null,
        ),
      },
    }).subscribe({
      next: () => {
        this.merging = false;
        this.dialogRef.close({
          contactId: survivor.id,
          merged: true,
        });
      },
      error: (error) => {
        this.merging = false;
        this.errorMessage =
          error?.error?.mensaje || 'No se pudieron fusionar los contactos.';
      },
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  contactName(contact: ContactCenterContact | null): string {
    return contact?.display_name || 'Sin nombre';
  }

  contactPhone(contact: ContactCenterContact | null): string {
    return (
      contact?.phone_mx10
      || contact?.primary_phone_raw
      || 'Sin teléfono'
    );
  }

  contactEmail(contact: ContactCenterContact | null): string {
    return contact?.email || 'Sin correo';
  }

  contactBranch(contact: ContactCenterContact | null): string {
    return contact?.preferred_sucursal?.name || 'Sin sucursal';
  }

  private applySmartDefaults(): void {
    const candidate = this.candidate;
    const base = this.data.baseContact;

    this.nameSource =
      !base.display_name && candidate?.display_name ? 'CANDIDATE' : 'BASE';
    this.phoneSource =
      !base.primary_phone_raw && candidate?.primary_phone_raw
        ? 'CANDIDATE'
        : 'BASE';
    this.emailSource =
      !base.email && candidate?.email ? 'CANDIDATE' : 'BASE';
    this.branchSource =
      !base.preferred_sucursal && candidate?.preferred_sucursal
        ? 'CANDIDATE'
        : 'BASE';
  }

  private valueFrom<T>(
    side: ContactSide,
    baseValue: T,
    candidateValue: T,
  ): T {
    return side === 'BASE' ? baseValue : candidateValue;
  }
}
