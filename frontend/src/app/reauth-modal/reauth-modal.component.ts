// frontend/src/app/reauth-modal/reauth-modal.component.ts

import { Component, Inject, OnDestroy, Renderer2 } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { MatDialogRef } from '@angular/material/dialog';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-reauth-modal',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './reauth-modal.component.html',
  styleUrls: ['./reauth-modal.component.css'],
})
export class ReauthModalComponent implements OnDestroy {
  form: FormGroup;
  loading = false;
  errorMessage = '';
  hidePassword = true;

  constructor(
    private dialogRef: MatDialogRef<ReauthModalComponent>,
    private fb: FormBuilder,
    private authService: AuthService,
    private renderer: Renderer2,
    @Inject(DOCUMENT) private document: Document,
  ) {
    this.renderer.addClass(
      this.document.body,
      'suite-reauth-active',
    );
    this.form = this.fb.group({
      username: [this.getStoredUsername(), Validators.required],
      password: ['', Validators.required],
    });
  }

  ngOnDestroy(): void {
    this.renderer.removeClass(
      this.document.body,
      'suite-reauth-active',
    );
  }

  reauthenticate(): void {
    if (this.form.invalid || this.loading) {
      this.form.markAllAsTouched();
      return;
    }

    const { username, password } = this.form.value;

    this.loading = true;
    this.errorMessage = '';

    this.authService.login(username, password).subscribe({
      next: (resp) => {
        this.loading = false;

        if (!resp?.token) {
          this.errorMessage = 'No se pudo renovar la sesión. Intenta nuevamente.';
          return;
        }

        localStorage.setItem('token', resp.token);

        if (resp.user) {
          localStorage.setItem('user', JSON.stringify(resp.user));
        }

        this.dialogRef.close({
          success: true,
          token: resp.token,
          user: resp.user,
        });
      },
      error: (err) => {
        this.loading = false;
        this.errorMessage =
          err?.error?.mensaje ||
          err?.error?.message ||
          'Usuario o contraseña incorrectos. Intenta nuevamente.';
      },
    });
  }

  cancel(): void {
    this.dialogRef.close({
      success: false,
      cancelled: true,
    });
  }

  private getStoredUsername(): string {
    try {
      const rawUser = localStorage.getItem('user');

      if (!rawUser) {
        return '';
      }

      const user = JSON.parse(rawUser);

      return (
        user?.username ||
        user?.usuario ||
        user?.nombre_usuario ||
        ''
      );
    } catch {
      return '';
    }
  }
}