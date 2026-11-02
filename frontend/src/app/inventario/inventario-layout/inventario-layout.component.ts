import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InventarioService } from '../../services/inventario.service';
import { SessionService } from '../../core/auth/session.service';
import { RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-inventario-layout',
  standalone: true,
  templateUrl: './inventario-layout.component.html',
  styleUrls: ['./inventario-layout.component.css'],
  imports: [
    CommonModule,
    RouterModule,
    MatIconModule,
  ],
})
export class InventarioLayoutComponent implements OnInit {
  puedeRevisarE3 = false;
  puedeGestionarE4 = false;
  esCoordinadorE3 = false;

  constructor(
    private readonly inventario: InventarioService,
    private readonly sesion: SessionService,
  ) {}

  ngOnInit(): void {
    // El frontend orienta; todos los endpoints E4 autorizan contra rol REAL en DB.
    this.puedeGestionarE4 = ['ADMIN', 'ADMINISTRADOR', 'SUPER_ADMIN'].includes(
      String(this.sesion.getUser()?.rol || '').trim().toUpperCase()
    );
    this.esCoordinadorE3 = String(this.sesion.getUser()?.rol || '')
      .trim().toUpperCase() === 'COORDINADOR_MANTENIMIENTO';
    this.inventario.contextoRevisionCorrecciones().subscribe({
      next: contexto => {
        this.puedeRevisarE3 = contexto.can_review;
      },
      error: () => { this.puedeRevisarE3 = false; },
    });
  }
}
