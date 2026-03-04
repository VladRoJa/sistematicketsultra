// src/app/pm/pm-escritorio-preventivo/pm-registrar-preventivo-modal.component.ts

import { Component, inject, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import {
    MAT_DIALOG_DATA,
    MatDialogModule,
    MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { PmPreventivoService } from '../../services/pm-preventivo.service';
import { RegistrarPmPayload, EquipoEstado } from '../../models/pm-preventivo.model';

@Component({
    selector: 'app-pm-registrar-preventivo-modal',
    standalone: true,
    imports: [
        CommonModule,
        ReactiveFormsModule,
        MatDialogModule,
        MatFormFieldModule,
        MatInputModule,
        MatSelectModule,
        MatCheckboxModule,
        MatButtonModule,
        MatDatepickerModule,
        MatNativeDateModule,
        MatSnackBarModule,
        MatProgressSpinnerModule,
    ],
    templateUrl: './pm-registrar-preventivo-modal.component.html',
    styleUrls: ['./pm-registrar-preventivo-modal.component.css'],
})
export class PmRegistrarPreventivoModalComponent {
    private fb = inject(FormBuilder);
    private pmService = inject(PmPreventivoService);
    private snack = inject(MatSnackBar);

    saving = false;

    /** Opciones de resultado para el select. */
    readonly resultadoOptions = [
        { value: 'OK', label: 'OK' },
        { value: 'FALLA', label: 'Falla' },
        { value: 'OBS', label: 'Observación' },
    ];

    /** Label descriptivo del equipo para mostrar en el header del modal. */
    equipoLabel: string;

    form = this.fb.group({
        fecha: [new Date(), [Validators.required]],
        resultado: ['OK' as 'OK' | 'FALLA' | 'OBS', [Validators.required]],
        notas: [''],
        check_limpieza: [true],
        check_ajustes: [false],
        check_ruidos: [false],
    });

    constructor(
        private dialogRef: MatDialogRef<PmRegistrarPreventivoModalComponent>,
        @Inject(MAT_DIALOG_DATA) public data: EquipoEstado,
    ) {
        this.equipoLabel = `${data.codigo_interno || ''} — ${data.nombre || ''}`.trim();
    }

    /** Indica si el botón Guardar está deshabilitado. */
    get guardarDisabled(): boolean {
        return this.form.invalid || this.saving;
    }

    guardar(): void {
        if (this.guardarDisabled) {
            return;
        }

        const v = this.form.getRawValue();
        const fechaStr = this.formatDate(v.fecha!);

        const payload: RegistrarPmPayload = {
            inventario_id: this.data.inventario_id,
            sucursal_id: this.data.sucursal_id,
            fecha: fechaStr,
            resultado: v.resultado!,
            notas: v.notas || '',
            checks: {
                limpieza: !!v.check_limpieza,
                ajustes: !!v.check_ajustes,
                ruidos: !!v.check_ruidos,
            },
        };

        this.saving = true;
        this.pmService.registrarPreventivo(payload).subscribe({
            next: (res) => {
                this.saving = false;
                this.snack.open(res?.msg || 'Registrado correctamente', 'OK', { duration: 2500 });
                this.dialogRef.close(true); // true = refresh dashboard
            },
            error: (err) => {
                this.saving = false;
                const msg = err?.error?.detail || err?.error?.message || 'Error al registrar';
                this.snack.open(msg, 'OK', { duration: 3500 });
            },
        });
    }

    cancelar(): void {
        this.dialogRef.close(false);
    }

    /** Formatea un Date a YYYY-MM-DD. */
    private formatDate(d: Date): string {
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    }
}
