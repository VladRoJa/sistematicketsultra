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

import {
  ContactCenterBranch,
  ContactCenterContact,
  ContactCenterSource,
  ContactCenterUserRef,
} from './contact-center.models';
import { ContactCenterService } from './contact-center.service';


export interface ContactCenterNewContactDialogData {
  branches: ContactCenterBranch[];
  agents: ContactCenterUserRef[];
  isSupervisor: boolean;
  currentUserId: number;
}


@Component({
  selector: 'app-contact-center-new-contact-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './contact-center-new-contact-dialog.component.html',
  styleUrls: ['./contact-center-new-contact-dialog.component.css'],
})
export class ContactCenterNewContactDialogComponent {
  name = '';
  phone = '';
  email = '';
  sourceType: ContactCenterSource = 'MANUAL';
  sucursalId: number | null = null;
  assignedUserId: number | null;
  comment = '';

  saving = false;
  errorMessage = '';
  duplicates: ContactCenterContact[] = [];

  readonly sources: Array<{ value: ContactCenterSource; label: string }> = [
    { value: 'MANUAL', label: 'Manual' },
    { value: 'MESSAGE', label: 'Mensaje' },
    { value: 'REACTIVATION', label: 'Reactivación' },
    { value: 'CAMPAIGN', label: 'Campaña' },
    { value: 'CRM', label: 'CRM' },
  ];

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public readonly data: ContactCenterNewContactDialogData,
    private readonly dialogRef: MatDialogRef<ContactCenterNewContactDialogComponent>,
    private readonly contactCenter: ContactCenterService,
  ) {
    this.assignedUserId = data.currentUserId;
  }

  save(): void {
    this.errorMessage = '';
    this.duplicates = [];

    const phone = this.phone.trim();
    if (!phone) {
      this.errorMessage = 'Captura un teléfono.';
      return;
    }

    this.saving = true;
    this.contactCenter.createContact({
      name: this.name.trim() || null,
      phone,
      email: this.email.trim() || null,
      sucursal_id: this.sucursalId,
      source_type: this.sourceType,
      comment: this.comment.trim() || null,
      assigned_user_id: this.assignedUserId,
    }).subscribe({
      next: (response) => {
        this.saving = false;
        this.dialogRef.close({
          contactId: response.contact.id,
          created: true,
        });
      },
      error: (error) => {
        this.saving = false;
        const duplicates = error?.error?.duplicates;
        if (error?.status === 409 && Array.isArray(duplicates)) {
          this.duplicates = duplicates;
          this.errorMessage =
            'Ese teléfono o correo ya existe. Abre el contacto existente para evitar duplicarlo.';
          return;
        }

        this.errorMessage =
          error?.error?.mensaje || 'No se pudo crear el contacto.';
      },
    });
  }

  openExisting(contact: ContactCenterContact): void {
    this.dialogRef.close({
      contactId: contact.id,
      created: false,
    });
  }

  cancel(): void {
    this.dialogRef.close();
  }

  branchName(contact: ContactCenterContact): string {
    return contact.preferred_sucursal?.name || 'Sin sucursal';
  }
}
