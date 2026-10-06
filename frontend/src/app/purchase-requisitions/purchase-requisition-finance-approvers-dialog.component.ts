import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { finalize, forkJoin } from 'rxjs';

import {
  UsuarioAdminOption,
  UsuarioService,
} from '../services/usuario.service';
import {
  PurchaseRequisitionFinanceApprover,
  PurchaseRequisitionService,
} from './purchase-requisition.service';

@Component({
  selector: 'app-purchase-requisition-finance-approvers-dialog',
  standalone: true,
  templateUrl: './purchase-requisition-finance-approvers-dialog.component.html',
  styleUrls: ['./purchase-requisition-finance-approvers-dialog.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
})
export class PurchaseRequisitionFinanceApproversDialogComponent
implements OnInit {
  approvers: PurchaseRequisitionFinanceApprover[] = [];
  users: UsuarioAdminOption[] = [];

  loading = true;
  loadError = '';
  actionError = '';
  actionBusy = false;

  userSearch = '';
  selectedUserId: number | null = null;
  notes = '';

  editingNotesUserId: number | null = null;
  editingNotesValue = '';

  constructor(
    private readonly requisitionService: PurchaseRequisitionService,
    private readonly usuarioService: UsuarioService,
    private readonly dialogRef: MatDialogRef<
      PurchaseRequisitionFinanceApproversDialogComponent
    >,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  get activeCount(): number {
    return this.approvers.filter(row => row.is_active).length;
  }

  get selectedUser(): UsuarioAdminOption | null {
    if (!this.selectedUserId) {
      return null;
    }
    return this.users.find(user => user.id === this.selectedUserId) || null;
  }

  get filteredUsers(): UsuarioAdminOption[] {
    const search = this.normalize(this.userSearch);
    if (search.length < 2) {
      return [];
    }

    const activeIds = new Set(
      this.approvers
        .filter(row => row.is_active)
        .map(row => row.user_id),
    );

    return this.users
      .filter(user => !activeIds.has(user.id))
      .filter(user => {
        const haystack = this.normalize([
          user.id,
          user.username,
          user.email || '',
          user.rol,
        ].join(' '));
        return haystack.includes(search);
      })
      .slice(0, 20);
  }

  get selectedUserIsInactiveApprover(): boolean {
    return Boolean(
      this.selectedUserId
      && this.approvers.some(
        row => row.user_id === this.selectedUserId && !row.is_active,
      ),
    );
  }

  get addButtonLabel(): string {
    return this.selectedUserIsInactiveApprover
      ? 'Reactivar aprobador'
      : 'Agregar aprobador';
  }

  load(): void {
    this.loading = true;
    this.loadError = '';
    this.actionError = '';

    forkJoin({
      approvers: this.requisitionService.listFinanceApprovers(),
      users: this.usuarioService.listarUsuariosAdmin(),
    }).subscribe({
      next: ({ approvers, users }) => {
        this.approvers = approvers.rows || [];
        this.users = users || [];
        this.loading = false;
      },
      error: (error) => {
        this.loadError = String(
          error?.error?.mensaje
          || 'No fue posible cargar la configuración financiera.',
        );
        this.loading = false;
      },
    });
  }

  chooseUser(user: UsuarioAdminOption): void {
    this.selectedUserId = user.id;
    this.userSearch = user.username;
    this.actionError = '';
  }

  clearSelectedUser(): void {
    this.selectedUserId = null;
    this.userSearch = '';
    this.notes = '';
    this.actionError = '';
  }

  addSelectedApprover(): void {
    if (!this.selectedUserId || this.actionBusy) {
      return;
    }

    const userId = this.selectedUserId;
    const notes = this.notes.trim();
    const existing = this.approvers.find(row => row.user_id === userId);

    this.actionBusy = true;
    this.actionError = '';

    const request$ = existing
      ? this.requisitionService.updateFinanceApprover(userId, {
          is_active: true,
          notes: notes || existing.notes || null,
        })
      : this.requisitionService.createFinanceApprover({
          user_id: userId,
          notes: notes || null,
        });

    request$
      .pipe(finalize(() => {
        this.actionBusy = false;
      }))
      .subscribe({
        next: () => {
          this.clearSelectedUser();
          this.reloadApprovers();
        },
        error: (error) => {
          this.actionError = String(
            error?.error?.mensaje
            || 'No fue posible actualizar el aprobador financiero.',
          );
        },
      });
  }

  toggleApprover(row: PurchaseRequisitionFinanceApprover): void {
    if (this.actionBusy) {
      return;
    }

    this.actionBusy = true;
    this.actionError = '';

    this.requisitionService.updateFinanceApprover(row.user_id, {
      is_active: !row.is_active,
    })
      .pipe(finalize(() => {
        this.actionBusy = false;
      }))
      .subscribe({
        next: () => {
          this.reloadApprovers();
        },
        error: (error) => {
          this.actionError = String(
            error?.error?.mensaje
            || 'No fue posible cambiar el estado del aprobador.',
          );
        },
      });
  }

  startEditNotes(row: PurchaseRequisitionFinanceApprover): void {
    if (this.actionBusy) {
      return;
    }
    this.editingNotesUserId = row.user_id;
    this.editingNotesValue = row.notes || '';
    this.actionError = '';
  }

  cancelEditNotes(): void {
    this.editingNotesUserId = null;
    this.editingNotesValue = '';
    this.actionError = '';
  }

  saveApproverNotes(row: PurchaseRequisitionFinanceApprover): void {
    if (
      this.actionBusy
      || this.editingNotesUserId !== row.user_id
    ) {
      return;
    }

    this.actionBusy = true;
    this.actionError = '';

    this.requisitionService.updateFinanceApprover(row.user_id, {
      notes: this.editingNotesValue.trim() || null,
    })
      .pipe(finalize(() => {
        this.actionBusy = false;
      }))
      .subscribe({
        next: () => {
          this.cancelEditNotes();
          this.reloadApprovers();
        },
        error: (error) => {
          this.actionError = String(
            error?.error?.mensaje
            || 'No fue posible actualizar la nota del aprobador.',
          );
        },
      });
  }

  isEditingNotes(row: PurchaseRequisitionFinanceApprover): boolean {
    return this.editingNotesUserId === row.user_id;
  }

  close(): void {
    this.dialogRef.close();
  }

  trackByApprover(
    _index: number,
    row: PurchaseRequisitionFinanceApprover,
  ): number {
    return row.user_id;
  }

  trackByUser(_index: number, user: UsuarioAdminOption): number {
    return user.id;
  }

  userSecondaryLabel(user: UsuarioAdminOption): string {
    const parts = [
      user.rol,
      user.email || '',
      `ID ${user.id}`,
    ].filter(Boolean);
    return parts.join(' · ');
  }

  approverSecondaryLabel(
    row: PurchaseRequisitionFinanceApprover,
  ): string {
    const user = row.user;
    const parts = [
      user?.role || '',
      user?.email || '',
      `ID ${row.user_id}`,
    ].filter(Boolean);
    return parts.join(' · ');
  }

  private reloadApprovers(): void {
    this.requisitionService.listFinanceApprovers().subscribe({
      next: (response) => {
        this.approvers = response.rows || [];
      },
      error: (error) => {
        this.actionError = String(
          error?.error?.mensaje
          || 'No fue posible refrescar los aprobadores.',
        );
      },
    });
  }

  private normalize(value: unknown): string {
    return String(value ?? '')
      .normalize('NFKC')
      .trim()
      .toLocaleUpperCase('es-MX');
  }
}
