//reauth-modal.component.ts

import { Component } from '@angular/core';
import { MatDialogRef } from '@angular/material/dialog';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-reauth-modal',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatInputModule, MatButtonModule],
  template: `
    <h2>Reautenticación</h2>
    <form [formGroup]="form" (ngSubmit)="reauthenticate()">
      <mat-form-field appearance="fill">
        <mat-label>Usuario</mat-label>
        <input matInput formControlName="username" />
      </mat-form-field>
      <mat-form-field appearance="fill">
        <mat-label>Contraseña</mat-label>
        <input matInput type="password" formControlName="password" />
      </mat-form-field>
      <div class="actions">
        <button mat-button type="button" (click)="cancel()">Cancelar</button>
        <button mat-raised-button type="submit" [disabled]="form.invalid">Aceptar</button>
      </div>
    </form>
  `,
  styles: [`
    h2 {
      margin-bottom: 16px;
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 24px;
    }
  `]
})
export class ReauthModalComponent {
  form: FormGroup;

  constructor(
    private dialogRef: MatDialogRef<ReauthModalComponent>,
    private fb: FormBuilder,
    private authService: AuthService
  ) {
    this.form = this.fb.group({
      username: ['', Validators.required],
      password: ['', Validators.required]
    });
  }

  reauthenticate(): void {
    if (this.form.valid) {
      const { username, password } = this.form.value;
      // Llama al método login del AuthService para reautenticar al usuario
      this.authService.login(username, password).subscribe({
        next: (resp) => {
          // Suponemos que la respuesta trae { token, user }
          if (resp.token) {
            localStorage.setItem('token', resp.token);
            localStorage.setItem('user', JSON.stringify(resp.user));
            this.dialogRef.close({ token: resp.token, user: resp.user });
          }
           else {
            // Si no se obtuvo token, cierra el modal sin devolver datos
            this.dialogRef.close();
          }
        },
        error: (err) => {
          console.error("Error al reautenticar:", err);
          this.dialogRef.close();
        }
      });
    }
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
