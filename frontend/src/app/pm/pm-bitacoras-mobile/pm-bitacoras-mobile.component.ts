// frontend\src\app\pm\pm-bitacoras-mobile\pm-bitacoras-mobile.component.ts

import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { SessionService } from '../../core/auth/session.service';

type ResultadoBitacora = 'OK' | 'FALLA' | 'OBS';

@Component({
  selector: 'app-pm-bitacoras-mobile',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,

    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatSnackBarModule,
  ],
  templateUrl: './pm-bitacoras-mobile.component.html',
  styleUrls: ['./pm-bitacoras-mobile.component.css'],
})
export class PmBitacorasMobileComponent {
  private fb = inject(FormBuilder);
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  private session = inject(SessionService);

  // ✅ Endpoint backend (proxy /api)
  private readonly endpoint = '/api/pm/mobile/bitacoras';

  loading = false;
  lastId: number | null = null;

  // Defaults útiles desde sesión
  private defaultSucursalId(): number | null {
    const user = this.session.getUser();
    const s = user?.sucursal_id;
    return typeof s === 'number' ? s : (s ? Number(s) : null);
  }

  form = this.fb.group({
    inventario_id: [null as number | null, [Validators.required]],
    sucursal_id: [this.defaultSucursalId(), [Validators.required]],
    fecha: [this.todayYYYYMMDD(), [Validators.required]],
    resultado: ['OK' as ResultadoBitacora, [Validators.required]],
    notas: [''],

    // MVP checks (puedes cambiarlos luego por checklist real)
    check_limpieza: [true],
    check_ajustes: [false],
    check_ruidos: [false],
  });

  private todayYYYYMMDD(): string {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }

  buildPayload(): any {
    const v = this.form.getRawValue();

    return {
      inventario_id: v.inventario_id,
      sucursal_id: v.sucursal_id,
      fecha: v.fecha,
      resultado: v.resultado,
      notas: v.notas || '',
      checks: {
        limpieza: !!v.check_limpieza,
        ajustes: !!v.check_ajustes,
        ruidos: !!v.check_ruidos,
      },
    };
  }

  async guardar(): Promise<void> {
    this.lastId = null;

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.snack.open('Completa los campos requeridos', 'OK', { duration: 2500 });
      return;
    }

    const payload = this.buildPayload();

    this.loading = true;
    this.http.post<{ id: number; msg: string }>(this.endpoint, payload).subscribe({
      next: (res) => {
        this.loading = false;
        this.lastId = res?.id ?? null;
        this.snack.open(res?.msg || 'Bitácora guardada', 'OK', { duration: 2500 });

        // opcional: limpiar notas, dejar defaults
        this.form.patchValue({ notas: '' });
      },
      error: (err) => {
        this.loading = false;
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'Error al guardar bitácora';
        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
  }
}