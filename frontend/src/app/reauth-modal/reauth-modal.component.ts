//frontend-angular\src\app\reauth-modal\reauth-modal.component.ts

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
  templateUrl: './reauth-modal.component.html',
  styleUrls: ['./reauth-modal.component.css'],
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
