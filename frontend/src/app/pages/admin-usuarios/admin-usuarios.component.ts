import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { forkJoin } from 'rxjs';

import {
  CrearUsuarioRequest,
  DepartamentoUsuarioOption,
  SucursalUsuarioOption,
  UsuarioAdminOption,
  UsuarioService,
} from '../../services/usuario.service';

function passwordsCoincidenValidator(
  control: AbstractControl,
): ValidationErrors | null {
  const password = String(control.get('password')?.value || '');
  const confirmacion = String(control.get('password_confirm')?.value || '');

  if (!password || !confirmacion) {
    return null;
  }

  return password === confirmacion ? null : { passwordMismatch: true };
}

@Component({
  selector: 'app-admin-usuarios',
  standalone: true,
  templateUrl: './admin-usuarios.component.html',
  styleUrls: ['./admin-usuarios.component.css'],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
  ],
})
export class AdminUsuariosComponent implements OnInit {
  private readonly departamentoPorRol: Record<string, string> = {
    AUX_MANTENIMIENTO: 'Mantenimiento',
    COMPRAS: 'Compras',
    FINANZAS: 'Finanzas',
    'GERENCIA DEPORTIVA': 'Gerencia Deportiva',
    GERENTE: 'Sucursales',
    MANTENIMIENTO: 'Mantenimiento',
    MARKETING: 'Marketing',
    RECEPCIONISTA: 'Sucursales',
    'RECURSOS HUMANOS': 'Recursos Humanos',
    SISTEMAS: 'Sistemas',
    SR_MANTENIMIENTO: 'Mantenimiento',
  };

  readonly rolesDisponibles: string[] = [
    'ADMINISTRADOR',
    'AUX_MANTENIMIENTO',
    'COMPRAS',
    'FINANZAS',
    'GERENCIA DEPORTIVA',
    'GERENTE',
    'GERENTE_REGIONAL',
    'LECTOR_GLOBAL',
    'MANTENIMIENTO',
    'MARKETING',
    'RECEPCIONISTA',
    'RECURSOS HUMANOS',
    'SISTEMAS',
    'SR_MANTENIMIENTO',
    'TECNICO',
  ];

  modo: 'crear' | 'password' = 'crear';

  form: FormGroup;
  passwordForm: FormGroup;

  sucursales: SucursalUsuarioOption[] = [];
  departamentos: DepartamentoUsuarioOption[] = [];
  usuarios: UsuarioAdminOption[] = [];

  cargandoCatalogos = false;
  cargandoUsuarios = false;
  guardando = false;
  guardandoPassword = false;

  constructor(
    private fb: FormBuilder,
    private usuarioService: UsuarioService,
    private snackBar: MatSnackBar,
  ) {
    this.form = this.fb.group({
      username: ['', [Validators.required]],
      password: ['', [Validators.required, Validators.minLength(6)]],
      email: ['', [Validators.email]],
      rol: ['', [Validators.required]],
      sucursal_id: [null, [Validators.required]],
      department_id: [null, [Validators.required]],
    });

    this.passwordForm = this.fb.group(
      {
        user_id: [null, [Validators.required]],
        password: ['', [Validators.required, Validators.minLength(6)]],
        password_confirm: ['', [Validators.required]],
      },
      {
        validators: [passwordsCoincidenValidator],
      },
    );
  }

  ngOnInit(): void {
    this.cargarCatalogos();

    this.form.get('rol')?.valueChanges.subscribe(() => {
      this.aplicarDepartamentoSugeridoPorRol();
    });
  }

  cambiarModo(modo: 'crear' | 'password'): void {
    this.modo = modo;

    if (
      modo === 'password' &&
      !this.cargandoUsuarios &&
      this.usuarios.length === 0
    ) {
      this.cargarUsuarios();
    }
  }

