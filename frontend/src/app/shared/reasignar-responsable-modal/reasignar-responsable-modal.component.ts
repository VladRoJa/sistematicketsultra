import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { isModalSubmitDisabled } from '../modal-submit-state';
import {
  MaintenanceAssignee,
  MaintenanceAttentionMode,
  ReassignMaintenanceTicketPayload,
} from '../../services/maintenance-coordination.service';

interface TicketConResponsable {
  asignado_a?: string | null;
  tipo_atencion?: MaintenanceAttentionMode | null;
}

@Component({
  selector: 'app-reasignar-responsable-modal',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  templateUrl: './reasignar-responsable-modal.component.html',
  styleUrls: ['./reasignar-responsable-modal.component.css'],
})
export class ReasignarResponsableModalComponent implements OnInit {
  @Input() ticket: TicketConResponsable | null = null;
  @Input() responsables: MaintenanceAssignee[] = [];
  @Input() guardando = false;
  @Input() permitirAutogestionMantenimiento = false;

  @Output() onGuardar = new EventEmitter<ReassignMaintenanceTicketPayload>();
  @Output() onCancelar = new EventEmitter<void>();

  tipoAtencion: MaintenanceAttentionMode | null = null;
  responsableUserId: number | null = null;
  motivo = '';

  ngOnInit(): void {
    const actual = String(this.ticket?.asignado_a || '').trim().toUpperCase();
    this.tipoAtencion = this.ticket?.tipo_atencion ?? (actual ? 'INTERNA' : null);

    if (this.tipoAtencion === 'INTERNA') {
      this.responsableUserId =
        this.responsables.find(
          (person) => person.username.trim().toUpperCase() === actual,
        )?.id ?? null;
    }
  }

  get responsableActual(): string {
    if (this.ticket?.tipo_atencion === 'EXTERNA') return 'Proveedor externo';
    return String(this.ticket?.asignado_a || '').trim() || 'Sin asignar';
  }

  get mismoResponsable(): boolean {
    const actual = String(this.ticket?.asignado_a || '').trim().toUpperCase();
    const modoActual = this.ticket?.tipo_atencion ?? (actual ? 'INTERNA' : null);
    if (modoActual !== this.tipoAtencion) return false;
    if (this.tipoAtencion === 'EXTERNA' || this.tipoAtencion === 'AUTOGESTION') return true;
    const seleccionado = this.responsables.find(
      (person) => person.id === this.responsableUserId,
    );
    return !!seleccionado && seleccionado.username.trim().toUpperCase() === actual;
  }

  get guardarDeshabilitado(): boolean {
    return isModalSubmitDisabled({
      requiredText: [this.motivo],
      requiredSelections: [
        this.tipoAtencion,
        ...(this.tipoAtencion === 'INTERNA' ? [this.responsableUserId] : []),
      ],
      blocked: this.guardando || this.motivo.trim().length > 500 || this.mismoResponsable,
    });
  }

  onTipoAtencionChange(): void {
    this.responsableUserId = null;
  }

  guardar(): void {
    if (this.guardarDeshabilitado || !this.tipoAtencion) return;
    this.onGuardar.emit({
      tipo_atencion: this.tipoAtencion,
      asignado_user_id: this.tipoAtencion === 'INTERNA' ? this.responsableUserId : null,
      motivo: this.motivo.trim(),
    });
  }

  cancelar(): void {
    if (!this.guardando) this.onCancelar.emit();
  }
}
