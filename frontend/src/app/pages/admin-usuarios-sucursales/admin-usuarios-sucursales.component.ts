import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  FormBuilder,
  FormGroup,
  FormsModule,
  ReactiveFormsModule,
} from '@angular/forms';
import { HttpClient, HttpParams } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { environment } from 'src/environments/environment';

import { AdminUsuariosService } from '../../services/admin-usuarios.service';

type UsuarioOption = {
  id: number;
  username: string;
  rol: string;
  sucursal_id: number;
};

type SucursalOption = {
  id: number;
  nombre: string;
};

@Component({
  selector: 'app-admin-usuarios-sucursales',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule],
  templateUrl: './admin-usuarios-sucursales.component.html',
})
export class AdminUsuariosSucursalesComponent implements OnInit {
  form: FormGroup;

  userId: number | null = null;
  username: string | null = null;
  userRole: string | null = null;
  userSucursalId: number | null = null;

  loadingUsuarios = false;
  loadingSucursales = false;
  loadingAsignacion = false;
  saving = false;

  errorMsg: string | null = null;
  okMsg: string | null = null;

  sucursales: SucursalOption[] = [];
  usuarios: UsuarioOption[] = [];
  usuariosFiltrados: UsuarioOption[] = [];

  busquedaUsuario = '';
  selectedUserIdForNav: number | null = null;

  private readonly API_BASE_URL = environment.apiUrl;

