import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { forkJoin } from 'rxjs';

import {
  PurchaseRequisitionAccess,
  PurchaseRequisitionAccessService,
} from './purchase-requisition-access.service';
import {
  PurchaseRequisition,
  PurchaseRequisitionService,
} from './purchase-requisition.service';
import {
  PurchaseRequisitionFormDialogComponent,
  PurchaseRequisitionBranchOption,
} from './purchase-requisition-form-dialog.component';
import { PurchaseRequisitionDetailDialogComponent } from './purchase-requisition-detail-dialog.component';
import {
  PurchaseRequisitionFinanceApproversDialogComponent,
} from './purchase-requisition-finance-approvers-dialog.component';
import { exportPurchaseRequisitionsWorkbook } from './purchase-requisition-export';

interface BranchOption {
  id: number;
  name: string;
}

@Component({
  selector: 'app-purchase-requisitions',
  standalone: true,
  templateUrl: './purchase-requisitions.component.html',
  styleUrls: ['./purchase-requisitions.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatDialogModule,
  ],
})
export class PurchaseRequisitionsComponent implements OnInit {
  access: PurchaseRequisitionAccess | null = null;
  rows: PurchaseRequisition[] = [];
  branches: BranchOption[] = [];
  branchCatalog: BranchOption[] = [];
  createBranches: BranchOption[] = [];

  loading = true;
  loadError = false;
  exportingExcel = false;
  exportError = '';

  statusFilter = '';
  priorityFilter = '';
  branchFilter: number | null = null;

  readonly statuses = [
    { value: 'PENDING_REVIEW', label: 'Pendiente de revisión' },
    { value: 'NEEDS_INFO', label: 'Requiere información' },
    { value: 'IN_QUOTATION', label: 'En cotización' },
    {
      value: 'QUOTE_PENDING_FINANCE_APPROVAL',
      label: 'Pendiente de aprobación financiera',
    },
    { value: 'PAYMENT_REQUESTED', label: 'En solicitud de pago' },
    { value: 'SHIPPING_IN_PROGRESS', label: 'En proceso de envío' },
    { value: 'IMPORT_IN_PROGRESS', label: 'En proceso de importación' },
    {
      value: 'FINAL_DESTINATION_SHIPMENT',
      label: 'Envío a destino final',
    },
    { value: 'RECEIPT_ISSUE', label: 'Incidencia de recepción' },
    { value: 'REJECTED', label: 'Rechazada' },
    { value: 'CLOSED', label: 'Cerrada' },
  ];

  readonly priorities = [
    { value: 'NORMAL', label: 'Normal' },
    { value: 'HIGH', label: 'Alta' },
    { value: 'CRITICAL', label: 'Crítica' },
  ];

  constructor(
    private readonly accessService: PurchaseRequisitionAccessService,
    private readonly requisitionService: PurchaseRequisitionService,
    private readonly dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.accessService.getAccess().subscribe({
      next: (access) => {
        this.access = access;
        this.loadBranches();
        this.loadRows();
      },
      error: () => {
        this.loadError = true;
        this.loading = false;
      },
    });
  }

  loadRows(): void {
    this.loading = true;
    this.loadError = false;

    this.requisitionService.list({
      status: this.statusFilter || undefined,
      priority: this.priorityFilter || undefined,
      sucursal_id: this.branchFilter,
    }).subscribe({
      next: (response) => {
        this.rows = response.rows || [];
        this.loading = false;
      },
      error: () => {
        this.rows = [];
        this.loadError = true;
        this.loading = false;
      },
    });
  }

  get canOpenCreate(): boolean {
    return Boolean(this.access?.can_create && this.createBranches.length > 0);
  }

  get canConfigureFinanceApprovers(): boolean {
    return Boolean(this.access?.can_configure_finance_approvers);
  }

  openFinanceApproversConfig(): void {
    if (!this.canConfigureFinanceApprovers) {
      return;
    }

    this.dialog.open(PurchaseRequisitionFinanceApproversDialogComponent, {
      width: '820px',
      maxWidth: '96vw',
      autoFocus: false,
      restoreFocus: false,
    });
  }

