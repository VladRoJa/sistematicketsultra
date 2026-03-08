// src/app/pm/pm-escritorio-preventivo/pm-escritorio-preventivo.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, FormControl, ReactiveFormsModule  } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { Observable } from 'rxjs';
import { map, startWith } from 'rxjs/operators';

import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';

import { PmPreventivoService } from '../../services/pm-preventivo.service';
import { EquipoEstado, SucursalOption,} from '../../models/pm-preventivo.model';
import { Router } from '@angular/router';

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
        MatChipsModule,
        MatTooltipModule,
        ReactiveFormsModule,
        MatAutocompleteModule,
    ],
    templateUrl: './pm-escritorio-preventivo.component.html',
    styleUrls: ['./pm-escritorio-preventivo.component.css'],
})
export class PmEscritorioPreventComponent implements OnInit {
    private pmService = inject(PmPreventivoService);
    private snack = inject(MatSnackBar);
    private router = inject(Router);

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
    sucursalCtrl = new FormControl<string | SucursalOption>('');
    filteredSucursales$!: Observable<SucursalOption[]>;

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
            this.filteredSucursales$ = this.sucursalCtrl.valueChanges.pipe(
        startWith(''),
        map((value) => {
            const term = (typeof value === 'string' ? value : value?.sucursal || '')
                .toLowerCase()
                .trim();

            if (!term) {
                return this.sucursalesList;
            }

            return this.sucursalesList.filter((s) =>
                s.sucursal.toLowerCase().includes(term)
            );
        })
    );
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


    // ── Callback cuando cambia la sucursal ──
    onSucursalChange(): void {
        this.limpiarDatos();
        if (this.selectedSucursalId) {
            this.cargarDashboard();
        }
    }


    
    onSucursalSelected(sucursal: SucursalOption): void {
        this.selectedSucursalId = sucursal.sucursal_id;
        this.sucursalCtrl.setValue(sucursal, { emitEvent: false });
        this.onSucursalChange();
    }

    /** Limpia las 3 listas. */
    private limpiarDatos(): void {
        this.atrasados = [];
        this.hoyList = [];
        this.proximos = [];
    }
    
    

    sucursalDisplay(value: SucursalOption | string | null): string {
        if (!value) return '';
        return typeof value === 'string' ? value : value.sucursal;
    }

    /** Navega a bitácora móvil con parámetros para autoseleccionar equipo. */

    irABitacoraPreventiva(equipo: EquipoEstado): void {
    this.router.navigate(['/pm/bitacoras-mobile'], {
        queryParams: {
            sucursalId: equipo.sucursal_id,
            inventarioId: equipo.inventario_id,
            modo: 'preventivo',
        },
    });
}
}
