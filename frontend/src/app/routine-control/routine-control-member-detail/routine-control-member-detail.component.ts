import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { RoutineControlMemberDetail } from '../models/routine-control.models';
import { RoutineControlService } from '../services/routine-control.service';

@Component({
  selector: 'app-routine-control-member-detail', standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  templateUrl: './routine-control-member-detail.component.html',
  styleUrls: ['./routine-control-member-detail.component.css'],
})
export class RoutineControlMemberDetailComponent implements OnInit {
  detail: RoutineControlMemberDetail | null = null;
  loading = true;
  errorMessage = '';
  constructor(private readonly route: ActivatedRoute, private readonly router: Router, private readonly service: RoutineControlService) {}
  ngOnInit(): void {
    const memberId = Number(this.route.snapshot.paramMap.get('memberId'));
    if (!Number.isInteger(memberId)) { this.loading = false; this.errorMessage = 'Identificador de socio inválido.'; return; }
    this.service.getMemberDetail(memberId).subscribe({
      next: (detail) => { this.detail = detail; this.loading = false; },
      error: () => { this.loading = false; this.errorMessage = 'No fue posible consultar el detalle del socio.'; },
    });
  }
  back(): void { this.router.navigate(['/control-rutinas']); }
  statusLabel(): string { return this.detail?.member.classification_status === 'INCIDENT' ? 'Incidencia' : (this.detail?.member.current_status || 'Sin estado').replace(/_/g, ' '); }
}
