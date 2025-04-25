// modal-agregar-producto.component.ts
import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { ModalAlertaCamposRequeridosComponent } from 'src/app/shared/modal-alerta-campos-requeridos/modal-alerta-campos-requeridos.component';
import { MatDialog } from '@angular/material/dialog';

@Component({
  standalone: true,
  selector: 'app-modal-agregar-producto',
  templateUrl: './modal-agregar-producto.component.html',
  styleUrls: ['./modal-agregar-producto.component.css'],
  imports: [
    CommonModule,
    MatDialogModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule
  ]
})
export class ModalAgregarProductoComponent {
  form: FormGroup;

  constructor(
    private dialogRef: MatDialogRef<ModalAgregarProductoComponent>,
    private fb: FormBuilder,
    private dialog: MatDialog,
    @Inject(MAT_DIALOG_DATA) public data: any
  ) {
    this.form = this.fb.group({
      nombre: ['', Validators.required],
      descripcion: [''],
      unidad: ['', Validators.required],
      categoria: ['', Validators.required],
      subcategoria: ['']
    });
  }

  guardar() {
    if (this.form.invalid) {
      this.form.markAllAsTouched(); // <<< esto activa la validación visual
      this.dialog.open(ModalAlertaCamposRequeridosComponent); // mostramos alerta también
      return;
    }
  
    this.dialogRef.close(this.form.value);
  }
  

  cancelar() {
    this.dialogRef.close();
  }
}