  cargarUsuarios(): void {
    this.cargandoUsuarios = true;

    this.usuarioService.listarUsuariosAdmin().subscribe({
      next: (usuarios) => {
        this.usuarios = [...usuarios].sort((a, b) =>
          a.username.localeCompare(b.username),
        );
        this.cargandoUsuarios = false;
      },
      error: () => {
        this.cargandoUsuarios = false;
        this.snackBar.open(
          'No se pudo cargar la lista de usuarios.',
          'Cerrar',
          { duration: 5000 },
        );
      },
    });
  }

  cargarCatalogos(): void {
    this.cargandoCatalogos = true;

    forkJoin({
      sucursales: this.usuarioService.getSucursales(),
      departamentos: this.usuarioService.getDepartamentos(),
    }).subscribe({
      next: ({ sucursales, departamentos }) => {
        this.sucursales = [...sucursales].sort((a, b) =>
          a.sucursal.localeCompare(b.sucursal),
        );

        this.departamentos = [...(departamentos.departamentos || [])].sort(
          (a, b) => a.nombre.localeCompare(b.nombre),
        );

        this.aplicarDepartamentoSugeridoPorRol();
        this.cargandoCatalogos = false;
      },
      error: () => {
        this.cargandoCatalogos = false;
        this.snackBar.open(
          'No se pudieron cargar sucursales y departamentos.',
          'Cerrar',
          { duration: 5000 },
        );
      },
    });
  }

  private aplicarDepartamentoSugeridoPorRol(): void {
    const rol = String(this.form.get('rol')?.value || '')
      .trim()
      .toUpperCase();

    const departamentoNombre = this.departamentoPorRol[rol];

    if (!departamentoNombre || this.departamentos.length === 0) {
      return;
    }

    const departamento = this.departamentos.find(
      (item) =>
        String(item.nombre || '').trim().toUpperCase() ===
        departamentoNombre.toUpperCase(),
    );

    if (!departamento) {
      return;
    }

    this.form.patchValue(
      {
        department_id: departamento.id,
      },
      {
        emitEvent: false,
      },
    );
  }

  crearUsuario(): void {
    if (this.form.invalid || this.guardando) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();

    const payload: CrearUsuarioRequest = {
      username: String(value.username || '').trim(),
      password: String(value.password || ''),
      rol: String(value.rol || '').trim().toUpperCase(),
      sucursal_id: Number(value.sucursal_id),
      department_id: Number(value.department_id),
      email: String(value.email || '').trim() || null,
    };

    this.guardando = true;

    this.usuarioService.crearUsuario(payload).subscribe({
      next: (response) => {
        this.guardando = false;

        this.snackBar.open(
          response.msg || 'Usuario creado correctamente.',
          'Cerrar',
          { duration: 4000 },
        );

        this.form.reset({
          username: '',
          password: '',
          email: '',
          rol: '',
          sucursal_id: null,
          department_id: null,
        });

        this.usuarios = [];
      },
      error: (error) => {
        this.guardando = false;

        const message =
          error?.error?.detail ||
          error?.error?.error ||
          'No se pudo crear el usuario.';

        this.snackBar.open(message, 'Cerrar', {
          duration: 5000,
        });
      },
    });
  }

  cambiarPassword(): void {
    if (this.passwordForm.invalid || this.guardandoPassword) {
      this.passwordForm.markAllAsTouched();
      return;
    }

    const value = this.passwordForm.getRawValue();
    const userId = Number(value.user_id);
    const password = String(value.password || '');

    this.guardandoPassword = true;

    this.usuarioService
      .cambiarPasswordUsuario(userId, { password })
      .subscribe({
        next: (response) => {
          this.guardandoPassword = false;

          this.snackBar.open(
            response.msg || 'Contraseña actualizada correctamente.',
            'Cerrar',
            { duration: 4000 },
          );

          this.passwordForm.reset({
            user_id: null,
            password: '',
            password_confirm: '',
          });
        },
        error: (error) => {
          this.guardandoPassword = false;

          const message =
            error?.error?.detail ||
            error?.error?.error ||
            'No se pudo actualizar la contraseña.';

          this.snackBar.open(message, 'Cerrar', {
            duration: 5000,
          });
        },
      });
  }
}