  constructor(
    private readonly fb: FormBuilder,
    private readonly adminUsuariosService: AdminUsuariosService,
    private readonly http: HttpClient,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {
    this.form = this.fb.group({
      sucursales_ids: this.fb.control<number[]>([]),
    });
  }

  ngOnInit(): void {
    this.cargarUsuarios();
    this.cargarCatalogoSucursales();

    this.route.paramMap.subscribe((params) => {
      const raw = params.get('userId');

      this.errorMsg = null;
      this.okMsg = null;

      if (!raw) {
        this.userId = null;
        this.username = null;
        this.userRole = null;
        this.userSucursalId = null;
        this.selectedUserIdForNav = null;
        this.form.patchValue({ sucursales_ids: [] });
        return;
      }

      const userId = Number(raw);
      if (Number.isNaN(userId) || userId <= 0) {
        this.userId = null;
        this.username = null;
        this.userRole = null;
        this.userSucursalId = null;
        this.selectedUserIdForNav = null;
        this.form.patchValue({ sucursales_ids: [] });
        this.errorMsg = 'El usuario indicado en la URL no es válido.';
        return;
      }

      this.userId = userId;
      this.selectedUserIdForNav = userId;

      this.cargarUsuario();
      this.cargarSucursalesAsignadas();
    });
  }

  get loading(): boolean {
    return (
      this.loadingUsuarios ||
      this.loadingSucursales ||
      this.loadingAsignacion ||
      this.saving
    );
  }

  get selectedIds(): number[] {
    return (this.form.value.sucursales_ids ?? []) as number[];
  }

  get cantidadSeleccionadas(): number {
    return this.selectedIds.length;
  }

  get usuarioSeleccionado(): UsuarioOption | null {
    if (this.userId === null) {
      return null;
    }

    return this.usuarios.find((usuario) => usuario.id === this.userId) ?? null;
  }

  get nombreSucursalBase(): string {
    const sucursalId =
      this.usuarioSeleccionado?.sucursal_id ?? this.userSucursalId;

    if (sucursalId === null || sucursalId === undefined) {
      return 'Sin sucursal base';
    }

    return (
      this.sucursales.find((sucursal) => sucursal.id === sucursalId)?.nombre ??
      `Sucursal #${sucursalId}`
    );
  }

  isSucursalSeleccionada(id: number): boolean {
    return this.selectedIds.includes(id);
  }

  toggleSucursal(id: number): void {
    this.okMsg = null;

    const next = this.isSucursalSeleccionada(id)
      ? this.selectedIds.filter((sucursalId) => sucursalId !== id)
      : [...this.selectedIds, id];

    this.form.patchValue({ sucursales_ids: next });
  }

  seleccionarTodasSucursales(): void {
    this.okMsg = null;
    this.form.patchValue({
      sucursales_ids: this.sucursales.map((sucursal) => sucursal.id),
    });
  }

  limpiarSucursales(): void {
    this.okMsg = null;
    this.form.patchValue({ sucursales_ids: [] });
  }

  trackBySucursal(_: number, sucursal: SucursalOption): number {
    return sucursal.id;
  }

  trackByUsuario(_: number, usuario: UsuarioOption): number {
    return usuario.id;
  }

  private cargarCatalogoSucursales(): void {
    this.loadingSucursales = true;

    const params = new HttpParams().set('audience', 'operational');

    this.http
      .get<Array<{ sucursal_id: number; sucursal: string }>>(
        `${this.API_BASE_URL}/sucursales/listar`,
        { params },
      )
      .subscribe({
        next: (rows) => {
          this.sucursales = (rows ?? [])
            .map((row) => ({
              id: Number(row.sucursal_id),
              nombre: String(row.sucursal),
            }))
            .sort((a, b) => a.nombre.localeCompare(b.nombre));

          this.loadingSucursales = false;
        },
        error: (err) => {
          this.loadingSucursales = false;
          this.errorMsg =
            err?.error?.mensaje ?? 'Error al cargar catálogo de sucursales';
        },
      });
  }

  cargarSucursalesAsignadas(): void {
    if (this.userId === null) {
      return;
    }

    this.loadingAsignacion = true;
    this.errorMsg = null;
    this.okMsg = null;

    this.adminUsuariosService.getSucursalesDeUsuario(this.userId).subscribe({
      next: (resp) => {
        this.form.patchValue({
          sucursales_ids: resp.sucursales_ids ?? [],
        });
        this.loadingAsignacion = false;
      },
      error: (err) => {
        this.form.patchValue({ sucursales_ids: [] });
        this.loadingAsignacion = false;
        this.errorMsg =
          err?.error?.mensaje ??
          'No se pudieron cargar las sucursales del usuario seleccionado';
      },
    });
  }

  private cargarUsuario(): void {
    if (this.userId === null) {
      return;
    }

    this.http
      .get<UsuarioOption>(`${this.API_BASE_URL}/usuarios/${this.userId}`)
      .subscribe({
        next: (usuario) => {
          this.username = usuario?.username ?? null;
          this.userRole = usuario?.rol ?? null;
          this.userSucursalId = Number(usuario?.sucursal_id) || null;
        },
        error: () => {
          this.username = null;
          this.userRole = null;
          this.userSucursalId = null;
        },
      });
  }

  private cargarUsuarios(): void {
    this.loadingUsuarios = true;

    this.http.get<UsuarioOption[]>(`${this.API_BASE_URL}/usuarios`).subscribe({
      next: (rows) => {
        this.usuarios = [...(rows ?? [])].sort((a, b) =>
          a.username.localeCompare(b.username),
        );
        this.aplicarFiltroUsuarios();

        const seleccionado = this.usuarioSeleccionado;
        if (seleccionado) {
          this.username = seleccionado.username;
          this.userRole = seleccionado.rol;
          this.userSucursalId = seleccionado.sucursal_id;
        }

        this.loadingUsuarios = false;
      },
      error: (err) => {
        this.loadingUsuarios = false;
        this.errorMsg =
          err?.error?.mensaje ?? 'Error al cargar la lista de usuarios';
      },
    });
  }

  aplicar(): void {
    if (this.userId === null || this.saving) {
      return;
    }

    this.saving = true;
    this.errorMsg = null;
    this.okMsg = null;

    this.adminUsuariosService
      .actualizarSucursalesDeUsuario(this.userId, {
        sucursales_ids: this.selectedIds,
      })
      .subscribe({
        next: (resp) => {
          this.form.patchValue({
            sucursales_ids: resp.sucursales_ids ?? [],
          });
          this.saving = false;
          this.okMsg = 'Visibilidad de sucursales actualizada correctamente.';
        },
        error: (err) => {
          this.saving = false;
          this.errorMsg =
            err?.error?.mensaje ?? 'Error al guardar sucursales';
        },
      });
  }

  aplicarFiltroUsuarios(): void {
    const query = (this.busquedaUsuario || '').trim().toLowerCase();

    if (!query) {
      this.usuariosFiltrados = [...this.usuarios];
      return;
    }

    this.usuariosFiltrados = this.usuarios.filter((usuario) => {
      return (
        usuario.username.toLowerCase().includes(query) ||
        usuario.rol.toLowerCase().includes(query) ||
        String(usuario.sucursal_id).includes(query) ||
        String(usuario.id).includes(query)
      );
    });
  }

  irAUsuarioSeleccionado(): void {
    const userId = Number(this.selectedUserIdForNav);

    if (!Number.isFinite(userId) || userId <= 0) {
      this.router.navigate(['admin-usuarios-sucursales']);
      return;
    }

    this.router.navigate(['admin-usuarios-sucursales', userId]);
  }
}
