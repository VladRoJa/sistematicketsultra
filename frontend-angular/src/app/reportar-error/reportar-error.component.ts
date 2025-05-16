//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\reportar-error\reportar-error.component.ts

import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { MatDialogRef } from '@angular/material/dialog';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { HttpClientModule } from '@angular/common/http';
import { ReactiveFormsModule } from '@angular/forms';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { RefrescoService } from '../services/refresco.service';




@Component({
  selector: 'app-reportar-error',
  standalone: true,
  templateUrl: './reportar-error.component.html',
  styleUrls: ['./reportar-error.component.css'],
  imports: [
    ReactiveFormsModule,
    HttpClientModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatSnackBarModule
  ]

})
export class ReportarErrorComponent {
  form: FormGroup;
  imagenSeleccionada: File | null = null;
  enviando = false;

  constructor(
    private fb: FormBuilder,
    private http: HttpClient,
    private dialogRef: MatDialogRef<ReportarErrorComponent>,
    private snackBar: MatSnackBar,
    private refrescoService: RefrescoService
  ) {
    this.form = this.fb.group({
      descripcion: ['', Validators.required],
      criticidad: ['media', Validators.required]
    });
  }

  onArchivoSeleccionado(event: any): void {
    this.imagenSeleccionada = event.target.files[0] || null;
  }

  enviarReporte(): void {
    if (this.form.invalid || this.enviando) return;

    const formData = new FormData();
    formData.append('descripcion', this.form.value.descripcion);
    formData.append('criticidad', this.form.value.criticidad);
    formData.append('modulo', window.location.pathname);
    if (this.imagenSeleccionada) {
      formData.append('imagen', this.imagenSeleccionada);
    }

    this.enviando = true;

    const token = localStorage.getItem('token');
    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`
    });

      this.http.post('/api/reportes/reportar-error', formData, { headers }).subscribe({
        next: () => {
          this.refrescoService.emitirRefresco();
          this.snackBar.open('Reporte enviado correctamente ✅', 'Cerrar', {
            duration: 3000,
            horizontalPosition: 'end',
            verticalPosition: 'bottom',
          });
          this.dialogRef.close();
        },
        error: () => {
          this.snackBar.open('Error al enviar el reporte ❌', 'Cerrar', {
            duration: 3000,
            horizontalPosition: 'end',
            verticalPosition: 'bottom',
          });
          this.enviando = false;
        }
      });
     }   
       cancelar(): void {
    this.dialogRef.close('recargar');
  }
    } 

