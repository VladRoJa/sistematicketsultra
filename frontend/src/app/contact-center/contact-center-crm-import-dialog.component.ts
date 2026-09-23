import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  ContactCenterCrmCandidate,
} from './contact-center.models';


export interface ContactCenterCrmImportDialogData {
  candidate: ContactCenterCrmCandidate;
}


@Component({
  selector: 'app-contact-center-crm-import-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: './contact-center-crm-import-dialog.component.html',
  styleUrls: ['./contact-center-crm-import-dialog.component.css'],
})
export class ContactCenterCrmImportDialogComponent {
  displayName: string;

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public readonly data: ContactCenterCrmImportDialogData,
    private readonly dialogRef: MatDialogRef<ContactCenterCrmImportDialogComponent>,
  ) {
    this.displayName = String(data.candidate.name || '').trim();
  }

  save(): void {
    const displayName = this.displayName.trim();
    if (!displayName) {
      return;
    }

    this.dialogRef.close({
      displayName,
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  canSave(): boolean {
    return Boolean(this.displayName.trim());
  }
}
