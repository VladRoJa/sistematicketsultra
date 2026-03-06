// src/app/pm/pm-escritorio-preventivo/pm-escritorio-preventivo.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatChipsModule } from '@angular/material/chips';

import { PmPreventivoService } from '../../services/pm-preventivo.service';
import {
    EquipoEstado,
    SucursalOption,
} from '../../models/pm-preventivo.model';
import { PmRegistrarPreventivoModalComponent } from './pm-registrar-preventivo-modal.component';

@Component({
    selector: 'app-pm-escritorio-preventivo',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        MatCardModule,
        MatFormFieldModule,
        MatSelectModule,
        MatInputModule,
        MatButtonModule,
        MatTableModule,
        MatIconModule,
        MatSnackBarModule,
        MatProgressSpinnerModule,
        MatDialogModule,
        MatChipsModule,
    ],
    templateUrl: './pm-escritorio-preventivo.component.html',
    styleUrls: ['./pm-escritorio-preventivo.component.css'],
})
export class PmEscritorioPreventComponent implements OnInit {
    private pmService = inject(PmPreventivoService);
    private snack = inject(MatSnackBar);
    private dialog = inject(MatDialog);

    // ── Estado UI ──
    loading = false;
    sucursalesLoading = false;

    // ── Datos ──
    sucursalesList: SucursalOption[] = [];
    selectedSucursalId: number | null = null;
    windowDays = 7;

    atrasados: EquipoEstado[] = [];
    hoyList: EquipoEstado[] = [];
    proximos: EquipoEstado[] = [];

    /** Columnas de las tablas Material. */
    readonly displayedColumns = ['equipo', 'sucursal', 'proximoPm', 'diasRestantes', 'accion'];

    // ── Contadores para los badges ──
    get contadorAtrasados(): number { return this.atrasados.length; }
    get contadorHoy(): number { return this.hoyList.length; }
    get contadorProximos(): number { return this.proximos.length; }

    /** Indica si hay datos en alguna sección. */
    get tieneDatos(): boolean {
        return this.atrasados.length > 0 || this.hoyList.length > 0 || this.proximos.length > 0;
    }

    get mostrarVaciosPorSeccion(): boolean {
        return this.tieneDatos;
    }

    /** Label para equipo en la columna de tabla. */
    equipoLabel(row: EquipoEstado): string {
        return [row.codigo_interno, row.nombre].filter(Boolean).join(' — ');
    }

    ngOnInit(): void {
        this.cargarSucursales();
    }

    // ── Carga de sucursales (filtradas por backend) ──
    private cargarSucursales(): void {
        this.sucursalesLoading = true;
        this.pmService.getSucursalesPermitidas().subscribe({
            next: (rows) => {
                this.sucursalesList = rows || [];
                this.sucursalesLoading = false;

                // Autoseleccionar si solo hay una
                if (this.sucursalesList.length === 1) {
                    this.selectedSucursalId = this.sucursalesList[0].sucursal_id;
                    this.cargarDashboard();
                }
            },
            error: () => {
                this.sucursalesLoading = false;
                this.snack.open('No se pudieron cargar sucursales', 'OK', { duration: 3000 });
            },
        });
    }

    // ── Carga del dashboard ──
    cargarDashboard(): void {
        if (!this.selectedSucursalId) {
            this.snack.open('Selecciona una sucursal', 'OK', { duration: 2000 });
            return;
        }

        this.loading = true;
        this.limpiarDatos();

        this.pmService.getDashboard(this.selectedSucursalId, this.windowDays).subscribe({
            next: (data) => {
                this.atrasados = data.atrasados || [];
                this.hoyList = data.hoy || [];
                this.proximos = data.proximos || [];
                this.loading = false;
            },
            error: (err) => {
                this.loading = false;
                const msg = err?.error?.detail || err?.error?.message || 'Error al cargar dashboard';
                this.snack.open(msg, 'OK', { duration: 3500 });
            },
        });
    }

    // ── Abrir modal de registro ──
    abrirModalRegistrar(equipo: EquipoEstado): void {
        const ref = this.dialog.open(PmRegistrarPreventivoModalComponent, {
            width: '480px',
            data: equipo,
            disableClose: true,
        });

        ref.afterClosed().subscribe((registrado: boolean) => {
            if (registrado) {
                this.cargarDashboard();
            }
        });
    }

    // ── Callback cuando cambia la sucursal ──
    onSucursalChange(): void {
        this.limpiarDatos();
        if (this.selectedSucursalId) {
            this.cargarDashboard();
        }
    }

    /** Limpia las 3 listas. */
    private limpiarDatos(): void {
        this.atrasados = [];
        this.hoyList = [];
        this.proximos = [];
    }
}