  exportToExcel(): void {
    if (!this.rows.length || this.exportingExcel) {
      return;
    }

    this.exportingExcel = true;
    this.exportError = '';

    forkJoin(
      this.rows.map(row => this.requisitionService.get(row.id)),
    ).subscribe({
      next: (responses) => {
        const exportRows = responses.map(response => ({
          requisition: response.requisition,
          branchName: this.branchLabel(response.requisition.sucursal_id),
        }));

        void exportPurchaseRequisitionsWorkbook(exportRows)
          .catch(() => {
            this.exportError = 'No fue posible generar el archivo Excel.';
          })
          .finally(() => {
            this.exportingExcel = false;
          });
      },
      error: () => {
        this.exportError = 'No fue posible cargar el detalle completo para exportar.';
        this.exportingExcel = false;
      },
    });
  }

  openCreateDialog(): void {
    if (!this.canOpenCreate) {
      return;
    }

    const dialogRef = this.dialog.open(PurchaseRequisitionFormDialogComponent, {
      width: '860px',
      maxWidth: '96vw',
      autoFocus: false,
      restoreFocus: false,
      data: {
        branches: this.createBranches as PurchaseRequisitionBranchOption[],
      },
    });

    dialogRef.afterClosed().subscribe((created) => {
      if (created) {
        this.loadRows();
      }
    });
  }

  openDetail(row: PurchaseRequisition): void {
    if (!this.access) {
      return;
    }

    const dialogRef = this.dialog.open(PurchaseRequisitionDetailDialogComponent, {
      width: '960px',
      maxWidth: '97vw',
      autoFocus: false,
      restoreFocus: false,
      data: {
        requisitionId: row.id,
        access: this.access,
        branches: this.branchCatalog as PurchaseRequisitionBranchOption[],
      },
    });

    dialogRef.afterClosed().subscribe((changed) => {
      if (changed) {
        this.loadRows();
      }
    });
  }

  clearFilters(): void {
    this.statusFilter = '';
    this.priorityFilter = '';
    this.branchFilter = null;
    this.loadRows();
  }

  statusLabel(status: string): string {
    return this.statuses.find(option => option.value === status)?.label || status;
  }

  priorityLabel(priority: string): string {
    return this.priorities.find(option => option.value === priority)?.label || priority;
  }

  reasonLabel(reason: string): string {
    const labels: Record<string, string> = {
      REPLACEMENT: 'Reemplazo',
      NEW_EQUIPMENT: 'Equipo nuevo',
      DAMAGE: 'Daño',
      EXPANSION: 'Expansión',
      OTHER: 'Otro',
    };
    return labels[reason] || reason;
  }

  branchLabel(branchId: number): string {
    return this.branchCatalog.find(branch => branch.id === branchId)?.name
      || `Sucursal #${branchId}`;
  }

  statusClass(status: string): string {
    return `status-pill status-${String(status || '').toLowerCase()}`;
  }

  trackById(_index: number, row: PurchaseRequisition): number {
    return row.id;
  }

  private loadBranches(): void {
    this.requisitionService.listBranches().subscribe({
      next: (rows: any[]) => {
        const role = String(this.access?.user?.role || '').trim().toUpperCase();
        const allowed = new Set(this.access?.allowed_branch_ids || []);
        const allBranches = (rows || [])
          .map((row: any) => ({
            id: Number(row?.sucursal_id ?? row?.id),
            name: String(
              row?.nombre
              ?? row?.nombre_sucursal
              ?? row?.sucursal
              ?? `Sucursal #${row?.sucursal_id ?? row?.id}`
            ),
          }))
          .filter(branch => Number.isFinite(branch.id) && branch.id > 0)
          .sort((a, b) => a.name.localeCompare(b.name, 'es'));

        this.branchCatalog = allBranches;

        const canSeeAllBranches = Boolean(
          this.access?.global_read || role === 'ADMINISTRADOR',
        );

        this.branches = canSeeAllBranches
          ? allBranches
          : allBranches.filter(branch => allowed.has(branch.id));

        this.createBranches = role === 'ADMINISTRADOR'
          ? allBranches
          : allBranches.filter(branch => allowed.has(branch.id));
      },
      error: () => {
        const fallback = (this.access?.allowed_branch_ids || []).map(id => ({
          id,
          name: `Sucursal #${id}`,
        }));
        this.branchCatalog = fallback;
        this.branches = fallback;
        this.createBranches = fallback;
      },
    });
  }
}
